"""信号监听器（R001-BF004）。

四类信号解析 + 路由：
- logcat_listener：Android logcat（FATAL EXCEPTION / AndroidRuntime / java.）
- flutter_error_listener：Flutter error channel（[ERROR] / Exception / DartError）
- process_listener：进程崩溃 / ANR
- visual_signal_detector：白屏 / Loading 视觉信号（只检测不决策）
- router：按 signal_type 路由给 BB003（执行流）/ BB004（假设树引擎）

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Signal 表（第 679-687 行）
- agent/schemas/signal.py（Signal / SignalType / SignalSeverity）
"""
from __future__ import annotations

from agent.signals.flutter_error_listener import FlutterErrorListener
from agent.signals.logcat_listener import LogcatListener
from agent.signals.process_listener import detect_anr, detect_crash, parse_anr
from agent.signals.router import (
    CONSUMER_BB003,
    CONSUMER_BB004,
    SignalRouter,
)
from agent.signals.visual_signal_detector import detect_blank_screen, detect_loading

__all__ = [
    "LogcatListener",
    "FlutterErrorListener",
    "detect_crash",
    "detect_anr",
    "parse_anr",
    "detect_blank_screen",
    "detect_loading",
    "SignalRouter",
    "CONSUMER_BB003",
    "CONSUMER_BB004",
]
