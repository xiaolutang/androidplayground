"""信号路由器（R001-BF004）。

按 signal_type 将信号路由给消费方：
- crash / ANR / logcat_fatal / flutter_error → BB003（PlaybookExecutor 执行流）
- visual_signal → BB004（HypothesisEngine 假设树引擎）

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md
  3.2 流程图 S3/S4：SIG → BB003（执行流）/ BB004（假设树）
  （第 189-205 行）
- agent/schemas/signal.py（SignalType 四类）

路由规则：
1. signal_type=logcat + severity=crash → BB003（崩溃立即中断执行流）
2. signal_type=logcat + severity=error/warn → BB003（错误信号供执行流判定）
3. signal_type=flutter_error → BB003（Flutter 异常供执行流判定）
4. signal_type=process + severity=crash → BB003（进程崩溃中断）
5. signal_type=visual → BB004（视觉异常供假设树推理，可能非崩溃而是 UI 缺陷）
"""
from __future__ import annotations

from typing import Any, Callable, Protocol

from agent.schemas.signal import SignalType


class SignalLike(Protocol):
    """信号鸭子类型（ParsedXxxSignal 或 dict 均可）。"""

    signal_type: str
    severity: str


# 消费方标识
CONSUMER_BB003 = "bb003"  # PlaybookExecutor 执行流
CONSUMER_BB004 = "bb004"  # HypothesisEngine 假设树引擎

# signal_type → 默认消费方
_DEFAULT_ROUTE: dict[str, str] = {
    SignalType.LOGCAT.value: CONSUMER_BB003,
    SignalType.FLUTTER_ERROR.value: CONSUMER_BB003,
    SignalType.PROCESS.value: CONSUMER_BB003,
    SignalType.VISUAL.value: CONSUMER_BB004,
}

ConsumerCallback = Callable[[SignalLike], Any]


class SignalRouter:
    """信号路由器：按 signal_type + severity 路由给注册的消费方。

    用法：
        router = SignalRouter()
        router.register_consumer(SignalType.LOGCAT.value, bb003_handler)
        router.register_consumer(SignalType.VISUAL.value, bb004_handler)
        results = router.dispatch(signal)
    """

    def __init__(self) -> None:
        # signal_type → list[callback]
        self._consumers: dict[str, list[ConsumerCallback]] = {}

    def register_consumer(
        self, signal_type: str, callback: ConsumerCallback
    ) -> None:
        """注册消费方回调。

        同一 signal_type 可注册多个回调（都会被调用）。
        """
        if signal_type not in self._consumers:
            self._consumers[signal_type] = []
        self._consumers[signal_type].append(callback)

    def route_to(self, signal: SignalLike) -> str:
        """判定信号应路由给哪个消费方（返回消费方标识）。

        路由规则：
        - crash 级的 logcat/flutter_error/process → BB003（执行流必须响应）
        - error/warn 级的 logcat/flutter_error/process → BB003（执行流参考）
        - visual → BB004（假设树引擎推理 UI 缺陷）
        """
        return _DEFAULT_ROUTE.get(signal.signal_type, CONSUMER_BB003)

    def dispatch(self, signal: SignalLike) -> list[Any]:
        """分发信号给所有已注册的对应消费方。

        返回每个回调的执行结果列表。
        若无注册消费方，返回空列表（信号被丢弃，不报错）。
        """
        signal_type = signal.signal_type
        callbacks = self._consumers.get(signal_type, [])
        results: list[Any] = []
        for cb in callbacks:
            results.append(cb(signal))
        return results

    def has_consumer(self, signal_type: str) -> bool:
        """检查是否有注册的消费方。"""
        return signal_type in self._consumers and len(self._consumers[signal_type]) > 0


__all__ = [
    "SignalRouter",
    "SignalLike",
    "CONSUMER_BB003",
    "CONSUMER_BB004",
]
