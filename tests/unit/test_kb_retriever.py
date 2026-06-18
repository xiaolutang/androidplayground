"""KBRetriever 纯算法单元测试（R001-BF005，无 DB 依赖）。

覆盖：
1. _apply_stale_demote：staleness 降权系数
2. _classify_negative：三档 negate verdict（>0.85 / 0.6-0.85 / <0.6 / None）
3. _decide_degraded：冷启动 degraded 判定逻辑
4. RetrievedEntry / NegativeVerdict dataclass 构建
"""
from __future__ import annotations

import pytest

from agent.infra.config import (
    KB_COLD_START_N,
    KB_NEGATIVE_DEMOTE,
    KB_NEGATIVE_PRUNE,
    KB_SIMILARITY_FLOOR,
    KB_STALE_DEMOTE,
)
from agent.kb.retriever import (
    NegativeVerdict,
    RetrievalResult,
    RetrievedEntry,
    _apply_stale_demote,
    _classify_negative,
    _decide_degraded,
)
from agent.schemas.kb_entry import KBValidityStatus


# ---------------------------------------------------------------------------
# _apply_stale_demote
# ---------------------------------------------------------------------------
class TestApplyStaleDemote:
    """staleness 降权系数计算（AC-4）。"""

    def test_stale_entry_demoted(self) -> None:
        """validity_status='stale' → similarity = raw * KB_STALE_DEMOTE(0.5)。"""
        raw = 0.8
        result = _apply_stale_demote(raw, KBValidityStatus.STALE.value)
        assert result == pytest.approx(raw * KB_STALE_DEMOTE)
        assert result == pytest.approx(0.4)

    def test_valid_entry_not_demoted(self) -> None:
        """validity_status='valid' → similarity = raw（不降权）。"""
        raw = 0.9
        result = _apply_stale_demote(raw, KBValidityStatus.VALID.value)
        assert result == pytest.approx(0.9)

    def test_conflicting_entry_not_demoted(self) -> None:
        """validity_status='conflicting' → similarity = raw（conflicting 不自动降权）。"""
        raw = 0.7
        result = _apply_stale_demote(raw, KBValidityStatus.CONFLICTING.value)
        assert result == pytest.approx(0.7)

    def test_stale_demote_factor_is_half(self) -> None:
        """KB_STALE_DEMOTE 应为 0.5（降权一半）。"""
        assert KB_STALE_DEMOTE == 0.5

    def test_stale_with_zero_raw(self) -> None:
        """raw=0 + stale → 0。"""
        result = _apply_stale_demote(0.0, KBValidityStatus.STALE.value)
        assert result == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _classify_negative
# ---------------------------------------------------------------------------
class TestClassifyNegative:
    """三档 negate verdict（AC-8）。"""

    def test_prune_high_similarity(self) -> None:
        """similarity > KB_NEGATIVE_PRUNE(0.85) → prune=True, demote=1.0。"""
        prune, demote = _classify_negative(0.9)
        assert prune is True
        assert demote == pytest.approx(1.0)

    def test_prune_at_boundary_above(self) -> None:
        """similarity = 0.86（刚超过 0.85）→ prune=True。"""
        prune, demote = _classify_negative(0.86)
        assert prune is True
        assert demote == pytest.approx(1.0)

    def test_demote_mid_range(self) -> None:
        """similarity = 0.7（[0.6, 0.85]）→ prune=False, demote=0.3。"""
        prune, demote = _classify_negative(0.7)
        assert prune is False
        assert demote == pytest.approx(0.3)

    def test_demote_at_lower_boundary(self) -> None:
        """similarity = 0.6（KB_NEGATIVE_DEMOTE 下界）→ demote=0.3。"""
        prune, demote = _classify_negative(KB_NEGATIVE_DEMOTE)
        assert prune is False
        assert demote == pytest.approx(0.3)

    def test_demote_at_upper_boundary(self) -> None:
        """similarity = 0.85（KB_NEGATIVE_PRUNE 上界）→ demote=0.3（<= 包含）。"""
        prune, demote = _classify_negative(KB_NEGATIVE_PRUNE)
        assert prune is False
        assert demote == pytest.approx(0.3)

    def test_unaffected_low_similarity(self) -> None:
        """similarity = 0.4（< 0.6）→ prune=False, demote=1.0。"""
        prune, demote = _classify_negative(0.4)
        assert prune is False
        assert demote == pytest.approx(1.0)

    def test_unaffected_none(self) -> None:
        """similarity=None（无匹配）→ prune=False, demote=1.0。"""
        prune, demote = _classify_negative(None)
        assert prune is False
        assert demote == pytest.approx(1.0)

    def test_unaffected_zero(self) -> None:
        """similarity = 0.0 → prune=False, demote=1.0。"""
        prune, demote = _classify_negative(0.0)
        assert prune is False
        assert demote == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _decide_degraded
# ---------------------------------------------------------------------------
class TestDecideDegraded:
    """冷启动 degraded 判定（AC-7）。"""

    def test_small_pool_degraded(self) -> None:
        """candidate_pool=3（< KB_COLD_START_N=10）→ degraded=True。"""
        assert _decide_degraded(3, 0.9) is True

    def test_large_pool_high_sim_not_degraded(self) -> None:
        """candidate_pool=15, top1_raw=0.7（> floor）→ degraded=False。"""
        assert _decide_degraded(15, 0.7) is False

    def test_large_pool_low_sim_degraded(self) -> None:
        """candidate_pool=15, top1_raw=0.3（< floor）→ degraded=True。"""
        assert _decide_degraded(15, 0.3) is True

    def test_empty_pool_degraded(self) -> None:
        """candidate_pool=0 → degraded=True。"""
        assert _decide_degraded(0, None) is True

    def test_pool_at_threshold(self) -> None:
        """candidate_pool=KB_COLD_START_N(10), top1_raw=0.9 → degraded=False。"""
        assert _decide_degraded(KB_COLD_START_N, 0.9) is False

    def test_sim_at_floor(self) -> None:
        """top1_raw = KB_SIMILARITY_FLOOR(0.5) → degraded=False（>= 不降级）。"""
        assert _decide_degraded(15, KB_SIMILARITY_FLOOR) is False

    def test_sim_just_below_floor(self) -> None:
        """top1_raw = 0.49（< 0.5）→ degraded=True。"""
        assert _decide_degraded(15, 0.49) is True


# ---------------------------------------------------------------------------
# dataclass 构建
# ---------------------------------------------------------------------------
class TestDataclassConstruction:
    """验证 RetrievedEntry / RetrievalResult / NegativeVerdict 可正确构建。"""

    def test_retrieved_entry_frozen(self) -> None:
        """RetrievedEntry 是 frozen dataclass。"""
        entry = RetrievedEntry(
            entry=None,  # type: ignore[arg-type]
            similarity=0.4,
            raw_similarity=0.8,
            validity_status="stale",
            conflicting_with=["B", "C"],
        )
        assert entry.similarity == pytest.approx(0.4)
        assert entry.raw_similarity == pytest.approx(0.8)
        assert entry.validity_status == "stale"
        assert entry.conflicting_with == ["B", "C"]
        # frozen → 不可修改
        with pytest.raises(AttributeError):
            entry.similarity = 0.5  # type: ignore[misc]

    def test_retrieval_result(self) -> None:
        """RetrievalResult 可正确构建。"""
        result = RetrievalResult(entries=[], degraded=True)
        assert result.entries == []
        assert result.degraded is True

    def test_negative_verdict_frozen(self) -> None:
        """NegativeVerdict 是 frozen dataclass。"""
        v = NegativeVerdict(
            hypothesis_id="hyp_0",
            max_negative_similarity=0.9,
            prune=True,
            demote_factor=1.0,
        )
        assert v.hypothesis_id == "hyp_0"
        assert v.prune is True
        with pytest.raises(AttributeError):
            v.prune = False  # type: ignore[misc]
