"""Logcat 信号监听器（R001-BF004）。

解析 Android logcat 输出，识别崩溃 / 错误 / 警告信号。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表
- agent/schemas/signal.py（SignalType.LOGCAT / SignalSeverity）

识别模式（design 信号路由 S3 → BB003/BB004）：
- FATAL EXCEPTION → severity=crash（进程级崩溃，路由 BB003 执行流）
- AndroidRuntime: / java.xxx.Exception → severity=error
- W/ tag（Warning）→ severity=warn
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent.schemas.signal import SignalSeverity, SignalType

# ----------------------------------------------------------------------------
# 正则模式
# logcat 行格式：<priority>/<tag>( <pid>): <message>
# 示例：E/AndroidRuntime( 1234): FATAL EXCEPTION: main
# ----------------------------------------------------------------------------
_FATAL_RE = re.compile(r"FATAL EXCEPTION", re.IGNORECASE)
_ANDROID_RUNTIME_RE = re.compile(r"AndroidRuntime(\s*\()?\s*\d*\)?\s*:", re.IGNORECASE)
_JAVA_EXCEPTION_RE = re.compile(r"(?:^|\s)(java\.[\w.]*Exception|kotlin\.[\w.]*Exception)", re.IGNORECASE)
# logcat priority 前缀：E/Tag( pid): 或 W/Tag( pid):
_PRIORITY_RE = re.compile(r"^([EFWI])/\S+")


@dataclass
class ParsedLogcatSignal:
    """解析后的 logcat 信号（不直接持久化，由调用方转 Signal 行）。"""

    signal_type: str
    severity: str
    pattern: str
    message: str
    stack_top: str | None  # stacktrace 顶帧摘要
    source_tag: str | None  # logcat tag


def _extract_stack_top(lines: list[str], start_idx: int) -> str | None:
    """从 FATAL EXCEPTION 行之后提取 stacktrace 顶帧。

    典型格式：
        E/AndroidRuntime( 1234): FATAL EXCEPTION: main
        E/AndroidRuntime( 1234): Process: com.example.app, PID: 1234
        E/AndroidRuntime( 1234): java.lang.NullPointerException
        E/AndroidRuntime( 1234):     at com.example.app.MainActivity.onCreate(MainActivity.java:42)
    顶帧 = 第一个 "    at ..." 行。
    """
    for line in lines[start_idx + 1 : start_idx + 15]:
        m = re.search(r"at\s+([\w.$]+\([\w.$]+:\d+\))", line)
        if m:
            return m.group(1)
    return None


def _grade_severity(line: str, has_fatal: bool) -> str:
    """严重度分级（design：crash / error / warn / info）。"""
    if has_fatal:
        return SignalSeverity.CRASH.value
    m = _PRIORITY_RE.match(line)
    if m:
        p = m.group(1)
        if p == "E":
            return SignalSeverity.ERROR.value
        if p == "W":
            return SignalSeverity.WARN.value
    # 无前缀但匹配 java.Exception
    if _JAVA_EXCEPTION_RE.search(line):
        return SignalSeverity.ERROR.value
    return SignalSeverity.INFO.value


def _extract_tag(line: str) -> str | None:
    """提取 logcat tag（E/<tag>( pid): 格式）。"""
    m = re.match(r"^[EFWI]/(\S+)", line)
    if m:
        return m.group(1).rstrip(":")
    return None


class LogcatListener:
    """logcat 信号解析器。

    用法：
        listener = LogcatListener()
        signals = listener.parse(raw_logcat_text)
    """

    def parse(self, raw_logcat: str) -> list[ParsedLogcatSignal]:
        """解析 logcat 原始文本，返回识别出的信号列表。

        识别规则：
        - FATAL EXCEPTION → crash 级，提取 stack top
        - AndroidRuntime: → error 级（崩溃报告 tag）
        - java./kotlin. Exception → error 级
        - W/ 前缀 → warn 级（仅在匹配到关键字时）
        """
        signals: list[ParsedLogcatSignal] = []
        lines = raw_logcat.splitlines()

        for idx, line in enumerate(lines):
            has_fatal = bool(_FATAL_RE.search(line))
            has_android_runtime = bool(_ANDROID_RUNTIME_RE.search(line))
            has_java_exc = bool(_JAVA_EXCEPTION_RE.search(line))

            # 至少匹配一个模式才算信号
            if not (has_fatal or has_android_runtime or has_java_exc):
                continue

            severity = _grade_severity(line, has_fatal)
            tag = _extract_tag(line)

            # 模式标记（哪个正则命中）
            matched: list[str] = []
            if has_fatal:
                matched.append("FATAL EXCEPTION")
            if has_android_runtime:
                matched.append("AndroidRuntime")
            if has_java_exc:
                m = _JAVA_EXCEPTION_RE.search(line)
                if m:
                    matched.append(m.group(1))
            pattern = " | ".join(matched)

            # stacktrace 顶帧（仅 FATAL 场景有完整 stack）
            stack_top = _extract_stack_top(lines, idx) if has_fatal else None

            signals.append(
                ParsedLogcatSignal(
                    signal_type=SignalType.LOGCAT.value,
                    severity=severity,
                    pattern=pattern,
                    message=line.strip(),
                    stack_top=stack_top,
                    source_tag=tag,
                )
            )

        return signals

    def to_signal_dicts(self, parsed: list[ParsedLogcatSignal]) -> list[dict[str, Any]]:
        """转成 Signal 行字典（含 id / source_config，供持久化）。"""
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for p in parsed:
            result.append(
                {
                    "id": f"logcat_{uuid.uuid4().hex[:12]}",
                    "signal_type": p.signal_type,
                    "severity": p.severity,
                    "pattern": {
                        "matched": p.pattern,
                        "stack_top": p.stack_top,
                    },
                    "source_config": {
                        "tag": p.source_tag,
                        "message": p.message[:500],
                        "captured_at": now.isoformat(),
                    },
                }
            )
        return result


__all__ = ["LogcatListener", "ParsedLogcatSignal"]
