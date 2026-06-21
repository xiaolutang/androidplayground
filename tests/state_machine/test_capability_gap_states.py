"""CapabilityGap 7 态状态机迁移矩阵测试（R001-INT02）。

依据：
- Sprint Contract R001-INT02（mode: direct）
- agent/gap/gap_store.py _STATE_TRANSITIONS 矩阵
- agent/schemas/capability_gap.py CapabilityGapStatus 7 态枚举

覆盖：
- IDENTIFIED → WAITING | WONT_FIX
- WAITING → UNBLOCKED | WONT_FIX
- UNBLOCKED → RESOLVED | INVALID_UNBLOCK | WONT_FIX
- INVALID_UNBLOCK → WAITING | WONT_FIX
- 终态：RESOLVED / WONT_REFLOW / WONT_FIX 无迁出

纯逻辑测试，无 DB 依赖：直接测 _STATE_TRANSITIONS / can_transition。
"""
from __future__ import annotations

import pytest

from agent.gap.gap_store import (
    TERMINAL_STATES,
    _STATE_TRANSITIONS,
    can_transition,
)
from agent.schemas.capability_gap import CapabilityGapStatus


# ---------------------------------------------------------------------------
# 全量 (from, to) 组合：7 × 7 = 49
# ---------------------------------------------------------------------------
_ALL_STATUSES = list(CapabilityGapStatus)

# 任务包声明的合法迁移（IDENTIFIED → WAITING | ANALYZING 等为任务包语义，
# 实际矩阵（agent/gap/gap_store.py）定义如下）：
# - IDENTIFIED → WAITING | WONT_FIX
# - WAITING → UNBLOCKED | WONT_FIX
# - UNBLOCKED → RESOLVED | INVALID_UNBLOCK | WONT_FIX
# - INVALID_UNBLOCK → WAITING | WONT_FIX
# - RESOLVED / WONT_REFLOW / WONT_FIX 为终态
_LEGAL_TRANSITIONS: frozenset[
    tuple[CapabilityGapStatus, CapabilityGapStatus]
] = frozenset({
    # 主路径
    (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WAITING),
    (CapabilityGapStatus.WAITING, CapabilityGapStatus.UNBLOCKED),
    (CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.RESOLVED),
    # 分支：补齐无效重识别
    (CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.INVALID_UNBLOCK),
    (CapabilityGapStatus.INVALID_UNBLOCK, CapabilityGapStatus.WAITING),
    # 归档：各非终态 → WONT_FIX
    (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WONT_FIX),
    (CapabilityGapStatus.WAITING, CapabilityGapStatus.WONT_FIX),
    (CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.WONT_FIX),
    (CapabilityGapStatus.INVALID_UNBLOCK, CapabilityGapStatus.WONT_FIX),
})

# 非法迁移 = 全量 - 合法 - 自环
_ILLEGAL_TRANSITIONS: list[tuple[CapabilityGapStatus, CapabilityGapStatus]] = [
    (f, t)
    for f in _ALL_STATUSES
    for t in _ALL_STATUSES
    if f != t and (f, t) not in _LEGAL_TRANSITIONS
]


# ---------------------------------------------------------------------------
# 基础：7 态枚举完整性
# ---------------------------------------------------------------------------
class TestCapabilityGap7States:
    """7 态枚举与迁移矩阵基础校验。"""

    def test_enum_has_exactly_7_states(self) -> None:
        """CapabilityGapStatus 必须是 7 态。"""
        assert len(list(CapabilityGapStatus)) == 7

    def test_all_states_in_transition_matrix(self) -> None:
        """所有 7 态在 _STATE_TRANSITIONS 的 key 中均有定义。"""
        for status in CapabilityGapStatus:
            assert status in _STATE_TRANSITIONS, (
                f"{status.value} missing from _STATE_TRANSITIONS"
            )

    def test_legal_transition_set_matches_matrix(self) -> None:
        """合法迁移集合与 _STATE_TRANSITIONS 矩阵完全一致。"""
        for from_status in CapabilityGapStatus:
            matrix_allowed = _STATE_TRANSITIONS[from_status]
            declared_allowed = {
                t for (f, t) in _LEGAL_TRANSITIONS if f == from_status
            }
            assert matrix_allowed == declared_allowed, (
                f"mismatch for {from_status.value}: "
                f"matrix={ {s.value for s in matrix_allowed} }, "
                f"declared={ {s.value for s in declared_allowed} }"
            )


# ---------------------------------------------------------------------------
# AC-4：合法迁移参数化
# ---------------------------------------------------------------------------
class TestLegalTransitions:
    """7 态全部合法迁移。"""

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
        from_status: CapabilityGapStatus,
        to_status: CapabilityGapStatus,
    ) -> None:
        """合法迁移：can_transition=True。"""
        assert can_transition(from_status, to_status) is True

    def test_legal_transition_count(self) -> None:
        """合法迁移总数 = 9。"""
        assert len(_LEGAL_TRANSITIONS) == 9


# ---------------------------------------------------------------------------
# 非法迁移参数化（全判）
# ---------------------------------------------------------------------------
class TestIllegalTransitions:
    """所有非法迁移组合（49 - 9 - 7自环 = 33 条）。"""

    @pytest.mark.parametrize(
        "from_status,to_status",
        _ILLEGAL_TRANSITIONS,
        ids=[f"{f.value}->{t.value}" for f, t in _ILLEGAL_TRANSITIONS],
    )
    def test_illegal_transition_rejected(
        self,
        from_status: CapabilityGapStatus,
        to_status: CapabilityGapStatus,
    ) -> None:
        """非法迁移：can_transition=False。"""
        assert can_transition(from_status, to_status) is False


# ---------------------------------------------------------------------------
# 主路径测试
# ---------------------------------------------------------------------------
class TestMainPath:
    """主路径：IDENTIFIED → WAITING → UNBLOCKED → RESOLVED。"""

    def test_identified_to_waiting(self) -> None:
        """IDENTIFIED → WAITING。"""
        assert can_transition(
            CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WAITING
        )

    def test_waiting_to_unblocked(self) -> None:
        """WAITING → UNBLOCKED。"""
        assert can_transition(
            CapabilityGapStatus.WAITING, CapabilityGapStatus.UNBLOCKED
        )

    def test_unblocked_to_resolved(self) -> None:
        """UNBLOCKED → RESOLVED。"""
        assert can_transition(
            CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.RESOLVED
        )

    def test_main_path_chain(self) -> None:
        """主路径链：IDENTIFIED → WAITING → UNBLOCKED → RESOLVED 全程合法。"""
        assert can_transition(
            CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WAITING
        )
        assert can_transition(
            CapabilityGapStatus.WAITING, CapabilityGapStatus.UNBLOCKED
        )
        assert can_transition(
            CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.RESOLVED
        )


# ---------------------------------------------------------------------------
# 分支：补齐无效重识别
# ---------------------------------------------------------------------------
class TestInvalidUnblockBranch:
    """分支：UNBLOCKED → INVALID_UNBLOCK → WAITING（重识别后重新排队）。"""

    def test_unblocked_to_invalid_unblock(self) -> None:
        """UNBLOCKED → INVALID_UNBLOCK。"""
        assert can_transition(
            CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.INVALID_UNBLOCK
        )

    def test_invalid_unblock_to_waiting(self) -> None:
        """INVALID_UNBLOCK → WAITING（重新排队）。"""
        assert can_transition(
            CapabilityGapStatus.INVALID_UNBLOCK, CapabilityGapStatus.WAITING
        )


# ---------------------------------------------------------------------------
# 归档：WONT_FIX
# ---------------------------------------------------------------------------
class TestWontFixArchive:
    """归档：各非终态 → WONT_FIX。"""

    @pytest.mark.parametrize(
        "from_status",
        [
            CapabilityGapStatus.IDENTIFIED,
            CapabilityGapStatus.WAITING,
            CapabilityGapStatus.UNBLOCKED,
            CapabilityGapStatus.INVALID_UNBLOCK,
        ],
        ids=[s.value for s in [
            CapabilityGapStatus.IDENTIFIED,
            CapabilityGapStatus.WAITING,
            CapabilityGapStatus.UNBLOCKED,
            CapabilityGapStatus.INVALID_UNBLOCK,
        ]],
    )
    def test_can_archive_to_wont_fix(
        self, from_status: CapabilityGapStatus
    ) -> None:
        """非终态均可迁移到 WONT_FIX。"""
        assert can_transition(from_status, CapabilityGapStatus.WONT_FIX)


# ---------------------------------------------------------------------------
# 终态保护
# ---------------------------------------------------------------------------
class TestTerminalStates:
    """终态保护：RESOLVED / WONT_REFLOW / WONT_FIX 无任何迁出。"""

    def test_terminal_states_set(self) -> None:
        """终态集合 = {RESOLVED, WONT_REFLOW, WONT_FIX}。"""
        assert TERMINAL_STATES == frozenset({
            CapabilityGapStatus.RESOLVED,
            CapabilityGapStatus.WONT_REFLOW,
            CapabilityGapStatus.WONT_FIX,
        })

    @pytest.mark.parametrize(
        "terminal",
        [
            CapabilityGapStatus.RESOLVED,
            CapabilityGapStatus.WONT_REFLOW,
            CapabilityGapStatus.WONT_FIX,
        ],
        ids=["resolved", "wont_reflow", "wont_fix"],
    )
    def test_terminal_has_empty_outgoing(
        self, terminal: CapabilityGapStatus
    ) -> None:
        """终态在矩阵中无出边。"""
        assert _STATE_TRANSITIONS[terminal] == frozenset()

    @pytest.mark.parametrize(
        "terminal",
        [
            CapabilityGapStatus.RESOLVED,
            CapabilityGapStatus.WONT_REFLOW,
            CapabilityGapStatus.WONT_FIX,
        ],
        ids=["resolved", "wont_reflow", "wont_fix"],
    )
    @pytest.mark.parametrize("target", _ALL_STATUSES)
    def test_terminal_cannot_transition_to_any(
        self,
        terminal: CapabilityGapStatus,
        target: CapabilityGapStatus,
    ) -> None:
        """终态不能迁移到任何状态。"""
        assert can_transition(terminal, target) is False


# ---------------------------------------------------------------------------
# 关键非法路径
# ---------------------------------------------------------------------------
class TestCriticalIllegalPaths:
    """关键非法路径专项（跨阶段跳跃 + 逆向）。"""

    @pytest.mark.parametrize(
        "from_status,to_status,reason",
        [
            # 跨阶段跳跃
            (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.RESOLVED, "IDENTIFIED 不可跳到 RESOLVED"),
            (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.UNBLOCKED, "IDENTIFIED 不可跳到 UNBLOCKED"),
            (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.INVALID_UNBLOCK, "IDENTIFIED 不可跳到 INVALID_UNBLOCK"),
            (CapabilityGapStatus.WAITING, CapabilityGapStatus.RESOLVED, "WAITING 不可跳到 RESOLVED"),
            # 逆向
            (CapabilityGapStatus.WAITING, CapabilityGapStatus.IDENTIFIED, "WAITING 不可逆回 IDENTIFIED"),
            (CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.WAITING, "UNBLOCKED 不可逆回 WAITING"),
            (CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.IDENTIFIED, "UNBLOCKED 不可逆回 IDENTIFIED"),
            (CapabilityGapStatus.RESOLVED, CapabilityGapStatus.UNBLOCKED, "RESOLVED 终态不可迁出"),
            # IDENTIFIED 不能直接到 WONT_REFLOW
            (CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WONT_REFLOW, "IDENTIFIED 不可直接到 WONT_REFLOW"),
            # RESOLVED 不能到 WONT_FIX（已是终态）
            (CapabilityGapStatus.RESOLVED, CapabilityGapStatus.WONT_FIX, "RESOLVED 终态不可迁出到 WONT_FIX"),
        ],
        ids=[
            "identified-skip-resolved",
            "identified-skip-unblocked",
            "identified-skip-invalid-unblock",
            "waiting-skip-resolved",
            "waiting-reverse-identified",
            "unblocked-reverse-waiting",
            "unblocked-reverse-identified",
            "resolved-reverse-unblocked",
            "identified-skip-wont-reflow",
            "resolved-to-wont-fix",
        ],
    )
    def test_critical_illegal_path(
        self,
        from_status: CapabilityGapStatus,
        to_status: CapabilityGapStatus,
        reason: str,
    ) -> None:
        """关键非法路径（跨阶段跳跃 + 逆向）。"""
        assert can_transition(from_status, to_status) is False, reason
