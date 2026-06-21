"""ReflowManager 单元测试（R001-BB011）。

覆盖回流管理器的 16 个测试场景（AC-1 ~ AC-8）：

1. 路径 A 正常回流（gap_pending → 发事件）
2. 路径 A 状态不符（非 gap_pending → skipped）
3. 路径 B 正常回流（concluded + regression → 发事件）
4. 路径 B 正常回流（reflected + regression → 发事件）
5. 路径 B 状态不符（非 concluded/reflected → skipped）
6. reflow_count 未超限（count=1 → 正常发事件）
7. reflow_count 刚到限（count=2 → 自增到 3，不超限）
8. reflow_count 超限（count=3 → wont_reflow=True）
9. max_reflow_count 自定义覆盖（max=5, count=3 → 未超限）
10. EventBus=None 降级（warning + reflowed=True）
11. EventBus.publish 异常降级（捕获 + warning + 不抛出）
12. 事件载荷路径 A（linked_gap_id 非 None + regression_signal None）
13. 事件载荷路径 B（regression_signal 非 None + linked_gap_id None）
14. ReflowEvent asdict 序列化 + event_type 固定
15. 路径判定 6 种组合
16. 事件驱动解耦（无 Orchestrator/ORB01 导入）

全 mock（FakeBugReport + FakeEventBus），无 DB / 无 ORB01 依赖。
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from agent.gap_mgmt.reflow_manager import ReflowEvent, ReflowManager, ReflowResult
from agent.schemas.bug_report import BugReportStatus


# ---------------------------------------------------------------------------
# FakeBugReport（in-memory，避免真实 DB / ORM 依赖）
# ---------------------------------------------------------------------------
class FakeBugReport:
    """in-memory BugReport 双。

    模拟 BugReport 的 status / reflow_count / id 属性（duck typing）。
    """

    def __init__(
        self,
        *,
        id: str = "bug-001",
        status: str = BugReportStatus.GAP_PENDING.value,
        reflow_count: int = 0,
    ) -> None:
        self.id = id
        self.status = status
        self.reflow_count = reflow_count


# ---------------------------------------------------------------------------
# FakeEventBus（in-memory，记录 publish 调用）
# ---------------------------------------------------------------------------
class FakeEventBus:
    """in-memory EventBus 双。

    记录 publish 调用参数；支持 inject_failure 让 publish 抛异常。
    """

    def __init__(
        self,
        *,
        publish_failure: Exception | None = None,
    ) -> None:
        self.published: list[tuple[str, dict]] = []
        self._publish_failure = publish_failure

    def publish(self, event_type: str, payload: dict) -> None:
        if self._publish_failure is not None:
            raise self._publish_failure
        self.published.append((event_type, payload))


# ---------------------------------------------------------------------------
# AC-1: 路径 A（gap_pending 补齐 → 发 bug.reflowed 事件）
# ---------------------------------------------------------------------------
class TestPathAGapFixed:
    """路径 A：gap_pending + gap 补齐 → 发 bug.reflowed 事件。"""

    @pytest.fixture
    def manager(self) -> ReflowManager:
        return ReflowManager(event_bus=FakeEventBus())

    def test_gap_pending_triggers_reflow(self, manager: ReflowManager) -> None:
        """AC-1: gap_pending → reflowed=True, trigger_path=gap_fixed。"""
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is True
        assert result.trigger_path == "gap_fixed"
        assert result.skipped is False

    def test_event_bus_publish_called(self, manager: ReflowManager) -> None:
        """AC-1: EventBus.publish 被调，事件类型为 bug.reflowed。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert len(bus.published) == 1
        event_type, _ = bus.published[0]
        assert event_type == "bug.reflowed"

    def test_event_payload_trigger_path_gap_fixed(
        self, manager: ReflowManager
    ) -> None:
        """AC-1: 事件载荷 trigger_path=gap_fixed。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        _, payload = bus.published[0]
        assert payload["trigger_path"] == "gap_fixed"

    def test_event_payload_linked_gap_id(self, manager: ReflowManager) -> None:
        """AC-1: 事件载荷 linked_gap_id 为传入的 gap_id。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        manager.trigger_by_gap_fixed(bug, gap_id="gap-999")

        _, payload = bus.published[0]
        assert payload["linked_gap_id"] == "gap-999"

    def test_event_payload_reflow_count_incremented(
        self, manager: ReflowManager
    ) -> None:
        """AC-1: 事件载荷 reflow_count = bug.reflow_count + 1。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value,
            reflow_count=2,
        )
        manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        _, payload = bus.published[0]
        assert payload["reflow_count"] == 3

    def test_non_gap_pending_skipped(self, manager: ReflowManager) -> None:
        """AC-1: 非 gap_pending 状态 → skipped=True, reason=not_gap_pending。"""
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.skipped is True
        assert result.reason == "not_gap_pending"
        assert result.reflowed is False


# ---------------------------------------------------------------------------
# AC-2: 路径 B（concluded/reflected + regression → 发 bug.reflowed 事件）
# ---------------------------------------------------------------------------
class TestPathBRegression:
    """路径 B：concluded/reflected + regression → 发 bug.reflowed 事件。"""

    @pytest.fixture
    def manager(self) -> ReflowManager:
        return ReflowManager(event_bus=FakeEventBus())

    def test_concluded_triggers_reflow(self, manager: ReflowManager) -> None:
        """AC-2: concluded + regression → reflowed=True。"""
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        result = manager.trigger_by_regression(
            bug, regression_signal={"test": "failed"}
        )

        assert result.reflowed is True
        assert result.trigger_path == "regression_feedback"

    def test_reflected_triggers_reflow(self, manager: ReflowManager) -> None:
        """AC-2: reflected + regression → 同样触发回流。"""
        bug = FakeBugReport(status=BugReportStatus.REFLECTED.value)
        result = manager.trigger_by_regression(
            bug, regression_signal={"test": "failed"}
        )

        assert result.reflowed is True
        assert result.trigger_path == "regression_feedback"

    def test_event_payload_trigger_path_regression(
        self, manager: ReflowManager
    ) -> None:
        """AC-2: 事件载荷 trigger_path=regression_feedback。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        manager.trigger_by_regression(bug, regression_signal={"test": "failed"})

        _, payload = bus.published[0]
        assert payload["trigger_path"] == "regression_feedback"

    def test_event_payload_regression_signal(self, manager: ReflowManager) -> None:
        """AC-2: 事件载荷 regression_signal 携带回归信号。"""
        bus = manager._event_bus  # type: ignore[attr-defined]
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        signal = {"outcome": "regression", "test_id": "T-42"}
        manager.trigger_by_regression(bug, regression_signal=signal)

        _, payload = bus.published[0]
        assert payload["regression_signal"] == signal

    def test_non_concluded_reflected_skipped(self, manager: ReflowManager) -> None:
        """AC-2: 非 concluded/reflected → skipped=True。"""
        bug = FakeBugReport(status=BugReportStatus.VERIFIED.value)
        result = manager.trigger_by_regression(
            bug, regression_signal={"test": "failed"}
        )

        assert result.skipped is True
        assert result.reason == "invalid_state_for_regression_reflow"
        assert result.reflowed is False


# ---------------------------------------------------------------------------
# AC-3 + AC-6: ReflowEvent / ReflowResult dataclass 完整性
# ---------------------------------------------------------------------------
class TestReflowEventDataclass:
    """ReflowEvent dataclass 字段 / 序列化 / event_type 固定常量。"""

    def test_reflow_event_is_dataclass(self) -> None:
        """AC-3/AC-6: ReflowEvent 为 @dataclass。"""
        assert dataclasses.is_dataclass(ReflowEvent)

    def test_reflow_event_fields(self) -> None:
        """AC-3: 字段——bug_report_id / reflow_count / trigger_path /
        linked_gap_id / regression_signal。"""
        event = ReflowEvent(
            bug_report_id="bug-001",
            reflow_count=1,
            trigger_path="gap_fixed",
        )
        assert event.bug_report_id == "bug-001"
        assert event.reflow_count == 1
        assert event.trigger_path == "gap_fixed"
        assert event.linked_gap_id is None
        assert event.regression_signal is None

    def test_trigger_path_values(self) -> None:
        """AC-3: trigger_path 取值为 gap_fixed / regression_feedback /
        limit_exceeded 之一。"""
        valid_paths = {"gap_fixed", "regression_feedback", "limit_exceeded"}
        for path in valid_paths:
            event = ReflowEvent(
                bug_report_id="bug-x", reflow_count=1, trigger_path=path
            )
            assert event.trigger_path == path

    def test_path_a_event_linked_gap_id_not_none(self) -> None:
        """AC-3: 路径 A 事件 linked_gap_id 非 None, regression_signal None。"""
        manager = ReflowManager(event_bus=FakeEventBus())
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.event is not None
        assert result.event.linked_gap_id == "gap-001"
        assert result.event.regression_signal is None

    def test_path_b_event_regression_signal_not_none(self) -> None:
        """AC-3: 路径 B 事件 regression_signal 非 None, linked_gap_id None。"""
        manager = ReflowManager(event_bus=FakeEventBus())
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        result = manager.trigger_by_regression(
            bug, regression_signal={"outcome": "regression"}
        )

        assert result.event is not None
        assert result.event.regression_signal is not None
        assert result.event.linked_gap_id is None

    def test_event_type_constant(self) -> None:
        """AC-3/AC-6: event_type 固定为 bug.reflowed。"""
        event = ReflowEvent(
            bug_report_id="bug-001", reflow_count=1, trigger_path="gap_fixed"
        )
        assert event.event_type == "bug.reflowed"

    def test_asdict_serializable(self) -> None:
        """AC-6: ReflowEvent 可通过 asdict() 序列化为 dict。"""
        event = ReflowEvent(
            bug_report_id="bug-001",
            reflow_count=2,
            trigger_path="regression_feedback",
            regression_signal={"key": "value"},
        )
        d = dataclasses.asdict(event)
        assert isinstance(d, dict)
        assert d["bug_report_id"] == "bug-001"
        assert d["reflow_count"] == 2
        assert d["trigger_path"] == "regression_feedback"
        assert d["regression_signal"] == {"key": "value"}

    def test_reflow_result_is_dataclass(self) -> None:
        """AC-6: ReflowResult 为 @dataclass。"""
        assert dataclasses.is_dataclass(ReflowResult)

    def test_reflow_result_fields(self) -> None:
        """AC-6: ReflowResult 字段——reflowed / trigger_path / wont_reflow /
        reflow_count / skipped / reason / event。"""
        field_names = {f.name for f in dataclasses.fields(ReflowResult)}
        expected = {
            "reflowed",
            "trigger_path",
            "wont_reflow",
            "reflow_count",
            "skipped",
            "reason",
            "event",
        }
        assert expected <= field_names


# ---------------------------------------------------------------------------
# AC-4: reflow_count 超限 → 不发事件 + 转 wont_reflow
# ---------------------------------------------------------------------------
class TestReflowCountLimit:
    """reflow_count 上限检查 + wont_reflow 信号。"""

    def test_count_below_limit_normal(self) -> None:
        """AC-4: reflow_count=2 + 路径 A → 自增到 3, 未超限, 正常发事件。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=3)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=2
        )
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is True
        assert result.reflow_count == 3
        assert result.wont_reflow is False
        assert len(bus.published) == 1

    def test_count_at_limit_still_ok(self) -> None:
        """AC-4: reflow_count=1 → 自增到 2, 未超限（max=3）。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=3)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=1
        )
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is True
        assert result.reflow_count == 2
        assert len(bus.published) == 1

    def test_count_exceeds_limit_wont_reflow(self) -> None:
        """AC-4: reflow_count=3 + 路径 A → 已达上限, wont_reflow=True。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=3)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=3
        )
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is False
        assert result.wont_reflow is True
        assert result.trigger_path == "limit_exceeded"

    def test_exceed_limit_no_event_published(self) -> None:
        """AC-4: 超限时 EventBus.publish 不被调用。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=3)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=3
        )
        manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert len(bus.published) == 0

    def test_max_reflow_count_custom(self) -> None:
        """AC-4: max_reflow_count=5, reflow_count=3 → 未超限。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=5)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=3
        )
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is True
        assert result.reflow_count == 4
        assert result.wont_reflow is False


# ---------------------------------------------------------------------------
# AC-5: 事件驱动解耦（不调 ORB01, 只产事件）
# ---------------------------------------------------------------------------
class TestEventDrivenDecouple:
    """事件驱动解耦：无 Orchestrator/ORB01 依赖 + EventBus 降级。"""

    def test_no_orchestrator_import_in_source(self) -> None:
        """AC-5: ReflowManager 源码中无 Orchestrator / ORB01 导入或调用。

        检查 import 行和函数体中无对 orchestrator 模块的引用（docstring 中的
        设计说明性文字允许出现 ORB01，但实际代码不得导入或调用）。
        """
        import agent.gap_mgmt.reflow_manager as module

        source = inspect.getsource(module)

        # 检查不含 orchestrator 的 import 语句
        for line in source.splitlines():
            stripped = line.strip()
            if stripped.startswith("import ") or stripped.startswith("from "):
                assert "orchestrator" not in stripped.lower(), (
                    f"orchestrator import found: {stripped}"
                )

        # 检查模块的全局名称空间不含 Orchestrator / ORB01 相关符号
        for name in dir(module):
            lower = name.lower()
            assert "orchestrator" not in lower, (
                f"orchestrator symbol in module namespace: {name}"
            )

        # 检查 ReflowManager 类不含 orchestrator 相关方法或属性
        for name in dir(ReflowManager):
            lower = name.lower()
            assert "orchestrator" not in lower, (
                f"orchestrator method/attr in ReflowManager: {name}"
            )

    def test_event_bus_none_degradation(self) -> None:
        """AC-5: EventBus=None → warning + reflowed=True（判定不受影响）。"""
        manager = ReflowManager(event_bus=None)
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        # 判定结论不受 EventBus 缺失影响
        assert result.reflowed is True
        assert result.event is not None

    def test_event_bus_publish_exception_degradation(self) -> None:
        """AC-5: EventBus.publish 抛异常 → 捕获 + 不抛出 + reflowed=True。"""
        bus = FakeEventBus(publish_failure=RuntimeError("connection lost"))
        manager = ReflowManager(event_bus=bus)
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)

        # 不应抛出异常
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        # 判定结论不受 publish 失败影响
        assert result.reflowed is True

    def test_only_side_effect_is_event_bus_publish(self) -> None:
        """AC-5: 回流触发后唯一副作用是 EventBus.publish（+ 返回 ReflowResult）。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus)
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        # 唯一外部副作用：一次 publish 调用
        assert len(bus.published) == 1
        # 返回值是 ReflowResult
        assert isinstance(result, ReflowResult)


# ---------------------------------------------------------------------------
# AC-7: 回流路径判定（determine_reflow_path）
# ---------------------------------------------------------------------------
class TestDetermineReflowPath:
    """determine_reflow_path 的 6 种组合判定。"""

    @pytest.fixture
    def manager(self) -> ReflowManager:
        return ReflowManager(event_bus=FakeEventBus())

    def test_gap_pending_with_gap_fixed_signal(self, manager: ReflowManager) -> None:
        """AC-7: gap_pending + gap_fixed 信号 → gap_fixed。"""
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        path = manager.determine_reflow_path(bug, gap_fixed="gap-001")
        assert path == "gap_fixed"

    def test_concluded_with_regression_signal(
        self, manager: ReflowManager
    ) -> None:
        """AC-7: concluded + regression 信号 → regression_feedback。"""
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        path = manager.determine_reflow_path(
            bug, regression_signal={"outcome": "regression"}
        )
        assert path == "regression_feedback"

    def test_reflected_with_regression_signal(
        self, manager: ReflowManager
    ) -> None:
        """AC-7: reflected + regression 信号 → regression_feedback。"""
        bug = FakeBugReport(status=BugReportStatus.REFLECTED.value)
        path = manager.determine_reflow_path(
            bug, regression_signal={"outcome": "regression"}
        )
        assert path == "regression_feedback"

    def test_invalid_state_returns_none(self, manager: ReflowManager) -> None:
        """AC-7: proposed/verifying/fixing 状态 → None。"""
        for status in [
            BugReportStatus.FIXING.value,
            BugReportStatus.VERIFIED.value,
            BugReportStatus.RECEIVED.value,
        ]:
            bug = FakeBugReport(status=status)
            path = manager.determine_reflow_path(
                bug, gap_fixed="gap-001", regression_signal={"x": 1}
            )
            assert path is None, f"status={status} should return None"

    def test_gap_pending_without_gap_fixed_signal(
        self, manager: ReflowManager
    ) -> None:
        """AC-7: gap_pending 但无 gap_fixed 信号 → None。"""
        bug = FakeBugReport(status=BugReportStatus.GAP_PENDING.value)
        path = manager.determine_reflow_path(bug, gap_fixed=None)
        assert path is None

    def test_concluded_without_regression_signal(
        self, manager: ReflowManager
    ) -> None:
        """AC-7: concluded 但无 regression 信号 → None。"""
        bug = FakeBugReport(status=BugReportStatus.CONCLUDED.value)
        path = manager.determine_reflow_path(bug, regression_signal=None)
        assert path is None


# ---------------------------------------------------------------------------
# AC-8: 补充场景（reflow_count 零值、路径 B 超限）
# ---------------------------------------------------------------------------
class TestAdditionalScenarios:
    """补充覆盖场景。"""

    def test_reflow_count_zero_first_reflow(self) -> None:
        """AC-8: reflow_count=0（首次回流）→ 自增到 1。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus)
        bug = FakeBugReport(
            status=BugReportStatus.GAP_PENDING.value, reflow_count=0
        )
        result = manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        assert result.reflowed is True
        assert result.reflow_count == 1

    def test_path_b_exceeds_limit(self) -> None:
        """AC-8: 路径 B 超限 → wont_reflow=True（路径 B 同样受 reflow_count 约束）。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus, max_reflow_count=3)
        bug = FakeBugReport(
            status=BugReportStatus.CONCLUDED.value, reflow_count=3
        )
        result = manager.trigger_by_regression(
            bug, regression_signal={"outcome": "regression"}
        )

        assert result.reflowed is False
        assert result.wont_reflow is True
        assert len(bus.published) == 0

    def test_event_payload_bug_report_id(self) -> None:
        """AC-8: 事件载荷 bug_report_id 为 bug_report.id。"""
        bus = FakeEventBus()
        manager = ReflowManager(event_bus=bus)
        bug = FakeBugReport(
            id="bug-special-42",
            status=BugReportStatus.GAP_PENDING.value,
        )
        manager.trigger_by_gap_fixed(bug, gap_id="gap-001")

        _, payload = bus.published[0]
        assert payload["bug_report_id"] == "bug-special-42"
