"""BugReport 14 态状态机迁移矩阵测试（R001-INT02）。

依据：
- Sprint Contract R001-INT02（mode: direct）
- agent/orchestrator.py STATE_TRANSITIONS 矩阵（参考但测试独立）
- agent/schemas/bug_report.py BugReportStatus 14 态枚举

覆盖：
- AC-1：BugReport 14 态（路径 A+B）合法迁移 100%
- AC-2：非法迁移全判（至少 10+ 关键非法路径）

纯逻辑测试，无 DB 依赖：直接测 STATE_TRANSITIONS / can_transition / transition_to。
"""
from __future__ import annotations

import pytest

from agent.orchestrator import (
    InvalidStateTransition,
    STATE_TRANSITIONS,
    can_transition,
    transition_to,
)
from agent.schemas.bug_report import BugReportStatus


# ---------------------------------------------------------------------------
# 全量 (from, to) 组合：14 × 14 = 196
# ---------------------------------------------------------------------------
_ALL_STATUSES = list(BugReportStatus)

# 合法迁移集合（路径 A + B 主链 + 分支）
_LEGAL_TRANSITIONS: frozenset[tuple[BugReportStatus, BugReportStatus]] = frozenset({
    # 主路径
    (BugReportStatus.RECEIVED, BugReportStatus.ASSESSING),
    (BugReportStatus.ASSESSING, BugReportStatus.DEGRADED),
    (BugReportStatus.ASSESSING, BugReportStatus.REPRODUCING),
    # 路径 A 回流
    (BugReportStatus.DEGRADED, BugReportStatus.RECEIVED),
    # 诊断主链
    (BugReportStatus.REPRODUCING, BugReportStatus.LOCATED),
    (BugReportStatus.LOCATED, BugReportStatus.FIXING),
    (BugReportStatus.LOCATED, BugReportStatus.GAP_PENDING),
    (BugReportStatus.FIXING, BugReportStatus.VERIFIED),
    # 根因回退
    (BugReportStatus.FIXING, BugReportStatus.LOCATED),
    # PR 分流
    (BugReportStatus.VERIFIED, BugReportStatus.PR_OPEN),
    (BugReportStatus.VERIFIED, BugReportStatus.DRAFT_PR),
    (BugReportStatus.PR_OPEN, BugReportStatus.CONCLUDED),
    (BugReportStatus.DRAFT_PR, BugReportStatus.CONCLUDED),
    # 反思
    (BugReportStatus.CONCLUDED, BugReportStatus.REFLECTED),
    # 路径 B：concluded | reflected → reflowed → received
    (BugReportStatus.CONCLUDED, BugReportStatus.REFLOWED),
    (BugReportStatus.REFLECTED, BugReportStatus.REFLOWED),
    (BugReportStatus.REFLOWED, BugReportStatus.RECEIVED),
    # 缺口分支
    (BugReportStatus.GAP_PENDING, BugReportStatus.WONT_REFLOW),
    (BugReportStatus.GAP_PENDING, BugReportStatus.RECEIVED),
})

# 非法迁移 = 全量组合 - 合法迁移 - 自环 (from == to)
_ILLEGAL_TRANSITIONS: list[tuple[BugReportStatus, BugReportStatus]] = [
    (f, t)
    for f in _ALL_STATUSES
    for t in _ALL_STATUSES
    if f != t and (f, t) not in _LEGAL_TRANSITIONS
]


# ---------------------------------------------------------------------------
# 基础：14 态枚举完整性
# ---------------------------------------------------------------------------
class TestBugReport14States:
    """14 态枚举与迁移矩阵基础校验。"""

    def test_enum_has_exactly_14_states(self) -> None:
        """BugReportStatus 必须是 14 态。"""
        assert len(list(BugReportStatus)) == 14

    def test_all_states_in_transition_matrix(self) -> None:
        """所有 14 态在 STATE_TRANSITIONS 的 key 中均有定义。"""
        for status in BugReportStatus:
            assert status in STATE_TRANSITIONS, (
                f"{status.value} missing from STATE_TRANSITIONS"
            )

    def test_legal_transition_set_matches_matrix(self) -> None:
        """合法迁移集合与 STATE_TRANSITIONS 矩阵完全一致。"""
        for from_status in BugReportStatus:
            matrix_allowed = STATE_TRANSITIONS[from_status]
            declared_allowed = {
                t for (f, t) in _LEGAL_TRANSITIONS if f == from_status
            }
            assert matrix_allowed == declared_allowed, (
                f"mismatch for {from_status.value}: "
                f"matrix={ {s.value for s in matrix_allowed} }, "
                f"declared={ {s.value for s in declared_allowed} }"
            )


# ---------------------------------------------------------------------------
# AC-1：合法迁移参数化（路径 A + B 全覆盖）
# ---------------------------------------------------------------------------
class TestLegalTransitions:
    """14 态全部合法迁移（路径 A+B）。"""

    @pytest.mark.parametrize(
        "from_status,to_status",
        sorted(_LEGAL_TRANSITIONS, key=lambda pair: (pair[0].value, pair[1].value)),
        ids=[
            f"{f.value}->{t.value}"
            for f, t in sorted(
                _LEGAL_TRANSITIONS, key=lambda pair: (pair[0].value, pair[1].value)
            )
        ],
    )
    def test_legal_transition_succeeds(
        self,
        from_status: BugReportStatus,
        to_status: BugReportStatus,
    ) -> None:
        """合法迁移：can_transition=True + transition_to 返回目标状态。"""
        # can_transition 判断
        assert can_transition(from_status, to_status) is True
        # transition_to 执行成功并返回 target
        result = transition_to(from_status, to_status)
        assert result == to_status

    def test_legal_transition_count(self) -> None:
        """合法迁移总数 = 19（路径 A+B 完整定义）。"""
        assert len(_LEGAL_TRANSITIONS) == 19


# ---------------------------------------------------------------------------
# AC-2：非法迁移参数化（全判）
# ---------------------------------------------------------------------------
class TestIllegalTransitions:
    """所有非法迁移组合（196 - 19 - 14自环 = 163 条）。"""

    @pytest.mark.parametrize(
        "from_status,to_status",
        _ILLEGAL_TRANSITIONS,
        ids=[f"{f.value}->{t.value}" for f, t in _ILLEGAL_TRANSITIONS],
    )
    def test_illegal_transition_rejected(
        self,
        from_status: BugReportStatus,
        to_status: BugReportStatus,
    ) -> None:
        """非法迁移：can_transition=False + transition_to 抛 InvalidStateTransition。"""
        assert can_transition(from_status, to_status) is False
        with pytest.raises(InvalidStateTransition):
            transition_to(from_status, to_status)


# ---------------------------------------------------------------------------
# 关键非法路径单独标注（INV 约束 + 终态保护）
# ---------------------------------------------------------------------------
class TestCriticalIllegalPaths:
    """关键非法路径专项（INV-3 终态保护、跨阶段跳跃、逆向回流）。"""

    # 至少 10+ 关键非法路径
    CRITICAL_ILLEGAL: list[tuple[BugReportStatus, BugReportStatus, str]] = [
        # INV-3：concluded 唯一回退仅 reflowed（其余均为非法）
        (BugReportStatus.CONCLUDED, BugReportStatus.FIXING, "INV-3 concluded 不可回退到 fixing"),
        (BugReportStatus.CONCLUDED, BugReportStatus.VERIFIED, "INV-3 concluded 不可回退到 verified"),
        (BugReportStatus.CONCLUDED, BugReportStatus.RECEIVED, "INV-3 concluded 不可直接回 received"),
        (BugReportStatus.CONCLUDED, BugReportStatus.PR_OPEN, "INV-3 concluded 不可回退到 pr_open"),
        # 终态保护：wont_reflow 无任何迁出
        (BugReportStatus.WONT_REFLOW, BugReportStatus.RECEIVED, "wont_reflow 终态无迁出"),
        (BugReportStatus.WONT_REFLOW, BugReportStatus.CONCLUDED, "wont_reflow 终态无迁出"),
        # 跨阶段跳跃
        (BugReportStatus.RECEIVED, BugReportStatus.FIXING, "received 不可跳到 fixing"),
        (BugReportStatus.RECEIVED, BugReportStatus.CONCLUDED, "received 不可跳到 concluded"),
        (BugReportStatus.ASSESSING, BugReportStatus.PR_OPEN, "assessing 不可跳到 pr_open"),
        (BugReportStatus.LOCATED, BugReportStatus.CONCLUDED, "located 不可跳到 concluded"),
        # 逆向
        (BugReportStatus.VERIFIED, BugReportStatus.FIXING, "verified 不可逆回 fixing"),
        (BugReportStatus.PR_OPEN, BugReportStatus.VERIFIED, "pr_open 不可逆回 verified"),
        (BugReportStatus.REFLECTED, BugReportStatus.CONCLUDED, "reflected 不可逆回 concluded"),
        # 自身迁移非法（不在矩阵中）
        (BugReportStatus.RECEIVED, BugReportStatus.RECEIVED, "received 不可自环"),
        (BugReportStatus.CONCLUDED, BugReportStatus.CONCLUDED, "concluded 不可自环"),
    ]

    @pytest.mark.parametrize(
        "from_status,to_status,reason",
        CRITICAL_ILLEGAL,
        ids=[c[2] for c in CRITICAL_ILLEGAL],
    )
    def test_critical_illegal_path(
        self,
        from_status: BugReportStatus,
        to_status: BugReportStatus,
        reason: str,
    ) -> None:
        """关键非法路径（INV 约束 + 终态保护 + 跨阶段跳跃 + 逆向）。"""
        assert can_transition(from_status, to_status) is False, reason
        with pytest.raises(InvalidStateTransition):
            transition_to(from_status, to_status)


# ---------------------------------------------------------------------------
# 路径 A：缺口补齐回流
# ---------------------------------------------------------------------------
class TestPathAReflow:
    """路径 A：degraded → received（缺口补齐后回流重跑）。"""

    def test_degraded_to_received_allowed(self) -> None:
        """路径 A 回流：degraded → received。"""
        assert can_transition(BugReportStatus.DEGRADED, BugReportStatus.RECEIVED)
        assert transition_to(
            BugReportStatus.DEGRADED, BugReportStatus.RECEIVED
        ) == BugReportStatus.RECEIVED

    def test_gap_pending_to_received_allowed(self) -> None:
        """gap_pending → received（补齐后回流）。"""
        assert can_transition(BugReportStatus.GAP_PENDING, BugReportStatus.RECEIVED)
        assert transition_to(
            BugReportStatus.GAP_PENDING, BugReportStatus.RECEIVED
        ) == BugReportStatus.RECEIVED

    def test_gap_pending_to_wont_reflow_allowed(self) -> None:
        """gap_pending → wont_reflow（超回流上限，终态）。"""
        assert can_transition(
            BugReportStatus.GAP_PENDING, BugReportStatus.WONT_REFLOW
        )


# ---------------------------------------------------------------------------
# 路径 B：regression-feedback 回流
# ---------------------------------------------------------------------------
class TestPathBRegressionReflow:
    """路径 B：concluded/reflected → reflowed → received。"""

    def test_concluded_to_reflowed_allowed(self) -> None:
        """concluded → reflowed（INV-3 唯一允许的 concluded 后迁移）。"""
        assert can_transition(BugReportStatus.CONCLUDED, BugReportStatus.REFLOWED)

    def test_reflected_to_reflowed_allowed(self) -> None:
        """reflected → reflowed。"""
        assert can_transition(BugReportStatus.REFLECTED, BugReportStatus.REFLOWED)

    def test_reflowed_to_received_allowed(self) -> None:
        """reflowed → received（重跑主链）。"""
        assert can_transition(BugReportStatus.REFLOWED, BugReportStatus.RECEIVED)

    def test_concluded_only_two_outgoing(self) -> None:
        """concluded 只有 2 个合法迁出（reflected + reflowed，INV-3）。"""
        allowed = STATE_TRANSITIONS[BugReportStatus.CONCLUDED]
        assert allowed == frozenset({
            BugReportStatus.REFLECTED,
            BugReportStatus.REFLOWED,
        })


# ---------------------------------------------------------------------------
# 终态保护
# ---------------------------------------------------------------------------
class TestTerminalStates:
    """终态保护：wont_reflow 无任何迁出。"""

    def test_wont_reflow_is_terminal(self) -> None:
        """wont_reflow 终态无迁出。"""
        assert STATE_TRANSITIONS[BugReportStatus.WONT_REFLOW] == frozenset()

    @pytest.mark.parametrize("target", _ALL_STATUSES)
    def test_wont_reflow_cannot_transition_to_any(
        self, target: BugReportStatus
    ) -> None:
        """wont_reflow 不能迁移到任何状态（包括自身）。"""
        assert can_transition(BugReportStatus.WONT_REFLOW, target) is False
