"""LLM Gateway 单元测试（R001-INF04）。

覆盖 Sprint Contract AC-1/3/4/6/7：
- AC-1 路由分发（4 个 prompt_type + 非法值 fail-fast）
- AC-3 重试机制（解析失败重试 / 耗尽抛错 / FIX_RETRY_MAX=0 不重试）
- AC-4 超时/超限降级（TimeoutError / RateLimitError → LLMError）
- AC-6 多模态消息构造（vision_decision + image_url）
- AC-7 FakeLLMGateway 4 scenarios

策略：
- 不引入 pytest-asyncio，用 asyncio.run() 同步包装异步测试。
- NewAPILLMGateway 的重试逻辑用 monkeypatch 替换 _client.chat.completions.create
  为 AsyncMock，通过 side_effect 控制（抛异常或返回 mock response）。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import openai
import pytest

from agent.infra.config import Settings
from agent.infra.llm_gateway import (
    FakeLLMGateway,
    LLMError,
    LLMGateway,
    LLMResponse,
    NewAPILLMGateway,
    _PROMPT_TYPE_TO_CHANNEL,
)


# ---------------------------------------------------------------------------
# 辅助：构造 mock completion response
# ---------------------------------------------------------------------------
def _make_mock_completion(content: str, model: str = "glm-5.1") -> MagicMock:
    """构造一个模拟的 openai ChatCompletion 响应对象。"""
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.usage = MagicMock(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    return resp


# ===========================================================================
# AC-1：路由分发测试
# ===========================================================================
def test_route_vision_decision_uses_vision_model():
    """vision_decision → vision model（GLM-5V-Turbo）。"""
    settings = Settings(LLM_VISION_MODEL="GLM-5V-Turbo", LLM_TEXT_MODEL="glm-5.1")
    gw = NewAPILLMGateway(settings=settings)
    mock_create = AsyncMock(
        return_value=_make_mock_completion('{"action": "click"}', "GLM-5V-Turbo")
    )
    gw._client.chat.completions.create = mock_create

    async def run():
        return await gw.complete(
            "vision_decision",
            messages=[{"role": "user", "content": "看图"}],
        )

    resp = asyncio.run(run())
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["model"] == "GLM-5V-Turbo"
    assert isinstance(resp, LLMResponse)


def test_route_symptom_classify_uses_text_model():
    """symptom_classify → text model（glm-5.1）。"""
    settings = Settings(LLM_VISION_MODEL="GLM-5V-Turbo", LLM_TEXT_MODEL="glm-5.1")
    gw = NewAPILLMGateway(settings=settings)
    mock_create = AsyncMock(
        return_value=_make_mock_completion('{"category": "crash"}', "glm-5.1")
    )
    gw._client.chat.completions.create = mock_create

    async def run():
        return await gw.complete(
            "symptom_classify",
            messages=[{"role": "user", "content": "崩溃了"}],
        )

    asyncio.run(run())
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["model"] == "glm-5.1"


def test_route_fix_patch_uses_text_model():
    """fix_patch → text model（glm-5.1）。"""
    settings = Settings(LLM_TEXT_MODEL="glm-5.1")
    gw = NewAPILLMGateway(settings=settings)
    mock_create = AsyncMock(
        return_value=_make_mock_completion('{"patch": "..."}', "glm-5.1")
    )
    gw._client.chat.completions.create = mock_create

    async def run():
        return await gw.complete(
            "fix_patch",
            messages=[{"role": "user", "content": "修复"}],
        )

    asyncio.run(run())
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["model"] == "glm-5.1"


def test_route_reflection_uses_text_model():
    """reflection → text model（glm-5.1）。"""
    settings = Settings(LLM_TEXT_MODEL="glm-5.1")
    gw = NewAPILLMGateway(settings=settings)
    mock_create = AsyncMock(
        return_value=_make_mock_completion('{"reflect": "ok"}', "glm-5.1")
    )
    gw._client.chat.completions.create = mock_create

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "反思"}],
        )

    asyncio.run(run())
    call_kwargs = mock_create.call_args
    assert call_kwargs.kwargs["model"] == "glm-5.1"


def test_invalid_prompt_type_raises_valueerror():
    """非法 prompt_type → ValueError（fail-fast）。"""
    settings = Settings()
    gw = NewAPILLMGateway(settings=settings)

    async def run():
        return await gw.complete(
            "unknown_type",
            messages=[{"role": "user", "content": "test"}],
        )

    with pytest.raises(ValueError, match="unsupported prompt_type"):
        asyncio.run(run())


# ===========================================================================
# AC-3：重试机制测试
# ===========================================================================
def test_retry_on_parse_failure_then_succeed():
    """解析失败重试后成功：empty content × 2，第 3 次合法。"""
    settings = Settings(FIX_RETRY_MAX=3)
    gw = NewAPILLMGateway(settings=settings)
    # 前 2 次返回空 content（解析失败），第 3 次返回合法内容
    responses = [
        _make_mock_completion("", "glm-5.1"),
        _make_mock_completion("   ", "glm-5.1"),
        _make_mock_completion("valid response", "glm-5.1"),
    ]
    gw._client.chat.completions.create = AsyncMock(side_effect=responses)

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "test"}],
        )

    resp = asyncio.run(run())
    assert resp.content == "valid response"
    assert gw._client.chat.completions.create.call_count == 3


def test_retry_exhausted_raises_llmerror():
    """重试耗尽抛 LLMError：持续返回 empty content。"""
    settings = Settings(FIX_RETRY_MAX=3)
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("", "glm-5.1")
    )

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "test"}],
        )

    with pytest.raises(LLMError, match="retry exhausted"):
        asyncio.run(run())
    # FIX_RETRY_MAX=3 → 总尝试 4 次（attempts 1,2,3,4）
    assert gw._client.chat.completions.create.call_count == 4


def test_fix_retry_max_zero_no_retry():
    """FIX_RETRY_MAX=0 时不重试，首次失败即抛 LLMError。"""
    settings = Settings(FIX_RETRY_MAX=0)
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("", "glm-5.1")
    )

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "test"}],
        )

    with pytest.raises(LLMError):
        asyncio.run(run())
    # 只调用 1 次（不重试）
    assert gw._client.chat.completions.create.call_count == 1


# ===========================================================================
# AC-4：超时/超限降级测试
# ===========================================================================
def test_timeout_raises_llmerror():
    """超时异常 → LLMError，不重试。"""
    settings = Settings(FIX_RETRY_MAX=3)
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        side_effect=openai.APITimeoutError(request=MagicMock())
    )

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "test"}],
        )

    with pytest.raises(LLMError, match="LLM API failure"):
        asyncio.run(run())
    assert gw._client.chat.completions.create.call_count == 1


def test_ratelimit_raises_llmerror():
    """限流异常 → LLMError，不重试。"""
    settings = Settings(FIX_RETRY_MAX=3)
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        side_effect=openai.RateLimitError(
            message="rate limited",
            response=MagicMock(),
            body=None,
        )
    )

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "test"}],
        )

    with pytest.raises(LLMError, match="LLM API failure"):
        asyncio.run(run())
    assert gw._client.chat.completions.create.call_count == 1


# ===========================================================================
# AC-6：多模态消息构造测试
# ===========================================================================
def test_vision_decision_with_image_url_builds_multimodal():
    """vision_decision + image_url → messages 含 image_url content。"""
    settings = Settings(LLM_VISION_MODEL="GLM-5V-Turbo")
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion('{"action":"click"}', "GLM-5V-Turbo")
    )

    image_url = "data:image/png;base64,iVBOR..."
    messages = [
        {"role": "system", "content": "你是视觉分析助手"},
        {"role": "user", "content": "分析这张截图"},
    ]

    async def run():
        return await gw.complete(
            "vision_decision",
            messages=messages,
            image_url=image_url,
        )

    asyncio.run(run())
    call_kwargs = gw._client.chat.completions.create.call_args
    sent_messages = call_kwargs.kwargs["messages"]
    # 最后一条 user message 的 content 应为 list（多模态）
    user_msg = sent_messages[-1]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)
    assert any(item.get("type") == "text" for item in content)
    assert any(item.get("type") == "image_url" for item in content)
    # image_url 的 url 字段
    img_item = [i for i in content if i.get("type") == "image_url"][0]
    assert img_item["image_url"]["url"] == image_url


def test_no_image_url_keeps_plain_text():
    """无 image_url 时 messages 保持原始纯文本结构。"""
    settings = Settings()
    gw = NewAPILLMGateway(settings=settings)
    gw._client.chat.completions.create = AsyncMock(
        return_value=_make_mock_completion("ok", "glm-5.1")
    )
    orig = [{"role": "user", "content": "纯文本"}]

    async def run():
        return await gw.complete("reflection", messages=orig)

    asyncio.run(run())
    sent = gw._client.chat.completions.create.call_args.kwargs["messages"]
    assert sent[0]["content"] == "纯文本"
    assert isinstance(sent[0]["content"], str)


# ===========================================================================
# AC-7：FakeLLMGateway 4 scenarios
# ===========================================================================
def test_fake_vision_decision_returns_valid_json():
    """Scenario 1: FakeLLM 返回合法视觉决策 JSON。"""
    valid_json = json.dumps({"action": "click", "target": "button"})
    fake = FakeLLMGateway(responses_queue=[valid_json])

    async def run():
        return await fake.complete(
            "vision_decision",
            messages=[{"role": "user", "content": "看图"}],
            image_url="data:image/png;base64,abc",
        )

    resp = asyncio.run(run())
    parsed = json.loads(resp.content)
    assert parsed["action"] == "click"
    assert fake.call_count == 1
    assert fake.calls[0]["prompt_type"] == "vision_decision"


def test_fake_symptom_classify_returns_valid_json():
    """Scenario 2: FakeLLM 返回合法分类 JSON。"""
    valid_json = json.dumps({"category": "crash", "confidence": 0.95})
    fake = FakeLLMGateway(responses_queue=[valid_json])

    async def run():
        return await fake.complete(
            "symptom_classify",
            messages=[{"role": "user", "content": "App 崩溃"}],
        )

    resp = asyncio.run(run())
    parsed = json.loads(resp.content)
    assert parsed["category"] == "crash"
    assert fake.call_count == 1


def test_fake_fix_patch_retry_success():
    """Scenario 3: FakeLLM 前 2 次返回非法内容，第 3 次合法。

    注：FakeLLMGateway 本身不重试，这里模拟上层调用方的重试行为——
    连续调用 FakeLLMGateway 3 次（队列控制返回值），第 3 次成功。
    """
    invalid1 = "INVALID PATCH"
    invalid2 = ""
    valid = json.dumps({"patch": "diff --git a/foo b/bar", "valid": True})
    fake = FakeLLMGateway(responses_queue=[invalid1, invalid2, valid])

    results = []

    async def run():
        for _ in range(3):
            resp = await fake.complete(
                "fix_patch",
                messages=[{"role": "user", "content": "修复 bug"}],
            )
            results.append(resp.content)

    asyncio.run(run())
    assert fake.call_count == 3
    assert results[0] == invalid1
    assert results[1] == invalid2
    parsed = json.loads(results[2])
    assert parsed["valid"] is True


def test_fake_reflection_persistent_invalid_raises():
    """Scenario 4: FakeLLM 队列耗尽 → LLMError（模拟持续非法至重试耗尽）。"""
    # 只放 2 条非法响应，第 3 次调用时队列已空 → LLMError
    fake = FakeLLMGateway(responses_queue=["INVALID", "ALSO_INVALID"])

    async def run():
        await fake.complete(
            "reflection",
            messages=[{"role": "user", "content": "反思"}],
        )
        await fake.complete(
            "reflection",
            messages=[{"role": "user", "content": "反思"}],
        )
        # 第 3 次：队列空
        await fake.complete(
            "reflection",
            messages=[{"role": "user", "content": "反思"}],
        )

    with pytest.raises(LLMError, match="queue empty"):
        asyncio.run(run())
    assert fake.call_count == 3


# ===========================================================================
# 额外：Protocol 兼容性验证
# ===========================================================================
def test_fake_llm_gateway_satisfies_protocol():
    """FakeLLMGateway 满足 LLMGateway Protocol。"""
    fake = FakeLLMGateway(responses_queue=["test"])
    assert isinstance(fake, LLMGateway)
    assert hasattr(fake, "complete")
