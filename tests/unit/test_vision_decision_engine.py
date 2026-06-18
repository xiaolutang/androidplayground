"""视觉决策引擎单元测试（R001-BF003）。

覆盖 Sprint Contract AC-1 ~ AC-8，全 mock（FakeLLMGateway + 简单 anchor stub），
主 CI 路径无需 NEW_API_API_KEY。

场景索引（对应 Contract 测试策略表 + 任务要求 12 场景）：
1. test_decide_pure_llm_no_anchor — 无锚点库 → 纯 LLM（AC-1/AC-4）
2. test_decide_with_anchor_context — 锚点对照（AC-3/AC-7）
3. test_decide_empty_anchor_library — AnchorLibrary.is_empty → 纯 LLM（AC-3/AC-4）
4. test_llm_failure_fallback_wait — LLMError → fallback degraded=True（AC-5）
5. test_json_parse_failure_fallback — LLM 返回非 JSON → fallback（AC-5）
6. test_invalid_action_fallback — action 不在白名单 → fallback（AC-6）
7. test_missing_required_field_fallback — 缺 confidence → 走默认值，不 fallback（AC-7）
   （注：缺 action/params 才触发 fallback；缺 confidence 用默认 0.5）
   并补 test_missing_action_field_fallback 覆盖 action 缺失场景
8. test_confidence_clamp — 超 [0,1] → clamp（AC-7）
9. test_confidence_with_anchor_blend — 0.6*LLM + 0.4*similarity（AC-7）
10. test_confidence_pure_llm_self_report — 纯 LLM 用 LLM 自评（AC-7）
11. test_valid_full_response — 正常完整响应解析（AC-1/AC-8）
12. test_params_validation_missing_coords — tap 缺 x/y → fallback（AC-6）

补充：
- test_prompt_type_vision_decision — AC-2：prompt_type 固定 vision_decision
- test_image_url_passthrough — AC-2：image_url 透传
- test_json_codeblock_extracted — ```json``` 包裹也能解析
- test_no_repeated_state_between_calls — 无状态（AC-5）
- test_swipe_missing_coord_fallback — swipe 缺字段 → fallback
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from agent.infra.llm_gateway import FakeLLMGateway
from agent.vision.vision_decision_engine import (
    VisionDecision,
    VisionDecisionEngine,
    _clamp_confidence,
    _fallback_decision,
    _parse_llm_response,
    _validate_params,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@dataclass
class _AnchorStub:
    """轻量 Anchor 替身（避免引入 DB session）。

    与 ``agent.schemas.anchor.Anchor`` 同名字段：page_id / text_expectation。
    """

    page_id: str | None = None
    text_expectation: str | None = None


class _EmptyAnchorLibStub:
    """AnchorLibrary 替身：is_empty() 恒为 True。"""

    def is_empty(self) -> bool:  # noqa: D401
        return True


class _NonEmptyAnchorLibStub:
    """AnchorLibrary 替身：is_empty() 恒为 False。"""

    def is_empty(self) -> bool:  # noqa: D401
        return False


def _run(coro: Any) -> Any:
    """同步执行 async coroutine（测试入口）。"""
    return asyncio.run(coro)


def _valid_tap_json(
    x: int = 100, y: int = 200, confidence: float = 0.8, reasoning: str = "ok"
) -> str:
    return (
        '{"action":"tap","params":{"x":'
        f"{x},"
        f'"y":{y}'
        f'}},"confidence":{confidence},"reasoning":"{reasoning}"}}'
    )


# ---------------------------------------------------------------------------
# 1. 纯 LLM 模式（无锚点库 / anchor_context=None）
# ---------------------------------------------------------------------------


def test_decide_pure_llm_no_anchor():
    """AC-1 / AC-4：无锚点库 → 纯 LLM，used_anchor=False，degraded=False。"""
    llm = FakeLLMGateway([_valid_tap_json()])
    engine = VisionDecisionEngine(llm)
    decision = _run(
        engine.decide(
            "https://example.com/s.png",
            task_description="点击登录按钮",
        )
    )
    assert isinstance(decision, VisionDecision)
    assert decision.action == "tap"
    assert decision.params == {"x": 100, "y": 200}
    assert decision.confidence == pytest.approx(0.8)
    assert decision.reasoning == "ok"
    assert decision.used_anchor is False
    assert decision.degraded is False


def test_confidence_pure_llm_self_report():
    """AC-7：纯 LLM 模式 confidence = LLM 自评。"""
    llm = FakeLLMGateway(
        [_valid_tap_json(confidence=0.65, reasoning="self-eval")]
    )
    engine = VisionDecisionEngine(llm)
    decision = _run(
        engine.decide("s.png", task_description="t", anchor_context=None)
    )
    assert decision.confidence == pytest.approx(0.65)
    assert decision.used_anchor is False


# ---------------------------------------------------------------------------
# 2. 锚点对照模式
# ---------------------------------------------------------------------------


def test_decide_with_anchor_context():
    """AC-3 / AC-7：anchor_context 非空 → prompt 含对照段 + confidence 加权。"""
    llm = FakeLLMGateway([_valid_tap_json(confidence=0.7)])
    engine = VisionDecisionEngine(llm, anchor_lib=_NonEmptyAnchorLibStub())
    anchor = _AnchorStub(page_id="login", text_expectation="登录页")
    decision = _run(
        engine.decide(
            "s.png",
            task_description="点击登录",
            anchor_context=[(anchor, 0.9)],
        )
    )
    # AC-7：confidence = 0.6*0.7 + 0.4*0.9 = 0.78
    assert decision.confidence == pytest.approx(0.78)
    assert decision.used_anchor is True
    assert decision.degraded is False
    # AC-3：prompt 含锚点对照段
    user_msg = llm.calls[0]["messages"][1]["content"]
    assert "锚点参考" in user_msg
    assert "page_id=login" in user_msg
    assert "登录页" in user_msg
    assert "similarity=0.90" in user_msg


def test_decide_empty_anchor_library():
    """AC-3 / AC-4：AnchorLibrary.is_empty() → 即使传了 anchor_context 也降纯 LLM。"""
    llm = FakeLLMGateway([_valid_tap_json(confidence=0.8)])
    engine = VisionDecisionEngine(llm, anchor_lib=_EmptyAnchorLibStub())
    anchor = _AnchorStub(page_id="home", text_expectation="首页")
    decision = _run(
        engine.decide(
            "s.png",
            task_description="t",
            anchor_context=[(anchor, 0.95)],  # 传入但库空
        )
    )
    # 库空 → 不走对照，降纯 LLM
    assert decision.used_anchor is False
    assert decision.degraded is False
    assert decision.confidence == pytest.approx(0.8)
    # prompt 不含对照段
    user_msg = llm.calls[0]["messages"][1]["content"]
    assert "锚点参考" not in user_msg


def test_confidence_with_anchor_blend():
    """AC-7：confidence = 0.6*LLM + 0.4*top_similarity（独立验证加权公式）。"""
    llm = FakeLLMGateway([_valid_tap_json(confidence=0.5)])
    engine = VisionDecisionEngine(llm, anchor_lib=_NonEmptyAnchorLibStub())
    decision = _run(
        engine.decide(
            "s.png",
            task_description="t",
            anchor_context=[(_AnchorStub(), 1.0)],
        )
    )
    # 0.6*0.5 + 0.4*1.0 = 0.3 + 0.4 = 0.7
    assert decision.confidence == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# 3. LLM 失败 / 解析失败 → fallback
# ---------------------------------------------------------------------------


def test_llm_failure_fallback_wait():
    """AC-5：LLMError → fallback action=wait, degraded=True。"""
    llm = FakeLLMGateway([])  # 队列空 → 抛 LLMError
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.action == "wait"
    assert decision.params == {"duration_ms": 1000}
    assert decision.confidence == 0.0
    assert decision.degraded is True
    assert decision.used_anchor is False
    assert "fallback" in decision.reasoning
    assert "LLM failed" in decision.reasoning


def test_json_parse_failure_fallback():
    """AC-5：LLM 返回非 JSON → fallback。"""
    llm = FakeLLMGateway(["this is not a json"])
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is True
    assert decision.action == "wait"
    assert "parse failed" in decision.reasoning


def test_invalid_action_fallback():
    """AC-6：action 不在白名单（click）→ fallback。"""
    llm = FakeLLMGateway(
        ['{"action":"click","params":{},"confidence":0.5}']
    )
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is True
    assert "invalid action" in decision.reasoning
    assert "click" in decision.reasoning


def test_missing_action_field_fallback():
    """AC-6：缺 action 字段 → 解析失败 → fallback。"""
    llm = FakeLLMGateway(['{"params":{},"confidence":0.5}'])
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is True
    assert "parse failed" in decision.reasoning


def test_missing_required_field_fallback():
    """AC-7：缺 confidence → 走默认值 0.5，不触发 fallback。

    注：action/params 是必填；confidence/reasoning 缺失用默认值。
    """
    llm = FakeLLMGateway(['{"action":"tap","params":{"x":1,"y":2}}'])
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is False
    assert decision.confidence == pytest.approx(0.5)
    assert decision.reasoning == ""


def test_confidence_clamp():
    """AC-7：confidence 超 [0,1] → clamp。"""
    # 上界 1.5 → 1.0
    llm_hi = FakeLLMGateway(
        ['{"action":"wait","params":{"duration_ms":500},"confidence":1.5}']
    )
    engine = VisionDecisionEngine(llm_hi)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.confidence == pytest.approx(1.0)
    assert decision.action == "wait"

    # 下界 -0.3 → 0.0
    llm_lo = FakeLLMGateway(
        ['{"action":"wait","params":{"duration_ms":500},"confidence":-0.3}']
    )
    engine2 = VisionDecisionEngine(llm_lo)
    decision2 = _run(engine2.decide("s.png", task_description="t"))
    assert decision2.confidence == pytest.approx(0.0)


def test_params_validation_missing_coords():
    """AC-6：tap 缺 x/y → fallback。"""
    llm = FakeLLMGateway(
        ['{"action":"tap","params":{"x":100},"confidence":0.8}']  # 缺 y
    )
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is True
    assert "invalid params" in decision.reasoning


def test_swipe_missing_coord_fallback():
    """AC-6 补充：swipe 缺字段 → fallback。"""
    llm = FakeLLMGateway(
        [
            '{"action":"swipe","params":{"x1":1,"y1":2,"x2":3},'
            '"confidence":0.8}'  # 缺 y2
        ]
    )
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.degraded is True
    assert "invalid params" in decision.reasoning


# ---------------------------------------------------------------------------
# 4. AC-2：LLMGateway 路由
# ---------------------------------------------------------------------------


def test_prompt_type_vision_decision():
    """AC-2：prompt_type 固定 vision_decision。"""
    llm = FakeLLMGateway([_valid_tap_json()])
    engine = VisionDecisionEngine(llm)
    _run(engine.decide("s.png", task_description="t"))
    assert llm.calls[0]["prompt_type"] == "vision_decision"


def test_image_url_passthrough():
    """AC-2：image_url 透传给 complete。"""
    llm = FakeLLMGateway([_valid_tap_json()])
    engine = VisionDecisionEngine(llm)
    url = "https://example.com/x.png"
    _run(engine.decide(url, task_description="t"))
    assert llm.calls[0]["image_url"] == url


def test_messages_system_and_user():
    """AC-2：messages 含 system + user 两条。"""
    llm = FakeLLMGateway([_valid_tap_json()])
    engine = VisionDecisionEngine(llm)
    _run(engine.decide("s.png", task_description="点击搜索"))
    msgs = llm.calls[0]["messages"]
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert "点击搜索" in msgs[1]["content"]


# ---------------------------------------------------------------------------
# 5. 完整正常响应 + JSON 代码块解析
# ---------------------------------------------------------------------------


def test_valid_full_response():
    """AC-1 / AC-8：正常完整响应（tap + reasoning + confidence）。"""
    llm = FakeLLMGateway([_valid_tap_json(x=320, y=480, confidence=0.92, reasoning="命中登录按钮")])
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.action == "tap"
    assert decision.params == {"x": 320, "y": 480}
    assert decision.confidence == pytest.approx(0.92)
    assert decision.reasoning == "命中登录按钮"
    assert decision.degraded is False


def test_json_codeblock_extracted():
    """```` ```json ... ``` ```` 包裹也能解析。"""
    wrapped = (
        "```json\n"
        '{"action":"input","params":{"text":"hello"},"confidence":0.7,"reasoning":"r"}\n'
        "```"
    )
    llm = FakeLLMGateway([wrapped])
    engine = VisionDecisionEngine(llm)
    decision = _run(engine.decide("s.png", task_description="t"))
    assert decision.action == "input"
    assert decision.params == {"text": "hello"}
    assert decision.degraded is False


# ---------------------------------------------------------------------------
# 6. 无状态（AC-5）
# ---------------------------------------------------------------------------


def test_no_repeated_state_between_calls():
    """AC-5：连续两次 decide 独立（无累积状态）。"""
    llm = FakeLLMGateway(
        [
            _valid_tap_json(confidence=0.8),
            '{"action":"wait","params":{"duration_ms":200},"confidence":0.3}',
        ]
    )
    engine = VisionDecisionEngine(llm)
    d1 = _run(engine.decide("s1.png", task_description="t1"))
    d2 = _run(engine.decide("s2.png", task_description="t2"))
    assert d1.action == "tap" and d1.confidence == pytest.approx(0.8)
    assert d2.action == "wait" and d2.confidence == pytest.approx(0.3)
    assert llm.call_count == 2


# ---------------------------------------------------------------------------
# 7. 模块级辅助函数直接覆盖（AC-6 / AC-7 白盒）
# ---------------------------------------------------------------------------


def test_parse_llm_response_helpers():
    """白盒：_parse_llm_response 各分支。"""
    assert _parse_llm_response('{"action":"tap","params":{"x":1,"y":2}}') == {
        "action": "tap",
        "params": {"x": 1, "y": 2},
    }
    assert _parse_llm_response("not json") is None
    assert _parse_llm_response("") is None
    assert _parse_llm_response('{"params":{}}') is None  # 缺 action
    assert _parse_llm_response('{"action":"tap"}') is None  # 缺 params
    assert _parse_llm_response('{"action":1,"params":{}}') is None  # action 非 str
    assert _parse_llm_response('{"action":"tap","params":[]}') is None  # params 非 dict


def test_validate_params_helpers():
    """白盒：_validate_params 各 action。"""
    assert _validate_params("tap", {"x": 1, "y": 2}) is True
    assert _validate_params("tap", {"x": 1}) is False
    assert _validate_params("tap", {"x": "1", "y": 2}) is False  # str 非 int
    assert _validate_params("tap", {"x": True, "y": 2}) is False  # bool 排除
    assert _validate_params("swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4}) is True
    assert (
        _validate_params("swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4, "duration_ms": 100})
        is True
    )
    assert _validate_params("input", {"text": "hi"}) is True
    assert _validate_params("input", {"text": 1}) is False
    assert _validate_params("press", {"keycode": "4"}) is True
    assert _validate_params("back", {}) is True
    assert _validate_params("back", {"keycode": "4"}) is True
    assert _validate_params("screenshot", {}) is True
    assert _validate_params("screenshot", {"extra": 1}) is False
    assert _validate_params("wait", {"duration_ms": 500}) is True
    assert _validate_params("wait", {}) is False
    assert _validate_params("unknown", {}) is False


def test_clamp_confidence_helper():
    """白盒：_clamp_confidence。"""
    assert _clamp_confidence(0.5) == 0.5
    assert _clamp_confidence(1.5) == 1.0
    assert _clamp_confidence(-0.2) == 0.0
    assert _clamp_confidence(None) == 0.5
    assert _clamp_confidence("abc") == 0.5
    assert _clamp_confidence("0.9") == pytest.approx(0.9)  # 字符串数值可解析


def test_fallback_decision_helper():
    """白盒：_fallback_decision。"""
    fb = _fallback_decision("test reason")
    assert fb.action == "wait"
    assert fb.params == {"duration_ms": 1000}
    assert fb.confidence == 0.0
    assert fb.reasoning == "fallback: test reason"
    assert fb.used_anchor is False
    assert fb.degraded is True
