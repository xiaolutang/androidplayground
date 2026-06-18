"""Flutter error 信号监听器（R001-BF004）。

解析 Flutter error channel 输出，识别 Dart 异常 / Flutter framework 错误。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表
- agent/schemas/signal.py（SignalType.FLUTTER_ERROR）

Flutter error 输出特征（经 logcat 或 flutter run 输出）：
- E/flutter ( pid): [ERROR:flutter/...] message
- flutter: Exception: message
- DartError / FileSystemException / StateError 等 Dart 异常类
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from agent.schemas.signal import SignalSeverity, SignalType

# ----------------------------------------------------------------------------
# Flutter error 行模式
# ----------------------------------------------------------------------------
# E/flutter (1234): [ERROR:flutter/lib/ui/...]
_FLUTTER_ERROR_RE = re.compile(r"\[ERROR:", re.IGNORECASE)
# flutter: Exception / flutter: SomeError
_FLUTTER_EXCEPTION_RE = re.compile(r"flutter:\s+(.*Exception|.*Error)", re.IGNORECASE)
# Dart 异常类名
_DART_EXCEPTION_RE = re.compile(
    r"(FileSystemException|StateError|FormatException|ArgumentError|"
    r"RangeError|TypeError|AssertionError|DartError|LateInitializationError)",
    re.IGNORECASE,
)
# Dart stacktrace 帧：#0      methodName (file.dart:line:col)
_DART_FRAME_RE = re.compile(r"#\d+\s+([\w.<>]+\s+\([\w./]+:\d+:\d+\))")


@dataclass
class ParsedFlutterSignal:
    """解析后的 Flutter error 信号。"""

    signal_type: str
    severity: str
    pattern: str
    message: str
    error_class: str | None  # Dart 异常类名
    stack_top: str | None  # Dart stack 顶帧
    channel: str | None  # Flutter channel 信息


def _grade_severity(line: str) -> str:
    """Flutter error 严重度分级。"""
    # [ERROR: 前缀 = Flutter framework 错误 → error
    if _FLUTTER_ERROR_RE.search(line):
        return SignalSeverity.ERROR.value
    # Dart 异常类 = 未捕获异常 → error
    if _DART_EXCEPTION_RE.search(line):
        return SignalSeverity.ERROR.value
    # flutter: 后跟 Exception/Error 关键字 → error
    if _FLUTTER_EXCEPTION_RE.search(line):
        return SignalSeverity.ERROR.value
    return SignalSeverity.WARN.value


def _extract_error_class(line: str) -> str | None:
    """提取 Dart 异常类名。"""
    m = _DART_EXCEPTION_RE.search(line)
    if m:
        return m.group(1)
    # 通用 Exception: / Error: 模式
    m = re.search(r"(\w+(?:Exception|Error))", line)
    if m:
        return m.group(1)
    return None


def _extract_dart_stack_top(lines: list[str], start_idx: int) -> str | None:
    """从异常行之后提取 Dart stacktrace 顶帧。"""
    for line in lines[start_idx + 1 : start_idx + 20]:
        m = _DART_FRAME_RE.search(line)
        if m:
            return m.group(1)
    return None


class FlutterErrorListener:
    """Flutter error 信号解析器。

    用法：
        listener = FlutterErrorListener()
        signals = listener.parse(flutter_output)
    """

    def parse(self, flutter_error_output: str) -> list[ParsedFlutterSignal]:
        """解析 Flutter error 输出文本，返回识别出的信号列表。

        识别规则：
        - [ERROR: 前缀 → Flutter framework error
        - flutter: Exception/Error → 未捕获 Dart 异常
        - Dart 异常类名（StateError / TypeError 等）
        """
        signals: list[ParsedFlutterSignal] = []
        lines = flutter_error_output.splitlines()

        for idx, line in enumerate(lines):
            has_flutter_error = bool(_FLUTTER_ERROR_RE.search(line))
            has_flutter_exc = bool(_FLUTTER_EXCEPTION_RE.search(line))
            has_dart_exc = bool(_DART_EXCEPTION_RE.search(line))

            if not (has_flutter_error or has_flutter_exc or has_dart_exc):
                continue

            severity = _grade_severity(line)
            error_class = _extract_error_class(line)
            stack_top = _extract_dart_stack_top(lines, idx)

            # 提取 channel 信息（[ERROR:flutter/...] 的路径部分）
            channel: str | None = None
            m = re.search(r"\[ERROR:([\w./]+)", line)
            if m:
                channel = m.group(1)

            matched: list[str] = []
            if has_flutter_error:
                matched.append("[ERROR:")
            if has_dart_exc and error_class:
                matched.append(error_class)
            elif has_flutter_exc:
                matched.append("flutter Exception/Error")
            pattern = " | ".join(matched) if matched else "flutter_error"

            signals.append(
                ParsedFlutterSignal(
                    signal_type=SignalType.FLUTTER_ERROR.value,
                    severity=severity,
                    pattern=pattern,
                    message=line.strip(),
                    error_class=error_class,
                    stack_top=stack_top,
                    channel=channel,
                )
            )

        return signals

    def to_signal_dicts(self, parsed: list[ParsedFlutterSignal]) -> list[dict[str, Any]]:
        """转成 Signal 行字典。"""
        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for p in parsed:
            result.append(
                {
                    "id": f"flutter_{uuid.uuid4().hex[:12]}",
                    "signal_type": p.signal_type,
                    "severity": p.severity,
                    "pattern": {
                        "matched": p.pattern,
                        "error_class": p.error_class,
                        "stack_top": p.stack_top,
                    },
                    "source_config": {
                        "channel": p.channel,
                        "message": p.message[:500],
                        "captured_at": now.isoformat(),
                    },
                }
            )
        return result


__all__ = ["FlutterErrorListener", "ParsedFlutterSignal"]
