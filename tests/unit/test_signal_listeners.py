"""信号监听器单元测试（R001-BF004）。

覆盖四类信号解析 + 路由，共 20 测试：

logcat_listener (5):
  1. test_parse_fatal_exception — FATAL EXCEPTION → crash + stack top
  2. test_parse_android_runtime — AndroidRuntime: → error
  3. test_parse_no_match — 无关键字的行不产生信号
  4. test_severity_grading — E/ → error / W/ → warn / FATAL → crash
  5. test_to_signal_dicts_format — to_signal_dicts 输出格式正确

flutter_error_listener (3):
  6. test_parse_flutter_error — [ERROR: 前缀 → error
  7. test_parse_dart_exception — StateError → error + 类名提取
  8. test_parse_no_match — 普通输出不产生信号

process_listener (5):
  9. test_detect_crash_non_zero_exit — exit_code=1 → crash
  10. test_detect_crash_zero_exit_returns_none — exit_code=0 → None
  11. test_detect_crash_none_input_returns_none — None/空dict → None
  12. test_detect_anr_from_trace — ANR trace → crash + 进程名
  13. test_no_anr_returns_none — 无 trace / 非 ANR → None

visual_signal_detector (3):
  14. test_detect_blank_screen — 纯白画面 → blank_screen
  15. test_detect_blank_screen_black — 纯黑画面 → blank_screen
  16. test_normal_screen_no_signal — 有内容画面 → None

router (4):
  17. test_register_and_dispatch — 注册回调 + 分发
  18. test_route_by_signal_type — logcat→BB003 / visual→BB004
  19. test_no_consumer_returns_empty — 无注册消费方 → []
  20. test_multiple_consumers_same_type — 同类型多消费方都被调用
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from agent.signals.flutter_error_listener import FlutterErrorListener
from agent.signals.logcat_listener import LogcatListener
from agent.signals.process_listener import detect_anr, detect_crash
from agent.signals.router import (
    CONSUMER_BB003,
    CONSUMER_BB004,
    SignalRouter,
)
from agent.signals.visual_signal_detector import detect_blank_screen
from agent.schemas.signal import SignalSeverity, SignalType


# ============================================================================
# Fixtures
# ============================================================================

LOGCAT_FATAL = """\
I/ActivityManager( 1000): Start proc 1234:com.example.app/u0a100
E/AndroidRuntime( 1234): FATAL EXCEPTION: main
E/AndroidRuntime( 1234): Process: com.example.app, PID: 1234
E/AndroidRuntime( 1234): java.lang.NullPointerException
E/AndroidRuntime( 1234): \tat com.example.app.MainActivity.onCreate(MainActivity.java:42)
E/AndroidRuntime( 1234): \tat android.app.Activity.performCreate(Activity.java:8000)
"""

LOGCAT_ANDROID_RUNTIME = """\
D/AndroidRuntime( 1234): Shutting down VM
E/AndroidRuntime( 1234): REPORT CRASH DETAILS
"""

LOGCAT_NO_MATCH = """\
I/ActivityManager( 1000): Displayed com.example.app/.MainActivity
D/Choreographer( 1234): Skipped frames
"""

LOGCAT_WARN = """\
W/System.err( 1234): Something went wrong but not fatal
"""

FLUTTER_ERROR_OUTPUT = """\
I/flutter ( 5678): App started
E/flutter ( 5678): [ERROR:flutter/lib/ui/hooks_zone.dart:166] Unhandled Exception: Failed to load resource
E/flutter ( 5678): #0      NetworkImage._loadAsset (painting.dart:501:12)
E/flutter ( 5678): #1      _ImageState._handleImageChanged (widgets.dart:800:20)
"""

FLUTTER_DART_EXCEPTION = """\
flutter: StateError: Bad state: No element
flutter: #0      List.first (dart:core/list.dart:123:45)
"""

FLUTTER_NORMAL = """\
flutter: hello world
I/flutter ( 5678): rendering frame
"""

ANR_TRACE = """\
----- pid 1234 at 2024-01-01 12:00:00 -----
Cmd line: com.example.app
...
ANR in com.example.app (com.example.app/.MainActivity)
PID: 1234
Reason: Input dispatching timed out (com.example.app/com.example.app.MainActivity in 5001ms)
"""


# ============================================================================
# logcat_listener 测试
# ============================================================================

class TestLogcatListener:
    def test_parse_fatal_exception(self) -> None:
        listener = LogcatListener()
        signals = listener.parse(LOGCAT_FATAL)

        # FATAL EXCEPTION 行 + java.lang.NPE 行
        assert len(signals) >= 1
        fatal_sig = signals[0]
        assert fatal_sig.severity == SignalSeverity.CRASH.value
        assert "FATAL EXCEPTION" in fatal_sig.pattern
        # stack top 应提取到 MainActivity.onCreate
        assert fatal_sig.stack_top is not None
        assert "MainActivity.onCreate" in fatal_sig.stack_top

    def test_parse_android_runtime(self) -> None:
        listener = LogcatListener()
        signals = listener.parse(LOGCAT_ANDROID_RUNTIME)

        # 两行都匹配 AndroidRuntime（D/ 和 E/）
        assert len(signals) >= 2
        # E/ 行 → error 级
        error_sigs = [s for s in signals if s.severity == SignalSeverity.ERROR.value]
        assert len(error_sigs) >= 1
        assert "AndroidRuntime" in error_sigs[0].pattern

    def test_parse_no_match(self) -> None:
        listener = LogcatListener()
        signals = listener.parse(LOGCAT_NO_MATCH)
        assert len(signals) == 0

    def test_severity_grading(self) -> None:
        listener = LogcatListener()
        # FATAL → crash
        sigs = listener.parse(LOGCAT_FATAL)
        fatal = [s for s in sigs if "FATAL" in s.pattern]
        assert all(s.severity == SignalSeverity.CRASH.value for s in fatal)

        # W/ 前缀但无关键字 → 不产生信号
        sigs_w = listener.parse(LOGCAT_WARN)
        # W/System.err 含 "err" 但不匹配 java.Exception/AndroidRuntime/FATAL
        assert len(sigs_w) == 0

    def test_to_signal_dicts_format(self) -> None:
        listener = LogcatListener()
        parsed = listener.parse(LOGCAT_FATAL)
        dicts = listener.to_signal_dicts(parsed)

        assert len(dicts) == len(parsed)
        d = dicts[0]
        assert d["signal_type"] == SignalType.LOGCAT.value
        assert d["id"].startswith("logcat_")
        assert "matched" in d["pattern"]
        assert "tag" in d["source_config"]


# ============================================================================
# flutter_error_listener 测试
# ============================================================================

class TestFlutterErrorListener:
    def test_parse_flutter_error(self) -> None:
        listener = FlutterErrorListener()
        signals = listener.parse(FLUTTER_ERROR_OUTPUT)

        assert len(signals) >= 1
        sig = signals[0]
        assert sig.severity == SignalSeverity.ERROR.value
        assert "[ERROR:" in sig.pattern
        assert sig.channel is not None
        assert "flutter" in sig.channel
        # stack top 提取
        assert sig.stack_top is not None
        assert "NetworkImage" in sig.stack_top

    def test_parse_dart_exception(self) -> None:
        listener = FlutterErrorListener()
        signals = listener.parse(FLUTTER_DART_EXCEPTION)

        assert len(signals) >= 1
        sig = signals[0]
        assert sig.severity == SignalSeverity.ERROR.value
        assert sig.error_class is not None
        assert "StateError" in sig.error_class

    def test_parse_no_match(self) -> None:
        listener = FlutterErrorListener()
        signals = listener.parse(FLUTTER_NORMAL)
        assert len(signals) == 0


# ============================================================================
# process_listener 测试
# ============================================================================

class TestProcessListener:
    def test_detect_crash_non_zero_exit(self) -> None:
        state = {
            "process_name": "com.example.app",
            "pid": 1234,
            "exit_code": 1,
            "signal": "SIGABRT",
        }
        sig = detect_crash(state)

        assert sig is not None
        assert sig.severity == SignalSeverity.CRASH.value
        assert sig.process_name == "com.example.app"
        assert "exit_code=1" in (sig.reason or "")
        assert "SIGABRT" in (sig.reason or "")

    def test_detect_crash_zero_exit_returns_none(self) -> None:
        state = {"process_name": "com.example.app", "pid": 1234, "exit_code": 0}
        sig = detect_crash(state)
        assert sig is None

    def test_detect_crash_none_input_returns_none(self) -> None:
        """None / 空 dict 输入应优雅返回 None，不抛异常。"""
        assert detect_crash(None) is None
        assert detect_crash({}) is None

    def test_detect_anr_from_trace(self) -> None:
        sig = detect_anr(ANR_TRACE)

        assert sig is not None
        assert sig.severity == SignalSeverity.CRASH.value
        assert sig.pattern == "ANR"
        assert sig.process_name == "com.example.app"
        assert sig.pid == 1234
        assert sig.reason is not None
        assert "Input dispatching" in sig.reason

    def test_no_anr_returns_none(self) -> None:
        # None 输入
        assert detect_anr(None) is None

        # 非 ANR 文本
        assert detect_anr("just some random log output") is None


# ============================================================================
# visual_signal_detector 测试
# ============================================================================

def _make_solid_png(color: tuple[int, int, int], width: int = 32, height: int = 32) -> bytes:
    """生成纯色 PNG（用 PIL）。"""
    from PIL import Image  # type: ignore[import-untyped]

    img = Image.new("RGB", (width, height), color)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_gradient_png(width: int = 64, height: int = 64) -> bytes:
    """生成渐变 PNG（有内容，方差大）。"""
    from PIL import Image  # type: ignore[import-untyped]

    img = Image.new("RGB", (width, height))
    for x in range(width):
        for y in range(height):
            img.putpixel((x, y), (x * 4 % 256, y * 4 % 256, (x + y) * 2 % 256))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestVisualSignalDetector:
    def test_detect_blank_screen(self) -> None:
        white_png = _make_solid_png((255, 255, 255))
        sig = detect_blank_screen(white_png)

        assert sig is not None
        assert sig.visual_type == "blank_screen"
        assert sig.severity == SignalSeverity.ERROR.value
        assert sig.metrics["variance"] < 50.0

    def test_detect_blank_screen_black(self) -> None:
        black_png = _make_solid_png((0, 0, 0))
        sig = detect_blank_screen(black_png)

        assert sig is not None
        assert sig.visual_type == "blank_screen"
        assert sig.metrics["avg_brightness"] < 30.0

    def test_normal_screen_no_signal(self) -> None:
        gradient_png = _make_gradient_png()
        sig = detect_blank_screen(gradient_png)

        assert sig is None


# ============================================================================
# router 测试
# ============================================================================

class TestSignalRouter:
    def test_register_and_dispatch(self) -> None:
        router = SignalRouter()
        received: list[Any] = []

        router.register_consumer(
            SignalType.LOGCAT.value, lambda s: received.append(s)
        )

        # 构造简单 signal-like 对象
        class FakeSignal:
            signal_type = SignalType.LOGCAT.value
            severity = SignalSeverity.CRASH.value

        sig = FakeSignal()
        results = router.dispatch(sig)

        assert len(results) == 1
        assert len(received) == 1
        assert received[0] is sig

    def test_route_by_signal_type(self) -> None:
        router = SignalRouter()

        class CrashSignal:
            signal_type = SignalType.LOGCAT.value
            severity = SignalSeverity.CRASH.value

        class VisualSignal:
            signal_type = SignalType.VISUAL.value
            severity = SignalSeverity.ERROR.value

        assert router.route_to(CrashSignal()) == CONSUMER_BB003
        assert router.route_to(VisualSignal()) == CONSUMER_BB004

        # flutter_error / process → BB003
        class FlutterSignal:
            signal_type = SignalType.FLUTTER_ERROR.value
            severity = SignalSeverity.ERROR.value

        class ProcessSignal:
            signal_type = SignalType.PROCESS.value
            severity = SignalSeverity.CRASH.value

        assert router.route_to(FlutterSignal()) == CONSUMER_BB003
        assert router.route_to(ProcessSignal()) == CONSUMER_BB003

    def test_no_consumer_returns_empty(self) -> None:
        router = SignalRouter()

        class FakeSignal:
            signal_type = SignalType.LOGCAT.value
            severity = SignalSeverity.CRASH.value

        results = router.dispatch(FakeSignal())
        assert results == []
        assert not router.has_consumer(SignalType.LOGCAT.value)

    def test_multiple_consumers_same_type(self) -> None:
        router = SignalRouter()
        calls: list[str] = []

        router.register_consumer(SignalType.VISUAL.value, lambda s: calls.append("bb004"))
        router.register_consumer(SignalType.VISUAL.value, lambda s: calls.append("extra"))

        class FakeSignal:
            signal_type = SignalType.VISUAL.value
            severity = SignalSeverity.WARN.value

        results = router.dispatch(FakeSignal())
        assert len(results) == 2
        assert calls == ["bb004", "extra"]
