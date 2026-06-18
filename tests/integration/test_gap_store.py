"""BF008 集成测试：GapStore CRUD + 7 态迁移 + INV-2 + bug 关联（真实 PG Testcontainers）。

覆盖 test_tasks 场景：
1. create 强制初始状态 IDENTIFIED
2. 合法迁移（IDENTIFIED -> WAITING -> UNBLOCKED -> RESOLVED）
3. 非法迁移抛 GapStateTransitionError
4. 终态保护（WONT_FIX 后不可迁出）
5. INV-2：delete 禁止（GapDeleteError）
6. link/unlink bug（去重 + 移除）
7. archive（软归档到 WONT_FIX）
8. list 按 status 过滤
"""
from __future__ import annotations

from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from agent.gap.gap_store import (
    GapDeleteError,
    GapStateTransitionError,
    GapStore,
)
from agent.infra.db import Base, init_vector_extension
from agent.schemas.capability_gap import CapabilityGapStatus


# ---------------------------------------------------------------------------
# Testcontainers fixture（module 级复用容器）
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
    """每个测试函数用独立 engine + 全量建表，测试结束 drop all。

    策略：
    - 用 create_engine 指向 Testcontainers 动态 URL（不依赖模块级 engine）。
    - init_vector_extension 注册 pgvector 适配器。
    - Base.metadata.create_all 建 SCH01 全部表（含 FK 依赖）。
    - 测试结束 drop_all 清理，避免测试间数据污染。
    """
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
        # 用 DROP SCHEMA CASCADE 替代 drop_all，规避 BugReport /
        # ConfidenceScore / FixPatch / Trajectory 之间的循环 FK 导致的
        # CircularDependencyError（drop_all 无法拓扑排序循环依赖表）。
        with engine_local.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        engine_local.dispose()


# ---------------------------------------------------------------------------
# 场景 1：create 强制初始 IDENTIFIED
# ---------------------------------------------------------------------------
def test_create_initial_state_identified(
    session_factory: sessionmaker,
) -> None:
    """新建 gap，status 必须为 IDENTIFIED。"""
    store = GapStore(session_factory)
    gap = store.create(
        {
            "id": "gap-test-001",
            "gap_type": "信息",
            "description": "test gap",
        }
    )
    assert gap.status == CapabilityGapStatus.IDENTIFIED.value
    assert gap.id == "gap-test-001"


def test_create_ignores_incoming_status(
    session_factory: sessionmaker,
) -> None:
    """即使 gap_data 传入 status，也被强制覆盖为 IDENTIFIED。"""
    store = GapStore(session_factory)
    gap = store.create(
        {
            "id": "gap-test-002",
            "gap_type": "设施",
            "description": "test",
            "status": CapabilityGapStatus.RESOLVED.value,  # 应被忽略
        }
    )
    assert gap.status == CapabilityGapStatus.IDENTIFIED.value


# ---------------------------------------------------------------------------
# 场景 2：合法迁移主路径
# ---------------------------------------------------------------------------
def test_legal_transition_main_path(
    session_factory: sessionmaker,
) -> None:
    """IDENTIFIED -> WAITING -> UNBLOCKED -> RESOLVED 全链路。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-main-001", "gap_type": "信息", "description": "main path"}
    )

    g1 = store.transition(gap.id, CapabilityGapStatus.WAITING)
    assert g1.status == CapabilityGapStatus.WAITING.value

    g2 = store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)
    assert g2.status == CapabilityGapStatus.UNBLOCKED.value

    g3 = store.transition(gap.id, CapabilityGapStatus.RESOLVED)
    assert g3.status == CapabilityGapStatus.RESOLVED.value


def test_legal_transition_invalid_unblock_loop(
    session_factory: sessionmaker,
) -> None:
    """UNBLOCKED -> INVALID_UNBLOCK -> WAITING 重识别回路。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-loop-001", "gap_type": "模式", "description": "loop"}
    )
    store.transition(gap.id, CapabilityGapStatus.WAITING)
    store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)
    g = store.transition(gap.id, CapabilityGapStatus.INVALID_UNBLOCK)
    assert g.status == CapabilityGapStatus.INVALID_UNBLOCK.value

    g2 = store.transition(gap.id, CapabilityGapStatus.WAITING)
    assert g2.status == CapabilityGapStatus.WAITING.value


# ---------------------------------------------------------------------------
# 场景 3：非法迁移抛 GapStateTransitionError
# ---------------------------------------------------------------------------
def test_illegal_transition_raises(
    session_factory: sessionmaker,
) -> None:
    """IDENTIFIED -> RESOLVED 跨阶段非法。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-illegal-001", "gap_type": "信息", "description": "illegal"}
    )
    with pytest.raises(GapStateTransitionError):
        store.transition(gap.id, CapabilityGapStatus.RESOLVED)


def test_illegal_transition_identified_to_unblocked(
    session_factory: sessionmaker,
) -> None:
    """IDENTIFIED -> UNBLOCKED 非法（必须经 WAITING）。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-illegal-002", "gap_type": "信息", "description": "skip"}
    )
    with pytest.raises(GapStateTransitionError):
        store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)


# ---------------------------------------------------------------------------
# 场景 4：终态保护
# ---------------------------------------------------------------------------
def test_terminal_state_no_out_transition(
    session_factory: sessionmaker,
) -> None:
    """WONT_FIX 终态后不可迁出。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-terminal-001", "gap_type": "信息", "description": "terminal"}
    )
    # IDENTIFIED -> WONT_FIX（合法入终态）
    store.transition(gap.id, CapabilityGapStatus.WONT_FIX)
    # 终态再迁出应失败
    with pytest.raises(GapStateTransitionError):
        store.transition(gap.id, CapabilityGapStatus.IDENTIFIED)
    with pytest.raises(GapStateTransitionError):
        store.transition(gap.id, CapabilityGapStatus.WAITING)


def test_resolved_is_terminal(
    session_factory: sessionmaker,
) -> None:
    """RESOLVED 终态后不可迁出。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-terminal-002", "gap_type": "信息", "description": "resolved"}
    )
    store.transition(gap.id, CapabilityGapStatus.WAITING)
    store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)
    store.transition(gap.id, CapabilityGapStatus.RESOLVED)
    # RESOLVED -> 任何状态均非法
    with pytest.raises(GapStateTransitionError):
        store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)


# ---------------------------------------------------------------------------
# 场景 5：INV-2 硬删禁止
# ---------------------------------------------------------------------------
def test_delete_forbidden(
    session_factory: sessionmaker,
) -> None:
    """INV-2：硬删禁止，抛 GapDeleteError。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-inv2-001", "gap_type": "信息", "description": "inv2"}
    )
    with pytest.raises(GapDeleteError):
        store.delete(gap.id)
    # 验证记录还在
    assert store.get(gap.id) is not None


# ---------------------------------------------------------------------------
# 场景 6：link / unlink bug
# ---------------------------------------------------------------------------
def test_link_unlink_bug(
    session_factory: sessionmaker,
) -> None:
    """关联 bug：去重添加 + 移除。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-link-001", "gap_type": "信息", "description": "link"}
    )

    store.link_bug(gap.id, "bug-100")
    store.link_bug(gap.id, "bug-200")
    store.link_bug(gap.id, "bug-100")  # 去重
    assert sorted(store.list_linked_bugs(gap.id)) == ["bug-100", "bug-200"]

    store.unlink_bug(gap.id, "bug-100")
    assert store.list_linked_bugs(gap.id) == ["bug-200"]


def test_link_bug_nonexistent_gap(
    session_factory: sessionmaker,
) -> None:
    """link_bug 到不存在的 gap 抛 ValueError。"""
    store = GapStore(session_factory)
    with pytest.raises(ValueError):
        store.link_bug("nonexistent", "bug-1")


def test_list_linked_bugs_nonexistent(
    session_factory: sessionmaker,
) -> None:
    """list_linked_bugs 不存在的 gap 返回空列表。"""
    store = GapStore(session_factory)
    assert store.list_linked_bugs("nonexistent") == []


# ---------------------------------------------------------------------------
# 场景 7：archive（软归档）
# ---------------------------------------------------------------------------
def test_archive_via_wont_fix(
    session_factory: sessionmaker,
) -> None:
    """archive 等价于 transition(WONT_FIX)。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-archive-001", "gap_type": "信息", "description": "archive"}
    )
    archived = store.archive(gap.id)
    assert archived.status == CapabilityGapStatus.WONT_FIX.value


def test_archive_terminal_raises(
    session_factory: sessionmaker,
) -> None:
    """已是终态 RESOLVED 的 gap 无法 archive。"""
    store = GapStore(session_factory)
    gap = store.create(
        {"id": "gap-archive-002", "gap_type": "信息", "description": "done"}
    )
    store.transition(gap.id, CapabilityGapStatus.WAITING)
    store.transition(gap.id, CapabilityGapStatus.UNBLOCKED)
    store.transition(gap.id, CapabilityGapStatus.RESOLVED)
    with pytest.raises(GapStateTransitionError):
        store.archive(gap.id)


# ---------------------------------------------------------------------------
# 场景 8：list 按 status 过滤
# ---------------------------------------------------------------------------
def test_list_filter_by_status(
    session_factory: sessionmaker,
) -> None:
    """list(status=X) 只返回该状态的 gap。"""
    store = GapStore(session_factory)
    store.create(
        {"id": "gap-list-001", "gap_type": "信息", "description": "a"}
    )
    g2 = store.create(
        {"id": "gap-list-002", "gap_type": "设施", "description": "b"}
    )
    store.transition(g2.id, CapabilityGapStatus.WAITING)

    waiting = store.list(status=CapabilityGapStatus.WAITING)
    assert len(waiting) == 1
    assert waiting[0].id == g2.id

    identified = store.list(status=CapabilityGapStatus.IDENTIFIED)
    assert len(identified) == 1
    assert identified[0].id == "gap-list-001"


def test_list_all(
    session_factory: sessionmaker,
) -> None:
    """list() 无过滤返回全部。"""
    store = GapStore(session_factory)
    store.create(
        {"id": "gap-all-001", "gap_type": "信息", "description": "a"}
    )
    store.create(
        {"id": "gap-all-002", "gap_type": "设施", "description": "b"}
    )
    all_gaps = store.list()
    assert len(all_gaps) == 2
