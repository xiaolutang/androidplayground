"""症状分类器单元测试（R001-BB002）。

覆盖 AC：crash/blank/loading/no_response/data_error 分类正确。

场景：
- 5 类 LLM 成功分类
- LLM 失败规则兜底（crash / ANR / 默认 data_error）
- 非法 symptom_type 规则兜底
- JSON 解析失败规则兜底
- confidence 透传
- dict 输入（duck typing）
- prompt 含 error_type / stacktrace

策略（与 ISM 测试一致）：
- 不引入 pytest-asyncio，用 asyncio.run() 同步包装异步测试。
- LLMGateway 用 FakeLLMGateway（队列返回预设响应）。
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agent.assessment.symptom_classifier import (
    ClassificationResult,
    SymptomClassifier,
    SymptomType,
    _extract_confidence,
    _parse_llm_json,
    _rule_fallback,
)
from agent.infra.llm_gateway import FakeLLMGateway


# ---------------------------------------------------------------------------
# 辅助构造
# ---------------------------------------------------------------------------
def _make_bug_report_obj(
    *,
    error_type: str | None = None,
    stacktrace: str | None = None,
    raw_report: dict | None = None,
) -> SimpleNamespace:
    """构造 BugReport-like 对象（属性访问，模拟 ORM）。"""
    return SimpleNamespace(
        error_type=error_type,
        stacktrace=stacktrace,
        raw_report=raw_report or {},
    )


def _make_bug_report_dict(
    *,
    error_type: str | None = None,
    stacktrace: str | None = None,
    raw_report: dict | None = None,
) -> dict:
    """构造 BugReport-like dict（验证 duck typing）。"""
    return {
        "error_type": error_type,
        "stacktrace": stacktrace,
        "raw_report": raw_report or {},
    }


def _llm_json(symptom: str, confidence: float = 0.9, reasoning: str = "test") -> str:
    """构造 LLM 返回的 JSON 字符串。"""
    return json.dumps(
        {"symptom_type": symptom, "confidence": confidence, "reasoning": reasoning}
    )


def _run(coro):
    """同步执行异步协程（避免引入 pytest-asyncio）。"""
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1-5: LLM 成功分类 5 类
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("symptom", "expected"),
    [
        ("crash", SymptomType.CRASH),
        ("blank", SymptomType.BLANK),
        ("loading", SymptomType.LOADING),
        ("no_response", SymptomType.NO_RESPONSE),
        ("data_error", SymptomType.DATA_ERROR),
    ],
)
def test_classify_llm_five_types(symptom: str, expected: SymptomType) -> None:
    """LLM 返回各类 symptom_type → 分类正确（覆盖 AC 5 类）。"""
    llm = FakeLLMGateway([_llm_json(symptom, confidence=0.9)])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.symptom_type == expected.value
    assert result.confidence == 0.9
    assert result.degraded is False
    assert result.fallback_used is False


def test_classify_crash_llm() -> None:
    """LLM 返回 crash → CRASH（显式独立场景）。"""
    llm = FakeLLMGateway([_llm_json("crash", confidence=0.95, reasoning="NPE")])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj(error_type="NPE")))
    assert result.symptom_type == "crash"
    assert result.reasoning == "NPE"


def test_classify_blank_llm() -> None:
    """LLM 返回 blank → BLANK。"""
    llm = FakeLLMGateway([_llm_json("blank")])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.symptom_type == "blank"


def test_classify_loading_llm() -> None:
    """LLM 返回 loading → LOADING。"""
    llm = FakeLLMGateway([_llm_json("loading")])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.symptom_type == "loading"


def test_classify_no_response_llm() -> None:
    """LLM 返回 no_response → NO_RESPONSE。"""
    llm = FakeLLMGateway([_llm_json("no_response")])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.symptom_type == "no_response"


def test_classify_data_error_llm() -> None:
    """LLM 返回 data_error → DATA_ERROR。"""
    llm = FakeLLMGateway([_llm_json("data_error")])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.symptom_type == "data_error"


# ---------------------------------------------------------------------------
# 6-8: LLM 失败规则兜底
# ---------------------------------------------------------------------------
def test_llm_failure_fallback_crash() -> None:
    """LLM 抛 LLMError + stacktrace 含 FATAL EXCEPTION → crash fallback。"""
    # FakeLLMGateway 空队列 → complete 抛 LLMError
    llm = FakeLLMGateway([])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(
        error_type="NPE",
        stacktrace="FATAL EXCEPTION: main\nAndroidRuntime: NPE",
    )
    result = _run(clf.classify(bug))
    assert result.symptom_type == "crash"
    assert result.degraded is True
    assert result.fallback_used is True
    assert result.confidence == 0.3


def test_llm_failure_fallback_anr() -> None:
    """LLM 失败 + 含 ANR 关键字 → no_response fallback。"""
    llm = FakeLLMGateway([])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(
        raw_report={"summary": "ANR detected in com.foo", "log": "..."},
    )
    result = _run(clf.classify(bug))
    assert result.symptom_type == "no_response"
    assert result.fallback_used is True


def test_llm_failure_fallback_default() -> None:
    """LLM 失败 + 无匹配关键字 → data_error 默认兜底。"""
    llm = FakeLLMGateway([])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(raw_report={"summary": "价格显示错误"})
    result = _run(clf.classify(bug))
    assert result.symptom_type == "data_error"
    assert result.fallback_used is True


# ---------------------------------------------------------------------------
# 9-10: 非法输出兜底
# ---------------------------------------------------------------------------
def test_invalid_symptom_type_fallback() -> None:
    """LLM 返回未知 symptom_type → 规则兜底。"""
    llm = FakeLLMGateway([_llm_json("unknown_type", confidence=0.8)])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(stacktrace="FATAL EXCEPTION")
    result = _run(clf.classify(bug))
    # 非法 symptom_type → fallback；stacktrace 含 FATAL → crash
    assert result.symptom_type == "crash"
    assert result.fallback_used is True
    assert result.degraded is True


def test_json_parse_failure_fallback() -> None:
    """LLM 返回非 JSON → 规则兜底。"""
    llm = FakeLLMGateway(["not a json at all"])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(stacktrace="loading spinner")
    result = _run(clf.classify(bug))
    assert result.fallback_used is True
    # stacktrace 含 loading/spinner → loading fallback
    assert result.symptom_type == "loading"


# ---------------------------------------------------------------------------
# 11-13: 字段与输入兼容性
# ---------------------------------------------------------------------------
def test_confidence_passthrough() -> None:
    """LLM confidence=0.95 → 透传到 ClassificationResult.confidence。"""
    llm = FakeLLMGateway([_llm_json("crash", confidence=0.95)])
    clf = SymptomClassifier(llm)
    result = _run(clf.classify(_make_bug_report_obj()))
    assert result.confidence == 0.95


def test_bug_report_dict_input() -> None:
    """dict 输入兼容（duck typing AC）。"""
    llm = FakeLLMGateway([_llm_json("blank")])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_dict(
        error_type="UI",
        raw_report={"summary": "白屏"},
    )
    result = _run(clf.classify(bug))
    assert result.symptom_type == "blank"
    assert result.degraded is False


def test_prompt_contains_bug_summary() -> None:
    """prompt 的 user message 应含 error_type / stacktrace 字段。"""
    llm = FakeLLMGateway([_llm_json("crash")])
    clf = SymptomClassifier(llm)
    bug = _make_bug_report_obj(
        error_type="NullPointerException",
        stacktrace="at com.foo.Bar(Bar.java:42)",
    )
    _run(clf.classify(bug))
    assert llm.call_count == 1
    calls = llm.calls[0]
    user_msg = next(m["content"] for m in calls["messages"] if m["role"] == "user")
    assert "NullPointerException" in user_msg
    assert "at com.foo.Bar" in user_msg
    # prompt_type 正确路由
    assert calls["prompt_type"] == "symptom_classify"


# ---------------------------------------------------------------------------
# 辅助函数单元测试（提升覆盖率 + 隔离逻辑）
# ---------------------------------------------------------------------------
def test_parse_llm_json_fenced() -> None:
    """```json 围栏解析。"""
    content = '```json\n{"symptom_type": "crash", "confidence": 0.9}\n```'
    parsed = _parse_llm_json(content)
    assert parsed is not None
    assert parsed["symptom_type"] == "crash"


def test_parse_llm_json_bare() -> None:
    """裸 JSON 解析。"""
    parsed = _parse_llm_json('{"symptom_type": "blank"}')
    assert parsed == {"symptom_type": "blank"}


def test_parse_llm_json_embedded() -> None:
    """文本中 {...} 子串提取。"""
    content = '分类结果：{"symptom_type": "loading"} 完成'
    parsed = _parse_llm_json(content)
    assert parsed == {"symptom_type": "loading"}


def test_parse_llm_json_invalid() -> None:
    """非法 JSON → None。"""
    assert _parse_llm_json("") is None
    assert _parse_llm_json("not json") is None
    assert _parse_llm_json("[1,2,3]") is None  # 非 dict


def test_extract_confidence_clamp() -> None:
    """confidence 钳制到 [0, 1]。"""
    assert _extract_confidence({"confidence": 1.5}) == 1.0
    assert _extract_confidence({"confidence": -0.2}) == 0.0
    assert _extract_confidence({"confidence": 0.7}) == 0.7
    assert _extract_confidence({}) is None
    assert _extract_confidence({"confidence": "abc"}) is None


def test_rule_fallback_default() -> None:
    """规则兜底无匹配 → data_error。"""
    result = _rule_fallback(_make_bug_report_obj(raw_report={"x": "y"}))
    assert result.symptom_type == "data_error"
    assert result.confidence == 0.3
    assert result.degraded is True
    assert result.fallback_used is True


def test_classification_result_is_frozen() -> None:
    """ClassificationResult 不可变（frozen dataclass）。"""
    r = ClassificationResult(
        symptom_type="crash",
        confidence=0.9,
        reasoning="",
        degraded=False,
        fallback_used=False,
    )
    with pytest.raises(Exception):
        r.symptom_type = "blank"  # type: ignore[misc]


def test_symptom_type_enum_values() -> None:
    """SymptomType 枚举值与字符串等价（str, Enum）。"""
    assert SymptomType.CRASH == "crash"
    assert SymptomType.NO_RESPONSE == "no_response"
    assert SymptomType.DATA_ERROR == "data_error"
