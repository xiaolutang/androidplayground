"""LLM Gateway 集成测试（R001-INF04）。

覆盖 Sprint Contract AC-5（真实文本链路）/ AC-6（视觉链路 skip）：
- AC-5: 真实调用 glm-5.1，验证返回非空。无凭据时 skipif 跳过。
- AC-6: 视觉链路 skip（GLM-5V-Turbo 不在 New API 可用列表，BF003 再补）。
"""
from __future__ import annotations

import asyncio
import os

import pytest

from agent.infra.llm_gateway import NewAPILLMGateway

# 判断是否有凭据（load_dotenv 已在 config.py import 时加载 agent/.env）
HAS_CREDS = bool(os.getenv("NEW_API_API_KEY"))


@pytest.mark.skipif(not HAS_CREDS, reason="NEW_API_API_KEY not set")
def test_text_complete_glm51():
    """AC-5：真实调用 glm-5.1，验证返回非空。

    用 reflection 通道（text model = glm-5.1），发送简单 prompt，
    断言返回 LLMResponse.content 非空字符串。
    """
    gw = NewAPILLMGateway()

    async def run():
        return await gw.complete(
            "reflection",
            messages=[{"role": "user", "content": "回复'收到'"}],
        )

    resp = asyncio.run(run())
    assert isinstance(resp.content, str)
    assert resp.content.strip(), "content should be non-empty"
    assert resp.model, "model should be non-empty"
    print(f"\n[AC-5] 真实返回内容: {resp.content!r}")
    print(f"[AC-5] model: {resp.model}")


@pytest.mark.skip(reason="GLM-5V-Turbo not available on New API, defer to BF003")
def test_vision_complete_glm5v():
    """AC-6：视觉链路真实调用，暂 skip。

    GLM-5V-Turbo 不在 New API 可用列表，BF003 阶段再补真实验证。
    代码层面已支持 image_url 多模态输入（见单元测试
    test_vision_decision_with_image_url_builds_multimodal）。
    """
    pass
