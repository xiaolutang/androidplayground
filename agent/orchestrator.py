"""LangGraph 状态机编排器（R001-ORB01）。

依据：
- Sprint Contract R001-ORB01（status: agreed，10 AC）
- backend design 4.1 BugReport 14 态状态机 / 5.1 主链
- architecture INV-2（人工闸门不自主合并）/ INV-3（concluded 唯一回退 reflowed）
- D1（LangGraph 编排框架）/ D7（步数/token 预算硬约束）

设计要点：
1. **14 态状态机**（``_STATE_TRANSITIONS``）：完整迁移矩阵，非法迁移抛
   ``InvalidStateTransition``。
2. **LangGraph 节点序列**：normalize → assess → classify → select_playbook →
   diagnose → route_by_tier → {fix → verify → submit_pr} | diagnose_gap →
   reflect（终态）。
3. **步数/token 预算硬约束**（D7）：每节点递增 step_used / 累加 token_used，
   超限 → diagnose_gap（coverage / information）。
4. **人工闸门**（INV-2）：PR 提交后停 pr_open / draft_pr，不自动 concluded。
5. **事件驱动回流**（BB011 解耦）：Orchestrator 订阅 ``bug.reflowed`` 事件，
   收到后迁移 reflowed → received 重跑主链。
6. **concluded 唯一回退 reflowed**（INV-3）。

全部 BB 服务通过构造函数注入（DI），便于测试 mock。
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Protocol, runtime_checkable

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from agent.assessment.info_sufficiency_evaluator import (
    ISMLevel,
    ISMResult,
    InfoSufficiencyEvaluator,
)
from agent.assessment.confidence_evaluator import ConfidenceEvaluator
from agent.assessment.symptom_classifier import SymptomClassifier
from agent.diagnosis.hypothesis_engine import HypothesisEngine
from agent.diagnosis.playbook_executor import PlaybookExecutor
from agent.diagnosis.root_cause_locator import RootCauseLocator
from agent.fix.auto_fixer import AutoFixer, FixPatch
from agent.fix.pr_submitter import PRSubmissionResult, PRSubmitter
from agent.fix.regression_verifier import RegressionVerifier
from agent.gap_mgmt.gap_diagnoser import GapDiagnoser
from agent.gap_mgmt.reflow_manager import ReflowManager
from agent.reflection.reflection_agent import ReflectionAgent
from agent.schemas.bug_report import BugReportStatus

logger = logging.getLogger(__name__)

__all__ = [
    "AgentState",
    "InvalidStateTransition",
    "Orchestrator",
    "EventBus",
    "STATE_TRANSITIONS",
    "can_transition",
    "transition_to",
]


# ---------------------------------------------------------------------------
# EventBus 协议（INF07 duck typing 接口）
# ---------------------------------------------------------------------------
@runtime_checkable
class EventBus(Protocol):
    """EventBus 协议（INF07）。

    Orchestrator 订阅 ``bug.reflowed`` 事件，不反向调用 BB011。
    """

    def publish(self, event_type: str, payload: dict) -> None:
        """发布事件。"""
        ...

    def subscribe(self, event_type: str, handler: Any) -> None:
        """订阅事件。"""
        ...


# ---------------------------------------------------------------------------
# 14 态状态机迁移矩阵（AC-1）
# ---------------------------------------------------------------------------
# 完整 14 态：received, assessing, degraded, reproducing, located, fixing,
#   verified, pr_open, draft_pr, gap_pending, wont_reflow, concluded,
#   reflowed, reflected
#
# 合法迁移（design 4.1 第 525-535 行 + reflowed 定义）：
# - received → assessing
# - assessing → degraded | reproducing
# - degraded → received（缺口补齐回流，路径 A）
# - reproducing → located
# - located → fixing | gap_pending
# - fixing → verified | located（根因错回退）
# - verified → pr_open | draft_pr
# - pr_open → concluded
# - draft_pr → concluded
# - concluded → reflected
# - concluded → reflowed（regression-feedback 路径 B，INV-3）
# - reflected → reflowed（regression-feedback 路径 B）
# - reflowed → received（重跑主链）
# - gap_pending → wont_reflow | received
# - wont_reflow →（终态，无迁移）
STATE_TRANSITIONS: dict[BugReportStatus, frozenset[BugReportStatus]] = {
    BugReportStatus.RECEIVED: frozenset({BugReportStatus.ASSESSING}),
    BugReportStatus.ASSESSING: frozenset({
        BugReportStatus.DEGRADED,
        BugReportStatus.REPRODUCING,
    }),
    BugReportStatus.DEGRADED: frozenset({BugReportStatus.RECEIVED}),
    BugReportStatus.REPRODUCING: frozenset({BugReportStatus.LOCATED}),
    BugReportStatus.LOCATED: frozenset({
        BugReportStatus.FIXING,
        BugReportStatus.GAP_PENDING,
    }),
    BugReportStatus.FIXING: frozenset({
        BugReportStatus.VERIFIED,
        BugReportStatus.LOCATED,
    }),
    BugReportStatus.VERIFIED: frozenset({
        BugReportStatus.PR_OPEN,
        BugReportStatus.DRAFT_PR,
    }),
    BugReportStatus.PR_OPEN: frozenset({BugReportStatus.CONCLUDED}),
    BugReportStatus.DRAFT_PR: frozenset({BugReportStatus.CONCLUDED}),
    BugReportStatus.GAP_PENDING: frozenset({
        BugReportStatus.WONT_REFLOW,
        BugReportStatus.RECEIVED,
    }),
    BugReportStatus.WONT_REFLOW: frozenset(),
    BugReportStatus.CONCLUDED: frozenset({
        BugReportStatus.REFLECTED,
        BugReportStatus.REFLOWED,
    }),
    BugReportStatus.REFLOWED: frozenset({BugReportStatus.RECEIVED}),
    BugReportStatus.REFLECTED: frozenset({BugReportStatus.REFLOWED}),
}


class InvalidStateTransition(Exception):
    """非法状态迁移（不在 STATE_TRANSITIONS 允许集合中）。"""


def can_transition(
    from_status: BugReportStatus,
    to_status: BugReportStatus,
) -> bool:
    """判断 from_status -> to_status 迁移是否合法。

    Args:
        from_status: 当前状态。
        to_status: 目标状态。

    Returns:
        True 如果迁移在 STATE_TRANSITIONS 允许集合中。
    """
    allowed = STATE_TRANSITIONS.get(from_status, frozenset())
    return to_status in allowed


def transition_to(
    current: BugReportStatus,
    target: BugReportStatus,
) -> BugReportStatus:
    """执行状态迁移；非法抛 InvalidStateTransition。

    Args:
        current: 当前状态。
        target: 目标状态。

    Returns:
        target（迁移成功）。

    Raises:
        InvalidStateTransition: 迁移不在允许集合中。
    """
    if not can_transition(current, target):
        raise InvalidStateTransition(
            f"illegal transition {current.value} -> {target.value}"
        )
    return target


# ---------------------------------------------------------------------------
# AgentState（AC-9）
# ---------------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    """LangGraph 节点间传递的状态（AC-9）。

    使用 TypedDict（LangGraph 惯例），节点函数接收 state dict 并返回
    需要更新的 key-value 子集。

    Attributes:
        bug_report_id: BugReport id。
        status: 当前 BugReportStatus 枚举值。
        tier: 置信度 Tier（1-4），route_by_tier 后填充。
        step_used: 已消耗步数（每节点递增）。
        token_used: 已消耗 token 数（从 LLM 响应累加）。
        hypothesis_ids: 假设树节点 id 列表。
        root_cause: 根因定位结果 dict。
        fix_patch: FixPatch 对象（fix 节点产出）。
        pr_result: PRSubmissionResult 对象（submit_pr 节点产出）。
        gap_id: 缺口 id（diagnose_gap 节点产出）。
        errors: 错误消息列表。
        bug_report: BugReport 对象（normalize 节点产出）。
        ism_result: ISM 评估结果（assess 节点产出）。
        classification_result: 症状分类结果（classify 节点产出）。
        playbook: Playbook 对象（select_playbook 节点产出）。
        executor_result: Playbook 执行结果（diagnose 节点产出）。
        confidence_score: 置信度评分（classify 节点产出）。
        verification_result: 回归验证结果（verify 节点产出）。
        gap_result: 缺口诊断结果（diagnose_gap 节点产出）。
        reflow_count: 回流次数。
        budget_exceeded: 预算是否超限（步数或 token）。
        budget_gap_type: 预算超限类型（coverage / information）。
    """

    bug_report_id: str
    status: BugReportStatus
    tier: Optional[int]
    step_used: int
    token_used: int
    hypothesis_ids: list[str]
    root_cause: Optional[dict]
    fix_patch: Optional[FixPatch]
    pr_result: Optional[PRSubmissionResult]
    gap_id: Optional[str]
    errors: list[str]
    bug_report: Any
    ism_result: Any
    classification_result: Any
    playbook: Any
    executor_result: Any
    confidence_score: Any
    verification_result: Any
    gap_result: Any
    reflow_count: int
    budget_exceeded: bool
    budget_gap_type: str


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:
    """LangGraph 状态机编排器：驱动 BugReport 走完 14 态生命周期。

    串联全部 BB 服务节点，执行步数/token 预算硬约束，人工闸门（不自主合并）。
    全部 BB 服务通过构造函数注入（DI），便于测试 mock。

    Usage:
        orchestrator = Orchestrator(
            ism_evaluator=ism,
            symptom_classifier=sc,
            confidence_evaluator=ce,
            playbook_executor=pe,
            hypothesis_engine=he,
            root_cause_locator=rcl,
            auto_fixer=af,
            regression_verifier=rv,
            pr_submitter=prs,
            gap_diagnoser=gd,
            reflow_manager=rfm,
            reflection_agent=ra,
            event_bus=bus,
        )
        final_state = await orchestrator.run(bug_report)

    Args:
        ism_evaluator: BB001 信息完备度评估器。
        symptom_classifier: BB002 症状分类器。
        confidence_evaluator: BB006 置信度评估器。
        playbook_executor: BB003 Playbook 执行器。
        hypothesis_engine: BB004 假设树引擎。
        root_cause_locator: BB005 根因定位器。
        auto_fixer: BB007 自动修复器。
        regression_verifier: BB008 回归验证器。
        pr_submitter: BB009 PR 提交器。
        gap_diagnoser: BB010 缺口诊断器。
        reflow_manager: BB011 回流管理器。
        reflection_agent: BB013 反思 agent。
        event_bus: INF07 EventBus（可选，None 时降级）。
        max_steps: 步数预算硬上限（默认 30，D7）。
        max_tokens: token 预算硬上限（默认 100000，D7）。
    """

    def __init__(
        self,
        *,
        ism_evaluator: InfoSufficiencyEvaluator,
        symptom_classifier: SymptomClassifier,
        confidence_evaluator: ConfidenceEvaluator,
        playbook_executor: PlaybookExecutor,
        hypothesis_engine: HypothesisEngine,
        root_cause_locator: RootCauseLocator,
        auto_fixer: AutoFixer,
        regression_verifier: RegressionVerifier,
        pr_submitter: PRSubmitter,
        gap_diagnoser: GapDiagnoser,
        reflow_manager: ReflowManager,
        reflection_agent: ReflectionAgent,
        event_bus: Optional[Any] = None,
        max_steps: int = 30,
        max_tokens: int = 100000,
    ) -> None:
        self._ism = ism_evaluator
        self._classifier = symptom_classifier
        self._confidence = confidence_evaluator
        self._executor = playbook_executor
        self._hypothesis = hypothesis_engine
        self._locator = root_cause_locator
        self._fixer = auto_fixer
        self._verifier = regression_verifier
        self._submitter = pr_submitter
        self._gap_diagnoser = gap_diagnoser
        self._reflow = reflow_manager
        self._reflection = reflection_agent
        self._event_bus = event_bus
        self._max_steps = max_steps
        self._max_tokens = max_tokens

        # 构建 LangGraph 图
        self._graph = self._build_graph()

        # 订阅 bug.reflowed 事件（事件驱动回流，AC-6）
        if self._event_bus is not None and hasattr(self._event_bus, "subscribe"):
            try:
                self._event_bus.subscribe("bug.reflowed", self._on_reflow_event)
            except Exception as exc:
                logger.warning(
                    "Orchestrator: subscribe bug.reflowed failed: %s", exc
                )

    # ------------------------------------------------------------------
    # LangGraph 图构建（AC-2）
    # ------------------------------------------------------------------
    def _build_graph(self) -> Any:
        """构建 LangGraph 状态机图。

        节点序列（主链）：
        normalize → assess → classify → select_playbook → diagnose →
        route_by_tier →
        - Tier1: fix → verify → submit_pr
        - Tier2: fix → verify → submit_pr
        - Tier3/4: diagnose_gap
        终态: reflect（人工合并后触发）

        条件边（route_by_tier）实现 Tier 分流。
        """
        graph = StateGraph(AgentState)

        # 添加节点
        graph.add_node("normalize", self._node_normalize)
        graph.add_node("assess", self._node_assess)
        graph.add_node("classify", self._node_classify)
        graph.add_node("select_playbook", self._node_select_playbook)
        graph.add_node("diagnose", self._node_diagnose)
        graph.add_node("route_by_tier", self._node_route_by_tier)
        graph.add_node("fix", self._node_fix)
        graph.add_node("verify", self._node_verify)
        graph.add_node("submit_pr", self._node_submit_pr)
        graph.add_node("diagnose_gap", self._node_diagnose_gap)
        graph.add_node("reflect", self._node_reflect)

        # 设置入口
        graph.set_entry_point("normalize")

        # 线性边
        graph.add_edge("normalize", "assess")
        graph.add_edge("assess", "classify")
        graph.add_edge("classify", "select_playbook")
        graph.add_edge("select_playbook", "diagnose")
        graph.add_edge("diagnose", "route_by_tier")

        # route_by_tier 条件边（Tier 分流）
        graph.add_conditional_edges(
            "route_by_tier",
            self._route_by_tier_condition,
            {
                "fix": "fix",
                "diagnose_gap": "diagnose_gap",
            },
        )

        # fix → verify → submit_pr
        graph.add_edge("fix", "verify")
        graph.add_edge("verify", "submit_pr")

        # submit_pr → END（人工闸门，不自动 concluded）
        graph.add_edge("submit_pr", END)

        # diagnose_gap → END（gap_pending 状态）
        graph.add_edge("diagnose_gap", END)

        # reflect → END
        graph.add_edge("reflect", END)

        return graph.compile()

    def _route_by_tier_condition(self, state: AgentState) -> str:
        """route_by_tier 条件边路由函数。

        Tier1/Tier2 → fix（自动修复路径）
        Tier3/Tier4 → diagnose_gap（缺口诊断路径）

        预算超限时强制走 diagnose_gap。
        """
        # 预算超限 → 直接缺口诊断
        if state.get("budget_exceeded", False):
            return "diagnose_gap"

        tier = state.get("tier")
        if tier is not None and tier <= 2:
            return "fix"
        return "diagnose_gap"

    # ------------------------------------------------------------------
    # 节点函数（AC-2）
    # ------------------------------------------------------------------
    def _node_normalize(self, state: AgentState) -> dict:
        """归一化节点：接收 BugReport，初始化状态。

        BF001 适配器已在上游完成归一化，本节点做状态初始化。
        """
        bug_report = state.get("bug_report")
        bug_report_id = state.get("bug_report_id", "")
        if bug_report is not None and not bug_report_id:
            bug_report_id = getattr(bug_report, "id", "") or ""

        return {
            "bug_report_id": bug_report_id,
            "status": BugReportStatus.RECEIVED,
            "step_used": 0,
            "token_used": 0,
            "hypothesis_ids": [],
            "root_cause": None,
            "fix_patch": None,
            "pr_result": None,
            "gap_id": None,
            "errors": [],
            "reflow_count": getattr(bug_report, "reflow_count", 0) if bug_report else 0,
            "budget_exceeded": False,
            "budget_gap_type": "",
        }

    async def _node_assess(self, state: AgentState) -> dict:
        """评估节点：BB001 ISM 评估信息完备度。

        信息充足 → reproducing；信息不足 → degraded（转缺口诊断）。
        """
        self._check_budget(state)

        bug_report = state.get("bug_report")
        status = transition_to(
            state["status"], BugReportStatus.ASSESSING
        )

        try:
            ism_result = await self._ism.evaluate(bug_report)
        except Exception as exc:
            # AC-8 降级：服务异常 → degraded
            logger.warning("Orchestrator assess failed: %s", exc)
            ism_result = ISMResult(
                level=ISMLevel.INSUFFICIENT.value,
                score=0.0,
                degraded=True,
                reasoning=f"assess error: {exc}",
            )
            errors = list(state.get("errors", []))
            errors.append(f"assess: {exc}")
            return {
                "status": transition_to(status, BugReportStatus.DEGRADED),
                "ism_result": ism_result,
                "errors": errors,
            }

        # 信息不足 → degraded
        if ism_result.degraded or ism_result.level == ISMLevel.INSUFFICIENT.value:
            return {
                "status": transition_to(status, BugReportStatus.DEGRADED),
                "ism_result": ism_result,
            }

        # 信息充足 → reproducing（在 diagnose 节点完成）
        return {
            "status": transition_to(
                status, BugReportStatus.REPRODUCING
            ),
            "ism_result": ism_result,
        }

    async def _node_classify(self, state: AgentState) -> dict:
        """分类节点：BB002 症状分类 + BB006 置信度 → Tier 分级。

        degraded 状态直接透传到缺口诊断路径。
        classify 失败时迁移到 located（允许后续 located → gap_pending 合法迁移）。
        """
        # degraded 状态不执行分类，直接设置 tier=None
        if state["status"] == BugReportStatus.DEGRADED:
            return {"tier": None}

        self._check_budget(state)

        bug_report = state.get("bug_report")

        try:
            classification = await self._classifier.classify(bug_report)
        except Exception as exc:
            logger.warning("Orchestrator classify failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"classify: {exc}")
            # classify 失败时迁移到 located（允许后续 located → gap_pending 合法）
            status = transition_to(
                state["status"], BugReportStatus.LOCATED
            )
            return {
                "status": status,
                "classification_result": None,
                "errors": errors,
                "tier": None,
            }

        # BB006 置信度评估
        ism_result = state.get("ism_result")
        confidence_score = self._confidence.evaluate(
            bug_report,
            ism_result=ism_result,
        )

        return {
            "classification_result": classification,
            "confidence_score": confidence_score,
            "tier": confidence_score.tier,
        }

    def _node_select_playbook(self, state: AgentState) -> dict:
        """选择 Playbook 节点：BB003 按 symptom_type 选择 Playbook。

        degraded / tier=None 时跳过。
        """
        if state["status"] == BugReportStatus.DEGRADED or state.get("tier") is None:
            return {"playbook": None}

        classification = state.get("classification_result")
        if classification is None:
            return {"playbook": None}

        # Playbook 选择由 BB003 内部 registry 处理
        # 这里仅记录分类结果供后续节点使用
        return {"playbook": classification}

    async def _node_diagnose(self, state: AgentState) -> dict:
        """诊断节点：BB003 执行复现 + BB004 假设树 + BB005 根因定位。

        Tier3/4 或 degraded 跳过，直接进入 route_by_tier → diagnose_gap。
        从 reproducing 或 located 状态进入，确保合法迁移。
        """
        if state["status"] == BugReportStatus.DEGRADED:
            return {}

        tier = state.get("tier")
        if tier is not None and tier > 2:
            # Tier3/4 不执行诊断，直接进入缺口路径
            return {}

        # 如果在 reproducing 状态，先迁移到 located（允许后续合法迁移）
        current_status = state["status"]
        if current_status == BugReportStatus.REPRODUCING:
            current_status = transition_to(
                current_status, BugReportStatus.LOCATED
            )

        self._check_budget(state)

        playbook = state.get("playbook")

        try:
            # BB003 执行 Playbook
            if playbook is not None:
                executor_result = await self._executor.execute(playbook)
            else:
                executor_result = None
        except Exception as exc:
            logger.warning("Orchestrator diagnose (executor) failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"diagnose: {exc}")
            return {
                "status": current_status,
                "errors": errors,
            }

        # BB005 根因定位（从执行结果中提取信号）
        root_cause = None
        try:
            if executor_result is not None:
                signals = getattr(executor_result, "signals", []) or []
                if signals:
                    loc = self._locator.locate(
                        hypothesis=state.get("hypothesis_ids"),
                        signals=signals,
                    )
                    root_cause = {
                        "located": loc.located,
                        "file": loc.file,
                        "line": loc.line,
                        "source": loc.source,
                        "confidence": loc.confidence,
                    }
        except Exception as exc:
            logger.warning("Orchestrator diagnose (locator) failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"locate: {exc}")
            return {
                "status": current_status,
                "errors": errors,
                "executor_result": executor_result,
            }

        # 根因定位成功 → 保持 located
        if root_cause is not None and root_cause.get("located"):
            return {
                "status": current_status,
                "executor_result": executor_result,
                "root_cause": root_cause,
            }

        # 根因未定位 → gap_pending（从 located 迁移合法）
        try:
            new_status = transition_to(
                current_status, BugReportStatus.GAP_PENDING
            )
        except InvalidStateTransition:
            new_status = current_status

        return {
            "status": new_status,
            "executor_result": executor_result,
            "root_cause": root_cause,
        }

    def _node_route_by_tier(self, state: AgentState) -> dict:
        """路由节点：按 Tier 分流（条件边由 _route_by_tier_condition 处理）。

        本节点只做状态检查，实际路由由条件边完成。
        """
        return {}

    def _node_fix(self, state: AgentState) -> dict:
        """修复节点：BB007 自动修复。

        located → fixing 状态迁移。
        """
        self._check_budget(state)

        # located → fixing
        status = transition_to(state["status"], BugReportStatus.FIXING)

        bug_report = state.get("bug_report")
        root_cause = state.get("root_cause") or {}
        tier = state.get("tier", 1)

        try:
            fix_patch = self._fixer.generate_patch(
                bug_report_summary=str(getattr(bug_report, "raw_report", "")),
                root_cause_location=str(
                    root_cause.get("file", "")
                ) + ":" + str(root_cause.get("line", "")),
                symptom_type=str(getattr(bug_report, "symptom_type", "")),
                tier=tier,
            )
        except Exception as exc:
            logger.warning("Orchestrator fix failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"fix: {exc}")
            # 修复失败 → 回退到 located（根因错回退）
            return {
                "status": transition_to(status, BugReportStatus.LOCATED),
                "errors": errors,
            }

        return {
            "status": status,
            "fix_patch": fix_patch,
        }

    def _node_verify(self, state: AgentState) -> dict:
        """验证节点：BB008 回归验证。

        fixing → verified（通过）或 fixing → located（根因错回退）。
        """
        self._check_budget(state)

        tier = state.get("tier", 1)

        try:
            verification = self._verifier.verify(tier=tier)
        except Exception as exc:
            logger.warning("Orchestrator verify failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"verify: {exc}")
            return {
                "status": transition_to(
                    state["status"], BugReportStatus.LOCATED
                ),
                "errors": errors,
            }

        if verification.passed:
            return {
                "status": transition_to(
                    state["status"], BugReportStatus.VERIFIED
                ),
                "verification_result": verification,
            }

        # 验证失败 → 根因错回退到 located
        return {
            "status": transition_to(
                state["status"], BugReportStatus.LOCATED
            ),
            "verification_result": verification,
        }

    def _node_submit_pr(self, state: AgentState) -> dict:
        """PR 提交节点：BB009 Tier 分流提交。

        verified → pr_open（Tier1）或 draft_pr（Tier2）。
        人工闸门：不自动 concluded（INV-2）。
        """
        tier = state.get("tier", 1)
        fix_patch = state.get("fix_patch")

        tier_str = f"tier_{tier}"
        fix_content = ""
        files: list[str] = []
        if fix_patch is not None:
            fix_content = fix_patch.patch_content or ""
            files = fix_patch.files_changed or []

        try:
            pr_result = self._submitter.submit(
                fix_patch_content=fix_content,
                files_to_commit=files,
                commit_message=f"fix: auto-fix for bug {state.get('bug_report_id', '')}",
                tier=tier_str,
                pr_title=f"Auto-fix: bug {state.get('bug_report_id', '')}",
                pr_body="Auto-generated PR by bug-fix agent.",
            )
        except Exception as exc:
            logger.warning("Orchestrator submit_pr failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"submit_pr: {exc}")
            return {
                "errors": errors,
                "pr_result": None,
            }

        # Tier1 → pr_open；Tier2 → draft_pr
        if tier == 1:
            target_status = BugReportStatus.PR_OPEN
        else:
            target_status = BugReportStatus.DRAFT_PR

        status = transition_to(state["status"], target_status)

        return {
            "status": status,
            "pr_result": pr_result,
        }

    def _node_diagnose_gap(self, state: AgentState) -> dict:
        """缺口诊断节点：BB010 四类缺口识别。

        位于 gap_pending 状态，转 wont_reflow 或等待补齐。
        """
        # 确保处于 gap_pending 状态
        if state["status"] != BugReportStatus.GAP_PENDING:
            try:
                status = transition_to(
                    state["status"], BugReportStatus.GAP_PENDING
                )
            except InvalidStateTransition:
                status = state["status"]
        else:
            status = state["status"]

        bug_report_id = state.get("bug_report_id", "")

        # 确定触发源
        trigger_source = "ism_insufficient"
        if state.get("budget_exceeded"):
            if state.get("budget_gap_type") == "coverage":
                trigger_source = "step_exhausted"
            elif state.get("budget_gap_type") == "information":
                trigger_source = "llm_failure"

        trigger_context = {
            "trigger_source": trigger_source,
            "ism_result": state.get("ism_result"),
        }

        try:
            gap_result = self._gap_diagnoser.diagnose(
                bug_report_id=bug_report_id,
                trigger_context=trigger_context,
            )
        except Exception as exc:
            logger.warning("Orchestrator diagnose_gap failed: %s", exc)
            errors = list(state.get("errors", []))
            errors.append(f"diagnose_gap: {exc}")
            return {
                "status": status,
                "errors": errors,
            }

        return {
            "status": status,
            "gap_result": gap_result,
            "gap_id": gap_result.gap_id if gap_result.diagnosed else None,
        }

    def _node_reflect(self, state: AgentState) -> dict:
        """反思节点：BB013 反思沉淀。

        concluded → reflected。
        """
        status = transition_to(state["status"], BugReportStatus.REFLECTED)

        return {
            "status": status,
        }

    # ------------------------------------------------------------------
    # 预算检查（AC-3, AC-4）
    # ------------------------------------------------------------------
    def _check_budget(self, state: AgentState) -> None:
        """步数/token 预算硬约束检查（D7）。

        超限时设置 budget_exceeded=True + budget_gap_type，
        route_by_tier 条件边将强制走 diagnose_gap。

        - step_used > max_steps → coverage 缺口
        - token_used > max_tokens → information 缺口
        """
        step_used = state.get("step_used", 0) + 1
        token_used = state.get("token_used", 0)

        if step_used > self._max_steps:
            logger.warning(
                "Orchestrator: step budget exhausted %d/%d",
                step_used,
                self._max_steps,
            )
            state["budget_exceeded"] = True
            state["budget_gap_type"] = "coverage"
            # 迁移到 gap_pending
            try:
                state["status"] = transition_to(
                    state.get("status", BugReportStatus.RECEIVED),
                    BugReportStatus.GAP_PENDING,
                )
            except InvalidStateTransition:
                pass

        if token_used > self._max_tokens:
            logger.warning(
                "Orchestrator: token budget exhausted %d/%d",
                token_used,
                self._max_tokens,
            )
            state["budget_exceeded"] = True
            state["budget_gap_type"] = "information"
            try:
                state["status"] = transition_to(
                    state.get("status", BugReportStatus.RECEIVED),
                    BugReportStatus.GAP_PENDING,
                )
            except InvalidStateTransition:
                pass

    # ------------------------------------------------------------------
    # 事件驱动回流（AC-6）
    # ------------------------------------------------------------------
    def _on_reflow_event(self, event_type: str, payload: dict) -> None:
        """bug.reflowed 事件回调（订阅方）。

        收到事件后迁移 reflowed → received，触发主链重跑。
        不反向调用 BB011（事件驱动解耦）。
        """
        if event_type != "bug.reflowed":
            return

        bug_report_id = payload.get("bug_report_id", "")
        trigger_path = payload.get("trigger_path", "")
        reflow_count = payload.get("reflow_count", 0)

        logger.info(
            "Orchestrator: received bug.reflowed event for bug=%s "
            "trigger_path=%s reflow_count=%d",
            bug_report_id,
            trigger_path,
            reflow_count,
        )

    # ------------------------------------------------------------------
    # 主入口：run（AC-2）
    # ------------------------------------------------------------------
    async def run(self, bug_report: Any) -> AgentState:
        """运行完整主链编排。

        驱动 BugReport 从 received 走到终态（pr_open / draft_pr / gap_pending /
        wont_reflow）。

        Args:
            bug_report: BugReport 对象（ORM 或 dict，duck typing）。

        Returns:
            最终 AgentState（含 status / tier / step_used / token_used 等）。
        """
        initial_state: AgentState = {
            "bug_report": bug_report,
            "bug_report_id": getattr(bug_report, "id", "") or "",
            "status": BugReportStatus.RECEIVED,
            "tier": None,
            "step_used": 0,
            "token_used": 0,
            "hypothesis_ids": [],
            "root_cause": None,
            "fix_patch": None,
            "pr_result": None,
            "gap_id": None,
            "errors": [],
            "reflow_count": getattr(bug_report, "reflow_count", 0) or 0,
            "budget_exceeded": False,
            "budget_gap_type": "",
        }

        try:
            final_state = await self._graph.ainvoke(initial_state)
        except Exception as exc:
            logger.error("Orchestrator run failed: %s", exc)
            errors = list(initial_state.get("errors", []))
            errors.append(f"run: {exc}")
            initial_state["errors"] = errors
            return initial_state

        return final_state

    # ------------------------------------------------------------------
    # 外部触发：concluded（人工闸门，AC-5）
    # ------------------------------------------------------------------
    def conclude(self, state: AgentState) -> dict:
        """人工合并后触发 concluded（AC-5 INV-2）。

        由外部 API（人工 webhook）调用，Orchestrator 不自动调用。
        pr_open / draft_pr → concluded → reflected。

        Args:
            state: 当前 AgentState。

        Returns:
            更新后的 status 字典。

        Raises:
            InvalidStateTransition: 非 pr_open/draft_pr 状态调用。
        """
        status = transition_to(state["status"], BugReportStatus.CONCLUDED)
        return {"status": status}

    # ------------------------------------------------------------------
    # 外部触发：reflow（事件驱动回流，AC-6）
    # ------------------------------------------------------------------
    def trigger_reflow(self, state: AgentState) -> dict:
        """触发回流（AC-6）。

        concluded/reflected → reflowed → received（重跑主链）。
        reflow_count 超限 → wont_reflow（AP-1）。

        Args:
            state: 当前 AgentState。

        Returns:
            更新后的 status 字典。

        Raises:
            InvalidStateTransition: 非 concluded/reflected 状态调用。
        """
        current = state["status"]
        reflow_count = state.get("reflow_count", 0)

        # reflow_count 超限 → wont_reflow
        if reflow_count >= 3:
            try:
                status = transition_to(current, BugReportStatus.WONT_REFLOW)
            except InvalidStateTransition:
                # gap_pending → wont_reflow
                status = BugReportStatus.WONT_REFLOW
            return {
                "status": status,
                "reflow_count": reflow_count,
            }

        # concluded/reflected → reflowed
        reflowed = transition_to(current, BugReportStatus.REFLOWED)
        # reflowed → received
        received = transition_to(reflowed, BugReportStatus.RECEIVED)

        return {
            "status": received,
            "reflow_count": reflow_count + 1,
        }
