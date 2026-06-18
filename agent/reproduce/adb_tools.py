"""ADB 工具层（双模式共用）。

BF002 复现模式 + BB003 探测模式共用此工具层，封装 INF05 ADBClient 为统一函数接口。
异常按 INF05 既有定义上抛（ADBError 家族），调用方自行降级。
"""
from __future__ import annotations

from typing import Optional

from agent.infra.adb_client import ADBClient, ADBResult


def tap(
    client: ADBClient, x: int, y: int, *, device_id: Optional[str] = None
) -> ADBResult:
    """单点点击。"""
    return client.tap(x, y, device_id=device_id)


def swipe(
    client: ADBClient,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = 300,
    *,
    device_id: Optional[str] = None,
) -> ADBResult:
    """滑动。"""
    return client.swipe(
        x1, y1, x2, y2, duration_ms=duration_ms, device_id=device_id
    )


def input_text(
    client: ADBClient, text: str, *, device_id: Optional[str] = None
) -> ADBResult:
    """输入文本（空格转 %s）。"""
    return client.input_text(text, device_id=device_id)


def screenshot(
    client: ADBClient, *, device_id: Optional[str] = None
) -> bytes:
    """截图，返回 PNG bytes。"""
    result = client.screenshot(device_id=device_id)
    return result.stdout


def install_apk(
    client: ADBClient, apk_path: str, *, device_id: Optional[str] = None
) -> ADBResult:
    """安装 APK（-r 覆盖）。"""
    return client.install_apk(apk_path, device_id=device_id)


def press_key(
    client: ADBClient, keycode: str, *, device_id: Optional[str] = None
) -> ADBResult:
    """按键（keyevent）。"""
    return client.press_key(keycode, device_id=device_id)


def list_devices(client: ADBClient) -> list[str]:
    """列出已连接设备。"""
    return client.list_devices()
