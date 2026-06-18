"""模拟器池（单实例 MVP）。

subprocess.Popen 启动 emulator，轮询 sys.boot_completed，
失败抛 EmulatorStartError -> 上层转设施缺口。
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agent.infra.adb_client import ADBClient
from agent.infra.config import Settings, get_settings

logger = logging.getLogger(__name__)


class EmulatorStartError(Exception):
    """模拟器启动失败。"""


@dataclass
class EmulatorHandle:
    """已启动模拟器的句柄。"""

    avd_name: str
    device_id: str  # emulator-XXXX
    process: subprocess.Popen
    started_at: float


def _resolve_emulator_bin(settings: Settings) -> str:
    """解析 emulator 二进制路径：env EMULATOR_BIN -> PATH -> 平台固定路径。"""
    env_bin = settings.EMULATOR_BIN or os.getenv("EMULATOR_BIN", "")
    if env_bin and Path(env_bin).exists():
        return env_bin
    which = shutil.which("emulator")
    if which:
        return which
    # macOS 固定路径
    candidate = Path.home() / "Library" / "Android" / "sdk" / "emulator" / "emulator"
    if candidate.exists():
        return str(candidate)
    raise EmulatorStartError(
        "emulator binary not found. Set EMULATOR_BIN env or install Android SDK emulator."
    )


class EmulatorPool:
    """单实例模拟器池（MVP）。

    多实例并发留作 future work；当前仅维护单个 active handle。
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        adb_client: ADBClient | None = None,
        gap_store=None,
    ):
        self._settings = settings or get_settings()
        self._adb = adb_client or ADBClient(settings=self._settings)
        self._gap_store = gap_store
        self._active: Optional[EmulatorHandle] = None
        self._emulator_bin = _resolve_emulator_bin(self._settings)

    def start(
        self, avd_name: str, *, extra_args: list[str] | None = None
    ) -> EmulatorHandle:
        """启动 avd，等待 boot_completed。

        超时或启动失败抛 EmulatorStartError（同时尝试创建设施缺口）。
        """
        if self._active is not None:
            raise EmulatorStartError(
                f"emulator already running: {self._active.avd_name}"
            )
        cmd = [
            self._emulator_bin,
            "-avd",
            avd_name,
            "-no-window",
            "-no-audio",
            "-no-snapshot",
            "-no-boot-anim",
        ]
        if extra_args:
            cmd += extra_args
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as e:
            self._create_facility_gap(f"failed to spawn emulator: {e}")
            raise EmulatorStartError(f"failed to spawn emulator: {e}") from e

        boot_timeout = self._settings.EMULATOR_BOOT_TIMEOUT
        deadline = time.time() + boot_timeout
        device_id = None
        while time.time() < deadline:
            # 检查进程是否已退出（启动失败）
            if proc.poll() is not None:
                stderr = b""
                try:
                    stderr = proc.stderr.read() if proc.stderr else b""
                except Exception:
                    pass
                reason = (
                    f"emulator process exited (code={proc.returncode}); "
                    f"stderr={stderr.decode('utf-8', errors='replace')[:500]}"
                )
                self._create_facility_gap(reason)
                raise EmulatorStartError(reason)

            # 找到 device_id
            devices = self._adb.list_devices()
            emulator_devices = [
                d for d in devices if d.startswith("emulator-")
            ]
            if emulator_devices:
                device_id = emulator_devices[0]
                if self._is_boot_completed(device_id):
                    handle = EmulatorHandle(
                        avd_name=avd_name,
                        device_id=device_id,
                        process=proc,
                        started_at=time.time(),
                    )
                    self._active = handle
                    return handle
            time.sleep(2)

        # 超时：清理进程
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        reason = f"emulator boot timeout after {boot_timeout}s for avd={avd_name}"
        self._create_facility_gap(reason)
        raise EmulatorStartError(reason)

    def _is_boot_completed(self, device_id: str) -> bool:
        """检查 sys.boot_completed。"""
        try:
            r = subprocess.run(
                [
                    "adb",
                    "-s",
                    device_id,
                    "shell",
                    "getprop",
                    "sys.boot_completed",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.returncode == 0 and r.stdout.strip() == "1"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _create_facility_gap(self, reason: str) -> None:
        """best-effort 创建设施缺口（失败仅 warning，不掩盖 emulator 异常）。"""
        if self._gap_store is None:
            return
        try:
            self._gap_store.create(
                {
                    "id": str(uuid4()),
                    "gap_type": "facility",
                    "description": f"emulator start failed: {reason}",
                    "linked_bug_ids": [],
                }
            )
        except Exception as gap_exc:
            logger.warning("GapStore.create failed: %s", gap_exc)

    def allocate(self) -> Optional[EmulatorHandle]:
        """分配一个已启动的模拟器（MVP 单实例：返回 self._active）。"""
        return self._active

    def release(self, handle: EmulatorHandle) -> None:
        """归还句柄（MVP：no-op，不关机）。"""
        pass

    def stop(self, handle: EmulatorHandle | None = None) -> None:
        """关闭模拟器。"""
        target = handle or self._active
        if target is None:
            return
        try:
            target.process.terminate()
            target.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            target.process.kill()
        finally:
            if self._active is target:
                self._active = None
