"""Hypothesis 4 态状态机迁移矩阵测试（R001-INT02）。

依据：
- Sprint Contract R001-INT02（mode: direct）
- agent/diagnosis/hypothesis_engine.py _STATE_TRANSITIONS 矩阵
- agent/schemas/trajectory.py HypothesisStatus 4 态枚举

覆盖：
- PROPOSED → VERIFYING
- VERIFYING → CONFIRMED | REFUTED
- PROPOSED → REFUTED（直接否定）
- CONFIRMED → REFUTED（仅 overturn_root_cause 路径）

纯逻辑测试，无 DB 依赖：直接测 _STATE_TRANSITIONS / can_transition。
"""
from __future__ import annotations

import pytest

from agent.diagnosis.hypothesis_engine import (
    HypothesisEngine,
    HypothesisTransitionError,
    _STATE_TRANSITIONS,
    can_transition,
)
from agent.schemas.trajectory import HypothesisStatus


# ---------------------------------------------------------------------------
# 全量 (from, to) 组合：4 × 4 = 16
# ---------------------------------------------------------------------------
_ALL_STATUSES = list(HypothesisStatus)

# 合法迁移集合
_LEGAL_TRANSITIONS: frozenset[tuple[HypothesisStatus, HypothesisStatus]] = frozenset({
    # proposed → verifying（开始验证）
    (HypothesisStatus.PROPOSED, HypothesisStatus.VERIFYING),
    # proposed → refuted（直接否定，如负向反查 prune）
    (HypothesisStatus.PROPOSED, HypothesisStatus.REFUTED),
    # verifying → confirmed（信号匹配）
    (HypothesisStatus.VERIFYING, HypothesisStatus.CONFIRMED),
    # verifying → refuted（信号不符 / 步数耗尽）
    (HypothesisStatus.VERIFYING, HypothesisStatus.REFUTED),
    # confirmed → refuted（仅 overturn_root_cause 路径，矩阵层声明合法）
    (HypothesisStatus.CONFIRMED, HypothesisStatus.REFUTED),
})

# 非法迁移 = 全量 - 合法 - 自环
_ILLEGAL_TRANSITIONS: list[tuple[HypothesisStatus, HypothesisStatus]] = [
    (f, t)
    for f in _ALL_STATUSES
    for t in _ALL_STATUSES
    if f != t and (f, t) not in _LEGAL_TRANSITIONS
]


# ---------------------------------------------------------------------------
# 基础：4 态枚举完整性
# ---------------------------------------------------------------------------
class TestHypothesis4States:
    """4 态枚举与迁移矩阵基础校验。"""

    def test_enum_has_exactly_4_states(self) -> None:
        """HypothesisStatus 必须是 4 态。"""
        assert len(list(HypothesisStatus)) == 4

    def test_all_states_in_transition_matrix(self) -> None:
        """所有 4 态在 _STATE_TRANSITIONS 的 key 中均有定义。"""
        for status in HypothesisStatus:
            assert status in _STATE_TRANSITIONS, (
                f"{status.value} missing from _STATE_TRANSITIONS"
            )

    def test_legal_transition_set_matches_matrix(self) -> None:
        """合法迁移集合与 _STATE_TRANSITIONS 矩阵完全一致。"""
        for from_status in HypothesisStatus:
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
# AC-3：合法迁移参数化
# ---------------------------------------------------------------------------
class TestLegalTransitions:
    """4 态全部合法迁移。"""

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
        from_status: HypothesisStatus,
        to_status: HypothesisStatus,
    ) -> None:
        """合法迁移：can_transition=True。"""
        assert can_transition(from_status, to_status) is True


# ---------------------------------------------------------------------------
# 非法迁移参数化（全判）
# ---------------------------------------------------------------------------
class TestIllegalTransitions:
    """所有非法迁移组合（16 - 5 - 4自环 = 7 条）。"""

    @pytest.mark.parametrize(
        "from_status,to_status",
        _ILLEGAL_TRANSITIONS,
        ids=[f"{f.value}->{t.value}" for f, t in _ILLEGAL_TRANSITIONS],
    )
    def test_illegal_transition_rejected(
        self,
        from_status: HypothesisStatus,
        to_status: HypothesisStatus,
    ) -> None:
        """非法迁移：can_transition=False。"""
        assert can_transition(from_status, to_status) is False


# ---------------------------------------------------------------------------
# INV-2：refuted 终态不可迁出
# ---------------------------------------------------------------------------
class TestRefutedTerminal:
    """INV-2：refuted 为终态，不可迁出到任何状态。"""

    def test_refuted_has_no_outgoing(self) -> None:
        """refuted 在矩阵中无出边。"""
        assert _STATE_TRANSITIONS[HypothesisStatus.REFUTED] == frozenset()

    @pytest.mark.parametrize("target", _ALL_STATUSES)
    def test_refuted_cannot_transition_to_any(
        self, target: HypothesisStatus
    ) -> None:
        """refuted 不能迁移到任何状态（INV-2）。"""
        assert can_transition(HypothesisStatus.REFUTED, target) is False


# ---------------------------------------------------------------------------
# 引擎层迁移：方法调用触发状态变更
# ---------------------------------------------------------------------------
class TestEngineTransitions:
    """通过 HypothesisEngine 方法验证 4 态迁移。"""

    def test_proposed_to_verifying(self) -> None:
        """propose → verify：proposed → verifying。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        assert node.status == HypothesisStatus.VERIFYING

    def test_verifying_to_confirmed(self) -> None:
        """verify → confirm：verifying → confirmed。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        engine.confirm(node.id, evidence={"match": True})
        assert node.status == HypothesisStatus.CONFIRMED

    def test_verifying_to_refuted(self) -> None:
        """verify → refute：verifying → refuted。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        engine.refute(node.id, reason="signal mismatch")
        assert node.status == HypothesisStatus.REFUTED

    def test_proposed_to_refuted_directly(self) -> None:
        """propose → refute：proposed → refuted（直接否定，如负向反查）。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.refute(node.id, reason="negative knowledge prune")
        assert node.status == HypothesisStatus.REFUTED

    def test_confirmed_to_refuted_in_matrix(self) -> None:
        """CONFIRMED → REFUTED 在矩阵中合法（overturn 路径 + 常规 refute 均可）。"""
        # 矩阵层允许
        assert can_transition(HypothesisStatus.CONFIRMED, HypothesisStatus.REFUTED)

        # 引擎层常规 refute 可执行
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="root")
        engine.verify(node.id)
        engine.confirm(node.id)
        engine.refute(node.id, reason="direct refute from confirmed")
        assert node.status == HypothesisStatus.REFUTED

    def test_overturn_root_cause_requires_confirmed_and_is_rootcause(self) -> None:
        """overturn_root_cause 仅适用于 CONFIRMED + is_rootcause=True 的节点。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="root")
        engine.verify(node.id)
        engine.confirm(node.id)
        node.is_rootcause = True

        # overturn 成功，并记录推翻信号 + 清除 is_rootcause
        engine.overturn_root_cause(
            node.id,
            reason="new signal推翻",
            overturning_signal={"sig": "new"},
            overturning_stage="fixing",
        )
        assert node.status == HypothesisStatus.REFUTED
        assert node.is_rootcause is False
        assert node.overturning_signal == {"sig": "new"}
        assert node.overturning_stage == "fixing"

    def test_overturn_rejects_non_confirmed(self) -> None:
        """overturn_root_cause 拒绝非 CONFIRMED 状态。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        # 仍在 PROPOSED，调 overturn 应抛异常
        with pytest.raises(HypothesisTransitionError):
            engine.overturn_root_cause(
                node.id,
                reason="invalid",
                overturning_signal={"sig": "x"},
                overturning_stage="fixing",
            )

    def test_overturn_rejects_non_rootcause(self) -> None:
        """overturn_root_cause 拒绝非 is_rootcause 的 CONFIRMED 节点。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.verify(node.id)
        engine.confirm(node.id)
        # is_rootcause 默认 False
        with pytest.raises(HypothesisTransitionError):
            engine.overturn_root_cause(
                node.id,
                reason="not rootcause",
                overturning_signal={"sig": "x"},
                overturning_stage="fixing",
            )

    def test_refuted_cannot_transition_out(self) -> None:
        """INV-2：refuted 不可迁出（verify/confirm/refute 均抛异常）。"""
        engine = HypothesisEngine()
        node = engine.propose(parent_id=None, content="h1")
        engine.refute(node.id, reason="killed")

        with pytest.raises(HypothesisTransitionError):
            engine.verify(node.id)
        with pytest.raises(HypothesisTransitionError):
            engine.confirm(node.id)
        with pytest.raises(HypothesisTransitionError):
            engine.refute(node.id, reason="again")


# ---------------------------------------------------------------------------
# 关键非法路径
# ---------------------------------------------------------------------------
class TestCriticalIllegalPaths:
    """关键非法路径专项。"""

    @pytest.mark.parametrize(
        "from_status,to_status,reason",
        [
            (HypothesisStatus.PROPOSED, HypothesisStatus.CONFIRMED, "proposed 不可跳过 verifying 直接到 confirmed"),
            (HypothesisStatus.VERIFYING, HypothesisStatus.PROPOSED, "verifying 不可逆回 proposed"),
            (HypothesisStatus.VERIFYING, HypothesisStatus.VERIFYING, "verifying 不可自环"),
            (HypothesisStatus.CONFIRMED, HypothesisStatus.PROPOSED, "confirmed 不可逆回 proposed"),
            (HypothesisStatus.CONFIRMED, HypothesisStatus.VERIFYING, "confirmed 不可逆回 verifying"),
            (HypothesisStatus.REFUTED, HypothesisStatus.PROPOSED, "INV-2 refuted 终态不可迁出"),
            (HypothesisStatus.REFUTED, HypothesisStatus.VERIFYING, "INV-2 refuted 终态不可迁出"),
            (HypothesisStatus.REFUTED, HypothesisStatus.CONFIRMED, "INV-2 refuted 终态不可迁出"),
        ],
        ids=lambda param: param if isinstance(param, str) else "",
    )
    def test_critical_illegal_path(
        self,
        from_status: HypothesisStatus,
        to_status: HypothesisStatus,
        reason: str,
    ) -> None:
        """关键非法路径。"""
        assert can_transition(from_status, to_status) is False, reason
