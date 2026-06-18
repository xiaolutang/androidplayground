"""R001-INF03 db.py 集成测试（Testcontainers PG + pgvector）。

覆盖 test_tasks 场景（D4 存储层基础设施）：
1. Testcontainers 启动 pgvector/pgvector:pg16 镜像，获取动态连接串
2. CREATE EXTENSION IF NOT EXISTS vector 成功
3. Vector(3) 类型可读写：建临时表 → 写入向量 → 读回断言相等
4. db.py 的 session 工厂能正常 insert/query

注意：
- Testcontainers 起容器需 10-30s，首次拉镜像更久（耐心等待）。
- 每个测试用独立 engine + 临时表，避免互相污染。
- 容器通过 session 级 fixture 复用（全文件只起一次），session 结束自动 stop。
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, text, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from testcontainers.postgres import PostgresContainer

# 用 monkeypatch 重建 engine 需要重新 import db 模块的 engine；
# 为隔离 Testcontainers 动态 URL 与模块级 engine（绑死 config 默认 URL），
# 测试中直接用 create_engine 指向 Testcontainers URL，不依赖模块级 engine。

from pgvector.sqlalchemy import Vector


# ---------------------------------------------------------------------------
# Testcontainers session 级 fixture：全文件复用一个容器
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def pg_container() -> Iterator[PostgresContainer]:
    """启动 pgvector/pgvector:pg16 容器，session 结束自动 stop。

    镜像说明：
    - ``pgvector/pgvector:pg16`` 官方 pgvector 镜像，自带 pgvector .so + .control，
      ``CREATE EXTENSION vector`` 即可启用，无需额外安装步骤。
    - driver='psycopg'：匹配 config.py 的 ``postgresql+psycopg://`` 协议（psycopg3）。
    """
    # 首次拉镜像可能很慢，给充足超时（Testcontainers 默认已较宽容）
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
    """返回指向 Testcontainers 的动态连接串（postgresql+psycopg://...）。"""
    return pg_container.get_connection_url()


@pytest.fixture
def engine(pg_url: str) -> Iterator[Engine]:
    """每个测试用独立 engine（隔离连接池 / event listener），测试结束 dispose。"""
    eng = create_engine(pg_url, pool_pre_ping=True, future=True)
    try:
        yield eng
    finally:
        eng.dispose()


# ---------------------------------------------------------------------------
# 场景 1 + 2：CREATE EXTENSION vector 成功
# ---------------------------------------------------------------------------
def test_create_extension_vector_succeeds(engine: Engine) -> None:
    """连上 Testcontainers PG 后，CREATE EXTENSION IF NOT EXISTS vector 成功。

    pgvector/pgvector:pg16 镜像预装 pgvector，此操作应无异常。
    再通过查 ``pg_extension`` 确认扩展确实已安装。
    """
    with engine.begin() as conn:
        # 不抛异常即成功
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        assert row is not None, "pg_extension 中应有 'vector' 扩展记录"
        assert row[0] == "vector"


def test_create_extension_is_idempotent(engine: Engine) -> None:
    """CREATE EXTENSION IF NOT EXISTS 幂等：多次执行不报错。"""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


# ---------------------------------------------------------------------------
# 场景 3：Vector 类型可读写
# ---------------------------------------------------------------------------
def test_vector_type_write_and_read(engine: Engine) -> None:
    """建临时表含 Vector(3) 列，写入向量，读回断言相等。

    验证 D4 核心能力：pgvector Vector 类型在 PG 内可正常存取。
    用裸 MetaData / Table（不依赖 ORM Base），聚焦类型层正确性。
    """
    # 先确保扩展已创建
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    metadata = MetaData()
    t = Table(
        "inf03_vec_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("embedding", Vector(3)),
    )
    metadata.create_all(engine, tables=[t])

    expected = [0.1, 0.2, 0.3]
    with engine.begin() as conn:
        conn.execute(t.insert().values(id=1, embedding=expected))

    with engine.connect() as conn:
        row = conn.execute(text("SELECT embedding FROM inf03_vec_probe WHERE id = 1")).fetchone()
        assert row is not None, "应能读回刚写入的向量行"
        # pgvector 返回 Python list（经 register_vector 后）或 PG 文本表示 "[0.1,0.2,0.3]"
        got = row[0]
        # 归一化为 list[float] 比较
        if isinstance(got, str):
            # 去除方括号后按逗号分割
            got = [float(x) for x in got.strip("[]").split(",")]
        assert list(got) == pytest.approx(expected), f"读回向量 {got} != 写入 {expected}"

    # 清理临时表
    t.drop(engine, checkfirst=True)


def test_vector_multiple_rows_query(engine: Engine) -> None:
    """写入多条向量后能用 raw SQL 正常查询（覆盖批量场景）。"""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    metadata = MetaData()
    t = Table(
        "inf03_vec_multi",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("embedding", Vector(3)),
    )
    metadata.create_all(engine, tables=[t])

    rows = [
        {"id": 1, "embedding": [1.0, 0.0, 0.0]},
        {"id": 2, "embedding": [0.0, 1.0, 0.0]},
        {"id": 3, "embedding": [0.0, 0.0, 1.0]},
    ]
    with engine.begin() as conn:
        conn.execute(t.insert(), rows)

    with engine.connect() as conn:
        result = conn.execute(text("SELECT count(*) FROM inf03_vec_multi")).scalar()
        assert result == 3

        # pgvector 距离查询（L2 距离最近）
        nearest = conn.execute(
            text("SELECT id FROM inf03_vec_multi ORDER BY embedding <-> '[1,0,0]' LIMIT 1")
        ).scalar()
        assert nearest == 1

    t.drop(engine, checkfirst=True)


# ---------------------------------------------------------------------------
# 场景 4：db.py 的 session 工厂能正常 insert/query
# ---------------------------------------------------------------------------
def test_session_factory_works(pg_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """通过 db.py 的 get_session / SessionLocal 能正常 insert/query。

    隔离策略：db.py 的模块级 engine 绑定了 config.DATABASE_URL（默认指向本地），
    无法直接连 Testcontainers。测试通过 monkeypatch 环境变量 + 重建模块级 engine
    的方式，让 db.SessionLocal 指向 Testcontainers。

    验证：
    - get_session() 返回的 Session 能建表（含 Vector 列）、insert、query、commit。
    """
    # 用 pg_url 重建 db 模块的 engine 与 SessionLocal 绑定
    import agent.infra.db as dbmod

    test_engine = create_engine(pg_url, pool_pre_ping=True, future=True)

    # 直接替换模块级 engine 与 SessionLocal 的绑定，避免依赖 import-time URL
    monkeypatch.setattr(dbmod, "engine", test_engine, raising=True)
    new_session_local = __import__(
        "sqlalchemy.orm", fromlist=["sessionmaker"]
    ).sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False, future=True)
    monkeypatch.setattr(dbmod, "SessionLocal", new_session_local, raising=True)

    # 初始化 pgvector 扩展（在 test_engine 上）
    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 用一个独立的 Base 子类定义临时表（不污染 SCH01 的 Base.metadata）
    from sqlalchemy.orm import DeclarativeBase

    class _ProbeBase(DeclarativeBase):
        pass

    class _ProbeRow(_ProbeBase):
        __tablename__ = "inf03_session_probe"
        id = Column(Integer, primary_key=True)
        embedding = Column(Vector(3))

    _ProbeBase.metadata.create_all(test_engine, tables=[_ProbeRow.__table__])

    try:
        # 测试 get_session() 路径
        s1 = dbmod.get_session()
        assert isinstance(s1, Session)
        try:
            s1.add(_ProbeRow(id=10, embedding=[0.5, 0.5, 0.5]))
            s1.commit()
        finally:
            s1.close()

        # 测试 SessionLocal() 路径
        with dbmod.SessionLocal() as s2:
            row = s2.execute(
                text("SELECT id, embedding FROM inf03_session_probe WHERE id = 10")
            ).fetchone()
            assert row is not None
            assert row[0] == 10
            got = row[1]
            if isinstance(got, str):
                got = [float(x) for x in got.strip("[]").split(",")]
            assert list(got) == pytest.approx([0.5, 0.5, 0.5])
    finally:
        _ProbeBase.metadata.drop_all(test_engine, tables=[_ProbeRow.__table__])
        test_engine.dispose()


def test_base_is_declarative_base_subclass() -> None:
    """db.Base 是 SQLAlchemy 2.0 DeclarativeBase 的子类（供 SCH01 继承）。"""
    from sqlalchemy.orm import DeclarativeBase

    from agent.infra.db import Base

    assert issubclass(Base, DeclarativeBase)


def test_vector_reexported_from_db() -> None:
    """db.py re-export Vector 供 SCH01 使用（from agent.infra.db import Vector）。"""
    from agent.infra.db import Vector as DbVector
    from pgvector.sqlalchemy import Vector as PgVector

    assert DbVector is PgVector
