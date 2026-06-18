"""视觉决策引擎（R001-BF003）。

依据：
- Sprint Contract R001-BF003（status: agreed，mode: negotiated / Mode 1）
- 技术决策 D2（LLMGateway prompt_type=vision_decision → GLM-5V-Turbo）
- 技术决策 D11（锚点库冷启动为空时降级纯 LLM 判断）

设计要点：
1. **无状态**：每次 ``decide()`` 独立调用，不维护 trajectory / step 计数
   （BB003 agent loop 负责），便于并发与测试。
2. **D2 路由**：固定走 ``prompt_type="vision_decision"``，INF04 自动路由到
   vision 通道（GLM-5V-Turbo），多模态（text + image_url）由 INF04 内部装配。
3. **D11 双模式**：
   - ``anchor_context`` 非空 → prompt 含锚点对照段，confidence = 0.6*LLM + 0.4*top_sim
   - ``anchor_context`` 为 None / ``[]`` → 纯 LLM，confidence = LLM 自评
     （这是 D11 设计内的正常路径，``degraded=False``）。
4. **不抛异常**：LLM 失败 / 解析失败 / 字段非法 → 返回固定 fallback
   ``VisionDecision(action="wait", params={"duration_ms": 1000}, confidence=0.0,
   degraded=True)``；BB003 agent loop 可继续，由 BB003 自行决定是否中止 loop。
5. **不重试**：重试由 INF04 ``NewAPILLMGateway`` 内部负责（解析失败耗尽抛
   ``LLMError``），本模块捕获即走 fallback。
6. **action 白名单与 BF002 adb_tools 对齐**：
   ``{tap, swipe, input, press, back, screenshot, wait}``；非法 action / params
   类型不合规 → fallback。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from agent.anchor.anchor_library import AnchorLibrary
from agent.infra.llm_gateway import LLMError, LLMGateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: ADB tool 动作白名单（与 BF002 adb_tools + reproduce_runner 特殊动作对齐）
_VALID_ACTIONS: frozenset[str] = frozenset(
    {"tap", "swipe", "input", "press", "back", "screenshot", "wait"}
)

#: system prompt（强约束 "只输出 JSON"）
SYSTEM_PROMPT = (
    "你是移动端测试专家，分析当前截图决策下一步操作。"
    "仅输出 JSON："
    '{"action": "<tap|swipe|input|press|back|screenshot|wait>", '
    '"params": {...}, "confidence": <0.0-1.0>, "reasoning": "..."}\n'
    "params 约定：tap={x,y}; swipe={x1,y1,x2,y2,duration_ms}; "
    "input={text}; press={keycode}; back={}; screenshot={}; wait={duration_ms}。"
)

#: 锚点对照 prompt 段最大条数（top_k 截断）
_ANCHOR_TOP_K_DEFAULT = 3

#: fallback action 固定为 wait，params 固定 duration_ms=1000ms
_FALLBACK_ACTION = "wait"
_FALLBACK_PARAMS: dict[str, Any] = {"duration_ms": 1000}
_FALLBACK_CONFIDENCE = 0.0

#: confidence 缺失时的默认值（LLM 未返回 confidence 字段）
_DEFAULT_LLM_CONFIDENCE = 0.5

#: 锚点融合权重（AC-7：0.6*LLM + 0.4*top_similarity）
_LLM_WEIGHT = 0.6
_ANCHOR_WEIGHT = 0.4

#: ```json ... ``` 代码块正则（DOTALL 支持换行）
_JSON_CODEBLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


# ---------------------------------------------------------------------------
# VisionDecision dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VisionDecision:
    """视觉决策引擎输出（BF003）。

    Attributes:
        action: ADB tool 动作，∈ {tap, swipe, input, press, back, screenshot, wait}。
        params: 动作参数，与 BF002 adb_tools 函数签名对齐（见 Contract Q5）。
        confidence: 决策置信度 [0.0, 1.0]。纯 LLM 模式取 LLM 自评；
            锚点对照模式 = 0.6*LLM + 0.4*top_similarity。
        reasoning: LLM 给出的决策理由（fallback 时为降级说明）。
        used_anchor: 是否使用了锚点对照（D11 纯 LLM 时为 False）。
        degraded: 是否为降级决策（LLM 失败 / 解析失败 / 非法 action 时为 True）。
    """

    action: str
    params: dict
    confidence: float
    reasoning: str
    used_anchor: bool
    degraded: bool


# ---------------------------------------------------------------------------
# VisionDecisionEngine
# ---------------------------------------------------------------------------


class VisionDecisionEngine:
    """视觉决策引擎（BF003）。

    输入截图（+ 可选锚点对照）→ 调 LLMGateway → 输出下一个 ADB 决策。
    供 BB003 探测/诱发模式（agent loop）消费；复现模式不调用本模块。

    无状态：每次 ``decide()`` 独立调用，不缓存 / 不累积 trajectory。

    Args:
        llm: LLMGateway（NewAPILLMGateway 生产 / FakeLLMGateway 测试）。
        anchor_lib: 锚点库（可选，仅用于 ``is_empty()`` 判定；
            实际锚点对照数据由调用方经 ``anchor_context`` 传入，避免重复查询）。
        anchor_top_k: 锚点对照段截断条数（默认 3）。
        anchor_similarity_threshold: 锚点相似度阈值（预留扩展，MVP 不裁剪）。
    """

    def __init__(
        self,
        llm: LLMGateway,
        anchor_lib: AnchorLibrary | None = None,
        anchor_top_k: int = _ANCHOR_TOP_K_DEFAULT,
        anchor_similarity_threshold: float = 0.5,
    ) -> None:
        self._llm = llm
        self._anchor_lib = anchor_lib
        self._anchor_top_k = anchor_top_k
        self._anchor_similarity_threshold = anchor_similarity_threshold

    async def decide(
        self,
        screenshot_url: str,
        *,
        task_description: str,
        anchor_context: list[tuple[Any, float]] | None = None,
    ) -> VisionDecision:
        """决策下一个 ADB 操作。

        Args:
            screenshot_url: 当前截图 URL（file_url / data_url，由 BF002 产出）。
            task_description: 当前任务描述（如 "点击登录按钮"）。
            anchor_context: 可选预注入锚点对照结果（``[(Anchor, similarity), ...]``），
                避免本模块重复查询锚点库。非空时走锚点对照双模式（D11）。

        Returns:
            VisionDecision（永不抛异常：LLM 失败 / 解析失败 → fallback）。
        """
        # AC-3 / AC-4：anchor_lib 为 None 或 is_empty() 时纯 LLM（设计内正常路径）
        # 调用方未传 anchor_context 但 anchor_lib 为空 → 不主动查（AC-3 断言）
        if anchor_context and self._anchor_lib is not None:
            try:
                if self._anchor_lib.is_empty():
                    anchor_context = None
            except Exception as exc:  # pragma: no cover - 防御性
                logger.warning(
                    "VisionDecision anchor_lib.is_empty() failed: %s", exc
                )

        used_anchor = bool(anchor_context)
        messages = self._build_messages(task_description, anchor_context)

        # AC-2：调 llm.complete(prompt_type="vision_decision", image_url=...)
        try:
            resp = await self._llm.complete(
                prompt_type="vision_decision",
                messages=messages,
                image_url=screenshot_url,
            )
        except LLMError as exc:
            # AC-5：LLM 失败降级不崩
            logger.warning("VisionDecision LLM failed: %s", exc)
            return _fallback_decision("LLM failed")
        except Exception as exc:  # pragma: no cover - 防御性兜底
            logger.warning("VisionDecision LLM unexpected error: %s", exc)
            return _fallback_decision(f"LLM error: {type(exc).__name__}")

        # AC-5 / AC-6：解析 + 字段校验
        parsed = _parse_llm_response(resp.content)
        if parsed is None:
            return _fallback_decision("parse failed")

        action = parsed["action"]
        params = parsed["params"]

        # AC-6：action 白名单 + params 类型合规
        if action not in _VALID_ACTIONS:
            return _fallback_decision(f"invalid action: {action}")
        if not _validate_params(action, params):
            return _fallback_decision(f"invalid params for action: {action}")

        # AC-7：置信度计算
        llm_conf = _clamp_confidence(
            parsed.get("confidence", _DEFAULT_LLM_CONFIDENCE)
        )
        if used_anchor and anchor_context:
            top_similarity = float(anchor_context[0][1])
            top_similarity = _clamp_confidence(top_similarity)
            confidence = _clamp_confidence(
                _LLM_WEIGHT * llm_conf + _ANCHOR_WEIGHT * top_similarity
            )
        else:
            confidence = llm_conf

        reasoning = str(parsed.get("reasoning", ""))

        return VisionDecision(
            action=action,
            params=dict(params),
            confidence=confidence,
            reasoning=reasoning,
            used_anchor=used_anchor,
            degraded=False,
        )

    # ------------------------------------------------------------------
    # prompt 构造
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        task_description: str,
        anchor_context: list[tuple[Any, float]] | None,
    ) -> list[dict]:
        """构造 messages（system + user）。

        user message 含 task_description；锚点对照模式下追加对照段。
        image_url 由 INF04 内部拼到 user message 的 content list（多模态）。
        """
        user_text = f"任务：{task_description}\n当前截图：[image]"
        if anchor_context:
            user_text += "\n\n锚点参考："
            for anchor, sim in anchor_context[: self._anchor_top_k]:
                # anchor 可能为 Anchor schema 或简单 mock 对象
                page_id = getattr(anchor, "page_id", None)
                text_expectation = getattr(anchor, "text_expectation", None)
                user_text += (
                    f"\n- page_id={page_id}, "
                    f"text_expectation={text_expectation}（正常状态）, "
                    f"similarity={float(sim):.2f}"
                )
            user_text += "\n当前截图：[image]"

        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]


# ---------------------------------------------------------------------------
# 解析 / 校验 / fallback 辅助（模块级，便于单元测试直接覆盖）
# ---------------------------------------------------------------------------


def _parse_llm_response(content: str) -> dict | None:
    """解析 LLM 返回的 JSON。失败返回 None（调用方走 fallback）。

    容错顺序：
    1. 优先提取 ```json ... ``` 代码块（GLM-5V-Turbo 偶发包裹 markdown）。
    2. 失败则尝试裸 JSON（json.loads 整段）。
    3. 字段校验：必填 {action, params}；action ∈ 白名单；params 为 dict。
       （confidence / reasoning 缺失不在此处判 fallback，由 decide() 用默认值。）
    """
    if not isinstance(content, str) or not content.strip():
        return None

    candidate = content.strip()

    # 1. ```json ... ``` 代码块
    m = _JSON_CODEBLOCK_RE.search(candidate)
    if m:
        candidate = m.group(1).strip()

    # 2. 裸 JSON
    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    # 3. 字段校验（action / params 必填）
    if "action" not in data or "params" not in data:
        return None
    if not isinstance(data["action"], str):
        return None
    if not isinstance(data["params"], dict):
        return None
    return data


def _validate_params(action: str, params: dict) -> bool:
    """按 action 校验 params 字段与类型（Contract Q5 映射表）。

    Returns:
        True 合规；False 触发 fallback。
    """
    if not isinstance(params, dict):
        return False

    def _is_int(v: Any) -> bool:
        # bool 是 int 子类，需排除（JSON 里 true/false 不应作为坐标）
        return isinstance(v, int) and not isinstance(v, bool)

    if action == "tap":
        return _is_int(params.get("x")) and _is_int(params.get("y"))
    if action == "swipe":
        required = ("x1", "y1", "x2", "y2")
        if not all(_is_int(params.get(k)) for k in required):
            return False
        # duration_ms 可缺省（默认 300），存在则必须 int
        if "duration_ms" in params and not _is_int(params["duration_ms"]):
            return False
        return True
    if action == "input":
        return isinstance(params.get("text"), str)
    if action == "press":
        return isinstance(params.get("keycode"), str)
    if action == "back":
        # back 可以是 {} 或 {"keycode": "4"}（reproduce_runner 兼容两者）
        if not params:
            return True
        return isinstance(params.get("keycode"), str)
    if action == "screenshot":
        # 空 dict（额外字段容忍但不鼓励；MVP 仅判是否为空）
        return not params
    if action == "wait":
        return _is_int(params.get("duration_ms"))
    return False


def _clamp_confidence(value: Any) -> float:
    """将 confidence clamp 到 [0.0, 1.0]。

    非数值 / None → 默认值 0.5；超出范围 → 截断。
    """
    if value is None:
        return _DEFAULT_LLM_CONFIDENCE
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DEFAULT_LLM_CONFIDENCE
    if v < 0.0:
        return 0.0
    if v > 1.0:
        return 1.0
    return v


def _fallback_decision(reason: str) -> VisionDecision:
    """构造 fallback 决策（固定值，避免 fallback 本身再出错）。

    Args:
        reason: 降级原因（写入 reasoning，便于 BB013 反思 / 监控降级频率）。

    Returns:
        VisionDecision(action="wait", params={"duration_ms": 1000},
        confidence=0.0, reasoning=f"fallback: {reason}",
        used_anchor=False, degraded=True)。
    """
    return VisionDecision(
        action=_FALLBACK_ACTION,
        params=dict(_FALLBACK_PARAMS),
        confidence=_FALLBACK_CONFIDENCE,
        reasoning=f"fallback: {reason}",
        used_anchor=False,
        degraded=True,
    )


__all__ = [
    "VisionDecision",
    "VisionDecisionEngine",
    "SYSTEM_PROMPT",
]
