"""信息完备度评估器 ISM 单元测试（R001-BB001）。

覆盖 Sprint Contract AC-1 ~ AC-8（14 场景）：
- AC-1 评估接口（sufficient/borderline/insufficient/dict 输入）
- AC-2 三档分级阈值（含 0.8/0.5 边界 + level 重算）
- AC-3 临界追问（borderline 非空 / sufficient/insufficient 清空）
- AC-4 不足降级（insufficient → degraded=True）
- AC-5 LLMGateway 调用 + JSON 解析容错
- AC-6 KB 派生 gaps（kb_context 提供/None）
- AC-7 gaps 分类过滤（A/B/C/D）
- AC-8 LLM 失败降级（LLMError / 非法 JSON / 缺 score）

策略：
- 不引入 pytest-asyncio，用 asyncio.run() 同步包装异步测试。
- LLMGateway 用 FakeLLMGateway（队列返回预设响应）。
- KB 用 mock RetrievedEntry / KBEntry（dataclass-like stub）。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agent.assessment.info_sufficiency_evaluator import (
    ISMLevel,
    ISMResult,
    InfoSufficiencyEvaluator,
    _build_clarify_questions,
    _compute_level,
    _derive_gaps_from_kb,
    _extract_score,
    _filter_gaps,
    _parse_llm_json,
)
from agent.infra.llm_gateway import FakeLLMGateway


# ---------------------------------------------------------------------------
# 辅助：构造 BugReport-like 对象（dict 和 SimpleNamespace 两种）
# ---------------------------------------------------------------------------
def _make_bug_report_obj(
    *,
    version_code: str = "1.2.3",
    symptom_type: str = "crash",
    raw_report: dict | None = None,
) -> SimpleNamespace:
    """构造 BugReport-like 对象（属性访问，模拟 ORM 对象）。"""
    if raw_report is None:
        raw_report = {
            "summary": "点击按钮崩溃",
            "steps": ["打开 app", "点击提交"],
        }
    return SimpleNamespace(
        version_code=version_code,
        symptom_type=symptom_type,
        raw_report=raw_report,
    )


def _make_bug_report_dict(
    *,
    version_code: str = "1.2.3",
    symptom_type: str = "crash",
    raw_report: dict | None = None,
) -> dict:
    """构造 BugReport-like dict（dict 输入，验证 duck typing）。"""
    if raw_report is None:
        raw_report = {"summary": "点击按钮崩溃"}
    return {
        "version_code": version_code,
        "symptom_type": symptom_type,
        "raw_report": raw_report,
    }


def _make_kb_entry(
    *,
    content: dict | None = None,
    layer: str = "pattern",
    symptom_type: str = "crash",
) -> SimpleNamespace:
    """构造 KBEntry-like 对象。"""
    return SimpleNamespace(
        content=content or {},
        layer=layer,
        symptom_type=symptom_type,
    )


def _make_retrieved_entry(entry: SimpleNamespace) -> SimpleNamespace:
    """构造 RetrievedEntry-like 对象。"""
    return SimpleNamespace(
        entry=entry,
        similarity=0.9,
        raw_similarity=0.95,
        validity_status="valid",
        conflicting_with=None,
    )


def _make_llm_response_json(
    *,
    score: float = 0.9,
    gaps: list[str] | None = None,
    clarify_questions: list[str] | None = None,
    reasoning: str = "信息完备",
    level: str | None = None,
) -> str:
    """构造 LLM 返回的 JSON 字符串。"""
    payload: dict = {
        "score": score,
        "gaps": gaps or [],
        "clarify_questions": clarify_questions or [],
        "reasoning": reasoning,
    }
    if level is not None:
        payload["level"] = level
    return json.dumps(payload, ensure_ascii=False)


def _run_async(coro):
    """同步运行 async 协程（asyncio.run 包装）。"""
    return asyncio.run(coro)


# ===========================================================================
# 纯函数辅助测试
# ===========================================================================
class TestComputeLevel:
    """AC-2：三档分级阈值（含边界）。"""

    def test_score_above_08_sufficient(self):
        assert _compute_level(0.85, 0.8, 0.5) is ISMLevel.SUFFICIENT

    def test_score_08_boundary_sufficient(self):
        """score=0.8 → sufficient（>= 语义）。"""
        assert _compute_level(0.8, 0.8, 0.5) is ISMLevel.SUFFICIENT

    def test_score_079_borderline(self):
        assert _compute_level(0.79, 0.8, 0.5) is ISMLevel.BORDERLINE

    def test_score_05_boundary_borderline(self):
        """score=0.5 → borderline（>= 语义）。"""
        assert _compute_level(0.5, 0.8, 0.5) is ISMLevel.BORDERLINE

    def test_score_049_insufficient(self):
        assert _compute_level(0.49, 0.8, 0.5) is ISMLevel.INSUFFICIENT

    def test_score_0_insufficient(self):
        assert _compute_level(0.0, 0.8, 0.5) is ISMLevel.INSUFFICIENT


class TestFilterGaps:
    """AC-7：gaps 分类过滤。"""

    def test_valid_gaps_preserved(self):
        assert _filter_gaps(["A", "B", "C", "D"]) == ["A", "B", "C", "D"]

    def test_invalid_gaps_filtered(self):
        assert _filter_gaps(["A", "X", "B", "Y", "Z"]) == ["A", "B"]

    def test_dedup(self):
        assert _filter_gaps(["A", "A", "B", "B"]) == ["A", "B"]

    def test_non_list_returns_empty(self):
        assert _filter_gaps("ABC") == []
        assert _filter_gaps(None) == []
        assert _filter_gaps(123) == []


class TestParseLlmJson:
    """AC-5：JSON 解析容错。"""

    def test_plain_json(self):
        parsed = _parse_llm_json('{"score": 0.9, "gaps": ["A"]}')
        assert parsed is not None
        assert parsed["score"] == 0.9

    def test_json_fence(self):
        content = '```json\n{"score": 0.8, "gaps": ["B"]}\n```'
        parsed = _parse_llm_json(content)
        assert parsed is not None
        assert parsed["score"] == 0.8

    def test_json_fence_no_lang(self):
        content = '```\n{"score": 0.7}\n```'
        parsed = _parse_llm_json(content)
        assert parsed is not None
        assert parsed["score"] == 0.7

    def test_json_with_prefix_text(self):
        """LLM 可能输出前缀文字 + JSON。"""
        content = '评估结果如下：\n{"score": 0.6, "gaps": ["C"]}\n谢谢'
        parsed = _parse_llm_json(content)
        assert parsed is not None
        assert parsed["score"] == 0.6

    def test_empty_content(self):
        assert _parse_llm_json("") is None
        assert _parse_llm_json("   ") is None

    def test_non_json(self):
        assert _parse_llm_json("not a json at all") is None

    def test_json_array_not_dict(self):
        assert _parse_llm_json("[1,2,3]") is None


class TestExtractScore:
    """AC-5：score 提取与钳制。"""

    def test_normal_score(self):
        assert _extract_score({"score": 0.85}) == 0.85

    def test_missing_score(self):
        assert _extract_score({"level": "sufficient"}) is None

    def test_string_score(self):
        assert _extract_score({"score": "0.9"}) == 0.9

    def test_invalid_score(self):
        assert _extract_score({"score": "abc"}) is None

    def test_clamp_high(self):
        assert _extract_score({"score": 1.5}) == 1.0

    def test_clamp_low(self):
        assert _extract_score({"score": -0.3}) == 0.0


class TestDeriveGapsFromKb:
    """AC-6：KB 派生 gaps 候选。"""

    def test_none_kb_returns_empty(self):
        assert _derive_gaps_from_kb(None) == []

    def test_empty_list_returns_empty(self):
        assert _derive_gaps_from_kb([]) == []

    def test_extract_from_metadata_gap_hint(self):
        entry = _make_kb_entry(content={"metadata": {"gap_hint": ["A", "C"]}})
        retrieved = _make_retrieved_entry(entry)
        result = _derive_gaps_from_kb([retrieved])
        assert result == ["A", "C"]

    def test_extract_from_content_gap_hint(self):
        entry = _make_kb_entry(content={"gap_hint": "B"})
        retrieved = _make_retrieved_entry(entry)
        result = _derive_gaps_from_kb([retrieved])
        assert result == ["B"]

    def test_dedup_across_entries(self):
        e1 = _make_kb_entry(content={"gap_hint": ["A", "B"]})
        e2 = _make_kb_entry(content={"gap_hint": ["A", "C"]})
        r1 = _make_retrieved_entry(e1)
        r2 = _make_retrieved_entry(e2)
        result = _derive_gaps_from_kb([r1, r2])
        assert result == ["A", "B", "C"]

    def test_no_gap_hint_returns_empty(self):
        entry = _make_kb_entry(content={"other": "data"})
        retrieved = _make_retrieved_entry(entry)
        assert _derive_gaps_from_kb([retrieved]) == []

    def test_invalid_hint_filtered(self):
        entry = _make_kb_entry(content={"gap_hint": ["X", "A", "Y"]})
        retrieved = _make_retrieved_entry(entry)
        assert _derive_gaps_from_kb([retrieved]) == ["A"]


class TestBuildClarifyQuestions:
    """AC-3：clarify_questions 构造。"""

    def test_use_llm_questions_when_provided(self):
        result = _build_clarify_questions(["A"], ["请提供复现步骤", "请提供日志"])
        assert result == ["请提供复现步骤", "请提供日志"]

    def test_fallback_to_gap_templates(self):
        result = _build_clarify_questions(["A", "C"], None)
        assert len(result) == 2
        assert "复现" in result[0]
        assert "堆栈" in result[1] or "logcat" in result[1]

    def test_empty_gaps_and_no_llm_questions(self):
        assert _build_clarify_questions([], None) == []

    def test_filter_empty_strings_in_llm_questions(self):
        result = _build_clarify_questions(["A"], ["", "  ", "有效问题"])
        assert result == ["有效问题"]


# ===========================================================================
# InfoSufficiencyEvaluator.evaluate 集成测试
# ===========================================================================
class TestEvaluateSufficient:
    """AC-1/2/3/4：sufficient 场景。"""

    def test_evaluate_sufficient(self):
        """LLM 返回 score=0.9 → SUFFICIENT，clarify_questions=[]，degraded=False。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9, reasoning="信息完备")])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert isinstance(result, ISMResult)
        assert result.level == ISMLevel.SUFFICIENT.value
        assert result.score == 0.9
        assert result.degraded is False
        assert result.clarify_questions == []
        assert result.gaps == []

    def test_clarify_questions_empty_when_sufficient(self):
        """sufficient → clarify_questions=[]（AC-3）。"""
        llm = FakeLLMGateway(
            [_make_llm_response_json(score=0.9, clarify_questions=["不应该出现"])]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.SUFFICIENT.value
        # sufficient 时强制清空，即使 LLM 返回了问题
        assert result.clarify_questions == []


class TestEvaluateBorderline:
    """AC-1/2/3/4：borderline 场景。"""

    def test_evaluate_borderline(self):
        """LLM 返回 score=0.6 → BORDERLINE，clarify_questions 非空，degraded=False。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.6,
                    gaps=["A", "C"],
                    clarify_questions=["请提供复现步骤", "请附上崩溃堆栈日志"],
                    reasoning="缺少复现步骤和堆栈",
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.BORDERLINE.value
        assert result.score == 0.6
        assert result.degraded is False
        assert len(result.clarify_questions) >= 1
        assert result.clarify_questions == ["请提供复现步骤", "请附上崩溃堆栈日志"]

    def test_borderline_clarify_from_gaps_when_llm_empty(self):
        """borderline 时 LLM 未生成 clarify_questions → 从 gaps 派生。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.6,
                    gaps=["A", "B"],
                    clarify_questions=[],
                    reasoning="缺信息",
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.BORDERLINE.value
        assert len(result.clarify_questions) >= 1

    def test_borderline_no_gaps_no_llm_questions_fallback(self):
        """borderline 但无 gaps 也无 LLM 问题 → 兜底通用追问。"""
        llm = FakeLLMGateway(
            [_make_llm_response_json(score=0.55, gaps=[], clarify_questions=[])]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.BORDERLINE.value
        assert len(result.clarify_questions) == 1


class TestEvaluateInsufficient:
    """AC-1/2/3/4：insufficient 场景。"""

    def test_evaluate_insufficient(self):
        """LLM 返回 score=0.3 → INSUFFICIENT，degraded=True，clarify_questions=[]。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.3,
                    gaps=["A", "B", "C", "D"],
                    clarify_questions=[],  # 不足不追问
                    reasoning="信息严重不足",
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.score == 0.3
        assert result.degraded is True
        assert result.clarify_questions == []
        assert result.gaps == ["A", "B", "C", "D"]

    def test_clarify_questions_empty_when_insufficient(self):
        """insufficient → clarify_questions=[]（AC-3）。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.3,
                    clarify_questions=["不应该出现"],
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.clarify_questions == []


class TestThresholdBoundaries:
    """AC-2：阈值边界（>= 语义）。"""

    def test_threshold_boundary_08(self):
        """score=0.8 → sufficient（>= 0.8）。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.8)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.SUFFICIENT.value

    def test_threshold_boundary_05(self):
        """score=0.5 → borderline（>= 0.5 且 < 0.8）。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.5)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.BORDERLINE.value

    def test_threshold_boundary_079(self):
        """score=0.79 → borderline。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.79)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.BORDERLINE.value

    def test_threshold_boundary_049(self):
        """score=0.49 → insufficient。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.49)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value


class TestLevelRecomputed:
    """AC-2：level 由 score 重算（不信任 LLM level）。"""

    def test_level_recomputed_from_score(self):
        """LLM 返回 level=sufficient 但 score=0.3 → 重算为 INSUFFICIENT。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.3,
                    level="sufficient",  # LLM 幻觉
                    reasoning="",
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.degraded is True

    def test_level_recomputed_llm_says_borderline_but_score_high(self):
        """LLM 返回 level=borderline 但 score=0.9 → 重算为 SUFFICIENT。"""
        llm = FakeLLMGateway(
            [_make_llm_response_json(score=0.9, level="borderline")]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.SUFFICIENT.value
        assert result.degraded is False


class TestLLMFailureFallback:
    """AC-8：LLM 失败降级。"""

    def test_llm_failure_fallback(self):
        """FakeLLMGateway 队列空 → LLMError → insufficient + degraded。"""
        llm = FakeLLMGateway([])  # 空队列，complete 抛 LLMError
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.score == 0.0
        assert result.degraded is True
        assert result.gaps == []
        assert result.clarify_questions == []
        assert "LLM failure" in result.reasoning

    def test_llm_error_not_propagated(self):
        """ISM 不向调用方抛 LLMError。"""
        llm = FakeLLMGateway([])
        evaluator = InfoSufficiencyEvaluator(llm)
        # 不应抛异常
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert isinstance(result, ISMResult)


class TestJsonParseFailureFallback:
    """AC-5：JSON 解析失败降级。"""

    def test_json_parse_failure_fallback(self):
        """LLM 返回非 JSON → insufficient + degraded。"""
        llm = FakeLLMGateway(["这不是 JSON"])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.degraded is True
        assert "invalid JSON" in result.reasoning or "LLM failure" in result.reasoning

    def test_missing_score_fallback(self):
        """LLM 返回 JSON 但缺 score → insufficient + degraded。"""
        llm = FakeLLMGateway(['{"level": "sufficient", "gaps": []}'])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.degraded is True
        assert "missing score" in result.reasoning or "LLM failure" in result.reasoning

    def test_empty_content_fallback(self):
        """LLM 返回空字符串 → insufficient + degraded。"""
        llm = FakeLLMGateway([""])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.level == ISMLevel.INSUFFICIENT.value
        assert result.degraded is True


class TestKbContextDeriveGaps:
    """AC-6：KB 派生 gaps 候选。"""

    def test_kb_context_derives_gaps_in_prompt(self):
        """kb_context 提供 → prompt 中注入 KB 候选 gaps。"""
        entry = _make_kb_entry(content={"gap_hint": ["A", "C"]})
        retrieved = _make_retrieved_entry(entry)
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        _run_async(evaluator.evaluate(_make_bug_report_obj(), kb_context=[retrieved]))
        # 验证 LLM 被调用且 messages 含 KB gaps
        assert llm.call_count == 1
        call = llm.calls[0]
        user_content = call["messages"][1]["content"]
        assert "A" in user_content
        assert "C" in user_content

    def test_kb_context_none_no_block(self):
        """kb_context=None → 正常评估，prompt 中 gaps 候选为"(无)"。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj(), kb_context=None))
        assert isinstance(result, ISMResult)
        assert result.level == ISMLevel.SUFFICIENT.value
        # 验证 prompt 中标注无候选
        call = llm.calls[0]
        user_content = call["messages"][1]["content"]
        assert "无" in user_content

    def test_kb_context_degraded_still_extracts_gaps(self):
        """AC-6：kb_context 检索质量低（模拟 degraded）→ entries 非空时仍提取 gaps。

        Contract AC-6 断言：kb_context.degraded=True 时，gaps 候选仍尽力提取。
        ISM 的 _derive_gaps_from_kb 只看 entries 是否含 gap_hint，不关心检索质量，
        所以只要 entries 非空且含 gap_hint，候选就会被提取。
        """
        # 构造低相似度但仍含 gap_hint 的 entries（模拟冷启动/低质量检索）
        entry = _make_kb_entry(content={"metadata": {"gap_hint": ["B", "D"]}})
        retrieved = SimpleNamespace(
            entry=entry,
            similarity=0.3,  # 低相似度
            raw_similarity=0.35,
            validity_status="stale",
            conflicting_with=None,
        )
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        _run_async(evaluator.evaluate(_make_bug_report_obj(), kb_context=[retrieved]))
        call = llm.calls[0]
        user_content = call["messages"][1]["content"]
        assert "B" in user_content
        assert "D" in user_content


class TestGapsFilterInvalid:
    """AC-7：gaps 过滤非法元素。"""

    def test_gaps_filter_invalid_in_evaluate(self):
        """LLM 返回 gaps 含 "X" → 过滤掉。"""
        llm = FakeLLMGateway(
            [
                _make_llm_response_json(
                    score=0.9,
                    gaps=["A", "X", "B", "Y", "Z", "C", "D"],
                )
            ]
        )
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert result.gaps == ["A", "B", "C", "D"]
        assert "X" not in result.gaps


class TestBugReportDictInput:
    """AC-1：dict 输入也能工作（duck typing）。"""

    def test_bug_report_dict_input(self):
        """dict 输入 → evaluate 正常返回 ISMResult。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.85)])
        evaluator = InfoSufficiencyEvaluator(llm)
        result = _run_async(evaluator.evaluate(_make_bug_report_dict()))
        assert isinstance(result, ISMResult)
        assert result.level == ISMLevel.SUFFICIENT.value
        # 验证 prompt 中字段被正确提取
        call = llm.calls[0]
        user_content = call["messages"][1]["content"]
        assert "1.2.3" in user_content  # version_code
        assert "crash" in user_content  # symptom_type


class TestLLMGatewayCall:
    """AC-5：LLMGateway 调用验证。"""

    def test_uses_symptom_classify_prompt_type(self):
        """调 llm.complete(prompt_type="symptom_classify", ...)。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        _run_async(evaluator.evaluate(_make_bug_report_obj()))
        assert llm.call_count == 1
        call = llm.calls[0]
        assert call["prompt_type"] == "symptom_classify"

    def test_messages_contain_system_and_user(self):
        """messages 含 system + user role。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        _run_async(evaluator.evaluate(_make_bug_report_obj()))
        call = llm.calls[0]
        roles = [m["role"] for m in call["messages"]]
        assert roles == ["system", "user"]

    def test_system_prompt_contains_keywords(self):
        """system prompt 含 "bug 分诊专家" / "信息完备度"。"""
        llm = FakeLLMGateway([_make_llm_response_json(score=0.9)])
        evaluator = InfoSufficiencyEvaluator(llm)
        _run_async(evaluator.evaluate(_make_bug_report_obj()))
        call = llm.calls[0]
        system_content = call["messages"][0]["content"]
        assert "bug 分诊专家" in system_content
        assert "信息完备度" in system_content
