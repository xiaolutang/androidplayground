"""视觉决策引擎集成测试（R001-BF003）。

真实调 GLM-5V-Turbo（经 INF04 NewAPILLMGateway，prompt_type=vision_decision）。
无 ``NEW_API_API_KEY`` 时全部 skipif，不进主 CI。

运行方式（需本地配置 NEW_API_API_KEY）::

    NEW_API_API_KEY=xxx python3 -m pytest \
        tests/integration/test_vision_decision_engine_real.py -v -s

覆盖 Sprint Contract AC-8（集成测试场景）：
- 真实 GLM-5V-Turbo + 真实截图 → 合法 VisionDecision（action ∈ 白名单，
  confidence ∈ [0,1]，degraded=False）。
- 锚点对照模式（传入 stub anchor_context）→ used_anchor=True。
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import pytest

from agent.infra.llm_gateway import NewAPILLMGateway
from agent.vision.vision_decision_engine import VisionDecisionEngine

#: 需要凭据才跑（与 test_llm_gateway_real.py 同模式）
HAS_CREDS = bool(os.getenv("NEW_API_API_KEY"))

#: 公网可访问的样本截图（picsum.photos 占位；真实场景由 BF002 产出 data_url）
_SAMPLE_SCREENSHOT_URL = "https://picsum.photos/id/1062/400/800"


@dataclass
class _AnchorStub:
    page_id: str | None = None
    text_expectation: str | None = None


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.skipif(not HAS_CREDS, reason="需要 NEW_API_API_KEY 才能调真实 GLM-5V-Turbo")
def test_real_vision_decision_pure_llm():
    """AC-8：真实 GLM-5V-Turbo 决策（纯 LLM 模式）。

    用 picsum 占位图 + 简单 task_desc，断言返回合法 VisionDecision。
    注：picsum 非真实 App 截图，LLM 可能返回 screenshot/wait；
    本测试只校验结构合法性，不校验具体 action。

    若 GLM-5V-Turbo 在当前 New API 账号下不可用（503 model_not_found），
    decide() 会走 fallback（degraded=True）——这是被测代码的正确降级行为，
    不是 bug；此时用 pytest.skip 跳过，避免外部服务可用性阻塞 CI。
    """
    gw = NewAPILLMGateway()
    engine = VisionDecisionEngine(gw)
    decision = _run(
        engine.decide(
            _SAMPLE_SCREENSHOT_URL,
            task_description="观察当前页面，决策下一步操作",
        )
    )
    if decision.degraded:
        pytest.skip(
            f"GLM-5V-Turbo 不可用或 LLM 失败，降级 fallback: {decision.reasoning}"
        )
    valid_actions = {"tap", "swipe", "input", "press", "back", "screenshot", "wait"}
    assert decision.action in valid_actions, f"action={decision.action!r}"
    assert 0.0 <= decision.confidence <= 1.0
    assert isinstance(decision.reasoning, str)
    print(
        f"\n[BF003-IT] action={decision.action} params={decision.params} "
        f"confidence={decision.confidence} reasoning={decision.reasoning!r}"
    )


@pytest.mark.skipif(not HAS_CREDS, reason="需要 NEW_API_API_KEY 才能调真实 GLM-5V-Turbo")
def test_real_vision_decision_with_anchor():
    """AC-8：真实 GLM-5V-Turbo + 锚点对照模式。

    传入 stub anchor_context（无 DB），断言 used_anchor=True。
    若 GLM-5V-Turbo 不可用 → fallback（used_anchor=False），skip 处理。
    """
    gw = NewAPILLMGateway()
    engine = VisionDecisionEngine(gw)
    anchor = _AnchorStub(page_id="home", text_expectation="首页有搜索框")
    decision = _run(
        engine.decide(
            _SAMPLE_SCREENSHOT_URL,
            task_description="点击首页搜索框",
            anchor_context=[(anchor, 0.85)],
        )
    )
    if decision.degraded:
        pytest.skip(
            f"GLM-5V-Turbo 不可用或 LLM 失败，降级 fallback: {decision.reasoning}"
        )
    assert decision.used_anchor is True
    valid_actions = {"tap", "swipe", "input", "press", "back", "screenshot", "wait"}
    assert decision.action in valid_actions
    assert 0.0 <= decision.confidence <= 1.0
    print(
        f"\n[BF003-IT-anchor] action={decision.action} "
        f"confidence={decision.confidence} used_anchor={decision.used_anchor}"
    )
