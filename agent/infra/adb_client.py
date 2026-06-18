"""ADB 客户端（R001-INF05）。

封装 subprocess 调 adb，支持本地直跑与容器网络桥两种部署形态。

依据：
- .dev-flow/R001/contracts/R001-INF05.md
- 技术决策 D3（模拟器+ADB subprocess 底座）/ D10（网络桥部署形态）

设计要点：
1. 纯标准库实现（subprocess + shutil + platform + dataclass），不引三方库。
2. adb 二进制三段式解析：env ADB_BIN → shutil.which → 平台固定路径，找不到 fail-fast。
3. 本地 vs 网络桥自适应：ADB_HOST="" 本地（不加 -H/-P）；非空走网络桥。
4. 六个动作：tap / swipe / input_text / screenshot / install_apk / press_key。
5. 异常分类四类：ADBError（基类）+ Connection / Command / Timeout + ConfigError。
6. 重试：连接错不重试（无意义），命令错/超时重试 retry_max 次（立即重试无 sleep）。
"""
from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.infra.config import Settings, get_settings


# ============================================================================
# 异常类
# ============================================================================
class ADBError(Exception):
    """ADB 调用异常基类（调用方可 `except ADBError` 统一捕获）。"""


class ADBConfigError(ADBError):
    """adb 二进制找不到 / 配置非法（启动期 fail-fast，不等到动作执行）。"""


class ADBConnectionError(ADBError):
    """adb server 不可达 / 设备 offline（不重试，直接上抛）。"""


class ADBCommandError(ADBError):
    """命令执行失败（非零退出码且非连接类，可重试）。"""


class ADBTimeoutError(ADBError):
    """subprocess 超时（可重试）。"""


# ============================================================================
# 数据结构
# ============================================================================
@dataclass(frozen=True)
class ADBResult:
    """adb 动作执行结果。"""

    success: bool
    stdout: bytes
    stderr: bytes
    returncode: int
    duration_ms: int


# ============================================================================
# stderr 关键词：判定为连接错误（不重试）
# 小写匹配，覆盖常见 adb 连接类故障。
# ============================================================================
_CONNECTION_ERR_KEYWORDS = (
    "cannot connect to daemon",
    "device offline",
    "device not found",
    "no devices/emulators",
    "failed to copy",
    "error: closed",
    "cannot connect to",
)


# ============================================================================
# adb 二进制三段式解析
# ============================================================================
def _resolve_adb_bin(settings: Settings) -> str:
    """三段式解析 adb 二进制路径：env ADB_BIN → shutil.which → 平台固定路径。

    找不到抛 ADBConfigError（含已尝试路径列表，便于排查）。
    """
    tried: list[str] = []

    # 1. env ADB_BIN（settings 优先，再兜底直接读 env）
    env_bin = settings.ADB_BIN or os.getenv("ADB_BIN", "")
    if env_bin:
        tried.append(f"ADB_BIN={env_bin!r}")
        if Path(env_bin).exists():
            return env_bin

    # 2. PATH (shutil.which)
    which_bin = shutil.which("adb")
    if which_bin:
        tried.append(f"which={which_bin!r}")
        return which_bin
    tried.append("which=None")

    # 3. 平台固定路径
    sys_name = _platform.system()
    candidates: list[Path] = []
    if sys_name == "Darwin":
        candidates = [
            Path.home() / "Library/Android/sdk/platform-tools/adb",
        ]
    elif sys_name == "Linux":
        candidates = [
            Path("/usr/local/android-sdk/platform-tools/adb"),
            Path("/opt/android-sdk/platform-tools/adb"),
            Path("/usr/bin/adb"),
        ]
    elif sys_name == "Windows":
        candidates = [
            Path(os.getenv("LOCALAPPDATA", "")) / "Android/Sdk/platform-tools/adb.exe",
        ]

    for c in candidates:
        tried.append(str(c))
        if c.exists():
            return str(c)

    raise ADBConfigError(
        "adb binary not found. Tried: " + ", ".join(tried)
        + ". Set ADB_BIN env or install Android platform-tools."
    )


# ============================================================================
# ADBClient
# ============================================================================
class ADBClient:
    """subprocess 调 adb，支持本地直跑和网络桥两种模式。"""

    def __init__(self, settings: Settings | None = None):
        self._settings: Settings = settings or get_settings()
        # 启动期 fail-fast：二进制找不到立刻抛 ADBConfigError
        self._adb_bin: str = _resolve_adb_bin(self._settings)

    # ------------------------------------------------------------------
    # 参数构造
    # ------------------------------------------------------------------
    def _build_base_args(self, device_id: Optional[str] = None) -> list[str]:
        """构造 adb 基础参数：[adb_bin, (-H/-P 网络桥)?, (-s device_id)?]"""
        args: list[str] = [self._adb_bin]
        # 网络桥：ADB_HOST 非空才加
        host = self._settings.ADB_HOST
        if host:  # 空串 = 本地直跑
            args += ["-H", host, "-P", str(self._settings.ADB_PORT)]
        if device_id:
            args += ["-s", device_id]
        return args

    # ------------------------------------------------------------------
    # subprocess 执行核心（含异常分类 + 重试）
    # ------------------------------------------------------------------
    def _run(
        self,
        args: list[str],
        *,
        timeout: Optional[int] = None,
        retry_max: Optional[int] = None,
        input_data: Optional[bytes] = None,
    ) -> ADBResult:
        """执行 subprocess，含异常分类 + 重试。

        - ADBConnectionError 不重试（adb server 不可达重试无意义）
        - ADBCommandError / ADBTimeoutError 重试 retry_max 次（立即重试无 sleep）
        """
        timeout = timeout if timeout is not None else self._settings.ADB_ACTION_TIMEOUT
        retry_max = (
            retry_max if retry_max is not None else self._settings.ADB_RETRY_MAX
        )

        last_exc: ADBError | None = None
        attempts = 0
        while attempts <= retry_max:
            attempts += 1
            start = time.time()
            try:
                proc = subprocess.run(
                    args,
                    capture_output=True,
                    timeout=timeout,
                    input=input_data,
                )
                duration_ms = int((time.time() - start) * 1000)
                stderr_text = proc.stderr.decode("utf-8", errors="replace").lower()

                # 连接错误：不重试，直接上抛
                if any(kw in stderr_text for kw in _CONNECTION_ERR_KEYWORDS):
                    raise ADBConnectionError(
                        f"adb connection failure (args={args}): "
                        f"{proc.stderr.decode('utf-8', errors='replace')}"
                    )

                # 非零退出码：命令错误（可重试）
                if proc.returncode != 0:
                    last_exc = ADBCommandError(
                        f"adb command failed (code={proc.returncode}, args={args}): "
                        f"{proc.stderr.decode('utf-8', errors='replace')}"
                    )
                    if attempts > retry_max:
                        raise last_exc
                    continue

                # 成功
                return ADBResult(
                    success=True,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                    returncode=proc.returncode,
                    duration_ms=duration_ms,
                )

            except subprocess.TimeoutExpired as e:
                last_exc = ADBTimeoutError(
                    f"adb timeout after {timeout}s (args={args})"
                )
                if attempts > retry_max:
                    raise last_exc from e
                continue

            except ADBConnectionError:
                raise  # 不重试，直接上抛

        # 理论不可达（循环内要么 return 要么 raise）
        raise last_exc if last_exc else ADBError("unknown adb failure")

    # ====================================================================
    # 六个动作（AC-3）
    # ====================================================================
    def tap(self, x: int, y: int, *, device_id: Optional[str] = None) -> ADBResult:
        args = self._build_base_args(device_id) + [
            "shell", "input", "tap", str(x), str(y),
        ]
        return self._run(args)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        *,
        device_id: Optional[str] = None,
    ) -> ADBResult:
        args = self._build_base_args(device_id) + [
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms),
        ]
        return self._run(args)

    def input_text(
        self, text: str, *, device_id: Optional[str] = None
    ) -> ADBResult:
        # adb shell input text 不支持空格，用 %s 替换（adb 约定）
        safe = text.replace(" ", "%s")
        args = self._build_base_args(device_id) + [
            "shell", "input", "text", safe,
        ]
        return self._run(args)

    def screenshot(self, *, device_id: Optional[str] = None) -> ADBResult:
        """exec-out screencap -p 直接拿 PNG bytes（stdout）。

        用 exec-out 避免 shell 模式的 \\r\\n 污染。
        返回 ADBResult（stdout 为 PNG 二进制 bytes）。
        """
        args = self._build_base_args(device_id) + [
            "exec-out", "screencap", "-p",
        ]
        return self._run(args)

    def install_apk(
        self, apk_path: str, *, device_id: Optional[str] = None
    ) -> ADBResult:
        args = self._build_base_args(device_id) + [
            "install", "-r", str(apk_path),
        ]
        # install 通常需要更长时间，给 120s
        return self._run(args, timeout=120)

    def press_key(
        self, keycode: str, *, device_id: Optional[str] = None
    ) -> ADBResult:
        args = self._build_base_args(device_id) + [
            "shell", "input", "keyevent", keycode,
        ]
        return self._run(args)

    # ====================================================================
    # 辅助：列出设备
    # ====================================================================
    def list_devices(self) -> list[str]:
        """adb devices，返回 device_id 列表（仅 device 状态，offline 不算）。"""
        args = self._build_base_args() + ["devices"]
        result = self._run(args)
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        devices: list[str] = []
        for line in lines[1:]:  # 跳过 "List of devices attached"
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices


__all__ = [
    "ADBError",
    "ADBConfigError",
    "ADBConnectionError",
    "ADBCommandError",
    "ADBTimeoutError",
    "ADBResult",
    "ADBClient",
    "_resolve_adb_bin",
]
