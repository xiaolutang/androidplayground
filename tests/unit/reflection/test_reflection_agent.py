"""ReflectionAgent 单元测试（R001-BB013）。

全 mock，覆盖 16+ 场景（AC-1 ~ AC-8）：

- TestCollectHypotheses（AC-1）：读 trajectory（含 refuted/overturned/confirmed）；
  空 trajectory；overturned 收集；dict / ORM 兼容。
- TestExtractNegativeKnowledge（AC-2）：LLM 提取；prompt 含 falsifying_signal；
  confirmed 不作为来源；LLM 返回结构化结果；多条提取；confidence 范围校验。
- TestHitClues（AC-3）：confirmed → raw_trajectory；无 confirmed 不写；
  HitClue 字段正确；不走 LLM。
- TestINV3Guard（AC-4）：无 add_pattern 方法；无 add_pattern 调用；
  available_operations 白名单。
- TestWriteNegativeKnowledge（AC-5）：逐条写入；单条失败继续；kb_retriever=None 降级。
- TestLLMFailure（AC-6）：LLM 失败 → llm_failed；LLM 不可解析 → llm_failed；
  LLM 失败不影响 raw_trajectory；extracted_count=0。
- TestReflectionResult（AC-7）：各字段正确性；skipped_reason 取值。
- TestReflectMainFlow：端到端主流程。

无 DB / 真实 LLM 依赖（全 mock）。
"""
from __future__ import annotations

import inspect
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.infra.llm_gateway import LLMError, LLMResponse
from agent.reflection.reflection_agent import (
    HitClue,
    NegativeKnowledgeItem,
    ReflectionAgent,
    ReflectionResult,
)
from agent.schemas.trajectory import HypothesisStatus


# ---------------------------------------------------------------------------
# 工厂辅助
# ---------------------------------------------------------------------------
def _make_hypothesis(
    *,
    id: str = "hyp_001",
    content: str = "假设 A 是根因",
    status: HypothesisStatus | str = HypothesisStatus.CONFIRMED,
    falsifying_signal: dict | None = None,
    overturning_signal: dict | None = None,
    overturning_stage: str | None = None,
    confirming_evidence: dict | None = None,
    verify_action: dict | None = None,
    is_rootcause: bool = False,
) -> dict:
    """构造一个 hypothesis dict（duck typing 兼容）。"""
    status_val = status.value if hasattr(status, "value") else status
    h = {
        "id": id,
        "content": content,
        "status": status_val,
        "is_rootcause": is_rootcause,
    }
    if falsifying_signal is not None:
        h["falsifying_signal"] = falsifying_signal
    if overturning_signal is not None:
        h["overturning_signal"] = overturning_signal
        h["overturning_stage"] = overturning_stage
    if confirming_evidence is not None:
        h["confirming_evidence"] = confirming_evidence
    if verify_action is not None:
        h["verify_action"] = verify_action
    return h


def _make_trajectory(hypotheses: list[dict]) -> dict:
    """构造 trajectory dict。"""
    return {"id": "traj_001", "hypotheses": hypotheses}


def _make_llm_gateway(
    *,
    response_content: str | None = None,
    side_effect: Exception | None = None,
) -> MagicMock:
    """构造 mock LLMGateway。

    - response_content 非空 → complete 返回 LLMResponse(content=response_content)；
    - side_effect 非空 → complete 抛出该异常；
    - 二者均为空 → 返回空 content（触发解析失败降级）。
    """
    gw = MagicMock()
    if side_effect is not None:
        gw.complete = AsyncMock(side_effect=side_effect)
    else:
        resp = LLMResponse(
            content=response_content if response_content is not None else "",
            model="glm-5.1",
        )
        gw.complete = AsyncMock(return_value=resp)
    return gw


class _FakeKBRetriever:
    """in-memory KBRetriever 双。

    记录所有 add_negative_knowledge / add_raw_trajectory 调用，
    支持注入单条失败（fail_on_nth）验证逐条容错。
    """

    def __init__(
        self,
        *,
        neg_failure_on_nth: int | None = None,
        raw_failure_on_nth: int | None = None,
    ) -> None:
        self.neg_calls: list[dict] = []
        self.raw_calls: list[dict] = []
        self._neg_fail = neg_failure_on_nth
        self._raw_fail = raw_failure_on_nth
        self._neg_call_count = 0
        self._raw_call_count = 0

    def add_negative_knowledge(
        self,
        *,
        content: str,
        source_hypothesis_id: str,
        confidence: float,
    ) -> None:
        # 基于调用次序（含失败），使失败仅触发一次
        self._neg_call_count += 1
        if self._neg_fail is not None and self._neg_call_count == self._neg_fail:
            raise RuntimeError(f"injected neg failure on #{self._neg_call_count}")
        self.neg_calls.append(
            {
                "content": content,
                "source_hypothesis_id": source_hypothesis_id,
                "confidence": confidence,
            }
        )

    def add_raw_trajectory(
        self,
        *,
        root_hypothesis_id: str,
        confirmed_evidence: dict,
        fixing_action_summary: str,
        success_signal: dict,
    ) -> None:
        self._raw_call_count += 1
        if self._raw_fail is not None and self._raw_call_count == self._raw_fail:
            raise RuntimeError(f"injected raw failure on #{self._raw_call_count}")
        self.raw_calls.append(
            {
                "root_hypothesis_id": root_hypothesis_id,
                "confirmed_evidence": confirmed_evidence,
                "fixing_action_summary": fixing_action_summary,
                "success_signal": success_signal,
            }
        )


def _agent(
    *,
    llm_gateway: MagicMock | None = None,
    kb_retriever=None,
) -> ReflectionAgent:
    """构造 ReflectionAgent（默认无 kb_retriever，测试自行注入）。"""
    gw = llm_gateway if llm_gateway is not None else _make_llm_gateway()
    return ReflectionAgent(llm_gateway=gw, kb_retriever=kb_retriever)


def _nk_json(items: list[dict]) -> str:
    """构造 LLM 返回的 negative_knowledge JSON 数组字符串。"""
    return json.dumps(items, ensure_ascii=False)


# ---------------------------------------------------------------------------
# AC-1：读 trajectory
# ---------------------------------------------------------------------------
class TestCollectHypotheses:
    """AC-1：_collect_hypotheses 收集所有 hypothesis（含 refuted/overturned）。"""

    def test_collects_all_statuses(self):
        """收集 confirmed + refuted + overturned 全部状态。"""
        agent = _agent()
        traj = _make_trajectory(
            [
                _make_hypothesis(id="h1", status=HypothesisStatus.CONFIRMED),
                _make_hypothesis(id="h2", status=HypothesisStatus.REFUTED),
                _make_hypothesis(
                    id="h3",
                    status=HypothesisStatus.CONFIRMED,
                    overturning_signal={"reason": "overturned in fixing"},
                ),
            ]
        )
        result = agent._collect_hypotheses(traj)
        assert len(result) == 3
        ids = {h["id"] for h in result}
        assert ids == {"h1", "h2", "h3"}

    def test_empty_trajectory_returns_empty(self):
        """空 trajectory（无 hypothesis）→ 返回空列表。"""
        agent = _agent()
        assert agent._collect_hypotheses({"hypotheses": []}) == []
        assert agent._collect_hypotheses({}) == []
        assert agent._collect_hypotheses(None) == []

    def test_refuted_not_filtered(self):
        """refuted hypothesis 不被过滤——negative_knowledge 核心来源。"""
        agent = _agent()
        traj = _make_trajectory(
            [
                _make_hypothesis(id="r1", status=HypothesisStatus.REFUTED),
                _make_hypothesis(id="r2", status=HypothesisStatus.REFUTED),
            ]
        )
        result = agent._collect_hypotheses(traj)
        assert len(result) == 2

    def test_overturned_collected(self):
        """overturned hypothesis（有 overturning_signal）被收集。"""
        agent = _agent()
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="ov1",
                    status=HypothesisStatus.CONFIRMED,
                    overturning_signal={"signal": "regression_fail"},
                    overturning_stage="regression",
                ),
            ]
        )
        result = agent._collect_hypotheses(traj)
        assert len(result) == 1
        assert result[0]["id"] == "ov1"

    def test_dict_with_spelling_variant(self):
        """dict 输入兼容 hypothese（拼写容错）。"""
        agent = _agent()
        traj = {"hypothese": [_make_hypothesis(id="x1")]}
        result = agent._collect_hypotheses(traj)
        assert len(result) == 1

    def test_orm_like_object(self):
        """ORM-like 对象（getattr 访问）兼容。"""
        agent = _agent()

        class _Traj:
            hypotheses = [_make_hypothesis(id="orm1")]

        result = agent._collect_hypotheses(_Traj())
        assert len(result) == 1
        assert result[0]["id"] == "orm1"


# ---------------------------------------------------------------------------
# AC-2：LLM 提取 negative_knowledge
# ---------------------------------------------------------------------------
class TestExtractNegativeKnowledge:
    """AC-2：_extract_negative_knowledge 调 LLM 提取 negative_knowledge。"""

    @pytest.mark.asyncio
    async def test_llm_called_with_reflection_prompt_type(self):
        """LLM 以 prompt_type=reflection 调用。"""
        gw = _make_llm_gateway(response_content="[]")
        agent = _agent(llm_gateway=gw)
        await agent._extract_negative_knowledge(
            [_make_hypothesis(id="h1", status=HypothesisStatus.REFUTED)]
        )
        gw.complete.assert_awaited_once()
        call_kwargs = gw.complete.await_args
        assert call_kwargs.kwargs["prompt_type"] == "reflection"

    @pytest.mark.asyncio
    async def test_prompt_includes_falsifying_signal(self):
        """LLM prompt 包含 refuted hypothesis 的 falsifying_signal。"""
        gw = _make_llm_gateway(response_content="[]")
        agent = _agent(llm_gateway=gw)
        h = _make_hypothesis(
            id="h1",
            status=HypothesisStatus.REFUTED,
            falsifying_signal={"matched": "no_crash"},
        )
        await agent._extract_negative_knowledge([h])
        messages = gw.complete.await_args.kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "falsifying_signal" in user_msg["content"]
        assert "no_crash" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_prompt_includes_overturning_signal(self):
        """LLM prompt 包含 overturned hypothesis 的 overturning_signal。"""
        gw = _make_llm_gateway(response_content="[]")
        agent = _agent(llm_gateway=gw)
        h = _make_hypothesis(
            id="h2",
            status=HypothesisStatus.CONFIRMED,
            overturning_signal={"reason": "fixing_fail"},
            overturning_stage="fixing",
        )
        await agent._extract_negative_knowledge([h])
        messages = gw.complete.await_args.kwargs["messages"]
        user_msg = next(m for m in messages if m["role"] == "user")
        assert "overturning_signal" in user_msg["content"]
        assert "fixing_fail" in user_msg["content"]

    @pytest.mark.asyncio
    async def test_returns_structured_items(self):
        """LLM 返回结构化结果 → 返回 NegativeKnowledgeItem 列表。"""
        llm_content = _nk_json(
            [
                {
                    "content": "不要假设 A，因为 X 信号缺失",
                    "source_hypothesis_id": "h1",
                    "confidence": 0.8,
                },
                {
                    "content": "B 路径在 Y 条件下不应尝试",
                    "source_hypothesis_id": "h2",
                    "confidence": 0.6,
                },
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [
                _make_hypothesis(id="h1", status=HypothesisStatus.REFUTED),
                _make_hypothesis(id="h2", status=HypothesisStatus.REFUTED),
            ]
        )
        assert items is not None
        assert len(items) == 2
        assert all(isinstance(i, NegativeKnowledgeItem) for i in items)
        assert items[0].content == "不要假设 A，因为 X 信号缺失"
        assert items[0].source_hypothesis_id == "h1"
        assert items[0].confidence == pytest.approx(0.8)

    @pytest.mark.asyncio
    async def test_confirmed_not_used_as_source(self):
        """confirmed hypothesis 不进入 negative_knowledge 提取（在 reflect 层过滤）。"""
        gw = _make_llm_gateway(response_content="[]")
        agent = _agent(llm_gateway=gw)
        # reflect 入口：只有 confirmed → no_refuted，不调 LLM
        traj = _make_trajectory(
            [_make_hypothesis(id="c1", status=HypothesisStatus.CONFIRMED)]
        )
        result = await agent.reflect(traj)
        assert result.skipped_reason == "no_refuted"
        gw.complete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_extracts_multiple_items(self):
        """LLM 提取多条 negative_knowledge（3 条）。"""
        llm_content = _nk_json(
            [
                {
                    "content": f"负面知识 {i}",
                    "source_hypothesis_id": f"h{i}",
                    "confidence": 0.5 + i * 0.1,
                }
                for i in range(1, 4)
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [
                _make_hypothesis(id=f"h{i}", status=HypothesisStatus.REFUTED)
                for i in range(1, 4)
            ]
        )
        assert items is not None
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_confidence_out_of_range_dropped(self):
        """confidence 超出 [0,1] → 该条丢弃 + warning。"""
        llm_content = _nk_json(
            [
                {
                    "content": "valid",
                    "source_hypothesis_id": "h1",
                    "confidence": 0.5,
                },
                {
                    "content": "invalid",
                    "source_hypothesis_id": "h2",
                    "confidence": 1.5,
                },
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [
                _make_hypothesis(id="h1", status=HypothesisStatus.REFUTED),
                _make_hypothesis(id="h2", status=HypothesisStatus.REFUTED),
            ]
        )
        assert items is not None
        assert len(items) == 1
        assert items[0].source_hypothesis_id == "h1"

    @pytest.mark.asyncio
    async def test_hallucination_id_dropped(self):
        """source_hypothesis_id 不存在于 trajectory → 丢弃（幻觉防护）。"""
        llm_content = _nk_json(
            [
                {
                    "content": "valid",
                    "source_hypothesis_id": "h1",
                    "confidence": 0.5,
                },
                {
                    "content": "hallucination",
                    "source_hypothesis_id": "nonexistent",
                    "confidence": 0.9,
                },
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [_make_hypothesis(id="h1", status=HypothesisStatus.REFUTED)]
        )
        assert items is not None
        assert len(items) == 1
        assert items[0].source_hypothesis_id == "h1"


# ---------------------------------------------------------------------------
# AC-3：命中线索
# ---------------------------------------------------------------------------
class TestHitClues:
    """AC-3：_extract_hit_clues / _write_raw_trajectory。"""

    def test_extract_confirmed_hit_clue(self):
        """confirmed hypothesis → 提取 HitClue，字段正确。"""
        agent = _agent()
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"matched": "stack_top", "success": True},
                    verify_action={"action": "patch_file", "file": "A.kt"},
                    is_rootcause=True,
                ),
            ]
        )
        clues = agent._extract_hit_clues(traj)
        assert len(clues) == 1
        clue = clues[0]
        assert isinstance(clue, HitClue)
        assert clue.root_hypothesis_id == "c1"
        assert clue.confirmed_evidence == {"matched": "stack_top", "success": True}
        assert "patch_file" in clue.fixing_action_summary or "A.kt" in clue.fixing_action_summary

    def test_no_confirmed_no_clues(self):
        """无 confirmed hypothesis → 无命中线索。"""
        agent = _agent()
        traj = _make_trajectory(
            [_make_hypothesis(id="r1", status=HypothesisStatus.REFUTED)]
        )
        clues = agent._extract_hit_clues(traj)
        assert clues == []

    def test_hit_clues_not_dependent_on_llm(self):
        """命中线索提取不走 LLM（LLM gateway 未被调用）。"""
        gw = _make_llm_gateway()
        agent = _agent(llm_gateway=gw)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    verify_action={"action": "noop"},
                )
            ]
        )
        agent._extract_hit_clues(traj)
        gw.complete.assert_not_called()

    def test_root_cause_prioritized(self):
        """is_rootcause=True 的假设优先作为命中线索来源。"""
        agent = _agent()
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    is_rootcause=False,
                    confirming_evidence={"ev": "non-root"},
                ),
                _make_hypothesis(
                    id="c2",
                    status=HypothesisStatus.CONFIRMED,
                    is_rootcause=True,
                    confirming_evidence={"ev": "root"},
                ),
            ]
        )
        clues = agent._extract_hit_clues(traj)
        # 只取 root cause（is_rootcause=True 的）
        assert len(clues) == 1
        assert clues[0].root_hypothesis_id == "c2"


# ---------------------------------------------------------------------------
# AC-4：INV-3 守护
# ---------------------------------------------------------------------------
class TestINV3Guard:
    """AC-4：INV-3 守护（仅写 negative_knowledge 层，禁写 pattern 层）。"""

    def test_no_add_pattern_method(self):
        """ReflectionAgent 类中无 add_pattern 方法。"""
        assert not hasattr(ReflectionAgent, "add_pattern")
        agent = _agent()
        assert not hasattr(agent, "add_pattern")

    def test_no_add_pattern_call_in_source(self):
        """源码中无对 kb_retriever.add_pattern 的调用（grep 验证）。"""
        import agent.reflection.reflection_agent as mod

        source = inspect.getsource(mod)
        # 允许在注释中提及 add_pattern（说明禁止原因），但不能有实际方法调用
        # 实际调用形式：self._kb_retriever.add_pattern(...) 或 kb_retriever.add_pattern(...)
        # 排除注释行（以 # 开头）
        code_lines = [
            line
            for line in source.splitlines()
            if not line.strip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert ".add_pattern(" not in code, (
            "INV-3 violation: found .add_pattern() call in source"
        )

    def test_available_operations_whitelist(self):
        """available_operations 返回白名单，不含 add_pattern。"""
        agent = _agent()
        ops = agent.available_operations
        assert isinstance(ops, list)
        assert "add_negative_knowledge" in ops
        assert "add_raw_trajectory" in ops
        assert "add_pattern" not in ops

    def test_available_operations_returns_sorted(self):
        """available_operations 返回排序后的列表。"""
        agent = _agent()
        ops = agent.available_operations
        assert ops == sorted(ops)


# ---------------------------------------------------------------------------
# AC-5：KBRetriever.add_negative_knowledge 调用
# ---------------------------------------------------------------------------
class TestWriteNegativeKnowledge:
    """AC-5：_write_negative_knowledge 逐条写入 + 单条失败继续。"""

    def test_writes_all_items(self):
        """逐条调 add_negative_knowledge。"""
        kb = _FakeKBRetriever()
        agent = _agent(kb_retriever=kb)
        items = [
            NegativeKnowledgeItem(
                content="nk1", source_hypothesis_id="h1", confidence=0.8
            ),
            NegativeKnowledgeItem(
                content="nk2", source_hypothesis_id="h2", confidence=0.6
            ),
        ]
        written = agent._write_negative_knowledge(items)
        assert written == 2
        assert len(kb.neg_calls) == 2
        assert kb.neg_calls[0]["content"] == "nk1"
        assert kb.neg_calls[0]["source_hypothesis_id"] == "h1"
        assert kb.neg_calls[0]["confidence"] == pytest.approx(0.8)

    def test_single_failure_continues(self):
        """单条写入失败 → 捕获 + 继续写下一条（written_count=2 of 3）。"""
        kb = _FakeKBRetriever(neg_failure_on_nth=2)
        agent = _agent(kb_retriever=kb)
        items = [
            NegativeKnowledgeItem(
                content=f"nk{i}", source_hypothesis_id=f"h{i}", confidence=0.5
            )
            for i in range(1, 4)
        ]
        written = agent._write_negative_knowledge(items)
        assert written == 2  # 第 2 条失败，第 1 + 第 3 成功
        assert len(kb.neg_calls) == 2

    def test_kb_retriever_none_returns_zero(self):
        """kb_retriever=None → 返回 0 + warning。"""
        agent = _agent(kb_retriever=None)
        items = [
            NegativeKnowledgeItem(
                content="nk", source_hypothesis_id="h1", confidence=0.5
            )
        ]
        written = agent._write_negative_knowledge(items)
        assert written == 0

    def test_kb_retriever_missing_method_returns_zero(self):
        """kb_retriever 缺少 add_negative_knowledge 方法 → 返回 0。"""
        kb = MagicMock()  # 无 add_negative_knowledge 方法
        # MagicMock 默认会有属性，所以用 spec 限定
        kb = MagicMock(spec=["add_raw_trajectory"])
        agent = _agent(kb_retriever=kb)
        items = [
            NegativeKnowledgeItem(
                content="nk", source_hypothesis_id="h1", confidence=0.5
            )
        ]
        written = agent._write_negative_knowledge(items)
        assert written == 0


# ---------------------------------------------------------------------------
# AC-6：LLM 失败降级
# ---------------------------------------------------------------------------
class TestLLMFailure:
    """AC-6：LLM 失败降级。"""

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_none(self):
        """LLM 抛 LLMError → _safe_llm_call 返回 None。"""
        gw = _make_llm_gateway(side_effect=LLMError("timeout"))
        agent = _agent(llm_gateway=gw)
        resp = await agent._safe_llm_call([{"role": "user", "content": "x"}])
        assert resp is None

    @pytest.mark.asyncio
    async def test_llm_unexpected_exception_returns_none(self):
        """LLM 抛非 LLMError → _safe_llm_call 返回 None。"""
        gw = _make_llm_gateway(side_effect=RuntimeError("unexpected"))
        agent = _agent(llm_gateway=gw)
        resp = await agent._safe_llm_call([{"role": "user", "content": "x"}])
        assert resp is None

    @pytest.mark.asyncio
    async def test_llm_failed_skips_negative_knowledge(self):
        """LLM 失败 → skipped_reason=llm_failed，extracted_count=0。"""
        gw = _make_llm_gateway(side_effect=LLMError("api error"))
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": 1},
                ),
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    verify_action={"action": "patch"},
                    is_rootcause=True,
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.skipped_reason == "llm_failed"
        assert result.extracted_count == 0
        assert result.written_count == 0
        # negative_knowledge 未写入
        assert len(kb.neg_calls) == 0

    @pytest.mark.asyncio
    async def test_llm_failed_raw_trajectory_still_written(self):
        """LLM 失败不影响 raw_trajectory 写入。"""
        gw = _make_llm_gateway(side_effect=LLMError("api error"))
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": 1},
                ),
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    verify_action={"action": "patch"},
                    is_rootcause=True,
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.raw_trajectory_written is True
        assert len(kb.raw_calls) == 1
        assert kb.raw_calls[0]["root_hypothesis_id"] == "c1"

    @pytest.mark.asyncio
    async def test_llm_unparseable_returns_none_items(self):
        """LLM 返回不可解析（非 JSON 数组）→ items=None → 触发 llm_failed。"""
        gw = _make_llm_gateway(response_content="this is not json at all")
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [_make_hypothesis(id="h1", status=HypothesisStatus.REFUTED)]
        )
        assert items is None

    @pytest.mark.asyncio
    async def test_llm_empty_content_returns_none(self):
        """LLM 返回空 content → 解析失败 → None。"""
        gw = _make_llm_gateway(response_content="")
        agent = _agent(llm_gateway=gw)
        items = await agent._extract_negative_knowledge(
            [_make_hypothesis(id="h1", status=HypothesisStatus.REFUTED)]
        )
        assert items is None


# ---------------------------------------------------------------------------
# AC-7：ReflectionResult dataclass
# ---------------------------------------------------------------------------
class TestReflectionResult:
    """AC-7：ReflectionResult 结构与字段正确性。"""

    def test_default_fields(self):
        """ReflectionResult 默认值正确。"""
        r = ReflectionResult(extracted_count=0, written_count=0)
        assert r.skipped_reason is None
        assert r.raw_trajectory_written is False

    def test_no_hypotheses_reason(self):
        """skipped_reason=no_hypotheses（reflect 为 async 协程函数）。"""
        agent = _agent()
        # 直接验证 reflect 是 coroutine function
        assert inspect.iscoroutinefunction(agent.reflect)

    @pytest.mark.asyncio
    async def test_empty_trajectory_result(self):
        """空 trajectory → skipped_reason=no_hypotheses。"""
        agent = _agent()
        result = await agent.reflect(_make_trajectory([]))
        assert result.extracted_count == 0
        assert result.written_count == 0
        assert result.skipped_reason == "no_hypotheses"
        assert result.raw_trajectory_written is False

    @pytest.mark.asyncio
    async def test_no_refuted_result(self):
        """全 confirmed → skipped_reason=no_refuted，raw_trajectory 仍写入。"""
        gw = _make_llm_gateway()
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    verify_action={"action": "patch"},
                    is_rootcause=True,
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.skipped_reason == "no_refuted"
        assert result.raw_trajectory_written is True
        # LLM 未被调用（无 refuted）
        gw.complete.assert_not_awaited()


# ---------------------------------------------------------------------------
# 端到端主流程
# ---------------------------------------------------------------------------
class TestReflectMainFlow:
    """端到端 reflect 主流程集成测试。"""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        """正常反思流程：refuted → LLM 提取 → 写 negative_knowledge + raw_trajectory。"""
        llm_content = _nk_json(
            [
                {
                    "content": "不要走 A 路径，因为 X 信号缺失",
                    "source_hypothesis_id": "r1",
                    "confidence": 0.85,
                }
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    content="假设 A 是根因",
                    falsifying_signal={"no_crash": True},
                ),
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    content="假设 B 是根因",
                    confirming_evidence={"matched": "stack"},
                    verify_action={"action": "patch", "file": "B.kt"},
                    is_rootcause=True,
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.extracted_count == 1
        assert result.written_count == 1
        assert result.skipped_reason is None
        assert result.raw_trajectory_written is True
        # KB 写入验证
        assert len(kb.neg_calls) == 1
        assert kb.neg_calls[0]["source_hypothesis_id"] == "r1"
        assert len(kb.raw_calls) == 1
        assert kb.raw_calls[0]["root_hypothesis_id"] == "c1"

    @pytest.mark.asyncio
    async def test_overturned_hypothesis_used_as_negative_source(self):
        """overturned hypothesis（confirmed + overturning_signal）作为负面知识来源。"""
        llm_content = _nk_json(
            [
                {
                    "content": "overturned 经验",
                    "source_hypothesis_id": "ov1",
                    "confidence": 0.7,
                }
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="ov1",
                    status=HypothesisStatus.CONFIRMED,
                    overturning_signal={"regression_fail": True},
                    overturning_stage="regression",
                ),
            ]
        )
        result = await agent.reflect(traj)
        # ov1 被 _is_refuted_or_overturned 判定为 True（有 overturning_signal）
        assert result.skipped_reason is None
        assert result.extracted_count == 1

    @pytest.mark.asyncio
    async def test_kb_none_full_flow(self):
        """kb_retriever=None 全流程：仍执行 LLM 提取，written_count=0。"""
        llm_content = _nk_json(
            [
                {
                    "content": "nk",
                    "source_hypothesis_id": "r1",
                    "confidence": 0.5,
                }
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        agent = _agent(llm_gateway=gw, kb_retriever=None)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": 1},
                ),
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    is_rootcause=True,
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.extracted_count == 1
        assert result.written_count == 0
        # raw_trajectory 也无法写入（kb_retriever=None）
        assert result.raw_trajectory_written is False

    @pytest.mark.asyncio
    async def test_llm_returns_empty_array(self):
        """LLM 返回空数组（合法 JSON）→ extracted_count=0, skipped_reason=None。"""
        gw = _make_llm_gateway(response_content="[]")
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": 1},
                ),
            ]
        )
        result = await agent.reflect(traj)
        assert result.extracted_count == 0
        assert result.written_count == 0
        # 空数组是合法返回，skipped_reason=None（LLM 成功但没提取到）
        assert result.skipped_reason is None

    @pytest.mark.asyncio
    async def test_multiple_extraction_and_write(self):
        """LLM 提取 3 条 → extracted_count=3, written_count=3。"""
        llm_content = _nk_json(
            [
                {
                    "content": f"nk{i}",
                    "source_hypothesis_id": f"r{i}",
                    "confidence": 0.5 + i * 0.1,
                }
                for i in range(1, 4)
            ]
        )
        gw = _make_llm_gateway(response_content=llm_content)
        kb = _FakeKBRetriever()
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id=f"r{i}",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": i},
                )
                for i in range(1, 4)
            ]
        )
        result = await agent.reflect(traj)
        assert result.extracted_count == 3
        assert result.written_count == 3
        assert len(kb.neg_calls) == 3

    def test_llm_gateway_none_raises(self):
        """llm_gateway=None → ValueError。"""
        with pytest.raises(ValueError, match="llm_gateway"):
            ReflectionAgent(llm_gateway=None)

    @pytest.mark.asyncio
    async def test_raw_trajectory_write_failure_does_not_crash(self):
        """raw_trajectory 写入失败 → 不崩溃，raw_trajectory_written=False。"""
        llm_content = _nk_json([])
        gw = _make_llm_gateway(response_content=llm_content)
        kb = _FakeKBRetriever(raw_failure_on_nth=1)
        agent = _agent(llm_gateway=gw, kb_retriever=kb)
        traj = _make_trajectory(
            [
                _make_hypothesis(
                    id="c1",
                    status=HypothesisStatus.CONFIRMED,
                    confirming_evidence={"ok": True},
                    is_rootcause=True,
                ),
                _make_hypothesis(
                    id="r1",
                    status=HypothesisStatus.REFUTED,
                    falsifying_signal={"x": 1},
                ),
            ]
        )
        result = await agent.reflect(traj)
        # raw_trajectory 写入失败 → False
        assert result.raw_trajectory_written is False
