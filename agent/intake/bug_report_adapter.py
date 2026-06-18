"""Bug 上报归一化适配器抽象基类（R001-BF001）。

依据：
- .dev-flow/R001/contracts/R001-BF001.md（AC-1 ~ AC-8）
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md（INV-1 versionCode 必携）
- D8（BugReportAdapter 参数化，MVP 第一适配器 Sentry）

职责边界（IN scope）：
- 定义 BugReportAdapter ABC：normalize / extract_external_id 抽象方法。
- 定义 VersionCodeMissingError（INV-1 守护异常）。
- 提供 _validate_version_code 共享校验逻辑。
- 提供 check_duplicate 幂等检查（依赖外部 BugReportStore 契约）。

职责边界（OUT of scope，归 FF001 router）：
- HTTP 接入、Pydantic DTO、DB 持久化、409 响应。
- exists_by_external_id 实际存储查询实现（BF001 只声明 Protocol 契约）。

幂等查询契约（由调用方 FF001 router 实现）：
    调用方应实现 BugReportStore.exists_by_external_id(source_platform, external_id) -> bool。
    BF001 adapter 只负责提取 external_id（extract_external_id），不碰 DB。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, runtime_checkable

from agent.schemas.bug_report import BugReport


class VersionCodeMissingError(Exception):
    """INV-1 守护：versionCode 必携，缺失或空即拒。

    message 约定含 "INV-1" 与 "version_code"（便于日志检索）。
    FF001 router 捕获后转 400 响应（转响应逻辑不在 BF001）。
    """


@runtime_checkable
class BugReportStore(Protocol):
    """幂等查询契约（由 FF001 router + data layer 实现）。

    BF001 不实现此 Protocol，只声明调用方契约。
    check_duplicate 通过此 Protocol 做存在性查询，解耦 adapter 与 DB。
    """

    def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
        """查询 (source_platform, external_id) 是否已存在。

        Args:
            source_platform: 平台标识（"sentry" / "bugly" / ...）。
            external_id: 平台级唯一 event_id。

        Returns:
            True = 已存在（重复上报）；False = 不存在（可入库）。
        """
        ...


class BugReportAdapter(ABC):
    """Bug 上报归一化适配器抽象基类。

    子类约定填 source_platform 类属性（"sentry" / "bugly" / "crashlytics"）。
    normalize 把平台 raw payload 归一化为 BugReport（status=received，内存对象未持久化）。
    """

    source_platform: str = ""

    @abstractmethod
    def normalize(self, raw: dict) -> BugReport:
        """raw payload → 归一化 BugReport（status=received）。

        子类实现要点：
        - 调 _validate_version_code 守护 INV-1（versionCode 缺失抛 VersionCodeMissingError）。
        - status 硬编码为 BugReportStatus.RECEIVED.value（不依赖 raw 中 status）。
        - 不填 id（由持久化层生成）、不触发 DB session。
        """
        ...

    @abstractmethod
    def extract_external_id(self, raw: dict) -> str | None:
        """从 raw 提取幂等 key（平台级唯一 event_id）。

        缺失返回 None（不抛错；调用方 FF001 决定是否拒绝无 event_id 的上报）。
        纯提取，不查 DB、不写存储（职责单一）。
        """
        ...

    def _validate_version_code(self, version_code: str | None) -> None:
        """INV-1 守护：versionCode 缺失 / 空字符串 / 仅空白 → VersionCodeMissingError。

        共享逻辑，子类复用不重复实现（DRY）。
        """
        if version_code is None or not str(version_code).strip():
            raise VersionCodeMissingError(
                f"INV-1 violation: version_code missing or empty for "
                f"source_platform={self.source_platform or '<unknown>'}"
            )

    def check_duplicate(self, raw: dict, store: BugReportStore) -> bool:
        """幂等检查（外部 store 查询）。返回 True = 重复。

        流程：extract_external_id → None 则不重复（无 key 无法判重）→
        store.exists_by_external_id 查询。

        BF001 提供此方法供 FF001 router 调用；store 实现归 FF001 / data layer。
        """
        external_id = self.extract_external_id(raw)
        if external_id is None:
            return False
        return store.exists_by_external_id(self.source_platform, external_id)


__all__ = [
    "BugReportAdapter",
    "BugReportStore",
    "VersionCodeMissingError",
]
