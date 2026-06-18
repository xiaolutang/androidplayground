"""adb_tools 单测（mock ADBClient）。"""
from unittest.mock import MagicMock

from agent.infra.adb_client import ADBResult
from agent.reproduce import adb_tools


def _mock_client():
    return MagicMock(
        spec=[
            "tap",
            "swipe",
            "input_text",
            "screenshot",
            "install_apk",
            "press_key",
            "list_devices",
        ]
    )


def test_tap_delegates():
    c = _mock_client()
    c.tap.return_value = ADBResult(True, b"", b"", 0, 5)
    r = adb_tools.tap(c, 100, 200)
    c.tap.assert_called_once_with(100, 200, device_id=None)
    assert r.success


def test_swipe_delegates():
    c = _mock_client()
    c.swipe.return_value = ADBResult(True, b"", b"", 0, 5)
    adb_tools.swipe(c, 1, 2, 3, 4, duration_ms=500)
    c.swipe.assert_called_once_with(
        1, 2, 3, 4, duration_ms=500, device_id=None
    )


def test_swipe_default_duration():
    c = _mock_client()
    c.swipe.return_value = ADBResult(True, b"", b"", 0, 5)
    adb_tools.swipe(c, 1, 2, 3, 4)
    c.swipe.assert_called_once_with(
        1, 2, 3, 4, duration_ms=300, device_id=None
    )


def test_input_text_delegates():
    c = _mock_client()
    c.input_text.return_value = ADBResult(True, b"", b"", 0, 5)
    adb_tools.input_text(c, "hello world")
    c.input_text.assert_called_once_with("hello world", device_id=None)


def test_screenshot_returns_png_bytes():
    c = _mock_client()
    fake_png = b"\x89PNG"
    c.screenshot.return_value = ADBResult(True, fake_png, b"", 0, 5)
    png = adb_tools.screenshot(c)
    assert png == fake_png


def test_install_delegates():
    c = _mock_client()
    c.install_apk.return_value = ADBResult(True, b"Success", b"", 0, 5)
    adb_tools.install_apk(c, "/tmp/app.apk")
    c.install_apk.assert_called_once_with("/tmp/app.apk", device_id=None)


def test_press_key_delegates():
    c = _mock_client()
    c.press_key.return_value = ADBResult(True, b"", b"", 0, 5)
    adb_tools.press_key(c, "BACK")
    c.press_key.assert_called_once_with("BACK", device_id=None)


def test_device_id_passed_through():
    c = _mock_client()
    c.tap.return_value = ADBResult(True, b"", b"", 0, 5)
    adb_tools.tap(c, 1, 2, device_id="emulator-5554")
    c.tap.assert_called_once_with(1, 2, device_id="emulator-5554")


def test_list_devices_delegates():
    c = _mock_client()
    c.list_devices.return_value = ["emulator-5554"]
    devices = adb_tools.list_devices(c)
    assert devices == ["emulator-5554"]
