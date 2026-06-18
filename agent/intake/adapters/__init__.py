"""Bug 上报平台适配器（R001-BF001，D8 参数化适配器）。

MVP 实现：SentryAdapter（完整）。
占位：BuglyAdapter（NotImplementedError）。
后续 roadmap：CrashlyticsAdapter。
"""
from agent.intake.adapters.bugly_adapter import BuglyAdapter
from agent.intake.adapters.sentry_adapter import SentryAdapter

__all__ = [
    "BuglyAdapter",
    "SentryAdapter",
]
