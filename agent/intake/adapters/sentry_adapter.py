"""Sentry webhook 适配器（R001-BF001，D8 第一适配器）。

依据：
- .dev-flow/R001/contracts/R001-BF001.md AC-2 / AC-7（字段映射）
- Sentry webhook payload 结构：https://docs.sentry.io/product/integrations/integration-platform/webhooks/

字段映射（AC-7）：
    event.event_id           → external_id（幂等 key）
    event.release            → version_code（INV-1 必携；约定 release = versionCode）
    event.dist               → version_name（约定 dist = versionName，可缺失）
    event.exception.values[0].stacktrace.frames → raw_report.stacktrace
    整个 raw payload          → raw_report._raw_sentry_payload（审计/回溯）
    （常量）                  → source_platform = "sentry"
    （常量）                  → status = BugReportStatus.RECEIVED.value

约定（INV-1）：release 必携，缺失/空 → VersionCodeMissingError（不静默降级）。
"""
from __future__ import annotations

from agent.intake.bug_report_adapter import BugReportAdapter
from agent.schemas.bug_report import BugReport, BugReportStatus

# stacktrace 摘要最多保留的帧数（避免 raw_report 过大；MVP 取 top N）
_MAX_STACKTRACE_FRAMES = 10


class SentryAdapter(BugReportAdapter):
    """Sentry webhook payload → BugReport 归一化适配器。

    source_platform 固定为 "sentry"（D8）。
    """

    source_platform = "sentry"

    def normalize(self, raw: dict) -> BugReport:
        """Sentry webhook payload → BugReport（status=received，内存对象）。

        INV-1 守护：release 缺失/空 → VersionCodeMissingError。
        """
        # Sentry webhook 外层可能包 data/event 两层，兼容裸 event 结构
        data = raw.get("data", raw)
        event = data.get("event", data)

        event_id = event.get("event_id")
        release = event.get("release")  # versionCode 约定
        dist = event.get("dist")  # versionName 约定

        # INV-1 守护（release 即 versionCode，缺失即拒）
        self._validate_version_code(release)

        # exception.values[0].stacktrace.frames 提取
        # 防御性解析：Sentry 结构理论上是 dict/list，但外部 webhook 可能发畸形数据。
        # 畸形结构不抛 AttributeError，静默降级为空 frames（审计 payload 仍留存 raw_report）。
        exception = event.get("exception")
        values = exception.get("values") if isinstance(exception, dict) else None
        frames: list[dict] = []
        if isinstance(values, list) and values:
            first = values[0]
            first = first if isinstance(first, dict) else {}
            stacktrace = first.get("stacktrace")
            raw_frames = stacktrace.get("frames") if isinstance(stacktrace, dict) else None
            if isinstance(raw_frames, list):
                frames = raw_frames

        # stacktrace 摘要（top N frames，便于日志/人读）
        stacktrace_summary = "\n".join(
            f"  at {f.get('function', '?')}("
            f"{f.get('filename', '?')}:{f.get('lineno', '?')})"
            for f in frames[:_MAX_STACKTRACE_FRAMES]
        )

        # raw_report：dict 结构留存（stacktrace 摘要 + 完整原始 payload，审计/回溯用）
        raw_report = {
            "stacktrace": stacktrace_summary,
            "_raw_sentry_payload": raw,
        }

        return BugReport(
            # id 不在此填充（AC-7：由持久化层生成）
            external_id=event_id,
            source_platform=self.source_platform,
            version_code=release,
            version_name=dist,
            status=BugReportStatus.RECEIVED.value,
            raw_report=raw_report,
        )

    def extract_external_id(self, raw: dict) -> str | None:
        """从 raw 提取 Sentry event_id（幂等 key）。

        兼容 data/event 两层包装与裸 event 结构。
        缺失返回 None（不抛错；调用方 FF001 决定是否拒绝）。
        """
        data = raw.get("data", raw)
        event = data.get("event", data)
        return event.get("event_id")


__all__ = ["SentryAdapter"]
