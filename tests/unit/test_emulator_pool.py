from unittest.mock import MagicMock, patch

import pytest

from agent.infra.config import Settings
from agent.reproduce.emulator_pool import (
    EmulatorHandle,
    EmulatorPool,
    EmulatorStartError,
    _resolve_emulator_bin,
)


def test_resolve_emulator_bin_from_env(tmp_path):
    fake_bin = tmp_path / "emulator"
    fake_bin.write_text("#!/bin/sh\n")
    s = Settings(EMULATOR_BIN=str(fake_bin))
    assert _resolve_emulator_bin(s) == str(fake_bin)


def test_resolve_emulator_bin_not_found_raises():
    s = Settings(EMULATOR_BIN="/nonexistent/emulator")
    with patch("shutil.which", return_value=None):
        with patch(
            "agent.reproduce.emulator_pool.Path.exists", return_value=False
        ):
            with patch("os.getenv", return_value=""):
                with pytest.raises(EmulatorStartError):
                    _resolve_emulator_bin(s)


def test_start_boot_timeout_raises():
    """模拟启动超时：进程不退出，boot_completed 永远 False。"""
    s = Settings(EMULATOR_BIN="/fake/emu", EMULATOR_BOOT_TIMEOUT=1)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = None  # 进程一直跑
    fake_proc.stderr = MagicMock()
    fake_proc.stderr.read.return_value = b""

    fake_adb = MagicMock()
    fake_adb.list_devices.return_value = [
        "emulator-5554"
    ]  # 设备在但 boot 没完

    with patch("subprocess.Popen", return_value=fake_proc):
        pool = EmulatorPool(settings=s, adb_client=fake_adb)
        pool._is_boot_completed = lambda device_id: False
        with pytest.raises(EmulatorStartError, match="boot timeout"):
            pool.start("test_avd")


def test_start_process_exit_raises():
    """模拟进程立即退出。"""
    s = Settings(EMULATOR_BIN="/fake/emu", EMULATOR_BOOT_TIMEOUT=10)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1  # 已退出
    fake_proc.returncode = 1
    fake_proc.stderr = MagicMock()
    fake_proc.stderr.read.return_value = b"AVD not found"

    fake_adb = MagicMock()
    fake_adb.list_devices.return_value = []

    with patch("subprocess.Popen", return_value=fake_proc):
        pool = EmulatorPool(settings=s, adb_client=fake_adb)
        with pytest.raises(EmulatorStartError, match="process exited"):
            pool.start("test_avd")


def test_start_already_running_raises():
    s = Settings(EMULATOR_BIN="/fake/emu")
    pool = EmulatorPool(settings=s, adb_client=MagicMock())
    pool._active = EmulatorHandle(
        avd_name="x",
        device_id="emulator-5554",
        process=MagicMock(),
        started_at=0,
    )
    with pytest.raises(EmulatorStartError, match="already running"):
        pool.start("other_avd")


def test_start_failure_creates_facility_gap():
    """启动失败时调 GapStore.create（best-effort）。"""
    s = Settings(EMULATOR_BIN="/fake/emu", EMULATOR_BOOT_TIMEOUT=1)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1
    fake_proc.returncode = 1
    fake_proc.stderr = MagicMock()
    fake_proc.stderr.read.return_value = b"error"

    fake_adb = MagicMock()
    fake_adb.list_devices.return_value = []

    fake_gap_store = MagicMock()

    with patch("subprocess.Popen", return_value=fake_proc):
        pool = EmulatorPool(
            settings=s, adb_client=fake_adb, gap_store=fake_gap_store
        )
        with pytest.raises(EmulatorStartError):
            pool.start("test_avd")

    fake_gap_store.create.assert_called_once()


def test_gap_store_failure_does_not_mask_error():
    """GapStore.create 失败时不应掩盖 emulator 异常。"""
    s = Settings(EMULATOR_BIN="/fake/emu", EMULATOR_BOOT_TIMEOUT=1)
    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1
    fake_proc.returncode = 1
    fake_proc.stderr = MagicMock()
    fake_proc.stderr.read.return_value = b"error"

    fake_adb = MagicMock()
    fake_adb.list_devices.return_value = []

    fake_gap_store = MagicMock()
    fake_gap_store.create.side_effect = RuntimeError("DB down")

    with patch("subprocess.Popen", return_value=fake_proc):
        pool = EmulatorPool(
            settings=s, adb_client=fake_adb, gap_store=fake_gap_store
        )
        with pytest.raises(EmulatorStartError, match="process exited"):
            pool.start("test_avd")

    # GapStore 失败了但仍然被调用
    fake_gap_store.create.assert_called_once()


def test_stop_terminates_process():
    s = Settings(EMULATOR_BIN="/fake/emu")
    fake_proc = MagicMock()
    fake_proc.wait.return_value = 0
    handle = EmulatorHandle(
        avd_name="x",
        device_id="emulator-5554",
        process=fake_proc,
        started_at=0,
    )
    pool = EmulatorPool(settings=s, adb_client=MagicMock())
    pool._active = handle
    pool.stop()
    fake_proc.terminate.assert_called_once()
    assert pool._active is None


def test_allocate_returns_active():
    s = Settings(EMULATOR_BIN="/fake/emu")
    handle = EmulatorHandle(
        avd_name="x",
        device_id="emulator-5554",
        process=MagicMock(),
        started_at=0,
    )
    pool = EmulatorPool(settings=s, adb_client=MagicMock())
    pool._active = handle
    assert pool.allocate() is handle
