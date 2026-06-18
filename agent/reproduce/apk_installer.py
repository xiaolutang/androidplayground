"""APK 安装/启动/卸载/版本查询。"""
from __future__ import annotations

import subprocess
from typing import Optional

from agent.infra.adb_client import ADBClient, ADBResult


def install(
    client: ADBClient, apk_path: str, *, device_id: Optional[str] = None
) -> ADBResult:
    """安装 APK（-r 覆盖）。"""
    return client.install_apk(apk_path, device_id=device_id)


def launch(
    client: ADBClient,
    package: str,
    activity: str,
    *,
    device_id: Optional[str] = None,
) -> ADBResult:
    """启动应用的指定 Activity（adb shell am start -n <package>/<activity>）。"""
    args = ["adb"]
    if device_id:
        args += ["-s", device_id]
    args += ["shell", "am", "start", "-n", f"{package}/{activity}"]
    proc = subprocess.run(args, capture_output=True, timeout=10)
    return ADBResult(
        success=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        duration_ms=0,
    )


def uninstall(
    client: ADBClient, package: str, *, device_id: Optional[str] = None
) -> ADBResult:
    """卸载应用（adb uninstall <package>）。"""
    args = ["adb"]
    if device_id:
        args += ["-s", device_id]
    args += ["uninstall", package]
    proc = subprocess.run(args, capture_output=True, timeout=30)
    return ADBResult(
        success=proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
        duration_ms=0,
    )


def get_installed_version(
    client: ADBClient, package: str, *, device_id: Optional[str] = None
) -> Optional[str]:
    """获取已安装应用的 versionName，未安装返回 None。

    调 adb shell dumpsys package <package>，解析 versionName= 行。
    """
    args = ["adb"]
    if device_id:
        args += ["-s", device_id]
    args += ["shell", "dumpsys", "package", package]
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=10
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("versionName="):
            return line.split("=", 1)[1].strip()
    return None
