"""进程信号监听器（R001-BF004）。

检测进程崩溃 / ANR（Application Not Responding）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表
- agent/schemas/signal.py（SignalType.PROCESS）

ANR trace 文件位置：/data/anr/traces.txt（Android 标准）
进程崩溃：退出码非 0 或 SIGABRT/SIGSEGV
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent.schemas.signal import SignalSeverity, SignalType


@dataclass
class ParsedProcessSignal:
    """解析后的进程信号。"""

    signal_type: str
    severity: str
    pattern: str
    message: str
    process_name: str | None
    pid: int | None
    reason: str | None


def detect_crash(process_state: dict[str, Any] | None) -> ParsedProcessSignal | None:
    """检测进程崩溃（退出码非 0）。

    process_state 结构：
        {
            "process_name": "com.example.app",
            "pid": 1234,
            "exit_code": 1,            # 非 0 = 崩溃
            "signal": "SIGSEGV",       # 可选，Unix 信号名
            "stderr_tail": "...",      # 可选，stderr 尾部
        }

    输入为 None 或空 dict → 返回 None（无状态可判定）。
    """
    if not process_state:
        return None
    exit_code = process_state.get("exit_code", 0)
    if exit_code == 0:
        return None

    process_name = process_state.get("process_name")
    pid = process_state.get("pid")
    sig = process_state.get("signal")

    # reason 组装
    parts: list[str] = [f"exit_code={exit_code}"]
    if sig:
        parts.append(f"signal={sig}")
    stderr_tail = process_state.get("stderr_tail", "")
    if stderr_tail:
        parts.append(f"stderr={stderr_tail[:200]}")
    reason = ", ".join(parts)

    return ParsedProcessSignal(
        signal_type=SignalType.PROCESS.value,
        severity=SignalSeverity.CRASH.value,
        pattern="non_zero_exit" + (f" | {sig}" if sig else ""),
        message=f"Process {process_name or 'unknown'} crashed: {reason}",
        process_name=process_name,
        pid=pid,
        reason=reason,
    )


def detect_anr(anr_trace: str | None) -> ParsedProcessSignal | None:
    """检测 ANR（从 ANR trace 文本）。

    无 trace 或非 ANR 返回 None。
    ANR trace 特征：含 "ANR in" 或 "Not Responding" 关键字。
    """
    if not anr_trace:
        return None
    if "ANR" not in anr_trace.upper() and "Not Responding" not in anr_trace:
        return None
    return parse_anr(anr_trace)


def parse_anr(anr_trace: str) -> ParsedProcessSignal:
    """解析 ANR trace，提取进程名 + reason。

    典型 ANR trace 格式：
        ----- pid 1234 at 2024-01-01 12:00:00 -----
        Cmd line: com.example.app
        ...
        ANR in com.example.app (com.example.app/.MainActivity)
        PID: 1234
        Reason: Input dispatching timed out (com.example.app/...
    """
    # 提取进程名
    process_name: str | None = None
    m = re.search(r"ANR in\s+([\w.]+)", anr_trace)
    if m:
        process_name = m.group(1)
    else:
        m = re.search(r"Cmd line:\s+([\w.]+)", anr_trace)
        if m:
            process_name = m.group(1)

    # 提取 PID
    pid: int | None = None
    m = re.search(r"PID:\s*(\d+)", anr_trace)
    if m:
        pid = int(m.group(1))
    else:
        m = re.search(r"pid\s+(\d+)", anr_trace)
        if m:
            pid = int(m.group(1))

    # 提取 Reason
    reason: str | None = None
    m = re.search(r"Reason:\s*(.+)", anr_trace)
    if m:
        reason = m.group(1).strip()
    else:
        # 推断 ANR 类型
        if "Input dispatching timed out" in anr_trace:
            reason = "Input dispatching timed out"
        elif "BroadcastQueue" in anr_trace:
            reason = "Broadcast timeout"
        elif "executing service" in anr_trace.lower():
            reason = "Service timeout"

    return ParsedProcessSignal(
        signal_type=SignalType.PROCESS.value,
        severity=SignalSeverity.CRASH.value,
        pattern="ANR",
        message=f"ANR in {process_name or 'unknown'}"
        + (f" (PID {pid})" if pid else "")
        + (f": {reason}" if reason else ""),
        process_name=process_name,
        pid=pid,
        reason=reason,
    )


def to_signal_dict(parsed: ParsedProcessSignal) -> dict[str, Any]:
    """转成 Signal 行字典。"""
    now = datetime.now(timezone.utc)
    return {
        "id": f"process_{uuid.uuid4().hex[:12]}",
        "signal_type": parsed.signal_type,
        "severity": parsed.severity,
        "pattern": {
            "matched": parsed.pattern,
            "process_name": parsed.process_name,
            "pid": parsed.pid,
        },
        "source_config": {
            "reason": parsed.reason,
            "message": parsed.message[:500],
            "captured_at": now.isoformat(),
        },
    }


__all__ = [
    "ParsedProcessSignal",
    "detect_crash",
    "detect_anr",
    "parse_anr",
    "to_signal_dict",
]
