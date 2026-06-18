"""Bug 上报接入层（R001-BF001）。

聚合导出适配器抽象基类、异常类与幂等查询契约 Protocol。
具体平台适配器见 agent.intake.adapters 子包。
"""
from agent.intake.bug_report_adapter import (
    BugReportAdapter,
    BugReportStore,
    VersionCodeMissingError,
)

__all__ = [
    "BugReportAdapter",
    "BugReportStore",
    "VersionCodeMissingError",
]
