"""假设树引擎（R001-BB004）—— 4 态状态机 + 换方向 + 根因回退 + 步数预算 + 负向反查。

依据：
- Sprint Contract R001-BB004（status: agreed，mode: negotiated / Mode 1）
- 技术决策 D7（步数预算硬约束）
- 技术决策 D1（MVP 用纯 Python 内存状态机等效实现 LangGraph 假设树/回溯语义）

设计要点：
1. **4 态迁移矩阵**（``_STATE_TRANSITIONS``）：proposed → verifying →
   {confirmed | refuted}；confirmed → refuted 仅经 ``overturn_root_cause`` 走特殊路径。
   refuted 为终态（INV-2 不可迁出）。非法迁移抛 ``HypothesisTransitionError``。
2. **换方向**（``refute_and_pivot``）：refute 当前 → 回溯 parent_id → 切下一个 proposed
   兄弟；无兄弟继续上溯；到根仍无 → 返回 None。
3. **根因回退**（``overturn_root_cause``）：confirmed + is_rootcause 的节点被新信号推翻 →
   绕过常规 _transition_check 直接置 refuted + is_rootcause=False + 记录
   overturning_signal/overturning_stage，然后触发 pivot。
4. **步数预算 D7**（``check_budget_and_pivot``）：``max_steps``（默认 20）为引擎级硬上限。
   耗尽 → refute 当前 + **不** pivot + 转 GapStore.create（coverage/reasoning 缺口）。
5. **INV-2 refuted 永久保留**：``delete()`` 始终抛 ``HypothesisDeleteError``。
6. **负向知识反查剪枝**（``negate_and_prune``）：调 ``KBRetriever.negate_hypotheses``
   获取 verdicts，prune=True 直接 refute，demote_factor<1.0 降权标记。

纯内存状态机：``self._nodes: dict[str, HypothesisNode]``，不持久化（持久化由调用方负责）。
不引 LangGraph 依赖（ORB01 负责 StateGraph 映射）。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.gap.gap_store import GapStore
from agent.kb.retriever import KBRetriever, NegativeVerdict
from agent.schemas.trajectory import HypothesisStatus

logger = logging.getLogger(__name__)

__all__ = [
    "HypothesisEngine",
    "HypothesisNode",
    "HypothesisTransitionError",
    "HypothesisDeleteError",
    "can_transition",
]


# ---------------------------------------------------------------------------
# 4 态迁移矩阵
# ---------------------------------------------------------------------------
# 语义对齐 GapStore._STATE_TRANSITIONS 模式（dict[Status, frozenset[Status]]）。
#
# 迁移语义：
# - PROPOSED -> VERIFYING：verify() 开始验证
# - PROPOSED -> REFUTED：refute() 直接否定（如负向反查 prune）
# - VERIFYING -> CONFIRMED：confirm() 信号匹配
# - VERIFYING -> REFUTED：refute() 信号不符 / 步数耗尽
# - CONFIRMED -> REFUTED：仅 overturn_root_cause() 走此路径（方法内绕过 _transition_check）
# - REFUTED：（无）终态，INV-2 不可迁出
_STATE_TRANSITIONS: dict[HypothesisStatus, frozenset[HypothesisStatus]] = {
    HypothesisStatus.PROPOSED: frozenset({
        HypothesisStatus.VERIFYING,
        HypothesisStatus.REFUTED,
    }),
    HypothesisStatus.VERIFYING: frozenset({
        HypothesisStatus.CONFIRMED,
        HypothesisStatus.REFUTED,
    }),
    HypothesisStatus.CONFIRMED: frozenset({HypothesisStatus.REFUTED}),
    HypothesisStatus.REFUTED: frozenset(),
}


def can_transition(
    from_status: HypothesisStatus,
    to_status: HypothesisStatus,
) -> bool:
    """判断 from_status -> to_status 迁移是否合法。

    Args:
        from_status: 当前状态。
        to_status: 目标状态。

    Returns:
        True 如果迁移在 _STATE_TRANSITIONS 允许集合中。
    """
    allowed = _STATE_TRANSITIONS.get(from_status, frozenset())
    return to_status in allowed


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class HypothesisTransitionError(Exception):
    """非法状态迁移（不在 _STATE_TRANSITIONS 允许集合中）。"""


class HypothesisDeleteError(Exception):
    """禁止物理删除 refuted 节点（INV-2）。

    INV-2 要求：Hypothesis refuted 节点（含被推翻的 confirmed）永久保留，
    作负向知识沉淀。refuted 状态本身不可迁出，但可经 overturn_root_cause
    在 confirmed 节点上写入 overturning_* 字段后置 refuted。
    """


# ---------------------------------------------------------------------------
# HypothesisNode dataclass（内存表示，与 SCH01 Hypothesis ORM 字段对齐）
# ---------------------------------------------------------------------------


@dataclass
class HypothesisNode:
    """假设树节点（内存表示）。

    字段与 SCH01 ``Hypothesis`` ORM 一一对应：
        id ↔ id / parent_id ↔ parent_id / content ↔ hypothesis_text
        status ↔ status / expected_signal ↔ expected_signal
        verifying_action ↔ verify_action / step_budget ↔ step_budget
        step_used ↔ step_used / confirming_evidence ↔ confirming_evidence
        falsifying_signal ↔ falsifying_signal
        overturning_signal ↔ overturning_signal
        overturning_stage ↔ overturning_stage / is_rootcause ↔ is_rootcause

    本引擎内存操作，不耦合 SQLAlchemy session；持久化映射由调用方负责。

    Attributes:
        id: 节点唯一标识（uuid.uuid4().hex）。
        parent_id: 父节点 id（None 为根假设）。
        content: 假设描述文本。
        status: 4 态之一（默认 PROPOSED）。
        expected_signal: 预测的可证伪信号。
        verifying_action: 验证动作。
        step_budget: 单假设验证步数预算（design D7 默认 5，由调用方设置）。
        step_used: 已消耗步数。
        confirming_evidence: 确认证据（confirm 时写入）。
        falsifying_signal: 证伪信号（refute 时写入）。
        overturning_signal: 被推翻时的信号（overturn 时写入）。
        overturning_stage: 被推翻时所处的阶段（fixing/verifying/regression）。
        is_rootcause: 是否定为根因（默认 False）。
        children: 子节点列表（构建假设树）。
        demote_factor: 负向反查降权因子（默认 1.0，<1.0 表示被降权）。
    """

    id: str
    parent_id: Optional[str]
    content: str
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    expected_signal: Optional[dict[str, Any]] = None
    verifying_action: Optional[dict[str, Any]] = None
    step_budget: Optional[int] = None
    step_used: int = 0
    confirming_evidence: Optional[dict[str, Any]] = None
    falsifying_signal: Optional[dict[str, Any]] = None
    overturning_signal: Optional[dict[str, Any]] = None
    overturning_stage: Optional[str] = None
    is_rootcause: bool = False
    children: list["HypothesisNode"] = field(default_factory=list)
    demote_factor: float = 1.0


# ---------------------------------------------------------------------------
# HypothesisEngine
# ---------------------------------------------------------------------------


class HypothesisEngine:
    """假设树引擎：4 态状态机 + 换方向 + 根因回退 + 步数预算 + 负向反查。

    封装回溯/根因回退/步数预算（内部闭环，不外泄 Orchestrator）。
    所有方法为同步（纯内存操作 + 同步调 gap_store / kb_retriever）。

    Args:
        gap_store: BF008 GapStore（步数耗尽转缺口，可 None 优雅降级）。
        kb_retriever: BF005 KBRetriever（负向知识反查剪枝，可 None 优雅降级）。
        max_steps: 引擎级步数预算硬上限（默认 20，D7 design 全局 30 留余量）。
    """

    def __init__(
        self,
        *,
        gap_store: Optional[GapStore] = None,
        kb_retriever: Optional[KBRetriever] = None,
        max_steps: int = 20,
    ) -> None:
        self._gap_store = gap_store
        self._kb_retriever = kb_retriever
        self._max_steps = max_steps
        self._nodes: dict[str, HypothesisNode] = {}

    # ------------------------------------------------------------------
    # 假设树构建（AC-8）
    # ------------------------------------------------------------------

    def propose(
        self,
        parent_id: Optional[str],
        content: str,
        expected_signal: Optional[dict[str, Any]] = None,
    ) -> HypothesisNode:
        """提出新假设（proposed 状态）。

        Args:
            parent_id: 父节点 id；None 表示根假设。
            content: 假设描述文本。
            expected_signal: 预测的可证伪信号（可选）。

        Returns:
            新建的 HypothesisNode（status=PROPOSED）。

        Raises:
            ValueError: parent_id 非空但在 _nodes 中不存在。
        """
        if parent_id is not None and parent_id not in self._nodes:
            raise ValueError(f"parent hypothesis {parent_id!r} not found")

        node = HypothesisNode(
            id=uuid.uuid4().hex,
            parent_id=parent_id,
            content=content,
            expected_signal=expected_signal,
        )
        self._nodes[node.id] = node

        if parent_id is not None:
            self._nodes[parent_id].children.append(node)

        return node

    # ------------------------------------------------------------------
    # 4 态迁移（AC-1）
    # ------------------------------------------------------------------

    def verify(self, hypothesis_id: str) -> None:
        """proposed → verifying（开始验证）。

        Args:
            hypothesis_id: 假设 id。

        Raises:
            ValueError: 节点不存在。
            HypothesisTransitionError: 非 PROPOSED → VERIFYING 迁移。
        """
        node = self._require_node(hypothesis_id)
        self._transition_check(node, HypothesisStatus.VERIFYING)
        node.status = HypothesisStatus.VERIFYING

    def confirm(
        self,
        hypothesis_id: str,
        evidence: Optional[dict[str, Any]] = None,
    ) -> None:
        """verifying → confirmed（信号匹配确认）。

        Args:
            hypothesis_id: 假设 id。
            evidence: 确认证据（写入 confirming_evidence）。

        Raises:
            ValueError: 节点不存在。
            HypothesisTransitionError: 非 VERIFYING → CONFIRMED 迁移。
        """
        node = self._require_node(hypothesis_id)
        self._transition_check(node, HypothesisStatus.CONFIRMED)
        node.status = HypothesisStatus.CONFIRMED
        if evidence is not None:
            node.confirming_evidence = evidence

    def refute(
        self,
        hypothesis_id: str,
        reason: str,
        falsifying_signal: Optional[dict[str, Any]] = None,
    ) -> None:
        """→ refuted（INV-2 不删，永久保留）。

        可从 PROPOSED / VERIFYING 迁移到 REFUTED。
        CONFIRMED → REFUTED 仅经 ``overturn_root_cause`` 走特殊路径，不直接调本方法。

        Args:
            hypothesis_id: 假设 id。
            reason: refuted 原因。
            falsifying_signal: 证伪信号（可选）。

        Raises:
            ValueError: 节点不存在。
            HypothesisTransitionError: 当前状态不可迁移到 REFUTED。
        """
        node = self._require_node(hypothesis_id)
        self._transition_check(node, HypothesisStatus.REFUTED)
        self._apply_refute(node, reason=reason, falsifying_signal=falsifying_signal)

    # ------------------------------------------------------------------
    # 换方向（AC-2）
    # ------------------------------------------------------------------

    def refute_and_pivot(
        self,
        hypothesis_id: str,
        reason: str,
    ) -> Optional[HypothesisNode]:
        """refute 当前 + 换方向（回溯 parent 切下一个 proposed 兄弟）。

        两步原子语义：先 refute（status → REFUTED），再 pivot（回溯找兄弟）。

        Args:
            hypothesis_id: 当前假设 id。
            reason: refuted 原因。

        Returns:
            下一个 proposed 兄弟节点；上溯到根仍无兄弟 → None（诊断路径穷尽）。
        """
        node = self._require_node(hypothesis_id)
        self._transition_check(node, HypothesisStatus.REFUTED)
        self._apply_refute(node, reason=reason, falsifying_signal=None)
        return self._find_next_proposed_sibling(node)

    # ------------------------------------------------------------------
    # 根因回退（AC-3）
    # ------------------------------------------------------------------

    def overturn_root_cause(
        self,
        root_id: str,
        reason: str,
        overturning_signal: dict[str, Any],
        overturning_stage: str,
    ) -> Optional[HypothesisNode]:
        """confirmed 根因被推翻 → refuted + overturned 标记 + pivot。

        绕过常规 _transition_check（CONFIRMED → REFUTED 只允许经此路径）：
        直接修改 status=REFUTED + is_rootcause=False + 记录 overturning_* 字段，
        然后触发 pivot。

        Args:
            root_id: 根因节点 id。
            reason: 推翻原因。
            overturning_signal: 推翻信号（写入 overturning_signal 字段）。
            overturning_stage: 推翻阶段（fixing / verifying / regression）。

        Returns:
            pivot 返回的下一个 proposed 兄弟；无兄弟 → None。

        Raises:
            ValueError: 节点不存在。
            HypothesisTransitionError: 节点非 CONFIRMED 或非 is_rootcause。
        """
        node = self._require_node(root_id)
        if node.status != HypothesisStatus.CONFIRMED or not node.is_rootcause:
            raise HypothesisTransitionError(
                f"overturn requires CONFIRMED + is_rootcause=True, "
                f"got status={node.status.value!r}, is_rootcause={node.is_rootcause} "
                f"for hypothesis {root_id!r}"
            )
        # 绕过 _transition_check：CONFIRMED → REFUTED 只允许经此路径
        node.status = HypothesisStatus.REFUTED
        node.is_rootcause = False
        node.overturning_signal = overturning_signal
        node.overturning_stage = overturning_stage
        # 区分"验证失败 refuted"与"被推翻 refuted"：后者有 overturning_signal
        node.falsifying_signal = {"reason": reason, "overturned": True}
        return self._find_next_proposed_sibling(node)

    # ------------------------------------------------------------------
    # 步数预算 D7（AC-4 / AC-5）
    # ------------------------------------------------------------------

    def check_budget_and_pivot(self, current_id: str) -> bool:
        """步数预算检查；耗尽 → refute + 转缺口 + 返回 True（不 pivot）。

        检查引擎级 ``self._max_steps``（全局硬上限）。耗尽时：
        (a) refute 当前假设；
        (b) **不**执行换方向（与 design 第 799 行一致）；
        (c) 调 ``gap_store.create`` 转缺口（coverage / reasoning）。

        Args:
            current_id: 当前假设 id。

        Returns:
            True 表示预算耗尽（已 refute + 转缺口）；False 表示预算未耗尽。
        """
        node = self._require_node(current_id)

        if node.step_used < self._max_steps:
            return False

        # 预算耗尽：refute 当前（CONFIRMED 状态经 _transition_check 守护，
        # VERIFYING/PROPOSED 合法迁移到 REFUTED）
        self._transition_check(node, HypothesisStatus.REFUTED)
        self._apply_refute(
            node,
            reason=f"step budget exhausted: {node.step_used}/{self._max_steps}",
            falsifying_signal=None,
        )

        # gap_type：当前节点是被推翻的根因 → reasoning；否则 coverage
        gap_type = (
            "reasoning"
            if node.overturning_signal is not None
            else "coverage"
        )
        self._create_budget_gap(node, gap_type)
        return True

    def _create_budget_gap(
        self,
        node: HypothesisNode,
        gap_type: str,
    ) -> None:
        """步数耗尽转缺口（coverage / reasoning）。

        gap_store=None 时降级（仅 warning，不阻断）；create 抛异常时捕获 + warning。
        """
        if self._gap_store is None:
            logger.warning(
                "HypothesisEngine step budget exhausted for %r but gap_store is None; "
                "skip gap creation (degraded)",
                node.id,
            )
            return

        gap_data = {
            "id": uuid.uuid4().hex,
            "gap_type": gap_type,
            "description": (
                f"step budget exhausted: {node.step_used}/{self._max_steps} "
                f"for hypothesis {node.id!r} (status={node.status.value})"
            ),
            "linked_bug_ids": [],
        }
        try:
            self._gap_store.create(gap_data)
        except Exception as exc:
            logger.warning(
                "HypothesisEngine gap_store.create failed for budget exhaustion: %s",
                exc,
            )

    # ------------------------------------------------------------------
    # 负向知识反查剪枝（AC-7）
    # ------------------------------------------------------------------

    def negate_and_prune(
        self,
        hypothesis_vectors: list[list[float]],
        symptom_type: str,
        hypothesis_ids: Optional[list[str]] = None,
    ) -> list[str]:
        """负向知识反查剪枝；返回被 prune 的 hypothesis_id 列表。

        调 ``KBRetriever.negate_hypotheses`` 获取 ``list[NegativeVerdict]``，
        按 verdict 处理：
        - ``prune == True`` → 对应假设直接 refute，id 加入 pruned_ids。
        - ``demote_factor < 1.0`` → 写入 ``node.demote_factor``，**不** refute。
        - 其他 → 不受影响。

        Args:
            hypothesis_vectors: 候选假设向量列表（调用方负责向量化）。
            symptom_type: 症状类型（预过滤键）。
            hypothesis_ids: 与 hypothesis_vectors 同长度同顺序的节点 id 列表。
                None 时按 ``[f"hyp_{i}" for i in range(len(vectors))]`` 占位
                （此时 prune/demote 仅作用于占位 id，不触碰引擎节点）。

        Returns:
            被 prune 的 hypothesis_id 列表（引擎节点 id 或占位 id）。
        """
        if self._kb_retriever is None:
            return []

        if hypothesis_ids is None:
            hypothesis_ids = [f"hyp_{i}" for i in range(len(hypothesis_vectors))]

        try:
            verdicts: list[NegativeVerdict] = self._kb_retriever.negate_hypotheses(
                hypothesis_vectors=hypothesis_vectors,
                symptom_type=symptom_type,
            )
        except Exception as exc:
            logger.warning(
                "HypothesisEngine negate_hypotheses failed: %s", exc
            )
            return []

        pruned_ids: list[str] = []
        for idx, verdict in enumerate(verdicts):
            if idx >= len(hypothesis_ids):
                break
            node_id = hypothesis_ids[idx]
            node = self._nodes.get(node_id)

            if verdict.prune:
                if node is not None:
                    try:
                        self._transition_check(node, HypothesisStatus.REFUTED)
                        self._apply_refute(
                            node,
                            reason=(
                                f"negative knowledge prune: "
                                f"similarity={verdict.max_negative_similarity}"
                            ),
                            falsifying_signal={
                                "negative_similarity": verdict.max_negative_similarity,
                            },
                        )
                    except HypothesisTransitionError:
                        logger.warning(
                            "HypothesisEngine negate prune skipped for %r "
                            "(illegal transition from %s)",
                            node_id,
                            node.status.value,
                        )
                pruned_ids.append(node_id)
            elif verdict.demote_factor < 1.0 and node is not None:
                node.demote_factor = verdict.demote_factor

        return pruned_ids

    # ------------------------------------------------------------------
    # INV-2 守护（AC-6）
    # ------------------------------------------------------------------

    def delete(self, hypothesis_id: str) -> None:
        """禁止物理删除（INV-2）。

        refuted 节点（含被推翻的 confirmed）永久保留作负向知识。
        refuted 状态本身不可迁出，但节点不可物理删除。

        Raises:
            HypothesisDeleteError: 始终抛出。
        """
        raise HypothesisDeleteError(
            f"hard delete hypothesis {hypothesis_id!r} is forbidden (INV-2). "
            f"refuted nodes are permanently retained as negative knowledge."
        )

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _require_node(self, hypothesis_id: str) -> HypothesisNode:
        """获取节点；不存在抛 ValueError。"""
        node = self._nodes.get(hypothesis_id)
        if node is None:
            raise ValueError(f"hypothesis {hypothesis_id!r} not found")
        return node

    def _transition_check(
        self,
        node: HypothesisNode,
        to_status: HypothesisStatus,
    ) -> None:
        """检查迁移合法性；非法抛 HypothesisTransitionError。"""
        if not can_transition(node.status, to_status):
            raise HypothesisTransitionError(
                f"illegal transition {node.status.value} -> {to_status.value} "
                f"for hypothesis {node.id!r}"
            )

    def _apply_refute(
        self,
        node: HypothesisNode,
        *,
        reason: str,
        falsifying_signal: Optional[dict[str, Any]],
    ) -> None:
        """应用 refute 副作用（status + falsifying_signal）。

        前置条件：调用方已通过 _transition_check。
        """
        node.status = HypothesisStatus.REFUTED
        if falsifying_signal is not None:
            node.falsifying_signal = falsifying_signal
        elif node.falsifying_signal is None:
            node.falsifying_signal = {"reason": reason}

    def _find_next_proposed_sibling(
        self,
        node: HypothesisNode,
    ) -> Optional[HypothesisNode]:
        """从 node 开始向上回溯，找下一个 proposed 兄弟。

        算法：
        1. 当前节点 parent_id 为 None（根）→ 无兄弟 → 返回 None。
        2. 在 parent.children 中找 status==PROPOSED 的兄弟（排除自身）。
        3. 无 proposed 兄弟 → 上溯到 parent，重复 1-2。
        4. 到根仍无 → 返回 None。

        refuted 兄弟不参与候选（INV-2 永久保留但不重选）。
        """
        current = node
        while current.parent_id is not None:
            parent = self._nodes[current.parent_id]
            for sibling in parent.children:
                if (
                    sibling.id != current.id
                    and sibling.status == HypothesisStatus.PROPOSED
                ):
                    return sibling
            current = parent
        return None
