"""BF002 集成测试：手动 --run-emulator 才执行。"""
import os

import pytest

from agent.infra.adb_client import ADBClient, ADBConfigError


def _has_emulator():
    try:
        c = ADBClient()
        return len(c.list_devices()) > 0
    except (ADBConfigError, Exception):
        return False


_SKIP_REASON = "no emulator attached or RUN_EMULATOR_TESTS not set"


@pytest.mark.skipif(
    not (_has_emulator() and os.getenv("RUN_EMULATOR_TESTS")),
    reason=_SKIP_REASON,
)
def test_real_reproduce_tap_screenshot():
    """端到端：tap + screenshot。"""
    from agent.reproduce import adb_tools

    c = ADBClient()
    devices = c.list_devices()
    device_id = devices[0]
    adb_tools.tap(c, 500, 500, device_id=device_id)
    png = adb_tools.screenshot(c, device_id=device_id)
    assert png.startswith(b"\x89PNG")


@pytest.mark.skipif(
    not (_has_emulator() and os.getenv("RUN_EMULATOR_TESTS")),
    reason=_SKIP_REASON,
)
def test_real_apk_installer_query_version():
    """查询已安装应用版本。"""
    from agent.reproduce.apk_installer import get_installed_version

    c = ADBClient()
    # 查 settings（通常存在），只验证不抛错
    get_installed_version(c, "com.android.settings")
