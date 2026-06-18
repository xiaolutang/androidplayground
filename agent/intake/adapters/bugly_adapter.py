"""Bugly 适配器占位（R001-BF001，D8 roadmap 后续实现）。

依据：.dev-flow/R001/contracts/R001-BF001.md AC-3（Bugly 占位）

MVP 不实现 Bugly 真实适配器；类可实例化（占位类本身可构造），
方法调用抛 NotImplementedError（明确未实现，避免静默错误归一化）。
"""
from __future__ import annotations

from agent.intake.bug_report_adapter import BugReportAdapter
from agent.schemas.bug_report import BugReport

_BUGLY_NOT_IMPLEMENTED_MSG = (
    "Bugly adapter not implemented yet; see D8 roadmap (R001 MVP scope: Sentry only)"
)


class BuglyAdapter(BugReportAdapter):
    """Bugly 适配器占位（NotImplementedError）。

    source_platform 固定为 "bugly"（预留）。
    """

    source_platform = "bugly"

    def normalize(self, raw: dict) -> BugReport:
        """占位：抛 NotImplementedError（Bugly 适配器待 D8 roadmap 实现）。"""
        raise NotImplementedError(_BUGLY_NOT_IMPLEMENTED_MSG)

    def extract_external_id(self, raw: dict) -> str | None:
        """占位：抛 NotImplementedError（Bugly 适配器待 D8 roadmap 实现）。"""
        raise NotImplementedError(_BUGLY_NOT_IMPLEMENTED_MSG)


__all__ = ["BuglyAdapter"]
