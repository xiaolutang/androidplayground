"""AnchorLibrary 单元测试（R001-BF007）。

覆盖：
1. CRUD：create / get / list（page_id 过滤 + 全量）/ update / delete
2. match_by_visual_features：空库降级 / 相似度排序 / page_id 过滤
3. is_empty：空库 / 有数据

注：match_by_visual_features / is_empty 依赖 pgvector ``<=>`` 运算符，
   无法用 sqlite 模拟，故本"单元"测试复用 Testcontainers pgvector fixture
   （与 ``tests/integration/test_kb_stores.py`` 同一 fixture 模式）。
   纯 CRUD 部分同样跑在真实 PG 上，保证 ORM 列类型（Vector）行为正确。
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
# Testcontainers session 级 fixture（与 test_kb_stores.py 同模式）
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
    """每个测试独立 engine + 建表 + 注册 pgvector。

    返回 (engine, session_factory)。
    """
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
# CRUD
# ---------------------------------------------------------------------------
class TestAnchorCRUD:
    """AnchorLibrary CRUD。"""

    def test_create_and_get(self, db_setup) -> None:
        """create 写入后 get 能读回。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        anchor = lib.create(
            {
                "id": "anchor-1",
                "page_id": "home",
                "screenshot_ref": "s3://x/home.png",
                "text_expectation": "底部 tab 高亮首页",
                "visual_features": [1.0, 0.0, 0.0],
                "git_commit_anchor": "abc123",
            }
        )
        assert anchor.id == "anchor-1"
        assert anchor.page_id == "home"

        got = lib.get("anchor-1")
        assert got is not None
        assert got.id == "anchor-1"
        assert got.screenshot_ref == "s3://x/home.png"

    def test_list_by_page_id(self, db_setup) -> None:
        """list 按 page_id 过滤。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "a-home", "page_id": "home"})
        lib.create({"id": "a-settings", "page_id": "settings"})

        home_anchors = lib.list(page_id="home")
        assert len(home_anchors) == 1
        assert home_anchors[0].id == "a-home"

    def test_list_all_no_filter(self, db_setup) -> None:
        """list 无过滤返回全部（受 limit 约束）。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "all-1", "page_id": "p1"})
        lib.create({"id": "all-2", "page_id": "p2"})
        lib.create({"id": "all-3", "page_id": "p1"})

        all_anchors = lib.list()
        assert len(all_anchors) == 3

    def test_update(self, db_setup) -> None:
        """update 能更新字段。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create(
            {"id": "upd-1", "page_id": "home", "text_expectation": "old"}
        )
        updated = lib.update("upd-1", {"text_expectation": "new"})
        assert updated is not None
        assert updated.text_expectation == "new"

        # update 不存在返回 None
        assert lib.update("nope", {"text_expectation": "x"}) is None

    def test_update_ignores_id_in_patch(self, db_setup) -> None:
        """update patch 中含 id 时应被忽略（主键不可变）。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "upd-id", "page_id": "home", "text_expectation": "old"})

        # 尝试通过 patch 改 id，应被忽略
        updated = lib.update("upd-id", {"id": "hacked", "text_expectation": "new"})
        assert updated is not None
        assert updated.id == "upd-id"  # id 未被篡改
        assert updated.text_expectation == "new"  # 其他字段正常更新

    def test_delete(self, db_setup) -> None:
        """delete 硬删，get 返回 None。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "del-1", "page_id": "home"})
        assert lib.delete("del-1") is True
        assert lib.get("del-1") is None
        # 再删返回 False
        assert lib.delete("del-1") is False


# ---------------------------------------------------------------------------
# match_by_visual_features
# ---------------------------------------------------------------------------
class TestMatchByVisualFeatures:
    """visual_features 向量比对（pgvector 余弦相似度排序）。"""

    def test_match_empty_db_returns_empty(self, db_setup) -> None:
        """空库返回 []（BF003 降级依据）。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        results = lib.match_by_visual_features([1.0, 0.0, 0.0])
        assert results == []

    def test_match_returns_sorted_by_similarity(self, db_setup) -> None:
        """结果按相似度降序。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "v1", "visual_features": [1.0, 0.0, 0.0]})
        lib.create({"id": "v2", "visual_features": [0.0, 1.0, 0.0]})
        lib.create({"id": "v3", "visual_features": [0.7, 0.7, 0.0]})

        results = lib.match_by_visual_features([1.0, 0.0, 0.0], top_k=3)
        assert len(results) == 3
        # v1 与查询完全一致 → similarity=1.0，应排第一
        assert results[0][0].id == "v1"
        assert results[0][1] == pytest.approx(1.0, abs=1e-6)
        # 相似度单调递减
        sims = [s for _, s in results]
        assert sims == sorted(sims, reverse=True)

    def test_match_with_page_id_filter(self, db_setup) -> None:
        """page_id 过滤限定检索范围。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create(
            {"id": "pf1", "page_id": "home", "visual_features": [1.0, 0.0, 0.0]}
        )
        lib.create(
            {"id": "pf2", "page_id": "settings", "visual_features": [1.0, 0.0, 0.0]}
        )

        # 只在 home 内对照
        home_results = lib.match_by_visual_features(
            [1.0, 0.0, 0.0], page_id="home"
        )
        assert len(home_results) == 1
        assert home_results[0][0].id == "pf1"

    def test_match_skips_anchor_without_visual_features(self, db_setup) -> None:
        """visual_features 为 NULL 的锚点应被过滤掉（不参与向量比对）。

        边界场景：用户录入了锚点但还没生成 embedding（visual_features=None），
        match_by_visual_features 的 SQL ``WHERE visual_features IS NOT NULL``
        应跳过这些锚点，只返回有向量的。
        """
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        # 有向量的锚点
        lib.create({"id": "vf1", "visual_features": [1.0, 0.0, 0.0]})
        # 无向量的锚点（录入但未 embedding）
        lib.create({"id": "vf_null", "page_id": "home"})

        results = lib.match_by_visual_features([1.0, 0.0, 0.0], top_k=5)
        assert len(results) == 1
        assert results[0][0].id == "vf1"


# ---------------------------------------------------------------------------
# is_empty
# ---------------------------------------------------------------------------
class TestIsEmpty:
    """is_empty（BF003 降级判定辅助）。"""

    def test_is_empty_true_when_no_data(self, db_setup) -> None:
        """空库返回 True。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        assert lib.is_empty() is True

    def test_is_empty_false_when_has_data(self, db_setup) -> None:
        """有数据返回 False。"""
        _, sf = db_setup
        lib = AnchorLibrary(sf)
        lib.create({"id": "ie-1", "page_id": "home"})
        assert lib.is_empty() is False
