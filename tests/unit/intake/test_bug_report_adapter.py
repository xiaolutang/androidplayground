"""R001-BF001 Bug 上报接入适配器单元测试。

依据：.dev-flow/R001/contracts/R001-BF001.md AC-1 ~ AC-8

覆盖矩阵（AC → 测试）：
- AC-1 抽象基类：test_abstract_cannot_instantiate / test_validate_version_code_*
- AC-2 Sentry normalize：test_normalize_basic / test_normalize_status_received
- AC-3 Bugly 占位：test_bugly_normalize_not_implemented / test_bugly_extract_not_implemented
- AC-4 INV-1 守护：test_normalize_missing_version_raises / test_normalize_empty_version_raises /
                   test_normalize_whitespace_version_raises
- AC-5 幂等 key 提取：test_extract_external_id / test_extract_external_id_missing /
                      test_check_duplicate_true / test_check_duplicate_no_external_id
- AC-6 状态归一化：test_normalize_status_received（引用 BugReportStatus.RECEIVED.value）
- AC-7 字段映射：test_normalize_basic / test_normalize_version_code_from_release /
                 test_stacktrace_extraction / test_source_platform_sentry / test_normalize_id_not_filled
- AC-8 测试覆盖：本文件 + fixture（无 DB / 无网络 / 无文件 IO）

测试策略：全 fixture（内联 dict），无 DB session、无网络、无文件 IO。
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect

from agent.intake import (
    BugReportAdapter,
    BugReportStore,
    VersionCodeMissingError,
)
from agent.intake.adapters import BuglyAdapter, SentryAdapter
from agent.schemas.bug_report import BugReport, BugReportStatus


# ---------------------------------------------------------------------------
# Fixture：Sentry webhook payload 样例（真实结构，内联）
# ---------------------------------------------------------------------------
SENTRY_SAMPLE = {
    "data": {
        "event": {
            "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "release": "102",  # versionCode 约定
            "dist": "1.2.3",  # versionName 约定
            "exception": {
                "values": [
                    {
                        "type": "NullPointerException",
                        "stacktrace": {
                            "frames": [
                                {
                                    "filename": "MainActivity.kt",
                                    "lineno": 42,
                                    "function": "onCreate",
                                },
                                {
                                    "filename": "BaseActivity.kt",
                                    "lineno": 15,
                                    "function": "onStart",
                                },
                            ]
                        },
                    }
                ]
            },
        }
    }
}


# ---------------------------------------------------------------------------
# AC-1：抽象基类 BugReportAdapter
# ---------------------------------------------------------------------------
class TestBaseClass:
    """AC-1 抽象基类契约。"""

    def test_abstract_cannot_instantiate(self):
        """BugReportAdapter 是 ABC，不可直接实例化。"""
        with pytest.raises(TypeError):
            BugReportAdapter()  # type: ignore[abstract]

    def test_validate_version_code_missing(self):
        """_validate_version_code(None) 抛 VersionCodeMissingError。"""
        adapter = SentryAdapter()
        with pytest.raises(VersionCodeMissingError) as exc_info:
            adapter._validate_version_code(None)
        # message 含 INV-1 与 version_code（便于日志检索）
        assert "INV-1" in str(exc_info.value)
        assert "version_code" in str(exc_info.value)

    def test_validate_version_code_empty(self):
        """_validate_version_code('') 抛 VersionCodeMissingError。"""
        adapter = SentryAdapter()
        with pytest.raises(VersionCodeMissingError):
            adapter._validate_version_code("")

    def test_validate_version_code_whitespace(self):
        """_validate_version_code('   ') 仅空白也抛错（AC-1 / AC-4）。"""
        adapter = SentryAdapter()
        with pytest.raises(VersionCodeMissingError):
            adapter._validate_version_code("   ")

    def test_validate_version_code_present(self):
        """_validate_version_code('102') 正常不抛错。"""
        adapter = SentryAdapter()
        # 不抛错即通过
        adapter._validate_version_code("102")

    def test_version_code_missing_error_is_exception(self):
        """VersionCodeMissingError 继承 Exception（AC-1）。"""
        assert issubclass(VersionCodeMissingError, Exception)


# ---------------------------------------------------------------------------
# AC-2 / AC-6 / AC-7：SentryAdapter normalize
# ---------------------------------------------------------------------------
class TestSentryAdapter:
    """AC-2 Sentry 归一化 + AC-6 状态归一化 + AC-7 字段映射。"""

    def test_normalize_basic(self):
        """标准 Sentry payload → BugReport，字段全断言（AC-2 / AC-7）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        assert isinstance(report, BugReport)
        assert report.external_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert report.version_code == "102"
        assert report.version_name == "1.2.3"

    def test_normalize_status_received(self):
        """状态归一化为 received（AC-6，引用枚举值不硬编码字符串）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        assert report.status == BugReportStatus.RECEIVED.value
        assert report.status == "received"

    def test_normalize_version_code_from_release(self):
        """version_code 从 event.release 提取（AC-7 字段映射）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        assert report.version_code == SENTRY_SAMPLE["data"]["event"]["release"]

    def test_normalize_missing_version_raises(self):
        """release 缺失 → VersionCodeMissingError（AC-4 INV-1 守护）。"""
        raw = {"data": {"event": {"event_id": "x", "dist": "1.0"}}}
        with pytest.raises(VersionCodeMissingError):
            SentryAdapter().normalize(raw)

    def test_normalize_empty_version_raises(self):
        """release 为空字符串 → VersionCodeMissingError（AC-4）。"""
        raw = {"data": {"event": {"event_id": "x", "release": ""}}}
        with pytest.raises(VersionCodeMissingError):
            SentryAdapter().normalize(raw)

    def test_normalize_whitespace_version_raises(self):
        """release 仅空白 → VersionCodeMissingError（AC-4 / AC-8）。"""
        raw = {"data": {"event": {"event_id": "x", "release": "   "}}}
        with pytest.raises(VersionCodeMissingError):
            SentryAdapter().normalize(raw)

    def test_normalize_id_not_filled(self):
        """normalize 不填 id（AC-7：由持久化层生成）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        # SQLAlchemy 未赋值字段访问返回 None（或默认值），id 无 default → None
        # 用 __dict__ 确认未显式传入 id
        assert "id" not in {k: v for k, v in report.__dict__.items() if v is not None}

    def test_normalize_raw_report_dict(self):
        """raw_report 是 dict，含 stacktrace 与 _raw_sentry_payload（AC-7）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        assert isinstance(report.raw_report, dict)
        assert "stacktrace" in report.raw_report
        assert "_raw_sentry_payload" in report.raw_report
        assert report.raw_report["_raw_sentry_payload"] is SENTRY_SAMPLE

    def test_extract_external_id(self):
        """extract_external_id 从 event.event_id 提取（AC-5）。"""
        eid = SentryAdapter().extract_external_id(SENTRY_SAMPLE)
        assert eid == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_extract_external_id_missing(self):
        """event_id 缺失返回 None（AC-5，不抛错）。"""
        raw = {"data": {"event": {"release": "102"}}}
        assert SentryAdapter().extract_external_id(raw) is None

    def test_extract_external_id_bare_event(self):
        """兼容裸 event 结构（无 data/event 包装，AC-5 鲁棒性）。"""
        raw = {"event_id": "bare-id", "release": "1"}
        assert SentryAdapter().extract_external_id(raw) == "bare-id"

    def test_check_duplicate_true(self):
        """mock store 返回 True → 重复（AC-5 幂等检查）。"""

        class _DupStore:
            def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
                assert source_platform == "sentry"
                return True

        assert SentryAdapter().check_duplicate(SENTRY_SAMPLE, _DupStore()) is True

    def test_check_duplicate_false(self):
        """mock store 返回 False → 不重复（AC-5）。"""

        class _NoDupStore:
            def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
                return False

        assert SentryAdapter().check_duplicate(SENTRY_SAMPLE, _NoDupStore()) is False

    def test_check_duplicate_no_external_id(self):
        """external_id=None → 不重复（无 key 无法判重，AC-5）。"""

        class _ExplodingStore:
            def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
                raise AssertionError("store should not be queried when external_id is None")

        raw = {"data": {"event": {"release": "102"}}}
        assert SentryAdapter().check_duplicate(raw, _ExplodingStore()) is False

    def test_stacktrace_extraction(self):
        """frames 提取为 stacktrace 摘要（AC-7）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        stacktrace = report.raw_report["stacktrace"]
        assert "MainActivity.kt" in stacktrace
        assert "onCreate" in stacktrace
        assert "42" in stacktrace
        assert "BaseActivity.kt" in stacktrace

    def test_source_platform_sentry(self):
        """source_platform 常量为 "sentry"（AC-7）。"""
        report = SentryAdapter().normalize(SENTRY_SAMPLE)
        assert report.source_platform == "sentry"
        assert SentryAdapter().source_platform == "sentry"

    def test_normalize_no_exception_field(self):
        """payload 无 exception 字段也能归一化（frames 为空，不抛错）。"""
        raw = {"data": {"event": {"event_id": "e1", "release": "1"}}}
        report = SentryAdapter().normalize(raw)
        assert report.raw_report["stacktrace"] == ""

    def test_normalize_malformed_exception_is_string(self):
        """exception 字段为字符串 → 静默降级空 frames（不抛 AttributeError）。"""
        raw = {"data": {"event": {"event_id": "e1", "release": "1", "exception": "oops"}}}
        report = SentryAdapter().normalize(raw)
        assert report.raw_report["stacktrace"] == ""

    def test_normalize_malformed_values_is_string(self):
        """exception.values 为字符串（非 list）→ 静默降级空 frames。"""
        raw = {"data": {"event": {"event_id": "e1", "release": "1",
                                   "exception": {"values": "not_a_list"}}}}
        report = SentryAdapter().normalize(raw)
        assert report.raw_report["stacktrace"] == ""

    def test_normalize_malformed_values_non_dict_item(self):
        """exception.values[0] 为非 dict（int/str）→ 静默降级空 frames。"""
        raw = {"data": {"event": {"event_id": "e1", "release": "1",
                                   "exception": {"values": [42]}}}}
        report = SentryAdapter().normalize(raw)
        assert report.raw_report["stacktrace"] == ""

    def test_normalize_malformed_stacktrace_is_string(self):
        """stacktrace 为字符串（非 dict）→ 静默降级空 frames。"""
        raw = {"data": {"event": {"event_id": "e1", "release": "1",
                                   "exception": {"values": [
                                       {"stacktrace": "corrupted"}
                                   ]}}}}
        report = SentryAdapter().normalize(raw)
        assert report.raw_report["stacktrace"] == ""

    def test_bug_report_store_protocol_runtime_checkable(self):
        """BugReportStore 是 runtime_checkable Protocol（AC-5 契约）。"""
        # _DupStore 无显式继承但结构匹配 Protocol
        class _CompatibleStore:
            def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
                return False

        assert isinstance(_CompatibleStore(), BugReportStore)


# ---------------------------------------------------------------------------
# AC-3：BuglyAdapter 占位
# ---------------------------------------------------------------------------
class TestBuglyAdapter:
    """AC-3 Bugly 占位（NotImplementedError）。"""

    def test_can_instantiate(self):
        """BuglyAdapter 可实例化（占位类本身可构造，AC-3）。"""
        # 不抛错即通过
        BuglyAdapter()

    def test_bugly_normalize_not_implemented(self):
        """normalize 抛 NotImplementedError，message 含 Bugly（AC-3）。"""
        with pytest.raises(NotImplementedError) as exc_info:
            BuglyAdapter().normalize({})
        assert "Bugly" in str(exc_info.value)

    def test_bugly_extract_not_implemented(self):
        """extract_external_id 抛 NotImplementedError（AC-3）。"""
        with pytest.raises(NotImplementedError):
            BuglyAdapter().extract_external_id({})

    def test_bugly_is_bug_report_adapter(self):
        """BuglyAdapter 继承 BugReportAdapter（isinstance，AC-3）。"""
        assert isinstance(BuglyAdapter(), BugReportAdapter)

    def test_bugly_source_platform(self):
        """source_platform 预留为 "bugly"。"""
        assert BuglyAdapter().source_platform == "bugly"


# ---------------------------------------------------------------------------
# AC-7（schema 演进）：external_id 字段
# ---------------------------------------------------------------------------
class TestSchemaExternalId:
    """BugReport.external_id 字段存在（SCH01 演进，AC-7）。"""

    def test_external_id_field_exists(self):
        """BugReport 有 external_id 列（nullable + indexed）。"""
        mapper = inspect(BugReport)
        assert "external_id" in mapper.columns
        col = mapper.columns["external_id"]
        assert col.nullable is True, "external_id must be nullable (AC-7 / 无 event_id 上报允许进入)"
        assert col.index is True, "external_id should be indexed (幂等查询性能)"
