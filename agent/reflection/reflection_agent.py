"""反思 agent（R001-BB013）——读 trajectory → LLM 提取 negative_knowledge + 命中线索。

依据：
- Sprint Contract R001-BB013（status: agreed，mode: negotiated）
- backend 5.3 reflection：读 trajectory → 提取 negative_knowledge + 命中线索
- architecture INV-3（知识分层写入禁止：BB013 仅写 negative_knowledge / raw_trajectory，
  禁写 pattern）；AP-3（KB 模式层禁止 agent 直接写入）
- 依赖 INF04 LLMGateway（reflection→glm-5.1）/ BF005 KBRetriever

设计要点：
1. **INV-3 守护**（代码结构保证）：
   - 类中**无** ``add_pattern`` 方法；
   - ``available_operations`` 属性返回白名单
     ``["add_negative_knowledge", "add_raw_trajectory"]``，不含 ``add_pattern``。
   - 类中**无**任何对 ``kb_retriever.add_pattern`` 的调用。
2. **LLM 驱动 negative_knowledge 提取**：仅对 refuted/overturned 假设提取负面知识
   （"为什么这条假设不该被提出"、"什么信号可早期排除这条路径"）。
   confirmed 假设是正面知识，不进入 negative_knowledge 层。
3. **命中线索走结构化提取（不走 LLM）**：从 confirmed → fixing 成功路径直接提取
   root_hypothesis_id / confirmed_evidence / fixing_action_summary / success_signal，
   写入 raw_trajectory 层。LLM 失败时命中线索仍正常写入。
4. **LLM 失败降级**：``_safe_llm_call`` 捕获 LLMError + 解析失败 → warning + 返回 None
   → negative_knowledge 跳过（ReflectionResult.skipped_reason="llm_failed"），
   但 raw_trajectory 命中线索不受影响。
5. **结构校验**：LLM 返回的每条必须有 content（非空 str）/ source_hypothesis_id
   （存在于 trajectory）/ confidence（[0.0, 1.0]）。缺字段或非法 → 该条丢弃 + warning。
6. **async**：与 ``SymptomClassifier``（BB002）/ ``VisionDecisionEngine``（BF003）等
   LLM 驱动的业务层一致——``reflect()`` 为 ``async def``，内部 ``await`` LLMGateway.complete。
   Contract 中"同步 def"注释与实际 LLMGateway（async Protocol）冲突，按 codebase 既成模式
   （INF04 LLMGateway.complete 为 async def）选择 async。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from agent.infra.llm_gateway import LLMError, LLMGateway, LLMResponse
from agent.schemas.trajectory import HypothesisStatus

logger = logging.getLogger(__name__)

__all__ = [
    "NegativeKnowledgeItem",
    "HitClue",
    "ReflectionResult",
    "ReflectionAgent",
]


# ---------------------------------------------------------------------------
# skipped_reason 取值（AC-7）
# ---------------------------------------------------------------------------
# None               正常完成（有 negative_knowledge 提取到，或无 refuted 但 raw_trajectory 写入）
# "no_hypotheses"    空 trajectory（无 hypothesis）
# "no_refuted"       无 refuted/overturned 假设（无负面知识可提取）
# "llm_failed"       LLM 调用失败 / 返回不可解析
SkippedReason = Optional[Literal["no_hypotheses", "no_refuted", "llm_failed"]]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class NegativeKnowledgeItem:
    """LLM 提取的单条 negative_knowledge（AC-2 / AC-5）。

    Attributes:
        content: LLM 概括的"为什么这条假设不该被提出 / 什么信号可早期排除这条路径"。
            非原始 hypothesis content。
        source_hypothesis_id: 对应的 refuted/overturned hypothesis id（可追溯来源）。
        confidence: LLM 返回的置信度 [0.0, 1.0]。
    """

    content: str
    source_hypothesis_id: str
    confidence: float


@dataclass
class HitClue:
    """命中线索（成功路径关键决策，AC-3）。

    从 confirmed hypothesis → fixing 成功的路径直接提取（不走 LLM），
    写入 raw_trajectory 层供后续根因定位参考。

    Attributes:
        root_hypothesis_id: confirmed 的根因假设 id。
        confirmed_evidence: 确认证据（Hypothesis.confirming_evidence）。
        fixing_action_summary: 修复动作摘要（从 verify_action 或 fixing 阶段提取）。
        success_signal: 成功信号（从 confirming_evidence 或 trajectory 元信息提取）。
    """

    root_hypothesis_id: str
    confirmed_evidence: dict
    fixing_action_summary: str
    success_signal: dict


@dataclass
class ReflectionResult:
    """反思结果（AC-7）。

    Attributes:
        extracted_count: LLM 成功提取的 negative_knowledge 条数。
        written_count: 成功写入 KB 的 negative_knowledge 条数
            （可能 <= extracted_count，因 KB 写入失败）。
        skipped_reason: 跳过原因；None=正常完成，
            "no_hypotheses"=空 trajectory，"no_refuted"=无 refuted/overturned 假设，
            "llm_failed"=LLM 调用失败 / 不可解析。
        raw_trajectory_written: True 表示命中线索已写入 raw_trajectory 层。
    """

    extracted_count: int
    written_count: int
    skipped_reason: SkippedReason = None
    raw_trajectory_written: bool = False


# ---------------------------------------------------------------------------
# LLM Prompt 模板
# ---------------------------------------------------------------------------
_REFLECTION_SYSTEM_PROMPT = (
    "你是移动端 bug 诊断反思助手。以下假设在诊断过程中被否定（refuted/overturned）。"
    "请从每条被否定的假设中提取 negative_knowledge——"
    '"为什么这条假设不该被提出"、"什么信号可以早期排除这条路径"。'
    '仅输出 JSON 数组，每条形如：'
    '{"content": "...", "source_hypothesis_id": "...", "confidence": 0.0-1.0}'
)

_JSON_ARRAY_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_negative_knowledge_json(content: str) -> list[dict] | None:
    """解析 LLM 返回的 JSON 数组（AC-2 / AC-6 不可解析降级）。

    支持格式：
    - ```json ... ``` 围栏内为数组
    - 裸 JSON 数组 ``[...]``
    - 文本中 ``[...]`` 子串提取

    Returns:
        解析后的 list[dict]；失败返回 None。
    """
    if not content or not content.strip():
        return None

    # 路径 1：围栏提取
    m = _JSON_ARRAY_FENCE_RE.search(content)
    candidate = m.group(1) if m else content

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # 路径 2：从裸文本提取首个 [...]
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            return None

    if not isinstance(parsed, list):
        return None
    return parsed


# ---------------------------------------------------------------------------
# ReflectionAgent
# ---------------------------------------------------------------------------
class ReflectionAgent:
    """反思 agent：读 trajectory → LLM 提取 negative_knowledge + 命中线索。

    INV-3 守护：仅写 negative_knowledge / raw_trajectory 层，**禁写 pattern**。
    从代码结构保证：
    - 类中无 ``add_pattern`` 方法；
    - 无任何对 ``kb_retriever.add_pattern`` 的调用；
    - ``available_operations`` 返回白名单不含 ``add_pattern``。

    Usage:
        agent = ReflectionAgent(llm_gateway=gw, kb_retriever=kb)
        result = await agent.reflect(trajectory)
        # result.extracted_count / written_count / skipped_reason / raw_trajectory_written

    Args:
        llm_gateway: INF04 LLMGateway（必需，None 抛 ValueError）。
        kb_retriever: BF005 KBRetriever（可选，None 时跳过 KB 写入 + warning）。
            duck typing：需提供 ``add_negative_knowledge`` / ``add_raw_trajectory`` 方法。
        model: LLM model 名（默认 glm-5.1，仅用于日志；实际路由由 LLMGateway
            按 prompt_type=reflection 决定）。
    """

    # INV-3 守护：白名单操作（frozenset，不含 add_pattern）
    AVAILABLE_OPERATIONS: frozenset[str] = frozenset(
        {"add_negative_knowledge", "add_raw_trajectory"}
    )

    # 假设状态字段名（与 HypothesisStatus 对齐，duck typing 兼容 ORM / dataclass / dict）
    _REFUTED_STATUSES: frozenset[str] = frozenset(
        {HypothesisStatus.REFUTED.value, "refuted"}
    )
    _CONFIRMED_STATUSES: frozenset[str] = frozenset(
        {HypothesisStatus.CONFIRMED.value, "confirmed"}
    )

    def __init__(
        self,
        *,
        llm_gateway: LLMGateway,
        kb_retriever: Optional[Any] = None,
        model: str = "glm-5.1",
    ) -> None:
        if llm_gateway is None:
            raise ValueError("llm_gateway is required (got None)")
        self._llm_gateway = llm_gateway
        self._kb_retriever = kb_retriever
        self._model = model

    # ------------------------------------------------------------------
    # INV-3 守护：available_operations 白名单
    # ------------------------------------------------------------------
    @property
    def available_operations(self) -> list[str]:
        """返回可用写入操作白名单（INV-3 守护，AC-4）。

        固定返回 ``["add_negative_knowledge", "add_raw_trajectory"]``，
        不包含 ``add_pattern``（pattern 层由 BB015 专属写入）。
        """
        return sorted(self.AVAILABLE_OPERATIONS)

    # ------------------------------------------------------------------
    # 主入口（AC-1 ~ AC-7 主流程）
    # ------------------------------------------------------------------
    async def reflect(self, trajectory: Any) -> ReflectionResult:
        """主入口：反思 trajectory → 写 negative_knowledge + raw_trajectory。

        流程：
        1. 收集所有 hypothesis（含 refuted/overturned）。
        2. 命中线索提取（不走 LLM）→ 写 raw_trajectory 层。
        3. 对 refuted/overturned 假设 → LLM 提取 negative_knowledge → 写 KB。
        4. 任何阶段失败均降级（LLM 失败不影响 raw_trajectory；KB 写入失败不抛）。

        Args:
            trajectory: Trajectory（ORM 对象 / dataclass / dict，duck typing）。
                需提供 ``hypotheses`` 字段（list）或经 ``_collect_hypotheses`` 解析。

        Returns:
            ReflectionResult。
        """
        # 1. 收集所有 hypothesis（AC-1）
        all_hypotheses = self._collect_hypotheses(trajectory)
        if not all_hypotheses:
            logger.info(
                "ReflectionAgent: empty trajectory (no hypotheses); skip reflection"
            )
            return ReflectionResult(
                extracted_count=0,
                written_count=0,
                skipped_reason="no_hypotheses",
                raw_trajectory_written=False,
            )

        # 2. 命中线索（AC-3）——结构化提取，不依赖 LLM，先执行确保不受 LLM 失败影响
        hit_clues = self._extract_hit_clues(trajectory)
        raw_trajectory_written = self._write_raw_trajectory(hit_clues)

        # 3. negative_knowledge 提取（AC-2）——仅从 refuted/overturned 假设
        refuted_hypotheses = [
            h for h in all_hypotheses if self._is_refuted_or_overturned(h)
        ]
        if not refuted_hypotheses:
            logger.info(
                "ReflectionAgent: no refuted/overturned hypotheses; "
                "skip negative_knowledge extraction"
            )
            return ReflectionResult(
                extracted_count=0,
                written_count=0,
                skipped_reason="no_refuted",
                raw_trajectory_written=raw_trajectory_written,
            )

        # 4. LLM 提取 negative_knowledge（AC-2 / AC-6 降级）
        items = await self._extract_negative_knowledge(refuted_hypotheses)
        if items is None:
            # LLM 失败 / 不可解析（AC-6）——raw_trajectory 已写入不受影响
            return ReflectionResult(
                extracted_count=0,
                written_count=0,
                skipped_reason="llm_failed",
                raw_trajectory_written=raw_trajectory_written,
            )

        # 5. 写入 negative_knowledge 层（AC-5）
        written = self._write_negative_knowledge(items)

        return ReflectionResult(
            extracted_count=len(items),
            written_count=written,
            skipped_reason=None,
            raw_trajectory_written=raw_trajectory_written,
        )

    # ------------------------------------------------------------------
    # AC-1：读 trajectory（收集所有 hypothesis，含 refuted/overturned）
    # ------------------------------------------------------------------
    def _collect_hypotheses(self, trajectory: Any) -> list[Any]:
        """收集 trajectory 中所有 hypothesis（含 confirmed / refuted / overturned）。

        duck typing 兼容：
        - ORM Trajectory：优先 ``trajectory.hypotheses``（relationship）；
        - dict：``trajectory["hypotheses"]``；
        - 兼容 ``hypothese``（拼写容错，部分老代码）。

        refuted / overturned 假设是 negative_knowledge 的核心来源，必须完整收集，
        不做状态过滤。

        Args:
            trajectory: Trajectory 对象或 dict。

        Returns:
            hypothesis 列表（空 trajectory 返回空列表）。
        """
        if trajectory is None:
            return []

        # 优先 getattr（ORM）
        hypotheses = getattr(trajectory, "hypotheses", None)
        # 回退 dict
        if hypotheses is None and isinstance(trajectory, dict):
            hypotheses = trajectory.get("hypotheses") or trajectory.get("hypothese")
        return list(hypotheses or [])

    # ------------------------------------------------------------------
    # AC-2：LLM 提取 negative_knowledge（仅从 refuted/overturned 假设）
    # ------------------------------------------------------------------
    async def _extract_negative_knowledge(
        self, hypotheses: list[Any]
    ) -> Optional[list[NegativeKnowledgeItem]]:
        """LLM 提取 negative_knowledge（AC-2 / AC-6 降级）。

        调 LLMGateway.complete(prompt_type="reflection", messages=...) → 解析 JSON
        数组 → 结构校验（content / source_hypothesis_id / confidence）→ 返回 items。

        Args:
            hypotheses: refuted/overturned hypothesis 列表。

        Returns:
            NegativeKnowledgeItem 列表；LLM 失败 / 不可解析返回 None（触发降级）。
        """
        # 构造 prompt（含 refuted/overturned 的 content + falsifying_signal /
        # overturning_signal，提供否定证据上下文）
        messages = self._build_reflection_messages(hypotheses)

        # LLM 调用 + 降级（AC-6）
        resp = await self._safe_llm_call(messages)
        if resp is None:
            return None

        # 解析 JSON 数组
        parsed = _parse_negative_knowledge_json(resp.content)
        if parsed is None:
            logger.warning(
                "ReflectionAgent: LLM returned non-JSON-array content, degrade. "
                "content[:200]=%r",
                resp.content[:200],
            )
            return None

        # 结构校验：构建合法 hypothesis_id 集合，丢弃无效条目
        valid_ids = {self._get_hypothesis_id(h) for h in hypotheses}
        valid_ids.discard(None)

        items: list[NegativeKnowledgeItem] = []
        for idx, entry in enumerate(parsed):
            item = self._validate_entry(entry, idx, valid_ids)
            if item is not None:
                items.append(item)
        return items

    def _build_reflection_messages(self, hypotheses: list[Any]) -> list[dict]:
        """构造 LLM 反思 prompt（system + user）。

        user prompt 包含每条 refuted/overturned hypothesis 的：
        - hypothesis_id / content / status
        - falsifying_signal（refuted 否定证据）
        - overturning_signal + overturning_stage（overturned 推翻证据）

        Args:
            hypotheses: refuted/overturned hypothesis 列表。

        Returns:
            [{"role": "system", ...}, {"role": "user", ...}]
        """
        serialized: list[dict] = []
        for h in hypotheses:
            entry = {
                "hypothesis_id": self._get_hypothesis_id(h),
                "content": self._get_hypothesis_content(h),
                "status": self._get_hypothesis_status(h),
            }
            # 否定证据上下文
            falsifying = self._get_field(h, "falsifying_signal")
            if falsifying:
                entry["falsifying_signal"] = falsifying
            overturning = self._get_field(h, "overturning_signal")
            if overturning:
                entry["overturning_signal"] = overturning
                entry["overturning_stage"] = self._get_field(
                    h, "overturning_stage"
                )
            serialized.append(entry)

        user_content = (
            "以下是诊断过程中被否定（refuted/overturned）的假设列表，"
            "请逐条提取 negative_knowledge：\n"
            + json.dumps(serialized, ensure_ascii=False, default=str)
        )
        return [
            {"role": "system", "content": _REFLECTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

    def _validate_entry(
        self,
        entry: Any,
        idx: int,
        valid_ids: set[str],
    ) -> Optional[NegativeKnowledgeItem]:
        """结构校验单条 LLM 返回（AC-2 / Q4 决策）。

        必须满足：
        - entry 为 dict；
        - content 非空字符串；
        - source_hypothesis_id 存在于 trajectory（valid_ids）；
        - confidence ∈ [0.0, 1.0]。

        不满足 → 该条丢弃 + warning，不影响其他条目。

        Args:
            entry: LLM 返回的单条（应为 dict）。
            idx: 在 LLM 返回数组中的下标（日志定位用）。
            valid_ids: trajectory 中合法的 hypothesis_id 集合。

        Returns:
            NegativeKnowledgeItem；校验失败返回 None。
        """
        if not isinstance(entry, dict):
            logger.warning(
                "ReflectionAgent: LLM entry[%d] not a dict, drop: %r", idx, entry
            )
            return None

        content = entry.get("content")
        if not isinstance(content, str) or not content.strip():
            logger.warning(
                "ReflectionAgent: LLM entry[%d] missing/empty content, drop", idx
            )
            return None

        source_id = entry.get("source_hypothesis_id")
        if not isinstance(source_id, str) or not source_id.strip():
            logger.warning(
                "ReflectionAgent: LLM entry[%d] missing source_hypothesis_id, drop",
                idx,
            )
            return None
        # 幻觉防护：source_hypothesis_id 必须存在于 trajectory（Q4 决策）
        # 若 valid_ids 为空（理论上不应发生），跳过此校验避免误杀
        if valid_ids and source_id not in valid_ids:
            logger.warning(
                "ReflectionAgent: LLM entry[%d] source_hypothesis_id=%r not in "
                "trajectory (hallucination?), drop",
                idx,
                source_id,
            )
            return None

        raw_conf = entry.get("confidence")
        try:
            confidence = float(raw_conf)
        except (TypeError, ValueError):
            logger.warning(
                "ReflectionAgent: LLM entry[%d] invalid confidence=%r, drop",
                idx,
                raw_conf,
            )
            return None
        if confidence < 0.0 or confidence > 1.0:
            logger.warning(
                "ReflectionAgent: LLM entry[%d] confidence=%.3f out of [0,1], drop",
                idx,
                confidence,
            )
            return None

        return NegativeKnowledgeItem(
            content=content,
            source_hypothesis_id=source_id,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # AC-3：命中线索（成功路径关键决策记录到 raw_trajectory）
    # ------------------------------------------------------------------
    def _extract_hit_clues(self, trajectory: Any) -> list[HitClue]:
        """提取命中线索（成功路径关键决策，AC-3）。

        从 confirmed hypothesis（is_rootcause=True 优先）提取：
        - root_hypothesis_id
        - confirmed_evidence（Hypothesis.confirming_evidence）
        - fixing_action_summary（verify_action 摘要）
        - success_signal（从 confirming_evidence 或 trajectory 提取）

        不依赖 LLM——直接从 Trajectory 结构化数据提取。

        Args:
            trajectory: Trajectory 对象或 dict。

        Returns:
            HitClue 列表；无 confirmed 假设时返回空列表。
        """
        all_hypotheses = self._collect_hypotheses(trajectory)
        if not all_hypotheses:
            return []

        # 筛选 confirmed（优先 is_rootcause=True 的根因假设）
        confirmed: list[Any] = []
        for h in all_hypotheses:
            status = self._get_hypothesis_status(h)
            if status in self._CONFIRMED_STATUSES:
                confirmed.append(h)

        if not confirmed:
            return []

        # 优先 is_rootcause=True 的假设作为命中线索来源
        root_causes = [h for h in confirmed if self._get_field(h, "is_rootcause")]
        sources = root_causes if root_causes else confirmed

        clues: list[HitClue] = []
        for h in sources:
            h_id = self._get_hypothesis_id(h)
            if h_id is None:
                continue
            evidence = self._get_field(h, "confirming_evidence") or {}
            verify_action = self._get_field(h, "verify_action") or self._get_field(
                h, "verifying_action"
            )
            fixing_summary = self._summarize_fixing_action(verify_action)
            success_signal = self._extract_success_signal(evidence)

            clues.append(
                HitClue(
                    root_hypothesis_id=h_id,
                    confirmed_evidence=evidence if isinstance(evidence, dict) else {},
                    fixing_action_summary=fixing_summary,
                    success_signal=success_signal,
                )
            )
        return clues

    @staticmethod
    def _summarize_fixing_action(verify_action: Any) -> str:
        """从 verify_action 提取修复动作摘要（AC-3）。"""
        if not verify_action:
            return ""
        if isinstance(verify_action, str):
            return verify_action
        if isinstance(verify_action, dict):
            # 常见字段：action / type / description / patch / command
            for key in ("action", "type", "description", "patch", "command"):
                v = verify_action.get(key)
                if v:
                    return str(v)
            # 兜底：JSON 摘要（截断）
            return json.dumps(verify_action, ensure_ascii=False, default=str)[:200]
        return str(verify_action)[:200]

    @staticmethod
    def _extract_success_signal(evidence: dict) -> dict:
        """从 confirming_evidence 提取成功信号（AC-3）。"""
        if not isinstance(evidence, dict):
            return {}
        # 常见字段：success_signal / matched_signal / signal / result
        for key in ("success_signal", "matched_signal", "signal", "result"):
            v = evidence.get(key)
            if v is not None:
                return v if isinstance(v, dict) else {"value": v}
        # 兜底：返回整个 evidence 作为 success_signal 上下文
        return evidence

    # ------------------------------------------------------------------
    # AC-5：KBRetriever.add_negative_knowledge 调用
    # ------------------------------------------------------------------
    def _write_negative_knowledge(
        self, items: list[NegativeKnowledgeItem]
    ) -> int:
        """逐条写入 negative_knowledge 层；返回成功写入条数（AC-5）。

        - ``kb_retriever=None`` → 跳过写入 + warning + 返回 0。
        - 单条写入异常 → 捕获 + warning + 继续写下一条（不因单条失败丢弃全部）。
        - duck typing：``kb_retriever.add_negative_knowledge(content=...,
          source_hypothesis_id=..., confidence=...)``。

        Args:
            items: LLM 提取并校验通过的 NegativeKnowledgeItem 列表。

        Returns:
            成功写入条数。
        """
        if self._kb_retriever is None:
            logger.warning(
                "ReflectionAgent: kb_retriever not injected; "
                "skip negative_knowledge write (%d items dropped)",
                len(items),
            )
            return 0

        if not hasattr(self._kb_retriever, "add_negative_knowledge"):
            logger.warning(
                "ReflectionAgent: kb_retriever lacks add_negative_knowledge method; "
                "skip write"
            )
            return 0

        written = 0
        for item in items:
            try:
                self._kb_retriever.add_negative_knowledge(
                    content=item.content,
                    source_hypothesis_id=item.source_hypothesis_id,
                    confidence=item.confidence,
                )
                written += 1
            except Exception as exc:  # noqa: BLE001  逐条容错
                logger.warning(
                    "ReflectionAgent: kb_retriever.add_negative_knowledge failed "
                    "for source_hypothesis_id=%s (continue next): %s",
                    item.source_hypothesis_id,
                    exc,
                )
        return written

    # ------------------------------------------------------------------
    # AC-3：raw_trajectory 写入
    # ------------------------------------------------------------------
    def _write_raw_trajectory(self, clues: list[HitClue]) -> bool:
        """写入 raw_trajectory 层命中线索（AC-3）。

        - 无命中线索 → 返回 False（不写）。
        - ``kb_retriever=None`` 或缺少方法 → 跳过 + warning + 返回 False。
        - duck typing：``kb_retriever.add_raw_trajectory(...)``。
        - 写入异常 → 捕获 + warning + 返回 False（不阻塞主流程）。

        Args:
            clues: 命中线索列表。

        Returns:
            True 表示至少写入一条；False 表示未写入（无线索 / 未注入 / 异常）。
        """
        if not clues:
            return False

        if self._kb_retriever is None:
            logger.warning(
                "ReflectionAgent: kb_retriever not injected; "
                "skip raw_trajectory write (%d clues dropped)",
                len(clues),
            )
            return False

        if not hasattr(self._kb_retriever, "add_raw_trajectory"):
            logger.warning(
                "ReflectionAgent: kb_retriever lacks add_raw_trajectory method; "
                "skip raw_trajectory write"
            )
            return False

        any_written = False
        for clue in clues:
            try:
                self._kb_retriever.add_raw_trajectory(
                    root_hypothesis_id=clue.root_hypothesis_id,
                    confirmed_evidence=clue.confirmed_evidence,
                    fixing_action_summary=clue.fixing_action_summary,
                    success_signal=clue.success_signal,
                )
                any_written = True
            except Exception as exc:  # noqa: BLE001  逐条容错
                logger.warning(
                    "ReflectionAgent: kb_retriever.add_raw_trajectory failed "
                    "for root_hypothesis_id=%s (continue next): %s",
                    clue.root_hypothesis_id,
                    exc,
                )
                continue
        return any_written

    # ------------------------------------------------------------------
    # AC-6：LLM 失败降级
    # ------------------------------------------------------------------
    async def _safe_llm_call(
        self, messages: list[dict]
    ) -> Optional[LLMResponse]:
        """LLM 调用 + 失败降级（AC-6）。

        捕获 LLMError（超时 / API 错误）+ 其他异常 → warning + 返回 None。
        调用方据此跳过 negative_knowledge 提取（不写部分结果）。

        Args:
            messages: LLM messages（system + user）。

        Returns:
            LLMResponse；失败返回 None。
        """
        try:
            resp = await self._llm_gateway.complete(
                prompt_type="reflection",
                messages=messages,
            )
        except LLMError as exc:
            logger.warning(
                "ReflectionAgent: LLM call failed (LLMError), skip "
                "negative_knowledge extraction: %s",
                exc,
            )
            return None
        except Exception as exc:  # noqa: BLE001  降级捕获
            logger.warning(
                "ReflectionAgent: LLM call failed (unexpected %s), skip "
                "negative_knowledge extraction: %s",
                type(exc).__name__,
                exc,
            )
            return None
        return resp

    # ------------------------------------------------------------------
    # duck typing 辅助（兼容 ORM / dataclass / dict）
    # ------------------------------------------------------------------
    @staticmethod
    def _get_field(obj: Any, name: str, default: Any = None) -> Any:
        """duck typing 字段访问（getattr 优先，dict 回退）。"""
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def _get_hypothesis_id(self, h: Any) -> Optional[str]:
        """获取 hypothesis id（duck typing）。"""
        return self._get_field(h, "id")

    def _get_hypothesis_content(self, h: Any) -> str:
        """获取 hypothesis 描述文本（兼容 hypothesis_text / content）。"""
        text = self._get_field(h, "hypothesis_text") or self._get_field(h, "content")
        return text or ""

    def _get_hypothesis_status(self, h: Any) -> str:
        """获取 hypothesis status（duck typing，兼容 enum / str）。"""
        status = self._get_field(h, "status")
        if status is None:
            return ""
        # enum → value
        if hasattr(status, "value"):
            return str(status.value)
        return str(status)

    def _is_refuted_or_overturned(self, h: Any) -> bool:
        """判断 hypothesis 是否为 refuted 或 overturned（AC-1）。

        - status == "refuted" → True
        - overturning_signal 非空（被推翻的 confirmed，SCH02 schema 语义）→ True

        Args:
            h: hypothesis 对象。

        Returns:
            True 表示该假设是被否定的（negative_knowledge 来源）。
        """
        status = self._get_hypothesis_status(h)
        if status in self._REFUTED_STATUSES:
            return True
        # overturned：status 可能是 confirmed 但有 overturning_signal（design 4.1 第 572 行）
        overturning = self._get_field(h, "overturning_signal")
        if overturning:
            return True
        return False

    # ------------------------------------------------------------------
    # INV-3 守护：显式无 add_pattern 方法
    # ------------------------------------------------------------------
    # 注意：本类故意不定义 add_pattern 方法，从 API 层面保证不可能写 pattern 层。
    # pattern 层唯一写入入口是 BB015（人工修复录入器，AP-3 / INV-3）。
    # 任何未来添加 add_pattern 的尝试都应被 CR 拒绝。
