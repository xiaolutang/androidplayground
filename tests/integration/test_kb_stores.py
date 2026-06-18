"""KB 三层 store 集成测试（R001-BF005，Testcontainers pgvector/pgvector:pg16）。

覆盖：
1. 三层 store CRUD（共表 layer 分流）
2. pattern_store 写入权限拒绝（非白名单 caller_id → KBPermissionError + 事务回滚）
3. layer 防串层（TrajectoryStore.create 传 layer="pattern" 被覆写为 "raw_trajectory"）

沿用 INF03 conftest 的 Testcontainers fixture 模式。
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from agent.kb.exceptions import KBPermissionError
from agent.kb.stores.negative_knowledge_store import NegativeKnowledgeStore
from agent.kb.stores.pattern_store import (
    PATTERN_WRITE_ALLOWLIST,
    PatternStore,
)
from agent.kb.stores.trajectory_store import TrajectoryStore
from agent.schemas.kb_entry import KBEntry, KBLayer


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
    """返回指向 Testcontainers 的动态连接串。"""
    return pg_container.get_connection_url()


@pytest.fixture
def db_setup(pg_url: str) -> Iterator[tuple[Engine, sessionmaker]]:
    """每个测试用独立 engine + 建表 + 注册 pgvector。

    返回 (engine, session_factory)。
    """
    from agent.infra.db import init_vector_extension

    eng = create_engine(pg_url, pool_pre_ping=True, future=True)

    # 创建 pgvector 扩展
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 注册 pgvector 适配器
    init_vector_extension(eng)

    # 建表（KBEntry.__table__）
    KBEntry.__table__.create(eng, checkfirst=True)

    SessionFactory = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)

    yield eng, SessionFactory

    # 清理
    KBEntry.__table__.drop(eng, checkfirst=True)
    eng.dispose()


# ---------------------------------------------------------------------------
# AC-1: 三层 store CRUD
# ---------------------------------------------------------------------------
class TestTrajectoryStoreCRUD:
    """TrajectoryStore CRUD（raw_trajectory 层）。"""

    def test_create_and_get(self, db_setup) -> None:
        """create 写入后 layer=raw_trajectory，get 能读回。"""
        _, sf = db_setup
        store = TrajectoryStore(sf)
        entry = store.create(
            {
                "id": "traj-1",
                "symptom_type": "crash",
                "root_cause_signals": [1.0, 0.0, 0.0],
                "content": {"trace": "NullPointerException"},
                "source": "bb013",
            }
        )
        assert entry.layer == KBLayer.RAW_TRAJECTORY.value
        assert entry.id == "traj-1"

        got = store.get("traj-1")
        assert got is not None
        assert got.layer == KBLayer.RAW_TRAJECTORY.value
        assert got.symptom_type == "crash"

    def test_list_by_symptom(self, db_setup) -> None:
        """list 按 symptom_type 过滤。"""
        _, sf = db_setup
        store = TrajectoryStore(sf)
        store.create(
            {"id": "traj-a", "symptom_type": "crash", "root_cause_signals": [1, 0, 0]}
        )
        store.create(
            {"id": "traj-b", "symptom_type": "anr", "root_cause_signals": [0, 1, 0]}
        )

        crashes = store.list(symptom_type="crash")
        assert len(crashes) == 1
        assert crashes[0].id == "traj-a"

    def test_update(self, db_setup) -> None:
        """update 能更新字段。"""
        _, sf = db_setup
        store = TrajectoryStore(sf)
        store.create({"id": "traj-u", "symptom_type": "crash", "content": {"old": 1}})
        updated = store.update("traj-u", {"content": {"new": 2}})
        assert updated is not None
        assert updated.content == {"new": 2}

    def test_delete(self, db_setup) -> None:
        """delete 硬删，get 返回 None。"""
        _, sf = db_setup
        store = TrajectoryStore(sf)
        store.create({"id": "traj-d", "symptom_type": "crash"})
        assert store.delete("traj-d") is True
        assert store.get("traj-d") is None

    def test_layer_override(self, db_setup) -> None:
        """传 layer="pattern" 也被覆写为 raw_trajectory。"""
        _, sf = db_setup
        store = TrajectoryStore(sf)
        entry = store.create(
            {"id": "traj-override", "layer": "pattern", "symptom_type": "crash"}
        )
        assert entry.layer == KBLayer.RAW_TRAJECTORY.value


class TestNegativeKnowledgeStoreCRUD:
    """NegativeKnowledgeStore CRUD（negative_knowledge 层）。"""

    def test_create_and_get(self, db_setup) -> None:
        """create 写入后 layer=negative_knowledge。"""
        _, sf = db_setup
        store = NegativeKnowledgeStore(sf)
        entry = store.create(
            {
                "id": "neg-1",
                "symptom_type": "crash",
                "root_cause_signals": [0.9, 0.1, 0],
                "content": {"reason": "refuted"},
                "source": "bb013",
            }
        )
        assert entry.layer == KBLayer.NEGATIVE_KNOWLEDGE.value

        got = store.get("neg-1")
        assert got is not None
        assert got.layer == KBLayer.NEGATIVE_KNOWLEDGE.value

    def test_list_by_symptom(self, db_setup) -> None:
        """list 按 symptom_type 过滤。"""
        _, sf = db_setup
        store = NegativeKnowledgeStore(sf)
        store.create({"id": "neg-a", "symptom_type": "crash"})
        store.create({"id": "neg-b", "symptom_type": "anr"})

        crashes = store.list(symptom_type="crash")
        assert len(crashes) == 1
        assert crashes[0].id == "neg-a"


class TestPatternStoreCRUD:
    """PatternStore CRUD（pattern 层）。"""

    def test_create_allowed(self, db_setup) -> None:
        """白名单 caller_id 写入成功。"""
        _, sf = db_setup
        store = PatternStore(sf)
        entry = store.create(
            caller_id="bb015_manual_fix_recorder",
            entry_data={
                "id": "pat-1",
                "symptom_type": "crash",
                "root_cause_signals": [1, 0, 0],
                "content": {
                    "trigger_conditions": "NPE in MainActivity",
                    "patch_template": "null check",
                    "fix_example": "if (x != null)",
                },
                "source": "bb015_manual",
            },
        )
        assert entry.layer == KBLayer.PATTERN.value
        assert entry.content["trigger_conditions"] == "NPE in MainActivity"

    def test_get_no_caller_id(self, db_setup) -> None:
        """读操作不需要 caller_id。"""
        _, sf = db_setup
        store = PatternStore(sf)
        store.create(
            caller_id="bb015_manual_fix_recorder",
            entry_data={"id": "pat-r", "symptom_type": "crash"},
        )
        got = store.get("pat-r")
        assert got is not None
        assert got.id == "pat-r"


# ---------------------------------------------------------------------------
# AC-2: pattern_store 写入权限校验
# ---------------------------------------------------------------------------
class TestPatternStorePermission:
    """PatternStore 写权限校验（KBPermissionError + 事务回滚）。"""

    def test_non_whitelist_caller_denied(self, db_setup) -> None:
        """非白名单 caller_id → KBPermissionError。"""
        _, sf = db_setup
        store = PatternStore(sf)
        with pytest.raises(KBPermissionError) as exc_info:
            store.create(
                caller_id="bb013_reflection_agent",
                entry_data={"id": "pat-denied", "symptom_type": "crash"},
            )
        # 错误信息含 caller_id 和允许列表
        assert "bb013_reflection_agent" in str(exc_info.value)
        assert "bb015_manual_fix_recorder" in str(exc_info.value)

    def test_permission_error_not_builtin(self) -> None:
        """KBPermissionError 不继承 PermissionError。"""
        assert not issubclass(KBPermissionError, PermissionError)
        assert issubclass(KBPermissionError, Exception)

    def test_no_write_after_permission_error(self, db_setup) -> None:
        """权限失败后 DB 无写入（事务回滚）。"""
        _, sf = db_setup
        store = PatternStore(sf)
        with pytest.raises(KBPermissionError):
            store.create(
                caller_id="random_caller",
                entry_data={"id": "pat-rollback", "symptom_type": "crash"},
            )
        # 验证 DB 中没有该条目
        got = store.get("pat-rollback")
        assert got is None

    def test_update_permission_denied(self, db_setup) -> None:
        """update 非 caller_id → KBPermissionError。"""
        _, sf = db_setup
        store = PatternStore(sf)
        store.create(
            caller_id="bb015_manual_fix_recorder",
            entry_data={"id": "pat-upd", "symptom_type": "crash"},
        )
        with pytest.raises(KBPermissionError):
            store.update(
                caller_id="bad_caller",
                entry_id="pat-upd",
                patch={"content": {"new": 1}},
            )

    def test_delete_permission_denied(self, db_setup) -> None:
        """delete 非 caller_id → KBPermissionError。"""
        _, sf = db_setup
        store = PatternStore(sf)
        store.create(
            caller_id="bb015_manual_fix_recorder",
            entry_data={"id": "pat-del", "symptom_type": "crash"},
        )
        with pytest.raises(KBPermissionError):
            store.delete(caller_id="bad_caller", entry_id="pat-del")

    def test_allowlist_contains_bb015(self) -> None:
        """PATTERN_WRITE_ALLOWLIST 包含 bb015_manual_fix_recorder。"""
        assert "bb015_manual_fix_recorder" in PATTERN_WRITE_ALLOWLIST
