"""BF002 模拟器集成测试（R001-INT03）。

手动集成测试，全部标记 ``@pytest.mark.emulator``。
需 ``--run-emulator`` 显式触发，默认 skip，不进主 CI。

覆盖场景：
1. 真实模拟器启停（EmulatorPool start/stop）
2. ADB 动作（list_devices / shell / screenshot）
3. 截图验证（PNG bytes 非空 + magic number）
4. 超时重试（ADB timeout -> ADBTimeoutError）
5. 故障注入表 BF002 场景：
   - 模拟器不可用（无 emulator binary -> EmulatorStartError）
   - ADB offline（device_id 指向不存在的 emulator -> ADBConnectionError）
   - ADB 超时（install_apk 超时 -> ADBTimeoutError）
"""
from __future__ import annotations

import os
import subprocess
from unittest.mock import patch

import pytest

from agent.infra.adb_client import (
    ADBClient,
    ADBConnectionError,
    ADBTimeoutError,
)
from agent.reproduce.emulator_pool import EmulatorStartError, EmulatorPool

# ============================================================================
# Fixtures
# ============================================================================
pytestmark = pytest.mark.emulator


@pytest.fixture
def adb_client() -> ADBClient:
    """创建 ADBClient 实例（依赖 adb binary 在 PATH 或 ADB_BIN env）。"""
    return ADBClient()


@pytest.fixture
def emulator_pool() -> EmulatorPool:
    """创建 EmulatorPool 实例。"""
    return EmulatorPool()


@pytest.fixture
def test_avd() -> str:
    """测试用 AVD 名称（通过环境变量 TEST_AVD 覆盖）。"""
    return os.getenv("TEST_AVD", "Pixel_7_API_34")


# ============================================================================
# 1. 真实模拟器启停
# ============================================================================
class TestEmulatorLifecycle:
    """模拟器启停生命周期测试。"""

    def test_emulator_start_and_stop(
        self, emulator_pool: EmulatorPool, test_avd: str
    ) -> None:
        """启动模拟器 -> 等待 boot_completed -> 停止。

        验证：
        - start() 返回 EmulatorHandle
        - handle.device_id 以 "emulator-" 开头
        - stop() 后 _active 为 None
        """
        handle = emulator_pool.start(test_avd)
        assert handle is not None
        assert handle.device_id.startswith("emulator-")
        assert handle.avd_name == test_avd

        emulator_pool.stop(handle)
        assert emulator_pool._active is None

    def test_emulator_double_start_raises(
        self, emulator_pool: EmulatorPool, test_avd: str
    ) -> None:
        """重复 start 应抛 EmulatorStartError。"""
        handle = emulator_pool.start(test_avd)
        try:
            with pytest.raises(EmulatorStartError, match="already running"):
                emulator_pool.start(test_avd)
        finally:
            emulator_pool.stop(handle)


# ============================================================================
# 2. ADB 动作
# ============================================================================
class TestADBActions:
    """ADB 动作集成测试（需真实模拟器在线）。"""

    def test_list_devices(self, adb_client: ADBClient) -> None:
        """list_devices 至少返回一个 emulator-XXXX 设备。"""
        devices = adb_client.list_devices()
        assert len(devices) > 0
        assert any(d.startswith("emulator-") for d in devices)

    def test_shell_command(
        self, adb_client: ADBClient
    ) -> None:
        """adb shell getprop ro.build.version.sdk 返回非空。"""
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )
        # 直接用 subprocess 验证 shell 动作
        result = subprocess.run(
            ["adb", "-s", emulator_id, "shell", "getprop",
             "ro.build.version.sdk"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert result.stdout.strip().isdigit()

    def test_screenshot_returns_png(
        self, adb_client: ADBClient
    ) -> None:
        """screenshot() 返回非空 PNG bytes。"""
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )
        result = adb_client.screenshot(device_id=emulator_id)
        assert result.success
        assert len(result.stdout) > 0
        # PNG magic number: \x89PNG\r\n\x1a\n
        assert result.stdout[:8] == b"\x89PNG\r\n\x1a\n"

    def test_install_nonexistent_apk_fails(
        self, adb_client: ADBClient
    ) -> None:
        """安装不存在的 APK 应失败（返回非零或抛异常）。"""
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )
        from agent.infra.adb_client import ADBCommandError

        with pytest.raises(ADBCommandError):
            adb_client.install_apk(
                "/nonexistent/app.apk", device_id=emulator_id
            )


# ============================================================================
# 3. 截图验证
# ============================================================================
class TestScreenshotValidation:
    """截图采集与格式验证。"""

    def test_screenshot_valid_png(
        self, adb_client: ADBClient
    ) -> None:
        """截图为有效 PNG（magic number + IHDR chunk）。"""
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )
        png = adb_client.screenshot(device_id=emulator_id).stdout

        # PNG magic number
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # IHDR chunk: bytes 12-16 = "IHDR"
        assert png[12:16] == b"IHDR"
        # 至少 1KB（非空截图）
        assert len(png) > 1024

    def test_screenshot_data_url_conversion(
        self, adb_client: ADBClient
    ) -> None:
        """通过 screenshot_collector 转 data_url 格式。"""
        from agent.reproduce.screenshot_collector import to_data_url

        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )
        png = adb_client.screenshot(device_id=emulator_id).stdout
        data_url = to_data_url(png)

        assert data_url.startswith("data:image/png;base64,")
        # base64 部分可解码
        import base64

        b64_part = data_url.split(",", 1)[1]
        decoded = base64.b64decode(b64_part)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


# ============================================================================
# 4. 超时重试
# ============================================================================
class TestTimeoutRetry:
    """ADB 超时重试机制测试。"""

    def test_adb_timeout_raises_and_retries(
        self, adb_client: ADBClient
    ) -> None:
        """超时配置为极小值时，ADB 动作应触发 ADBTimeoutError。

        使用 mock 验证重试次数：retry_max=2 表示共 3 次尝试。
        """
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )

        call_count = 0
        original_run = adb_client._run

        def mock_run(args, **kwargs):
            nonlocal call_count
            call_count += 1
            # 强制 timeout=0 让 subprocess 立刻超时
            return original_run(args, timeout=0, retry_max=2)

        with patch.object(adb_client, "_run", side_effect=mock_run):
            with pytest.raises(ADBTimeoutError):
                adb_client.tap(
                    100, 100, device_id=emulator_id
                )

        # retry_max=2 -> 3 次尝试
        assert call_count == 3

    def test_connection_error_no_retry(
        self, adb_client: ADBClient
    ) -> None:
        """ADBConnectionError 不重试（device offline 场景）。

        指向不存在的 device_id，应立即抛 ADBConnectionError。
        """
        with pytest.raises(ADBConnectionError):
            adb_client.tap(
                100, 100, device_id="emulator-99999"
            )


# ============================================================================
# 5. 故障注入表 BF002 场景
# ============================================================================
class TestFaultInjectionBF002:
    """BF002 故障注入场景测试。

    验证系统在以下故障下的行为：
    - 模拟器不可用（emulator binary 缺失）
    - ADB offline（设备不存在）
    - 超时（动作执行超时）
    """

    def test_emulator_binary_not_found(self) -> None:
        """emulator binary 缺失时抛 EmulatorStartError。"""
        with patch.dict(os.environ, {"EMULATOR_BIN": "/nonexistent/emulator"}):
            with pytest.raises(EmulatorStartError, match="emulator binary not found"):
                EmulatorPool()

    def test_adb_offline_device(self, adb_client: ADBClient) -> None:
        """offline device 的 ADB 动作应抛 ADBConnectionError。"""
        with pytest.raises(ADBConnectionError):
            adb_client.screenshot(device_id="emulator-99999")

    def test_adb_install_timeout(self, adb_client: ADBClient) -> None:
        """install_apk 超时应抛 ADBTimeoutError。

        使用 mock 让 subprocess.run 超时，验证重试逻辑。
        """
        devices = adb_client.list_devices()
        emulator_id = next(
            d for d in devices if d.startswith("emulator-")
        )

        call_count = 0

        def fake_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise subprocess.TimeoutExpired(
                cmd=args[0] if args else "adb",
                timeout=kwargs.get("timeout", 1),
            )

        with patch("subprocess.run", side_effect=fake_run):
            with pytest.raises(ADBTimeoutError):
                adb_client.install_apk(
                    "/tmp/fake.apk", device_id=emulator_id
                )

        # 默认 retry_max 来自 settings
        assert call_count >= 1

    def test_boot_check_with_no_emulator(self) -> None:
        """无模拟器在线时，boot_completed 检查返回 False。"""
        pool = EmulatorPool()
        # 指向不存在的 device_id
        assert pool._is_boot_completed("emulator-99999") is False
