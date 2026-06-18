"""视觉信号检测器（R001-BF004）。

检测白屏 / Loading 等视觉信号（只做检测，不做决策）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表
- agent/schemas/signal.py（SignalType.VISUAL）
- design D11：锚点库 MVP 数据为空，视觉决策降级纯 LLM；本模块只检测不决策

注意：决策由 BB003 + BF003（VisionDecisionEngine）完成。
本模块输出 ParsedVisualSignal，供 BB003/BB004 消费做路由判断。
"""
from __future__ import annotations

import struct
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent.schemas.signal import SignalSeverity, SignalType

# 白屏判定阈值：平均亮度低于此值视为纯色/白屏（0-255）
# 白屏 = 纯白（亮度接近 255），黑屏 = 纯黑（接近 0）
# MVP 用方差判定：纯色画面方差极低
_BLANK_VARIANCE_THRESHOLD = 50.0  # 像素方差低于此 = 纯色画面

# Loading 检测：连续 N 帧无明显变化
_LOADING_STAGNANT_FRAMES = 3


@dataclass
class ParsedVisualSignal:
    """解析后的视觉信号。"""

    signal_type: str
    severity: str
    pattern: str
    message: str
    visual_type: str  # blank_screen / loading / normal
    metrics: dict[str, float]  # 平均亮度 / 方差等


def _decode_png_dimensions(png_bytes: bytes) -> tuple[int, int] | None:
    """从 PNG bytes 提取宽高（IHDR chunk）。

    PNG 结构：8 字节签名 + IHDR chunk（13 字节数据：宽 4 + 高 4 + ...）。
    """
    if len(png_bytes) < 24:
        return None
    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    # IHDR 在偏移 8 处：长度(4) + "IHDR"(4) + 数据(13)
    width = struct.unpack(">I", png_bytes[16:20])[0]
    height = struct.unpack(">I", png_bytes[20:24])[0]
    return width, height


def _sample_pixels(png_bytes: bytes, max_samples: int = 1000) -> list[tuple[int, int, int]] | None:
    """从 PNG bytes 采样像素（简化：用 zlib 解压 IDAT，采 RGB）。

    MVP 简化实现：如果 PIL 可用则用 PIL，否则 fallback 到粗采样。
    本方法在无 PIL 环境下返回 None（测试用 mock 注入）。
    """
    try:
        from PIL import Image  # type: ignore[import-untyped]
    except ImportError:
        return None

    import io

    try:
        img = Image.open(io.BytesIO(png_bytes))
        img = img.convert("RGB")
        # 缩小到固定尺寸加速采样
        img.thumbnail((32, 32))
        # get_flattened_data() 是 Pillow 12+ 的推荐方法（getdata() 在 14 废弃）
        if hasattr(img, "get_flattened_data"):
            pixels = list(img.get_flattened_data())
        else:
            pixels = list(img.getdata())
        return pixels
    except Exception:
        return None


def _compute_metrics(pixels: list[tuple[int, int, int]]) -> dict[str, float]:
    """计算平均亮度和方差。"""
    if not pixels:
        return {"avg_brightness": 0.0, "variance": 0.0}
    brightness = [(r + g + b) / 3 for r, g, b in pixels]
    avg = sum(brightness) / len(brightness)
    var = sum((b - avg) ** 2 for b in brightness) / len(brightness)
    return {"avg_brightness": avg, "variance": var}


def detect_blank_screen(screenshot: bytes) -> ParsedVisualSignal | None:
    """检测白屏 / 纯色画面。

    判定逻辑：像素方差 < 阈值 → 纯色画面（白屏或黑屏）。
    返回 ParsedVisualSignal 或 None（非纯色）。
    """
    dims = _decode_png_dimensions(screenshot)
    if dims is None:
        # 非 PNG 或无法解码，不报错返回 None
        return None

    pixels = _sample_pixels(screenshot)
    if pixels is None:
        # 无 PIL 或解码失败，无法判定
        return None

    metrics = _compute_metrics(pixels)
    if metrics["variance"] >= _BLANK_VARIANCE_THRESHOLD:
        return None  # 方差大 = 有内容

    # 纯色画面：判断白屏还是黑屏
    avg = metrics["avg_brightness"]
    if avg > 200:
        visual_type = "blank_screen"
        msg = f"White/blank screen detected (avg_brightness={avg:.1f}, variance={metrics['variance']:.1f})"
    elif avg < 30:
        visual_type = "blank_screen"
        msg = f"Black screen detected (avg_brightness={avg:.1f}, variance={metrics['variance']:.1f})"
    else:
        # 纯灰/纯色（非极端白/黑），仍算异常纯色
        visual_type = "blank_screen"
        msg = f"Solid color screen detected (avg_brightness={avg:.1f}, variance={metrics['variance']:.1f})"

    return ParsedVisualSignal(
        signal_type=SignalType.VISUAL.value,
        severity=SignalSeverity.ERROR.value,
        pattern="low_variance_solid",
        message=msg,
        visual_type=visual_type,
        metrics=metrics,
    )


def detect_loading(
    screenshot: bytes,
    history: list[bytes] | None,
    *,
    stagnant_frames: int = _LOADING_STAGNANT_FRAMES,
) -> ParsedVisualSignal | None:
    """检测 Loading 卡住（连续 N 帧无明显变化）。

    MVP 简化实现：
    - history 为空或帧数不足 → None（无法判断）
    - 对比当前帧与历史帧的相似度（用像素方差差异代理）
    - 连续 stagnant_frames 帧方差差异 < 阈值 → loading 卡住

    注意：真正的 loading 检测需配合锚点（BF007）和文字识别（BF003），
    本方法只做帧间静态变化检测（placeholder 级 MVP）。
    """
    if not history or len(history) < stagnant_frames - 1:
        return None

    pixels = _sample_pixels(screenshot)
    if pixels is None:
        return None

    current_metrics = _compute_metrics(pixels)
    current_var = current_metrics["variance"]

    # 与历史帧对比：所有帧的方差接近 = 画面无变化
    stagnant_count = 0
    for hist_frame in history[-(stagnant_frames - 1) :]:
        hist_pixels = _sample_pixels(hist_frame)
        if hist_pixels is None:
            continue
        hist_metrics = _compute_metrics(hist_pixels)
        # 方差差异 < 10 = 极相似
        if abs(hist_metrics["variance"] - current_var) < 10.0:
            stagnant_count += 1

    if stagnant_count < stagnant_frames - 1:
        return None

    return ParsedVisualSignal(
        signal_type=SignalType.VISUAL.value,
        severity=SignalSeverity.WARN.value,
        pattern="stagnant_frames",
        message=f"Loading/stagnant screen detected ({stagnant_count + 1} frames without change)",
        visual_type="loading",
        metrics=current_metrics,
    )


def to_signal_dict(parsed: ParsedVisualSignal) -> dict[str, Any]:
    """转成 Signal 行字典。"""
    now = datetime.now(timezone.utc)
    return {
        "id": f"visual_{uuid.uuid4().hex[:12]}",
        "signal_type": parsed.signal_type,
        "severity": parsed.severity,
        "pattern": {
            "matched": parsed.pattern,
            "visual_type": parsed.visual_type,
        },
        "source_config": {
            "metrics": parsed.metrics,
            "message": parsed.message,
            "captured_at": now.isoformat(),
        },
    }


__all__ = [
    "ParsedVisualSignal",
    "detect_blank_screen",
    "detect_loading",
    "to_signal_dict",
]
