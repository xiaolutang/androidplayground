"""截图采集（喂 BF003 vision engine）。"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from agent.infra.adb_client import ADBClient
from agent.infra.config import get_settings


class ScreenshotError(Exception):
    """截图采集失败（空 bytes）。"""


def capture(
    client: ADBClient, *, device_id: Optional[str] = None
) -> bytes:
    """采集截图，返回 PNG bytes。"""
    png = client.screenshot(device_id=device_id).stdout
    if not png:
        raise ScreenshotError("empty screenshot bytes")
    return png


def to_data_url(png_bytes: bytes) -> str:
    """PNG bytes -> base64 data URL（喂 LLM image_url）。"""
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def to_file_url(png_bytes: bytes, path: str | Path) -> str:
    """PNG bytes -> 落盘 file:// URL。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png_bytes)
    return f"file://{path.resolve()}"


def collect(
    client: ADBClient,
    *,
    device_id: Optional[str] = None,
    output_format: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    """采集 + 转换：根据 output_format 返回 data_url 或 file_url。

    output_format=None 时用 settings.SCREENSHOT_FORMAT。
    """
    settings = get_settings()
    fmt = output_format or settings.SCREENSHOT_FORMAT
    png = capture(client, device_id=device_id)
    if fmt == "data_url":
        return to_data_url(png)
    elif fmt == "file_url":
        if not file_path:
            raise ScreenshotError("file_url format requires file_path")
        return to_file_url(png, file_path)
    else:
        raise ScreenshotError(f"unsupported screenshot format: {fmt}")
