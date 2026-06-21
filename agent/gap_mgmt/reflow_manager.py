"""回流管理器（R001-BB011）—— 回流路径判定 + 产 ``bug.reflowed`` 事件。

依据：
- Sprint Contract R001-BB011（status: agreed，mode: negotiated / business）
- 依赖 BF008 BugReport schema（含 reflow_count / gap_ids）
- 依赖 INF07 EventBus（publish/subscribe 机制，本任务通过 DI 接收）

设计要点：
1. **两条回流路径（互斥）**：
   - 路径 A（``trigger_by_gap_fixed``）：BugReport 处于 gap_pending，关联 Gap 被补齐
     → 发 ``bug.reflowed`` 事件，``trigger_path="gap_fixed"``。
   - 路径 B（``trigger_by_regression``）：BugReport 处于 concluded/reflected，
     出现 regression 信号 → 发 ``bug.reflowed`` 事件，
     ``trigger_path="regression_feedback"``。
2. **事件驱动解耦（核心约束）**：ReflowManager 只产事件（``EventBus.publish``），
   不调 ORB01 / Orchestrator。ORB01 订阅 ``bug.reflowed`` 事件后自主决定是否
   重跑主链。无反向依赖。
3. **reflow_count 上限（默认 3）**：``_check_reflow_limit`` 读取
   ``bug_report.reflow_count``，自增后判断是否超限。超限 → 不发事件，返回
   ``ReflowResult(wont_reflow=True, trigger_path="limit_exceeded")``，由 ORB01
   将 BugReport 置 wont_reflow 状态转人工（AP-1）。
4. **不持久化 BugReport**：本任务不写 BugReport.reflow_count / status。reflow_count
   自增值放在 ReflowResult / ReflowEvent 中返回，由调用方（ORB01）持久化。
5. **降级**：EventBus=None 或 publish 抛异常 → logging.warning 记录事件载荷，
   ReflowResult.reflowed 仍为 True（逻辑判定已完成，事件发布失败不影响判定结论）。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from agent.schemas.bug_report import BugReportStatus

logger = logging.getLogger(__name__)

__all__ = [
    "ReflowEvent",
    "ReflowResult",
    "ReflowManager",
]

# 事件类型固定常量（ORB01 订阅此 key）
_EVENT_TYPE = "bug.reflowed"

# 路径 B 允许的状态（concluded / reflected）
_REGRESSION_REFLOW_STATES: frozenset[str] = frozenset(
    {
        BugReportStatus.CONCLUDED.value,
        BugReportStatus.REFLECTED.value,
    }
)


@dataclass
class ReflowEvent:
    """回流事件载荷（发布到 EventBus）。

    Attributes:
        bug_report_id: 关联的 BugReport id。
        reflow_count: 自增后的 reflow 次数（事件载荷携带最新值）。
        trigger_path: 触发路径标识——
            ``"gap_fixed"``（路径 A）/ ``"regression_feedback"``（路径 B）/
            ``"limit_exceeded"``（超限不发事件，仅用于 ReflowResult 内部标记）。
        linked_gap_id: 路径 A 携带的关联 Gap id；路径 B 为 None。
        regression_signal: 路径 B 携带的回归信号 dict；路径 A 为 None。
    """

    bug_report_id: str
    reflow_count: int
    trigger_path: str
    linked_gap_id: Optional[str] = None
    regression_signal: Optional[dict] = None

    # event_type 为固定常量，不参与 __init__（field(init=False)）
    event_type: str = field(default=_EVENT_TYPE, init=False, repr=False, compare=False)


@dataclass
class ReflowResult:
    """回流判定结果（返回给调用方 ORB01）。

    Attributes:
        reflowed: True=已发 ``bug.reflowed`` 事件（或判定应发但 EventBus 降级）。
        trigger_path: 触发路径标识（同 ReflowEvent.trigger_path）。
        wont_reflow: True=reflow_count 超限，ORB01 应置 BugReport=wont_reflow。
        reflow_count: 自增后的 reflow 次数（调用方据此持久化）。
        skipped: True=状态不符或缺触发条件，未进入回流流程。
        reason: skipped / wont_reflow 时的人类可读原因。
        event: 构造的 ReflowEvent（即使 EventBus 降级也填充，供调用方补偿）。
    """

    reflowed: bool
    trigger_path: str
    wont_reflow: bool = False
    reflow_count: int = 0
    skipped: bool = False
    reason: Optional[str] = None
    event: Optional[ReflowEvent] = None


class ReflowManager:
    """回流管理器：判定回流路径 + 产 ``bug.reflowed`` 事件。

    事件驱动解耦——不直接调 ORB01 / Orchestrator，只通过 EventBus 发布事件。
    ORB01 订阅 ``bug.reflowed`` 后自主决定是否重跑主链。

    Usage:
        manager = ReflowManager(event_bus=event_bus, max_reflow_count=3)

        # 路径 A：Gap 补齐触发
        result = manager.trigger_by_gap_fixed(bug_report, gap_id="gap-001")
        if result.reflowed:
            # bug.reflowed 事件已发布（或降级记录）
            ...
        elif result.wont_reflow:
            # reflow_count 超限，ORB01 置 wont_reflow 状态
            ...

        # 路径 B：回归信号触发
        result = manager.trigger_by_regression(
            bug_report, regression_signal={"test": "regression_detected"},
        )

    Args:
        event_bus: INF07 EventBus 实例（需有 ``publish(event_type, payload)`` 方法）。
            None 时降级（logging.warning + ReflowResult.reflowed 仍为 True）。
        max_reflow_count: reflow 次数上限，默认 3。超限不发事件，返回 wont_reflow 信号。
    """

    def __init__(
        self,
        *,
        event_bus: Optional[Any] = None,
        max_reflow_count: int = 3,
    ) -> None:
        self._event_bus = event_bus
        self._max_reflow_count = max_reflow_count

    # ------------------------------------------------------------------
    # 路径 A：gap_pending 补齐回流
    # ------------------------------------------------------------------
    def trigger_by_gap_fixed(
        self,
        bug_report: Any,
        gap_id: str,
    ) -> ReflowResult:
        """路径 A：gap_pending 补齐 → 发 ``bug.reflowed`` 事件。

        前置条件：BugReport.status == gap_pending。其他状态 → skipped。

        Args:
            bug_report: BugReport 实例（需有 status / reflow_count / id 属性）。
            gap_id: 被补齐的 Gap id（事件载荷 linked_gap_id 携带此值）。

        Returns:
            ReflowResult——reflowed=True 表示已发事件（或降级）；
            skipped=True 表示状态不符；wont_reflow=True 表示超限。
        """
        status = self._get_status(bug_report)

        # 状态守卫：仅 gap_pending 可走路径 A
        if status != BugReportStatus.GAP_PENDING.value:
            return ReflowResult(
                reflowed=False,
                trigger_path="gap_fixed",
                skipped=True,
                reason="not_gap_pending",
                reflow_count=self._get_reflow_count(bug_report),
            )

        return self._execute_reflow(
            bug_report=bug_report,
            trigger_path="gap_fixed",
            linked_gap_id=gap_id,
            regression_signal=None,
        )

    # ------------------------------------------------------------------
    # 路径 B：regression-feedback 回流
    # ------------------------------------------------------------------
    def trigger_by_regression(
        self,
        bug_report: Any,
        regression_signal: dict,
    ) -> ReflowResult:
        """路径 B：concluded/reflected + regression → 发 ``bug.reflowed`` 事件。

        前置条件：BugReport.status in {concluded, reflected}。

        Args:
            bug_report: BugReport 实例。
            regression_signal: 回归信号 dict（事件载荷原样携带）。

        Returns:
            ReflowResult——reflowed=True 表示已发事件（或降级）；
            skipped=True 表示状态不符；wont_reflow=True 表示超限。
        """
        status = self._get_status(bug_report)

        # 状态守卫：仅 concluded / reflected 可走路径 B
        if status not in _REGRESSION_REFLOW_STATES:
            return ReflowResult(
                reflowed=False,
                trigger_path="regression_feedback",
                skipped=True,
                reason="invalid_state_for_regression_reflow",
                reflow_count=self._get_reflow_count(bug_report),
            )

        return self._execute_reflow(
            bug_report=bug_report,
            trigger_path="regression_feedback",
            linked_gap_id=None,
            regression_signal=regression_signal,
        )

    # ------------------------------------------------------------------
    # 回流路径判定
    # ------------------------------------------------------------------
    def determine_reflow_path(
        self,
        bug_report: Any,
        gap_fixed: Optional[str] = None,
        regression_signal: Optional[dict] = None,
    ) -> Optional[str]:
        """判定回流路径（纯判定，不发事件）。

        根据 BugReport 当前状态 + 触发信号返回路径标识：
        - gap_pending + gap_fixed 非 None → ``"gap_fixed"``
        - concluded/reflected + regression_signal 非 None → ``"regression_feedback"``
        - 其他 → ``None``（不可回流或缺触发条件）

        路径 A 优先于路径 B（状态互斥，实际不会同时命中）。

        Args:
            bug_report: BugReport 实例。
            gap_fixed: 路径 A 触发信号——被补齐的 Gap id（None=无信号）。
            regression_signal: 路径 B 触发信号——回归信号 dict（None=无信号）。

        Returns:
            路径标识字符串或 None。
        """
        status = self._get_status(bug_report)

        # 路径 A：gap_pending + gap_fixed 信号
        if status == BugReportStatus.GAP_PENDING.value and gap_fixed is not None:
            return "gap_fixed"

        # 路径 B：concluded/reflected + regression 信号
        if status in _REGRESSION_REFLOW_STATES and regression_signal is not None:
            return "regression_feedback"

        return None

    # ------------------------------------------------------------------
    # 内部：执行回流（共用逻辑）
    # ------------------------------------------------------------------
    def _execute_reflow(
        self,
        *,
        bug_report: Any,
        trigger_path: str,
        linked_gap_id: Optional[str],
        regression_signal: Optional[dict],
    ) -> ReflowResult:
        """执行回流判定 + 事件发布（路径 A / B 共用）。

        步骤：
        1. 检查 reflow_count 上限 → 超限返回 wont_reflow（不发事件）。
        2. 自增 reflow_count。
        3. 构造 ReflowEvent。
        4. 通过 EventBus 发布（降级处理）。
        5. 返回 ReflowResult。
        """
        current_count = self._get_reflow_count(bug_report)

        # 超限检查：当前 count >= max 时超限（第 max+1 次回流被拒）
        if self._check_reflow_limit(bug_report):
            logger.warning(
                "ReflowManager: reflow_count=%d >= max=%d for bug=%s; "
                "wont_reflow signal (AP-1: transfer to human)",
                current_count,
                self._max_reflow_count,
                self._get_bug_id(bug_report),
            )
            return ReflowResult(
                reflowed=False,
                trigger_path="limit_exceeded",
                wont_reflow=True,
                reflow_count=current_count,
                reason=(
                    f"reflow_count {current_count} >= max {self._max_reflow_count}"
                ),
            )

        # 自增 reflow_count
        new_count = current_count + 1

        # 构造事件
        event = self._build_event(
            bug_report=bug_report,
            reflow_count=new_count,
            trigger_path=trigger_path,
            linked_gap_id=linked_gap_id,
            regression_signal=regression_signal,
        )

        # 发布事件（降级处理）
        self._publish_reflow_event(event)

        return ReflowResult(
            reflowed=True,
            trigger_path=trigger_path,
            reflow_count=new_count,
            event=event,
        )

    # ------------------------------------------------------------------
    # 内部：reflow_count 上限检查
    # ------------------------------------------------------------------
    def _check_reflow_limit(self, bug_report: Any) -> bool:
        """检查 reflow_count 是否超限。

        当前 count >= max_reflow_count 时返回 True（超限，第 max+1 次被拒）。

        Args:
            bug_report: BugReport 实例。

        Returns:
            True=超限（不发事件，转 wont_reflow）；False=未超限。
        """
        current_count = self._get_reflow_count(bug_report)
        return current_count >= self._max_reflow_count

    # ------------------------------------------------------------------
    # 内部：事件发布（降级处理）
    # ------------------------------------------------------------------
    def _publish_reflow_event(self, event: ReflowEvent) -> None:
        """通过 EventBus 发布事件。

        降级策略：
        - EventBus=None → logging.warning 记录事件载荷，不抛异常。
        - EventBus.publish 抛异常 → 捕获 + logging.warning，不抛出。
        - 正常 → 调用 publish。

        无论发布成功与否，调用方（``_execute_reflow``）的 ReflowResult.reflowed
        均为 True——逻辑判定已完成，事件发布失败不影响判定结论（调用方可从
        ReflowResult.event 补偿）。
        """
        if self._event_bus is None:
            logger.warning(
                "ReflowManager: EventBus not injected; bug.reflowed event lost "
                "(event=%s)",
                asdict(event),
            )
            return

        try:
            self._event_bus.publish(_EVENT_TYPE, asdict(event))
        except Exception as exc:
            logger.warning(
                "ReflowManager: EventBus.publish failed for bug.reflowed "
                "(event=%s): %s",
                asdict(event),
                exc,
            )

    # ------------------------------------------------------------------
    # 内部：构造 ReflowEvent
    # ------------------------------------------------------------------
    @staticmethod
    def _build_event(
        *,
        bug_report: Any,
        reflow_count: int,
        trigger_path: str,
        linked_gap_id: Optional[str] = None,
        regression_signal: Optional[dict] = None,
    ) -> ReflowEvent:
        """构造 ReflowEvent 实例。"""
        return ReflowEvent(
            bug_report_id=ReflowManager._get_bug_id(bug_report),
            reflow_count=reflow_count,
            trigger_path=trigger_path,
            linked_gap_id=linked_gap_id,
            regression_signal=regression_signal,
        )

    # ------------------------------------------------------------------
    # 内部：属性读取辅助（duck typing，兼容 mock 对象）
    # ------------------------------------------------------------------
    @staticmethod
    def _get_status(bug_report: Any) -> str:
        """读取 BugReport.status（兼容 None → 空字符串）。"""
        status = getattr(bug_report, "status", None)
        return status if status is not None else ""

    @staticmethod
    def _get_reflow_count(bug_report: Any) -> int:
        """读取 BugReport.reflow_count（None → 0）。"""
        count = getattr(bug_report, "reflow_count", None)
        return count if count is not None else 0

    @staticmethod
    def _get_bug_id(bug_report: Any) -> str:
        """读取 BugReport.id。"""
        return getattr(bug_report, "id", "")
