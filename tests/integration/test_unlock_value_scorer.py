"""BF008 集成测试：UnlockValueScorer（真实 PG Testcontainers）。

覆盖 test_tasks 场景：
1. 空表 frequency=0.0
2. 有数据时 frequency 计算正确
3. fix_ratio 从 effectiveness 均值计算
4. estimated_unlock_value = frequency x fix_ratio
5. gap_type 为 None 时返回 0
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from agent.gap.unlock_value_scorer import UnlockValueScorer
from agent.infra.db import Base, init_vector_extension
from agent.schemas.capability_gap import CapabilityGap, CapabilityGapStatus
from agent.schemas.metric_point import MetricPoint, MetricType


# ---------------------------------------------------------------------------
# Testcontainers fixture
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


@pytest.fixture
def session_factory(pg_container: PostgresContainer) -> Iterator[sessionmaker]:
    """每个测试用独立 engine + 全量建表。"""
    url = pg_container.get_connection_url()
    engine_local = create_engine(url, pool_pre_ping=True, future=True)
    init_vector_extension(engine_local)
    Base.metadata.create_all(engine_local)
    factory = sessionmaker(
        bind=engine_local,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    try:
        yield factory
    finally:
        # 用 DROP SCHEMA CASCADE 替代 drop_all，规避循环 FK 导致的
        # CircularDependencyError（见 test_gap_store.py 同款注释）。
        with engine_local.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine_local.dispose()


# ---------------------------------------------------------------------------
# 场景 1：空表 frequency=0
# ---------------------------------------------------------------------------
def test_frequency_empty_returns_zero(
    session_factory: sessionmaker,
) -> None:
    """MetricPoint 表为空时 frequency=0.0。"""
    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-001",
        gap_type="信息",
        description="test",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    assert factors.frequency == 0.0
    assert factors.fix_ratio == 0.0
    assert factors.estimated_unlock_value == 0.0


# ---------------------------------------------------------------------------
# 场景 2：frequency 计算
# ---------------------------------------------------------------------------
def test_frequency_with_data(
    session_factory: sessionmaker,
) -> None:
    """frequency = count(ref_gap_type == gap_type) / count(all)。

    插入 3 条 ref_gap_type='信息' + 7 条 ref_gap_type='设施' = 10 条总数。
    '信息' 的 frequency = 3/10 = 0.3
    """
    with session_factory() as session:
        for i in range(3):
            session.add(
                MetricPoint(
                    id=f"mp-info-{i}",
                    metric_type=MetricType.COVERAGE.value,
                    value=1.0,
                    ref_gap_type="信息",
                )
            )
        for i in range(7):
            session.add(
                MetricPoint(
                    id=f"mp-facility-{i}",
                    metric_type=MetricType.COVERAGE.value,
                    value=1.0,
                    ref_gap_type="设施",
                )
            )
        session.commit()

    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-002",
        gap_type="信息",
        description="freq test",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    assert abs(factors.frequency - 0.3) < 0.01


# ---------------------------------------------------------------------------
# 场景 3：fix_ratio 从 effectiveness 均值计算
# ---------------------------------------------------------------------------
def test_fix_ratio_from_effectiveness(
    session_factory: sessionmaker,
) -> None:
    """fix_ratio = avg(effectiveness.value where ref_gap_type=gap_type)。

    插入 2 条 effectiveness：value=0.8, value=0.6 -> 均值=0.7
    另插入 1 条非 effectiveness（不应参与 fix_ratio 计算）。
    """
    with session_factory() as session:
        session.add(
            MetricPoint(
                id="mp-eff-1",
                metric_type=MetricType.EFFECTIVENESS.value,
                value=0.8,
                ref_gap_type="信息",
            )
        )
        session.add(
            MetricPoint(
                id="mp-eff-2",
                metric_type=MetricType.EFFECTIVENESS.value,
                value=0.6,
                ref_gap_type="信息",
            )
        )
        # 非 effectiveness，不应影响 fix_ratio
        session.add(
            MetricPoint(
                id="mp-cov-1",
                metric_type=MetricType.COVERAGE.value,
                value=0.5,
                ref_gap_type="信息",
            )
        )
        session.commit()

    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-003",
        gap_type="信息",
        description="fix_ratio test",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    assert abs(factors.fix_ratio - 0.7) < 0.01


def test_fix_ratio_no_effectiveness_returns_zero(
    session_factory: sessionmaker,
) -> None:
    """无 effectiveness 数据时 fix_ratio=0.0（保守估计）。"""
    with session_factory() as session:
        session.add(
            MetricPoint(
                id="mp-cov-only",
                metric_type=MetricType.COVERAGE.value,
                value=0.5,
                ref_gap_type="信息",
            )
        )
        session.commit()

    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-004",
        gap_type="信息",
        description="no eff",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    assert factors.fix_ratio == 0.0


# ---------------------------------------------------------------------------
# 场景 4：estimated_unlock_value = frequency x fix_ratio
# ---------------------------------------------------------------------------
def test_unlock_value_is_product(
    session_factory: sessionmaker,
) -> None:
    """estimated_unlock_value = frequency x fix_ratio。"""
    # 10 条 metric_point，4 条 ref_gap_type='信息'
    # 其中 2 条 effectiveness value=1.0 -> fix_ratio=1.0
    with session_factory() as session:
        for i in range(2):
            session.add(
                MetricPoint(
                    id=f"mp-prod-eff-{i}",
                    metric_type=MetricType.EFFECTIVENESS.value,
                    value=1.0,
                    ref_gap_type="信息",
                )
            )
        for i in range(2):
            session.add(
                MetricPoint(
                    id=f"mp-prod-cov-{i}",
                    metric_type=MetricType.COVERAGE.value,
                    value=0.5,
                    ref_gap_type="信息",
                )
            )
        for i in range(6):
            session.add(
                MetricPoint(
                    id=f"mp-prod-other-{i}",
                    metric_type=MetricType.COST.value,
                    value=1.0,
                    ref_gap_type="设施",
                )
            )
        session.commit()

    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-005",
        gap_type="信息",
        description="product test",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    # frequency = 4/10 = 0.4
    assert abs(factors.frequency - 0.4) < 0.01
    # fix_ratio = avg(1.0, 1.0) = 1.0
    assert abs(factors.fix_ratio - 1.0) < 0.01
    # unlock_value = 0.4 x 1.0 = 0.4
    assert abs(factors.estimated_unlock_value - 0.4) < 0.01


# ---------------------------------------------------------------------------
# 场景 5：gap_type 为 None
# ---------------------------------------------------------------------------
def test_gap_type_none_returns_zero(
    session_factory: sessionmaker,
) -> None:
    """gap.gap_type 为 None 时 frequency=fix_ratio=0.0。"""
    scorer = UnlockValueScorer(session_factory)
    gap = CapabilityGap(
        id="gap-score-006",
        gap_type=None,
        description="no type",
        status=CapabilityGapStatus.IDENTIFIED.value,
    )
    factors = scorer.score(gap)
    assert factors.frequency == 0.0
    assert factors.fix_ratio == 0.0
    assert factors.estimated_unlock_value == 0.0
