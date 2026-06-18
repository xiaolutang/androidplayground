"""CapabilityGap 存储 + 7 态状态机 + INV-2 软删（status 改不能删）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 CapabilityGap 表（602-617 行）
- D12（状态机 7 态 + 解锁价值公式）
- INV-2：状态只能改不能删（hard delete 禁止，用 transition(WONT_FIX) 软关闭）

设计要点：
1. **7 态迁移矩阵**（_STATE_TRANSITIONS）：明确每个状态的合法迁出目标集合。
   - 主路径：identified -> waiting -> unblocked -> resolved
   - 分支：unblocked -> invalid_unblock（补齐无效）-> waiting（重识别后重新排队）
   - 归档：identified/waiting/unblocked/invalid_unblock -> wont_fix
   - 超回流上限：-> wont_reflow（由 BB011 触发，此处仅声明终态）
2. **终态保护**（TERMINAL_STATES）：resolved / wont_reflow / wont_fix 不可迁出。
3. **INV-2**：delete() 始终抛 GapDeleteError；archive() = transition(WONT_FIX)。
4. 主键 id 为 String（UUID），与 SCH01 schema 一致。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import sessionmaker

from agent.schemas.capability_gap import (
    CapabilityGap,
    CapabilityGapStatus,
)

__all__ = [
    "GapStore",
    "GapStateTransitionError",
    "GapDeleteError",
    "TERMINAL_STATES",
    "can_transition",
]


# 7 态迁移矩阵：from_state -> 合法的 to_state 集合
# 设计依据：design 4.1 D12 + CapabilityGap 状态机（第 616 行 7 态枚举）
#
# 迁移语义：
# - IDENTIFIED -> WAITING：识别后排队等待补齐
# - IDENTIFIED -> WONT_FIX：识别后直接决定不修（成本/优先级）
# - WAITING -> UNBLOCKED：补齐完成，待回流验证
# - WAITING -> WONT_FIX：等待中决定不修
# - UNBLOCKED -> RESOLVED：回流验证通过，缺口关闭（终态）
# - UNBLOCKED -> INVALID_UNBLOCK：补齐无效（重识别真实缺口）
# - UNBLOCKED -> WONT_FIX：补齐后决定不修
# - INVALID_UNBLOCK -> WAITING：重识别后重新排队
# - INVALID_UNBLOCK -> WONT_FIX：重识别后决定不修
# - WONT_REFLOW：由外部（BB011 回流超上限）直接写入终态，不在本矩阵的常规迁移路径中
#   （wont_reflow 作为终态，进入后不可迁出）
#
# 注意：WONT_REFLOW 没有入边在本矩阵中声明，因为它由 reflow_manager 直接
# 在 BugReport 层面判定后、对 CapabilityGap.status 赋值（不走 GapStore.transition）。
# 但为了完整性，本矩阵仍将其声明为终态（无出边）。
_STATE_TRANSITIONS: dict[CapabilityGapStatus, frozenset[CapabilityGapStatus]] = {
    CapabilityGapStatus.IDENTIFIED: frozenset({
        CapabilityGapStatus.WAITING,
        CapabilityGapStatus.WONT_FIX,
    }),
    CapabilityGapStatus.WAITING: frozenset({
        CapabilityGapStatus.UNBLOCKED,
        CapabilityGapStatus.WONT_FIX,
    }),
    CapabilityGapStatus.UNBLOCKED: frozenset({
        CapabilityGapStatus.RESOLVED,
        CapabilityGapStatus.INVALID_UNBLOCK,
        CapabilityGapStatus.WONT_FIX,
    }),
    # 终态：无合法迁出
    CapabilityGapStatus.RESOLVED: frozenset(),
    CapabilityGapStatus.INVALID_UNBLOCK: frozenset({
        CapabilityGapStatus.WAITING,  # 重新等待
        CapabilityGapStatus.WONT_FIX,
    }),
    CapabilityGapStatus.WONT_REFLOW: frozenset(),  # 终态
    CapabilityGapStatus.WONT_FIX: frozenset(),  # 终态
}

# 终态集合（不可迁出）
TERMINAL_STATES: frozenset[CapabilityGapStatus] = frozenset({
    CapabilityGapStatus.RESOLVED,
    CapabilityGapStatus.WONT_REFLOW,
    CapabilityGapStatus.WONT_FIX,
})


class GapStateTransitionError(Exception):
    """非法状态迁移（不在 _STATE_TRANSITIONS 允许集合中）。"""


class GapDeleteError(Exception):
    """尝试硬删 CapabilityGap（违反 INV-2）。

    INV-2 要求：CapabilityGap 状态只能改不能删。
    如需关闭缺口，使用 transition(WONT_FIX) 或 archive()。
    """


def can_transition(
    from_status: CapabilityGapStatus,
    to_status: CapabilityGapStatus,
) -> bool:
    """判断 from_status -> to_status 迁移是否合法。

    Args:
        from_status: 当前状态。
        to_status: 目标状态。

    Returns:
        True 如果迁移在 _STATE_TRANSITIONS 允许集合中。
    """
    allowed = _STATE_TRANSITIONS.get(from_status, frozenset())
    return to_status in allowed


class GapStore:
    """CapabilityGap 持久化 + 7 态状态迁移 + INV-2 守护。

    封装 CRUD + 状态机迁移 + bug 关联，所有写操作经 session_factory 开启事务。
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create(self, gap_data: dict[str, Any]) -> CapabilityGap:
        """新建 CapabilityGap，初始状态强制为 IDENTIFIED。

        Args:
            gap_data: CapabilityGap 字段字典。id 为 String PK，需调用方提供。

        Returns:
            创建后的 CapabilityGap（已 commit + refresh）。

        注意:
            - status 被强制覆盖为 IDENTIFIED，不接受调用方传入的初始状态。
            - id 需调用方在 gap_data 中提供（String PK，无自增）。
        """
        # 强制初始状态为 IDENTIFIED
        gap_data = {**gap_data, "status": CapabilityGapStatus.IDENTIFIED.value}
        with self._session_factory() as session:
            gap = CapabilityGap(**gap_data)
            session.add(gap)
            session.commit()
            session.refresh(gap)
            return gap

    def get(self, gap_id: str) -> Optional[CapabilityGap]:
        """按 id 查询单个 CapabilityGap。"""
        with self._session_factory() as session:
            return session.get(CapabilityGap, gap_id)

    def list(
        self,
        *,
        status: Optional[CapabilityGapStatus] = None,
    ) -> list[CapabilityGap]:
        """列表查询，可选按 status 过滤。

        Args:
            status: 仅返回该状态的 gap；None 返回全部。
        """
        with self._session_factory() as session:
            q = session.query(CapabilityGap)
            if status is not None:
                q = q.filter(CapabilityGap.status == status.value)
            return q.all()

    # ------------------------------------------------------------------
    # linked_bug_ids 管理
    # ------------------------------------------------------------------
    def list_linked_bugs(self, gap_id: str) -> list[str]:
        """返回该 gap 关联的 bug_report ids（linked_bug_ids JSON 字段）。

        Args:
            gap_id: CapabilityGap id。

        Returns:
            关联的 bug id 列表；gap 不存在则返回空列表。
        """
        with self._session_factory() as session:
            gap = session.get(CapabilityGap, gap_id)
            if gap is None:
                return []
            return list(gap.linked_bug_ids or [])

    def link_bug(self, gap_id: str, bug_id: str) -> CapabilityGap:
        """关联一个 bug_report 到 gap（去重）。

        Args:
            gap_id: CapabilityGap id。
            bug_id: BugReport id。

        Returns:
            更新后的 CapabilityGap。

        Raises:
            ValueError: gap 不存在。
        """
        with self._session_factory() as session:
            gap = session.get(CapabilityGap, gap_id)
            if gap is None:
                raise ValueError(f"gap {gap_id!r} not found")
            ids = list(gap.linked_bug_ids or [])
            if bug_id not in ids:
                ids.append(bug_id)
                gap.linked_bug_ids = ids
                session.commit()
                session.refresh(gap)
            return gap

    def unlink_bug(self, gap_id: str, bug_id: str) -> CapabilityGap:
        """取消关联一个 bug_report。

        Args:
            gap_id: CapabilityGap id。
            bug_id: 要移除的 BugReport id。

        Returns:
            更新后的 CapabilityGap。

        Raises:
            ValueError: gap 不存在。
        """
        with self._session_factory() as session:
            gap = session.get(CapabilityGap, gap_id)
            if gap is None:
                raise ValueError(f"gap {gap_id!r} not found")
            ids = [i for i in (gap.linked_bug_ids or []) if i != bug_id]
            gap.linked_bug_ids = ids
            session.commit()
            session.refresh(gap)
            return gap

    # ------------------------------------------------------------------
    # 状态机迁移
    # ------------------------------------------------------------------
    def transition(
        self,
        gap_id: str,
        to_status: CapabilityGapStatus,
        *,
        reason: str = "",
    ) -> CapabilityGap:
        """状态迁移。

        非法迁移（不在 _STATE_TRANSITIONS 中）抛 GapStateTransitionError。
        终态保护：终态的 from_status 在矩阵中为空集，任何迁出都会失败。

        Args:
            gap_id: CapabilityGap id。
            to_status: 目标状态。
            reason: 迁移原因（可选，用于日志/审计；当前 schema 无独立 reason
                    字段，仅做参数保留）。

        Returns:
            更新后的 CapabilityGap。

        Raises:
            ValueError: gap 不存在。
            GapStateTransitionError: from -> to 不在合法迁移矩阵中。
        """
        with self._session_factory() as session:
            gap = session.get(CapabilityGap, gap_id)
            if gap is None:
                raise ValueError(f"gap {gap_id!r} not found")
            from_status = CapabilityGapStatus(gap.status)
            if not can_transition(from_status, to_status):
                raise GapStateTransitionError(
                    f"illegal transition {from_status.value} -> {to_status.value} "
                    f"for gap {gap_id!r}; reason={reason!r}"
                )
            gap.status = to_status.value
            # reason 参数保留供未来扩展（写入 metadata 或审计表），当前 schema
            # 无独立 reason 字段，不持久化 reason。
            session.commit()
            session.refresh(gap)
            return gap

    # ------------------------------------------------------------------
    # INV-2 守护
    # ------------------------------------------------------------------
    def delete(self, gap_id: str) -> None:
        """禁止硬删（INV-2）。

        CapabilityGap 状态只能改不能删。如需关闭缺口，使用
        ``transition(gap_id, WONT_FIX)`` 或 ``archive(gap_id)``。

        Raises:
            GapDeleteError: 始终抛出。
        """
        raise GapDeleteError(
            f"hard delete CapabilityGap {gap_id!r} is forbidden (INV-2). "
            f"Use transition(WONT_FIX) or archive() to soft-close."
        )

    def archive(self, gap_id: str) -> CapabilityGap:
        """软归档：迁移到 WONT_FIX。

        如果当前状态不允许直接迁移到 WONT_FIX（如已是终态 RESOLVED），
        会抛 GapStateTransitionError。

        Args:
            gap_id: CapabilityGap id。

        Returns:
            更新后的 CapabilityGap。

        Raises:
            GapStateTransitionError: 当前状态无法迁移到 WONT_FIX（如已是终态）。
        """
        return self.transition(
            gap_id,
            CapabilityGapStatus.WONT_FIX,
            reason="archive",
        )
