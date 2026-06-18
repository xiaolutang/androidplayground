"""ADBClient 单元测试（R001-INF05，全 mock subprocess）。

覆盖 AC-1~AC-7：二进制解析 / 网络桥参数 / 六个动作 / device_id / 重试 / 异常分类。
"""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from agent.infra.adb_client import (
    ADBClient,
    ADBCommandError,
    ADBConfigError,
    ADBConnectionError,
    ADBResult,
    ADBTimeoutError,
    _resolve_adb_bin,
)
from agent.infra.config import Settings


# ============================================================================
# AC-1: adb 二进制三段式解析
# ============================================================================
def test_resolve_adb_bin_from_env(tmp_path):
    """ADB_BIN env 指向存在的文件 → 返回该路径。"""
    fake_bin = tmp_path / "fake_adb"
    fake_bin.write_text("#!/bin/sh\n")
    s = Settings(ADB_BIN=str(fake_bin))
    assert _resolve_adb_bin(s) == str(fake_bin)


def test_resolve_adb_bin_from_which():
    """ADB_BIN 空 + which 找到 → 返回 which 结果。"""
    s = Settings(ADB_BIN="")
    with patch("shutil.which", return_value="/usr/local/bin/adb"):
        assert _resolve_adb_bin(s) == "/usr/local/bin/adb"


def test_resolve_adb_bin_not_found_raises():
    """三段都找不到 → 抛 ADBConfigError。

    本机 adb 在平台固定路径存在，需同时 mock 掉平台判定才能测「找不到」分支。
    """
    s = Settings(ADB_BIN="/nonexistent/path/adb")
    with patch("shutil.which", return_value=None), \
         patch("agent.infra.adb_client._platform.system", return_value="UnknownOS"):
        with pytest.raises(ADBConfigError, match="adb binary not found"):
            _resolve_adb_bin(s)


def test_resolve_adb_bin_from_platform_fixed_path(tmp_path):
    """ADB_BIN 空 + which None + 平台固定路径存在 → 返回固定路径。

    AC-1 第三段：Darwin 平台命中 ~/Library/Android/sdk/platform-tools/adb。
    """
    s = Settings(ADB_BIN="")
    fake_adb = tmp_path / "Library" / "Android" / "sdk" / "platform-tools" / "adb"
    fake_adb.parent.mkdir(parents=True)
    fake_adb.write_text("#!/bin/sh\n")
    with patch("shutil.which", return_value=None), \
         patch("agent.infra.adb_client._platform.system", return_value="Darwin"), \
         patch("pathlib.Path.home", return_value=tmp_path):
        result = _resolve_adb_bin(s)
    assert result == str(fake_adb)


def test_adb_bin_cached_in_init():
    """ADBClient.__init__ 时解析并缓存二进制路径。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ) as m:
        c = ADBClient(settings=s)
        assert c._adb_bin == "/fake/adb"
        # 只在 init 时解析一次
        assert m.call_count == 1


# ============================================================================
# AC-2: 本地 vs 网络桥参数构造（D10）
# ============================================================================
def test_local_mode_no_host_args():
    """ADB_HOST="" 本地模式 → 不加 -H/-P。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ):
        c = ADBClient(settings=s)
    args = c._build_base_args()
    assert args == ["/fake/adb"]


def test_bridge_mode_adds_host_port():
    """ADB_HOST 非空 → 加 -H/-P 网络桥参数。"""
    s = Settings(ADB_HOST="host.docker.internal", ADB_PORT=5037)
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ):
        c = ADBClient(settings=s)
    args = c._build_base_args()
    assert args == [
        "/fake/adb", "-H", "host.docker.internal", "-P", "5037",
    ]


# ============================================================================
# AC-4: device_id 路由
# ============================================================================
def test_device_id_routed():
    """device_id 非空 → 加 -s <device_id>。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ):
        c = ADBClient(settings=s)
    args = c._build_base_args(device_id="emulator-5554")
    assert args == ["/fake/adb", "-s", "emulator-5554"]


def test_no_device_id_no_s_flag():
    """device_id=None → 无 -s 段。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ):
        c = ADBClient(settings=s)
    args = c._build_base_args()
    assert "-s" not in args


# ============================================================================
# AC-3: 六个动作 subprocess 调用契约
# ============================================================================
def _make_completed(returncode=0, stdout=b"", stderr=b""):
    """构造 mock subprocess.run 返回值。"""
    r = MagicMock()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def test_tap_calls_correct_args():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.tap(100, 200)
    called_args = m.call_args[0][0]
    assert called_args == [
        "/fake/adb", "shell", "input", "tap", "100", "200",
    ]


def test_tap_with_device_id():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.tap(100, 200, device_id="emulator-5554")
    called_args = m.call_args[0][0]
    assert called_args == [
        "/fake/adb", "-s", "emulator-5554",
        "shell", "input", "tap", "100", "200",
    ]


def test_swipe_calls_correct_args():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.swipe(100, 200, 300, 400, duration_ms=500)
    called_args = m.call_args[0][0]
    assert called_args == [
        "/fake/adb", "shell", "input", "swipe",
        "100", "200", "300", "400", "500",
    ]


def test_swipe_default_duration():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.swipe(100, 200, 300, 400)
    called_args = m.call_args[0][0]
    assert "300" in called_args  # 默认 300ms


def test_input_text_basic():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.input_text("hello")
    called_args = m.call_args[0][0]
    assert called_args == [
        "/fake/adb", "shell", "input", "text", "hello",
    ]


def test_input_text_escapes_space():
    """空格替换为 %s（adb shell input text 约定）。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.input_text("hello world")
    called_args = m.call_args[0][0]
    assert "hello%sworld" in called_args


def test_screenshot_returns_adb_result_with_png():
    """screenshot 返回 ADBResult，stdout 为 PNG 二进制 bytes。"""
    s = Settings(ADB_HOST="")
    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00"
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed(stdout=fake_png)
    ) as m:
        c = ADBClient(settings=s)
        result = c.screenshot()
    assert isinstance(result, ADBResult)
    assert result.success is True
    assert result.stdout == fake_png
    called_args = m.call_args[0][0]
    assert "exec-out" in called_args
    assert "screencap" in called_args
    assert "-p" in called_args


def test_install_apk_uses_long_timeout():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.install_apk("/tmp/app.apk")
    call_kwargs = m.call_args[1]
    assert call_kwargs["timeout"] == 120
    called_args = m.call_args[0][0]
    assert "install" in called_args
    assert "-r" in called_args
    assert "/tmp/app.apk" in called_args


def test_install_apk_not_found_raises_command_error():
    """apk_path 不存在时 adb install 返回非零码 → 抛 ADBCommandError。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=0)
    err_result = _make_completed(
        returncode=1, stderr=b"file does not exist"
    )
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch("subprocess.run", return_value=err_result):
        c = ADBClient(settings=s)
        with pytest.raises(ADBCommandError):
            c.install_apk("/nonexistent/app.apk")


def test_press_key_calls_keyevent():
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ) as m:
        c = ADBClient(settings=s)
        c.press_key("BACK")
    called_args = m.call_args[0][0]
    assert called_args == [
        "/fake/adb", "shell", "input", "keyevent", "BACK",
    ]


def test_action_returns_adb_result():
    """每个动作返回 ADBResult dataclass。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run",
        return_value=_make_completed(stdout=b"ok", stderr=b""),
    ):
        c = ADBClient(settings=s)
        result = c.tap(1, 2)
    assert isinstance(result, ADBResult)
    assert result.success is True
    assert result.returncode == 0
    assert result.stdout == b"ok"
    assert result.duration_ms >= 0


# ============================================================================
# AC-5: 超时与重试
# ============================================================================
def test_retry_on_command_error_then_succeed():
    """非零码重试，第 3 次成功。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=2)
    side_effects = [
        _make_completed(returncode=1, stderr=b"fail"),
        _make_completed(returncode=1, stderr=b"fail"),
        _make_completed(returncode=0, stdout=b"ok"),
    ]
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", side_effect=side_effects
    ) as m:
        c = ADBClient(settings=s)
        result = c.tap(1, 2)
    assert m.call_count == 3
    assert result.success is True


def test_retry_exhausted_raises_command_error():
    """重试耗尽抛 ADBCommandError。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=1)
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run",
        return_value=_make_completed(returncode=1, stderr=b"fail"),
    ) as m:
        c = ADBClient(settings=s)
        with pytest.raises(ADBCommandError):
            c.tap(1, 2)
    # ADB_RETRY_MAX=1 表示总尝试 2 次（首次 + 1 次重试）
    assert m.call_count == 2


def test_timeout_raises_timeout_error():
    """超时抛 ADBTimeoutError。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=0, ADB_ACTION_TIMEOUT=5)
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=5),
    ):
        c = ADBClient(settings=s)
        with pytest.raises(ADBTimeoutError):
            c.tap(1, 2)


def test_timeout_preserves_cause():
    """TimeoutExpired 的 __cause__ 保留。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=0, ADB_ACTION_TIMEOUT=5)
    orig = subprocess.TimeoutExpired(cmd="adb", timeout=5)
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch("subprocess.run", side_effect=orig):
        c = ADBClient(settings=s)
        try:
            c.tap(1, 2)
        except ADBTimeoutError as e:
            assert e.__cause__ is orig
        else:
            pytest.fail("should raise ADBTimeoutError")


def test_timeout_retry_then_succeed():
    """超时可重试，重试后成功。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=1, ADB_ACTION_TIMEOUT=5)
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run",
        side_effect=[
            subprocess.TimeoutExpired(cmd="adb", timeout=5),
            _make_completed(returncode=0, stdout=b"ok"),
        ],
    ) as m:
        c = ADBClient(settings=s)
        result = c.tap(1, 2)
    assert m.call_count == 2
    assert result.success is True


# ============================================================================
# AC-6: 异常分类（连接错不重试）
# ============================================================================
def test_connection_error_no_retry():
    """连接错不重试，只调 1 次。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=3)
    err_result = _make_completed(returncode=1, stderr=b"device offline")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=err_result
    ) as m:
        c = ADBClient(settings=s)
        with pytest.raises(ADBConnectionError):
            c.tap(1, 2)
    assert m.call_count == 1


def test_no_devices_emulators_is_connection_error():
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=3)
    err_result = _make_completed(
        returncode=1, stderr=b"no devices/emulators found"
    )
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch("subprocess.run", return_value=err_result):
        c = ADBClient(settings=s)
        with pytest.raises(ADBConnectionError):
            c.tap(1, 2)


def test_cannot_connect_daemon_is_connection_error():
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=3)
    err_result = _make_completed(
        returncode=1, stderr=b"cannot connect to daemon at tcp:5037"
    )
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch("subprocess.run", return_value=err_result):
        c = ADBClient(settings=s)
        with pytest.raises(ADBConnectionError):
            c.tap(1, 2)


def test_all_exceptions_inherit_adb_error():
    """所有异常继承 ADBError 基类（统一捕获）。"""
    from agent.infra.adb_client import ADBError
    assert issubclass(ADBConfigError, ADBError)
    assert issubclass(ADBConnectionError, ADBError)
    assert issubclass(ADBCommandError, ADBError)
    assert issubclass(ADBTimeoutError, ADBError)


def test_error_message_contains_args_and_stderr():
    """异常 message 含原始 args + stderr（便于排查）。"""
    s = Settings(ADB_HOST="", ADB_RETRY_MAX=0)
    err_result = _make_completed(returncode=1, stderr=b"some failure")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch("subprocess.run", return_value=err_result):
        c = ADBClient(settings=s)
        try:
            c.tap(1, 2)
        except ADBCommandError as e:
            msg = str(e)
            assert "some failure" in msg
            assert "tap" in msg
        else:
            pytest.fail("should raise")


# ============================================================================
# list_devices 辅助方法
# ============================================================================
def test_list_devices_parses_output():
    s = Settings(ADB_HOST="")
    output = (
        b"List of devices attached\n"
        b"emulator-5554\tdevice\n"
        b"emulator-5556\toffline\n"
        b"\n"
    )
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed(stdout=output)
    ):
        c = ADBClient(settings=s)
        devices = c.list_devices()
    assert devices == ["emulator-5554"]  # 只取 device 状态


def test_list_devices_empty():
    s = Settings(ADB_HOST="")
    output = b"List of devices attached\n\n"
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed(stdout=output)
    ):
        c = ADBClient(settings=s)
        devices = c.list_devices()
    assert devices == []


# ============================================================================
# AC-7: BF002 工具层接口对齐（签名一致性 smoke test）
# ============================================================================
def test_action_signatures_callable():
    """6 个动作方法名与签名存在（BF002 对齐 smoke test）。"""
    s = Settings(ADB_HOST="")
    with patch(
        "agent.infra.adb_client._resolve_adb_bin", return_value="/fake/adb"
    ), patch(
        "subprocess.run", return_value=_make_completed()
    ):
        c = ADBClient(settings=s)
        # 签名存在性 + 可调用
        assert callable(c.tap)
        assert callable(c.swipe)
        assert callable(c.input_text)
        assert callable(c.screenshot)
        assert callable(c.install_apk)
        assert callable(c.press_key)
        # smoke 调用（全 mock，不报错即通过）
        c.tap(1, 2)
        c.swipe(1, 2, 3, 4)
        c.input_text("x")
        c.screenshot()
        c.install_apk("/tmp/x.apk")
        c.press_key("BACK")
