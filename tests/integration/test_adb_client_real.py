"""ADBClient 集成测试（R001-INF05，真实 adb，skipif 无设备守护）。

覆盖 AC-8：无设备/无 adb 时全 skip（不 fail），有设备时 smoke 验证。
"""
import pytest

from agent.infra.adb_client import ADBClient, ADBConfigError


def _has_adb_and_device() -> bool:
    """检查是否有可用 adb 二进制 + 至少一个设备。

    adb 不可达 / 无二进制 / 无设备 / adb server 超时 → 返回 False（测试 skip）。
    """
    try:
        c = ADBClient()
        devices = c.list_devices()
        return len(devices) > 0
    except ADBConfigError:
        return False
    except Exception:
        # adb server 不可达等异常 → skip（不 fail）
        return False


_SKIP_REASON = "no adb binary or no device/emulator attached"


@pytest.mark.skipif(not _has_adb_and_device(), reason=_SKIP_REASON)
def test_real_tap():
    """真实 tap（弱断言：命令能跑通即通过，不验证 UI 变化）。"""
    c = ADBClient()
    result = c.tap(500, 500)
    assert result.success
    assert result.returncode == 0


@pytest.mark.skipif(not _has_adb_and_device(), reason=_SKIP_REASON)
def test_real_screenshot():
    """真实 screenshot（弱断言：PNG 魔数）。"""
    c = ADBClient()
    result = c.screenshot()
    assert result.success
    assert result.stdout.startswith(b"\x89PNG")  # PNG 魔数


@pytest.mark.skipif(not _has_adb_and_device(), reason=_SKIP_REASON)
def test_real_list_devices():
    """真实 list_devices（至少返回一个设备）。"""
    c = ADBClient()
    devices = c.list_devices()
    assert len(devices) >= 1
