"""AnchorLibrary 集成测试（R001-BF007，Testcontainers pgvector/pgvector:pg16）。

覆盖：
1. CRUD 端到端（真实 PG + pgvector）
2. match_by_visual_features 真实 pgvector ``<=>`` 余弦相似度排序

沿用 INF03 / test_kb_stores.py 的 Testcontainers fixture 模式。
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from agent.anchor.anchor_library import AnchorLibrary
from agent.schemas.anchor import Anchor


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
    """每个测试独立 engine + 建表 + 注册 pgvector。"""
    from agent.infra.db import init_vector_extension

    eng = create_engine(pg_url, pool_pre_ping=True, future=True)

    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    init_vector_extension(eng)
    Anchor.__table__.create(eng, checkfirst=True)

    SessionFactory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    yield eng, SessionFactory

    Anchor.__table__.drop(eng, checkfirst=True)
    eng.dispose()


# ---------------------------------------------------------------------------
# 集成测试：CRUD + match 真实 pgvector
# ---------------------------------------------------------------------------
class TestAnchorLibraryIntegration:
    """AnchorLibrary 端到端集成（真实 pgvector）。"""

    def test_crud_full_cycle(self, db_setup) -> None:
        """create → get → list → update → delete 全流程。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)

        # create
        anchor = lib.create(
            {
                "id": "int-1",
                "page_id": "home",
                "screenshot_ref": "s3://int/home.png",
                "text_expectation": "首页底部 tab",
                "visual_features": [1.0, 0.0, 0.0],
                "git_commit_anchor": "deadbeef",
            }
        )
        assert anchor.id == "int-1"

        # get
        got = lib.get("int-1")
        assert got is not None
        assert got.git_commit_anchor == "deadbeef"

        # list by page_id
        home = lib.list(page_id="home")
        assert len(home) == 1

        # update
        updated = lib.update("int-1", {"text_expectation": "更新后的预期"})
        assert updated is not None
        assert updated.text_expectation == "更新后的预期"

        # delete
        assert lib.delete("int-1") is True
        assert lib.get("int-1") is None

    def test_match_by_visual_features_real_pgvector(self, db_setup) -> None:
        """真实 pgvector 余弦相似度排序。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "m1", "visual_features": [1.0, 0.0, 0.0]})
        lib.create({"id": "m2", "visual_features": [0.0, 1.0, 0.0]})
        lib.create({"id": "m3", "visual_features": [0.6, 0.8, 0.0]})

        results = lib.match_by_visual_features([1.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3
        # m1 与查询正交同向 → similarity=1.0
        assert results[0][0].id == "m1"
        assert results[0][1] == pytest.approx(1.0, abs=1e-6)
        # m3 与查询有正分量（0.6），应高于正交的 m2
        id_to_sim = {a.id: s for a, s in results}
        assert id_to_sim["m3"] > id_to_sim["m2"]

    def test_match_by_visual_features_page_id_scope(self, db_setup) -> None:
        """page_id 过滤限定真实检索范围。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create(
            {"id": "pi1", "page_id": "home", "visual_features": [1.0, 0.0, 0.0]}
        )
        lib.create(
            {"id": "pi2", "page_id": "home", "visual_features": [0.9, 0.1, 0.0]}
        )
        lib.create(
            {"id": "pi3", "page_id": "settings", "visual_features": [1.0, 0.0, 0.0]}
        )

        home_results = lib.match_by_visual_features(
            [1.0, 0.0, 0.0], top_k=5, page_id="home"
        )
        ids = {a.id for a, _ in home_results}
        assert ids == {"pi1", "pi2"}

    def test_match_empty_db_returns_empty(self, db_setup) -> None:
        """空库返回 []（BF003 降级）。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        assert lib.match_by_visual_features([1.0, 0.0, 0.0]) == []

    def test_is_empty(self, db_setup) -> None:
        """is_empty 端到端。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        assert lib.is_empty() is True
        lib.create({"id": "ie", "page_id": "home"})
        assert lib.is_empty() is False
