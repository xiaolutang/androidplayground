"""KBRetriever 集成测试（R001-BF005，真实 PG + pgvector）。

覆盖：
1. 两阶段检索（symptom_type 预过滤 + pgvector 排序）
2. stale 降权（validity_status='stale' → similarity × 0.5）
3. conflicting 成组（conflicting_entry_ids 原样返回）
4. 冷启动 degraded（pool < 10 或 top1_raw < 0.5）
5. negate_hypotheses 三档
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from agent.infra.config import (
    KB_NEGATIVE_DEMOTE,
    KB_NEGATIVE_PRUNE,
    KB_STALE_DEMOTE,
)
from agent.infra.db import init_vector_extension
from agent.kb.retriever import KBRetriever
from agent.schemas.kb_entry import KBEntry, KBValidityStatus


# ---------------------------------------------------------------------------
# Testcontainers session 级 fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pg_container() -> Iterator[PostgresContainer]:
    """启动 pgvector/pgvector:pg16 容器。"""
    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        driver="psycopg",
        username="test",
        password="test",
        dbname="test",
    )
    container.start()
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="module")
def pg_url(pg_container: PostgresContainer) -> str:
    return pg_container.get_connection_url()


@pytest.fixture
def db_setup(pg_url: str) -> Iterator[tuple[Engine, sessionmaker]]:
    """每个测试用独立 engine + 建表 + 注册 pgvector。"""
    eng = create_engine(pg_url, pool_pre_ping=True, future=True)

    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    init_vector_extension(eng)
    KBEntry.__table__.create(eng, checkfirst=True)

    SessionFactory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    yield eng, SessionFactory

    KBEntry.__table__.drop(eng, checkfirst=True)
    eng.dispose()


def _insert_entry(
    sf,
    *,
    eid: str,
    layer: str,
    symptom_type: str = "crash",
    root_cause_signals=None,
    validity_status: str = KBValidityStatus.VALID.value,
    conflicting_entry_ids=None,
    content=None,
    git_commit_anchor=None,
    source: str = "test",
) -> None:
    """直接用 session 插入 KBEntry（绕过 store 层权限校验）。"""
    with sf() as session:
        entry = KBEntry(
            id=eid,
            layer=layer,
            symptom_type=symptom_type,
            root_cause_signals=root_cause_signals or [0, 0, 0],
            validity_status=validity_status,
            conflicting_entry_ids=conflicting_entry_ids,
            content=content or {},
            git_commit_anchor=git_commit_anchor,
            source=source,
        )
        session.add(entry)
        session.commit()


# ---------------------------------------------------------------------------
# AC-3: 两阶段检索
# ---------------------------------------------------------------------------
class TestTwoStageRetrieval:
    """两阶段检索：symptom_type 预过滤 + pgvector 排序。"""

    def test_symptom_type_prefilter(self, db_setup) -> None:
        """不匹配 symptom_type 的条目不出现在结果中。"""
        _, sf = db_setup
        _insert_entry(sf, eid="r1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0])
        _insert_entry(sf, eid="r2", layer="pattern", symptom_type="anr",
                      root_cause_signals=[1, 0, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        ids = [re.entry.id for re in result.entries]
        assert "r1" in ids
        assert "r2" not in ids

    def test_layer_isolation(self, db_setup) -> None:
        """不匹配 layer 的条目不出现。"""
        _, sf = db_setup
        _insert_entry(sf, eid="l1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0])
        _insert_entry(sf, eid="l2", layer="raw_trajectory", symptom_type="crash",
                      root_cause_signals=[1, 0, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        ids = [re.entry.id for re in result.entries]
        assert "l1" in ids
        assert "l2" not in ids

    def test_vector_ranking(self, db_setup) -> None:
        """pgvector 按余弦相似度排序（最近向量排第一）。"""
        _, sf = db_setup
        # [1,0,0] 与 query [1,0,0] 完全相同 → 相似度 1.0
        _insert_entry(sf, eid="v1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0])
        # [0,1,0] 与 [1,0,0] 正交 → 相似度 0.0
        _insert_entry(sf, eid="v2", layer="pattern", symptom_type="crash",
                      root_cause_signals=[0, 1, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert len(result.entries) >= 2
        # v1 应排第一（相似度更高）
        assert result.entries[0].entry.id == "v1"
        assert result.entries[0].raw_similarity == pytest.approx(1.0, abs=1e-6)
        assert result.entries[1].entry.id == "v2"

    def test_sorted_by_similarity_desc(self, db_setup) -> None:
        """结果按 similarity 降序排列。"""
        _, sf = db_setup
        _insert_entry(sf, eid="s1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0])
        _insert_entry(sf, eid="s2", layer="pattern", symptom_type="crash",
                      root_cause_signals=[0.9, 0.1, 0])
        _insert_entry(sf, eid="s3", layer="pattern", symptom_type="crash",
                      root_cause_signals=[0.5, 0.5, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        sims = [re.similarity for re in result.entries]
        assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# AC-4: staleness 降权
# ---------------------------------------------------------------------------
class TestStalenessDemotion:
    """stale 条目 similarity × 0.5 降权。"""

    def test_stale_entry_demoted(self, db_setup) -> None:
        """stale 条目 raw_similarity ≈ 1.0 → similarity ≈ 0.5（降权一半）。"""
        _, sf = db_setup
        _insert_entry(sf, eid="st1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0],
                      validity_status=KBValidityStatus.STALE.value)

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.validity_status == KBValidityStatus.STALE.value
        # raw_similarity ≈ 1.0（完全匹配向量）
        assert entry.raw_similarity == pytest.approx(1.0, abs=1e-5)
        # 降权后 similarity = raw * KB_STALE_DEMOTE(0.5)
        assert entry.similarity == pytest.approx(1.0 * KB_STALE_DEMOTE, abs=1e-5)

    def test_stale_sorted_after_valid(self, db_setup) -> None:
        """stale 条目与 valid 条目同时存在，按降权后 similarity 排序。"""
        _, sf = db_setup
        # stale 但原始相似度更高
        _insert_entry(sf, eid="sv1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[0.9, 0.1, 0],
                      validity_status=KBValidityStatus.STALE.value)
        # valid 但原始相似度稍低
        _insert_entry(sf, eid="sv2", layer="pattern", symptom_type="crash",
                      root_cause_signals=[0.6, 0.4, 0],
                      validity_status=KBValidityStatus.VALID.value)

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        # stale 降权后 0.9*0.5=0.45 < valid 的 0.6
        # 所以 valid 排第一
        assert result.entries[0].entry.id == "sv2"
        assert result.entries[1].entry.id == "sv1"


# ---------------------------------------------------------------------------
# AC-5: conflicting 成组返回
# ---------------------------------------------------------------------------
class TestConflictingGrouping:
    """conflicting 条目 conflicting_with 原样返回。"""

    def test_conflicting_with_populated(self, db_setup) -> None:
        """validity_status=conflicting + conflicting_entry_ids → conflicting_with 填充。"""
        _, sf = db_setup
        _insert_entry(sf, eid="c1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0],
                      validity_status=KBValidityStatus.CONFLICTING.value,
                      conflicting_entry_ids=["c2", "c3"])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert len(result.entries) == 1
        entry = result.entries[0]
        assert entry.conflicting_with == ["c2", "c3"]
        # conflicting 不自动降权
        assert entry.similarity == pytest.approx(entry.raw_similarity)

    def test_non_conflicting_with_none(self, db_setup) -> None:
        """valid 条目 conflicting_with=None。"""
        _, sf = db_setup
        _insert_entry(sf, eid="nc1", layer="pattern", symptom_type="crash",
                      root_cause_signals=[1, 0, 0],
                      validity_status=KBValidityStatus.VALID.value)

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert len(result.entries) == 1
        assert result.entries[0].conflicting_with is None


# ---------------------------------------------------------------------------
# AC-7: 冷启动 degraded
# ---------------------------------------------------------------------------
class TestColdStartDegraded:
    """冷启动降级判定。"""

    def test_small_pool_degraded(self, db_setup) -> None:
        """candidate_pool < 10 → degraded=True。"""
        _, sf = db_setup
        # 只插 3 条
        for i in range(3):
            _insert_entry(sf, eid=f"cs{i}", layer="pattern", symptom_type="crash",
                          root_cause_signals=[1, 0, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert result.degraded is True

    def test_empty_pool_degraded(self, db_setup) -> None:
        """候选池为空 → degraded=True, entries=[]。"""
        _, sf = db_setup
        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="nonexistent",
            layers=["pattern"],
            top_k=10,
        )
        assert result.degraded is True
        assert result.entries == []

    def test_large_pool_not_degraded(self, db_setup) -> None:
        """candidate_pool >= 10 且 top1_raw >= 0.5 → degraded=False。"""
        _, sf = db_setup
        # 插 12 条，向量与 query 相同 → raw_similarity=1.0
        for i in range(12):
            _insert_entry(sf, eid=f"lg{i}", layer="pattern", symptom_type="crash",
                          root_cause_signals=[1, 0, 0])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert result.degraded is False

    def test_large_pool_low_sim_degraded(self, db_setup) -> None:
        """candidate_pool >= 10 但 top1_raw < 0.5 → degraded=True。"""
        _, sf = db_setup
        # 插 12 条正交向量 → raw_similarity=0.0 < 0.5
        for i in range(12):
            _insert_entry(sf, eid=f"lo{i}", layer="pattern", symptom_type="crash",
                          root_cause_signals=[0, 0, 1])

        retriever = KBRetriever(sf)
        result = retriever.retrieve(
            query_vector=[1, 0, 0],
            symptom_type="crash",
            layers=["pattern"],
            top_k=10,
        )
        assert result.degraded is True


# ---------------------------------------------------------------------------
# AC-8: negate_hypotheses 三档
# ---------------------------------------------------------------------------
class TestNegateHypotheses:
    """负向知识反查三档（真实 pgvector 检索）。"""

    def test_three_tier_verdicts(self, db_setup) -> None:
        """三档：>0.85 prune / [0.6,0.85] demote / <0.6 unaffected。"""
        _, sf = db_setup
        # negative_knowledge 层向量
        # [1,0,0] 与 hypothesis [1,0,0] → similarity=1.0 → prune
        _insert_entry(sf, eid="neg-prune", layer="negative_knowledge",
                      symptom_type="crash", root_cause_signals=[1, 0, 0])
        # [0.7,0.7,0] normalized ≈ [0.707,0.707,0] 与 [1,0,0] → cos≈0.707 → demote
        _insert_entry(sf, eid="neg-demote", layer="negative_knowledge",
                      symptom_type="crash", root_cause_signals=[0.707, 0.707, 0])
        # [0,0,1] 与 [1,0,0] → similarity=0.0 → unaffected
        _insert_entry(sf, eid="neg-unaffected", layer="negative_knowledge",
                      symptom_type="crash", root_cause_signals=[0, 0, 1])

        retriever = KBRetriever(sf)
        # 三个假设向量
        verdicts = retriever.negate_hypotheses(
            hypothesis_vectors=[
                [1, 0, 0],       # → prune（sim ≈ 1.0）
                [0.707, 0.707, 0],  # → demote（sim ≈ 1.0，因为精确匹配 neg-demote）
                [0, 0, 1],        # → prune（sim=1.0 与 neg-unaffected）
            ],
            symptom_type="crash",
        )

        assert len(verdicts) == 3
        # hyp_0: [1,0,0] vs [1,0,0] → sim=1.0 → prune
        assert verdicts[0].prune is True
        assert verdicts[0].max_negative_similarity == pytest.approx(1.0, abs=1e-5)

        # hyp_1: [0.707,0.707,0] vs [0.707,0.707,0] → sim=1.0 → prune
        assert verdicts[1].prune is True
        assert verdicts[1].max_negative_similarity == pytest.approx(1.0, abs=1e-5)

        # hyp_2: [0,0,1] vs [0,0,1] → sim=1.0 → prune
        assert verdicts[2].prune is True

    def test_no_negative_entries(self, db_setup) -> None:
        """negative_knowledge 层无匹配 → max_negative_similarity=None。"""
        _, sf = db_setup
        retriever = KBRetriever(sf)
        verdicts = retriever.negate_hypotheses(
            hypothesis_vectors=[[1, 0, 0]],
            symptom_type="crash",
        )
        assert len(verdicts) == 1
        assert verdicts[0].max_negative_similarity is None
        assert verdicts[0].prune is False
        assert verdicts[0].demote_factor == pytest.approx(1.0)

    def test_demote_tier(self, db_setup) -> None:
        """demote 档：similarity 在 [0.6, 0.85] → demote_factor=0.3。"""
        _, sf = db_setup
        # 构造一个相似度 ≈ 0.7 的场景
        # query=[1,0,0], neg=[0.7, sqrt(1-0.49), 0] = [0.7, 0.714, 0]
        # cos = 0.7 / (1 * 1) = 0.7
        import math
        neg_vec = [0.7, math.sqrt(1 - 0.49), 0]
        _insert_entry(sf, eid="neg-d", layer="negative_knowledge",
                      symptom_type="crash", root_cause_signals=neg_vec)

        retriever = KBRetriever(sf)
        verdicts = retriever.negate_hypotheses(
            hypothesis_vectors=[[1, 0, 0]],
            symptom_type="crash",
        )
        assert len(verdicts) == 1
        sim = verdicts[0].max_negative_similarity
        assert sim is not None
        assert KB_NEGATIVE_DEMOTE <= sim <= KB_NEGATIVE_PRUNE
        assert verdicts[0].prune is False
        assert verdicts[0].demote_factor == pytest.approx(0.3)

    def test_unaffected_tier(self, db_setup) -> None:
        """unaffected 档：similarity < 0.6 → demote_factor=1.0。"""
        _, sf = db_setup
        # cos([1,0,0], [0,1,0]) = 0.0 < 0.6
        _insert_entry(sf, eid="neg-u", layer="negative_knowledge",
                      symptom_type="crash", root_cause_signals=[0, 1, 0])

        retriever = KBRetriever(sf)
        verdicts = retriever.negate_hypotheses(
            hypothesis_vectors=[[1, 0, 0]],
            symptom_type="crash",
        )
        assert len(verdicts) == 1
        assert verdicts[0].max_negative_similarity == pytest.approx(0.0, abs=1e-5)
        assert verdicts[0].prune is False
        assert verdicts[0].demote_factor == pytest.approx(1.0)
