"""BF008 单元测试：7 态状态机矩阵 + UnlockFactors 裁剪计算。

覆盖 test_tasks 场景（纯逻辑，无 DB）：
1. 7 态全部在 _STATE_TRANSITIONS 中覆盖
2. 合法迁移判断
3. 非法迁移判断
4. 终态保护（终态无出边）
5. UnlockFactors.compute 的 [0,1] 裁剪 + 乘积
"""
from __future__ import annotations

from agent.gap.gap_store import (
    _STATE_TRANSITIONS,
    TERMINAL_STATES,
    can_transition,
)
from agent.gap.unlock_value_scorer import UnlockFactors
from agent.schemas.capability_gap import CapabilityGapStatus


# ---------------------------------------------------------------------------
# 场景 1：7 态全覆盖
# ---------------------------------------------------------------------------
def test_all_7_states_covered() -> None:
    """7 态全部在 _STATE_TRANSITIONS 的 key 中。"""
    expected = {
        CapabilityGapStatus.IDENTIFIED,
        CapabilityGapStatus.WAITING,
        CapabilityGapStatus.UNBLOCKED,
        CapabilityGapStatus.RESOLVED,
        CapabilityGapStatus.INVALID_UNBLOCK,
        CapabilityGapStatus.WONT_REFLOW,
        CapabilityGapStatus.WONT_FIX,
    }
    assert set(_STATE_TRANSITIONS.keys()) == expected
    assert len(expected) == 7


# ---------------------------------------------------------------------------
# 场景 2：合法迁移
# ---------------------------------------------------------------------------
def test_legal_transitions() -> None:
    """主路径 + 分支的合法迁移。"""
    # 主路径
    assert can_transition(
        CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WAITING
    )
    assert can_transition(
        CapabilityGapStatus.WAITING, CapabilityGapStatus.UNBLOCKED
    )
    assert can_transition(
        CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.RESOLVED
    )
    # 分支
    assert can_transition(
        CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.INVALID_UNBLOCK
    )
    assert can_transition(
        CapabilityGapStatus.INVALID_UNBLOCK, CapabilityGapStatus.WAITING
    )
    # 各状态 -> WONT_FIX（归档）
    assert can_transition(
        CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WONT_FIX
    )
    assert can_transition(
        CapabilityGapStatus.WAITING, CapabilityGapStatus.WONT_FIX
    )
    assert can_transition(
        CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.WONT_FIX
    )
    assert can_transition(
        CapabilityGapStatus.INVALID_UNBLOCK, CapabilityGapStatus.WONT_FIX
    )


# ---------------------------------------------------------------------------
# 场景 3：非法迁移
# ---------------------------------------------------------------------------
def test_illegal_transitions() -> None:
    """跨阶段跳跃 / 逆向迁移均非法。"""
    # 跨阶段跳跃
    assert not can_transition(
        CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.RESOLVED
    )
    assert not can_transition(
        CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.UNBLOCKED
    )
    assert not can_transition(
        CapabilityGapStatus.WAITING, CapabilityGapStatus.RESOLVED
    )
    # 逆向
    assert not can_transition(
        CapabilityGapStatus.WAITING, CapabilityGapStatus.IDENTIFIED
    )
    assert not can_transition(
        CapabilityGapStatus.UNBLOCKED, CapabilityGapStatus.WAITING
    )
    assert not can_transition(
        CapabilityGapStatus.RESOLVED, CapabilityGapStatus.UNBLOCKED
    )
    # IDENTIFIED 不能直接到 UNBLOCKED/RESOLVED/INVALID_UNBLOCK/WONT_REFLOW
    assert not can_transition(
        CapabilityGapStatus.IDENTIFIED, CapabilityGapStatus.WONT_REFLOW
    )


# ---------------------------------------------------------------------------
# 场景 4：终态保护（终态无出边）
# ---------------------------------------------------------------------------
def test_terminal_states_no_outgoing() -> None:
    """3 个终态（RESOLVED / WONT_REFLOW / WONT_FIX）不能迁出到任何状态。"""
    expected_terminals = {
        CapabilityGapStatus.RESOLVED,
        CapabilityGapStatus.WONT_REFLOW,
        CapabilityGapStatus.WONT_FIX,
    }
    assert TERMINAL_STATES == expected_terminals

    for ts in TERMINAL_STATES:
        # 矩阵中终态的出边集合为空
        assert _STATE_TRANSITIONS[ts] == frozenset()
        # 对任何目标状态，can_transition 均为 False
        for target in CapabilityGapStatus:
            assert not can_transition(ts, target), (
                f"终态 {ts.value} 不应能迁出到 {target.value}"
            )


# ---------------------------------------------------------------------------
# 场景 5：UnlockFactors.compute 裁剪 + 乘积
# ---------------------------------------------------------------------------
def test_unlock_factors_normal_range() -> None:
    """正常 [0,1] 范围内的输入直接相乘。"""
    f = UnlockFactors.compute(0.5, 0.4)
    assert f.frequency == 0.5
    assert f.fix_ratio == 0.4
    assert abs(f.estimated_unlock_value - 0.2) < 1e-9


def test_unlock_factors_clipping_high() -> None:
    """超出 [0,1] 的正值被裁剪到 1.0。"""
    f = UnlockFactors.compute(1.5, 2.0)
    assert f.frequency == 1.0
    assert f.fix_ratio == 1.0
    assert f.estimated_unlock_value == 1.0


def test_unlock_factors_clipping_negative() -> None:
    """负值被裁剪到 0.0。"""
    f = UnlockFactors.compute(-0.5, -0.3)
    assert f.frequency == 0.0
    assert f.fix_ratio == 0.0
    assert f.estimated_unlock_value == 0.0


def test_unlock_factors_zero_frequency() -> None:
    """frequency=0 时 unlock_value=0（无论 fix_ratio）。"""
    f = UnlockFactors.compute(0.0, 0.9)
    assert f.estimated_unlock_value == 0.0


def test_unlock_factors_zero_fix_ratio() -> None:
    """fix_ratio=0 时 unlock_value=0。"""
    f = UnlockFactors.compute(0.8, 0.0)
    assert f.estimated_unlock_value == 0.0


def test_unlock_factors_both_one() -> None:
    """frequency=1, fix_ratio=1 时 unlock_value=1（最大值）。"""
    f = UnlockFactors.compute(1.0, 1.0)
    assert f.estimated_unlock_value == 1.0
