import base64
from unittest.mock import MagicMock

import pytest

from agent.infra.adb_client import ADBResult
from agent.reproduce.screenshot_collector import (
    ScreenshotError,
    capture,
    collect,
    to_data_url,
    to_file_url,
)


def _client_with_png(png=b"\x89PNG"):
    c = MagicMock()
    c.screenshot.return_value = ADBResult(True, png, b"", 0, 5)
    return c


def test_capture_returns_png():
    c = _client_with_png(b"\x89PNG\x00\x00")
    png = capture(c)
    assert png == b"\x89PNG\x00\x00"


def test_capture_empty_raises():
    c = MagicMock()
    c.screenshot.return_value = ADBResult(True, b"", b"", 0, 5)
    with pytest.raises(ScreenshotError):
        capture(c)


def test_to_data_url():
    url = to_data_url(b"abc")
    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded == b"abc"


def test_to_file_url(tmp_path):
    out = tmp_path / "sub" / "shot.png"
    url = to_file_url(b"abc", out)
    assert url.startswith("file://")
    assert out.read_bytes() == b"abc"


def test_collect_data_url(monkeypatch):
    monkeypatch.setenv("SCREENSHOT_FORMAT", "data_url")
    c = _client_with_png()
    url = collect(c, output_format="data_url")
    assert url.startswith("data:image/png;base64,")


def test_collect_file_url_requires_path():
    c = _client_with_png()
    with pytest.raises(ScreenshotError):
        collect(c, output_format="file_url")  # 缺 file_path


def test_collect_unsupported_format():
    c = _client_with_png()
    with pytest.raises(ScreenshotError):
        collect(c, output_format="bogus")


def test_collect_file_url_with_path(tmp_path):
    out = tmp_path / "shot.png"
    c = _client_with_png()
    url = collect(c, output_format="file_url", file_path=str(out))
    assert url.startswith("file://")
    assert out.read_bytes() == b"\x89PNG"
