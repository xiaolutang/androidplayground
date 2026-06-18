"""LLM Gateway（R001-INF04）。

依据：
- Sprint Contract R001-INF04（status: agreed）
- 技术决策 D2（LLM provider：OpenAI 兼容协议 + New API 网关 + prompt_type 路由）

设计要点：
1. 业务层 prompt_type（vision_decision / symptom_classify / fix_patch / reflection）
   先映射到通道（vision / text），再调 config.get_llm_model(channel) 路由到具体 model。
2. NewAPILLMGateway 封装 openai.AsyncOpenAI，走 chat.completions 非流式调用。
3. 重试机制：仅针对内容解析失败（empty content / OpenAIError 非 timeout/ratelimit/status），
   重试上限 = settings.FIX_RETRY_MAX；耗尽抛 LLMError。
4. 超时/超限/网络异常不重试（直接抛 LLMError，避免放大故障）。
5. 多模态：vision_decision + image_url 时构造 content list（text + image_url）。
6. FakeLLMGateway 作为 Protocol 的独立 mock 实现，供上层业务代码注入。
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol, runtime_checkable

import openai

from agent.infra.config import Settings, get_llm_model, get_settings

# 业务 prompt_type → 通道映射（D2）
_PROMPT_TYPE_TO_CHANNEL: dict[str, str] = {
    "vision_decision": "vision",
    "symptom_classify": "text",
    "fix_patch": "text",
    "reflection": "text",
}


class LLMError(Exception):
    """LLM 调用异常（超时/超限/解析失败耗尽），供调用方降级。"""


@dataclass(frozen=True)
class LLMResponse:
    """LLM 返回数据结构。

    Attributes:
        content: 文本内容。
        model: 实际使用的 model 名。
        raw: 原始 completion 对象（透传，供调试）。
        usage: token usage 字典（透传，不计数）。
    """

    content: str
    model: str
    raw: object | None = None
    usage: dict | None = None


@runtime_checkable
class LLMGateway(Protocol):
    """LLM 网关 Protocol（供 NewAPILLMGateway / FakeLLMGateway 实现）。"""

    async def complete(
        self,
        prompt_type: Literal[
            "vision_decision", "symptom_classify", "fix_patch", "reflection"
        ],
        *,
        messages: list[dict],
        image_url: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...


class FakeLLMGateway:
    """测试用 mock，按队列返回预设响应。

    不走重试逻辑——上层如需重试应自行实现或使用 NewAPILLMGateway。
    队列耗尽时抛 LLMError，便于测试验证重试耗尽场景（通过持续返回非法内容）。
    """

    def __init__(self, responses_queue: list[str] | None = None) -> None:
        self._queue = list(responses_queue or [])
        self._call_count = 0
        self.calls: list[dict] = []

    async def complete(
        self,
        prompt_type: str,
        *,
        messages: list[dict],
        image_url: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self.calls.append(
            {
                "prompt_type": prompt_type,
                "messages": messages,
                "image_url": image_url,
            }
        )
        self._call_count += 1
        if not self._queue:
            raise LLMError("FakeLLMGateway queue empty")
        content = self._queue.pop(0)
        return LLMResponse(content=content, model="fake-model", raw=None)

    @property
    def call_count(self) -> int:
        return self._call_count


def _route_model(prompt_type: str, settings: Settings) -> str:
    """业务 prompt_type → model 路由（经 channel 中转）。"""
    channel = _PROMPT_TYPE_TO_CHANNEL.get(prompt_type)
    if channel is None:
        raise ValueError(f"unsupported prompt_type={prompt_type!r}")
    return get_llm_model(channel, settings)


class NewAPILLMGateway:
    """基于 openai.AsyncOpenAI 的 New API 网关实现。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        api_key = os.getenv("NEW_API_API_KEY", "")
        self._client = openai.AsyncOpenAI(
            base_url=self._settings.LLM_BASE_URL,
            api_key=api_key,
        )

    async def complete(
        self,
        prompt_type: str,
        *,
        messages: list[dict],
        image_url: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        # 路由
        model = _route_model(prompt_type, self._settings)
        # 构造 messages（多模态）
        req_messages = self._build_messages(messages, image_url, prompt_type)
        # 重试：仅解析失败（empty content / OpenAIError 非 timeout/ratelimit/status）重试
        # 语义：attempts 从 1 开始；FIX_RETRY_MAX=0 时首次失败即抛（不重试）
        retry_max = self._settings.FIX_RETRY_MAX
        attempts = 0
        last_err: LLMError | None = None
        while attempts <= retry_max:
            attempts += 1
            try:
                resp = await self._client.chat.completions.create(
                    model=model,
                    messages=req_messages,
                    **kwargs,
                )
                content = resp.choices[0].message.content or ""
                if not content.strip():
                    # 解析失败：empty content
                    last_err = LLMError("empty content from LLM")
                    if attempts > retry_max:
                        break
                    continue
                usage: dict | None = None
                u = getattr(resp, "usage", None)
                if u is not None:
                    usage = {
                        "prompt_tokens": u.prompt_tokens,
                        "completion_tokens": u.completion_tokens,
                        "total_tokens": u.total_tokens,
                    }
                return LLMResponse(
                    content=content, model=model, raw=resp, usage=usage
                )
            except (
                asyncio.TimeoutError,
                openai.APITimeoutError,
                openai.RateLimitError,
                openai.APIStatusError,
            ) as e:
                # 超时/超限/HTTP 状态错误：不重试，直接抛
                raise LLMError(
                    f"LLM API failure: {type(e).__name__}: {e}"
                ) from e
            except openai.OpenAIError as e:
                # 其他 OpenAI 错误：解析失败，重试
                last_err = LLMError(f"LLM call failed: {type(e).__name__}: {e}")
                if attempts > retry_max:
                    break
                continue
        raise LLMError(
            f"LLM retry exhausted after {retry_max} (attempts={attempts}): {last_err}"
        )

    def _build_messages(
        self,
        messages: list[dict],
        image_url: str | None,
        prompt_type: str,
    ) -> list[dict]:
        """构造 messages；vision_decision + image_url 时升级为多模态 content。"""
        if image_url and prompt_type == "vision_decision":
            new_msgs = [dict(m) for m in messages]
            for m in reversed(new_msgs):
                if m.get("role") == "user":
                    orig = m.get("content", "")
                    m["content"] = [
                        {
                            "type": "text",
                            "text": orig if isinstance(orig, str) else str(orig),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_url},
                        },
                    ]
                    break
            return new_msgs
        return messages


__all__ = [
    "LLMError",
    "LLMResponse",
    "LLMGateway",
    "FakeLLMGateway",
    "NewAPILLMGateway",
]
# _PROMPT_TYPE_TO_CHANNEL 为内部实现细节（下划线前缀），不导出；
# 测试如需引用直接 import 即可，无需出现在 __all__。
