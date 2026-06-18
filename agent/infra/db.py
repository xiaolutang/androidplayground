"""数据库基础设施（R001-INF03）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md D4（PostgreSQL + pgvector 同库）
- 任务包 R001-INF03 test_tasks（Testcontainers 起 PG+pgvector；CREATE EXTENSION vector；Vector 类型可读写）

设计要点：
1. SQLAlchemy 2.0 风格：``DeclarativeBase`` + ``sessionmaker`` + ``create_engine``。
2. 连接串从 ``agent.infra.config.DATABASE_URL`` 读取（D4 默认
   ``postgresql+psycopg://localhost:5432/bugfix_agent``），不硬编码。
3. pgvector 注册：
   - ORM 层：直接使用 ``pgvector.sqlalchemy.Vector`` 列类型（SCH01 继承 Base 建表时引用）。
   - 连接层：``init_vector_extension(engine)`` 先 ``CREATE EXTENSION IF NOT EXISTS vector``，
     再通过 ``pgvector.psycopg.register_vector`` 在连接上注册 Vector 适配器，
     使 ``text()`` / raw SQL 路径也能正确编解码向量。
4. ``Base`` 供后续 Schema 任务（SCH01）继承；本模块不定义任何业务表。
5. ``SessionLocal`` 与 ``get_session()`` 两种风格同时暴露，便于业务层与测试按需取用。
6. **不在 import 期建连**：engine 在模块级创建（惰性连接池），``init_vector_extension``
   需显式调用（应用启动 / 测试 fixture 调用），避免纯 import 副作用触发 DB 依赖。
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# pgvector SQLAlchemy 列类型（供 SCH01 建表时 ``Column(Vector(dim))`` 使用）
from pgvector.sqlalchemy import Vector  # noqa: F401  re-export for downstream schemas

from agent.infra.config import DATABASE_URL

__all__ = [
    "Base",
    "engine",
    "SessionLocal",
    "get_session",
    "init_vector_extension",
    "Vector",
]


# ---------------------------------------------------------------------------
# SQLAlchemy 2.0 DeclarativeBase：SCH01 的 Schema 类继承自此 Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    """所有 ORM 表定义的公共基类（SQLAlchemy 2.0 风格）。

    注意：本模块不在此处声明任何业务表；表定义留给 R001-SCH01。
    """


# ---------------------------------------------------------------------------
# engine + session 工厂
# ---------------------------------------------------------------------------
# 模块级 engine（惰性连接池，import 时不会真正连 DB）
#   - pool_pre_ping=True：连接被回收后自动重建，避免长连接断开后首次操作失败
#   - future=True：SQLAlchemy 2.0 风格（默认即为 True，显式声明以明确意图）
engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

# session 工厂：业务层 ``with SessionLocal() as s: ...`` 或 ``get_session()``
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def get_session() -> Session:
    """返回一个新的 SQLAlchemy Session。

    典型用法（业务层 / FastAPI 依赖）::

        with get_session() as s:
            s.add(obj)
            s.commit()

    返回的 Session 需由调用方负责关闭（推荐 ``with`` 语句或 FastAPI ``yield`` 依赖）。
    """
    return SessionLocal()


def get_session_yield() -> Iterator[Session]:
    """FastAPI 依赖风格：yield 一个 Session 并在请求结束后关闭。

    用法::

        @app.get("/x")
        def handler(s: Session = Depends(get_session_yield)):
            ...
    """
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


# ---------------------------------------------------------------------------
# pgvector 扩展初始化
# ---------------------------------------------------------------------------
def init_vector_extension(eng: Engine) -> None:
    """在目标数据库上初始化 pgvector 扩展并注册 Vector 适配器。

    执行步骤：
    1. ``CREATE EXTENSION IF NOT EXISTS vector``：确保 pgvector 扩展存在（pgvector 镜像自带）。
    2. ``pgvector.psycopg.register_vector``：在当前 engine 的连接上注册 Vector 类型
       适配器，使 raw SQL / ``text()`` 路径能直接用 Python list/tuple 读写向量。

    幂等：多次调用无副作用（``IF NOT EXISTS`` + register 可重复执行）。

    Args:
        eng: 目标 engine（通常为模块级 ``engine``；测试可传入 Testcontainers engine）。

    Raises:
        OperationalError / ProgrammingError：若 DB 不可达或 pgvector 扩展不可用
            （镜像未预装 pgvector 时 CREATE EXTENSION 会失败）。
    """
    # 1. 创建扩展（pgvector 镜像自带 .so + .control，仅需 CREATE EXTENSION 启用）
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 2. 在连接层注册 pgvector 适配器（psycopg3 路径）
    #    register_vector 需要在每个物理连接上执行；SQLAlchemy 连接池场景下
    #    推荐用 event.listen 在 connect 事件上注册一次，使池中每条连接都生效。
    from sqlalchemy import event
    from pgvector.psycopg import register_vector

    @event.listens_for(eng, "connect")
    def _register_vector_on_connect(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        """每次从连接池取出新物理连接时，注册 pgvector 适配器。

        pgvector 的 register_vector 作用于单个 DBAPI 连接；SQLAlchemy 连接池
        会复用 / 新建连接，故在 connect 事件上挂载以保证每条连接都注册。
        """
        register_vector(dbapi_conn)
