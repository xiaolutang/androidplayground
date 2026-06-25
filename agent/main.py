"""FastAPI 应用入口（R001-ENT01）。

依据：
- Sprint Contract R001-ENT01（mode: direct）
- 依赖 FF001 report_router / FF002 gap_router / ORB01 Orchestrator / INF03 db

设计要点：
1. **lifespan**：应用启动时初始化数据库（建表 + pgvector 扩展），
   启动失败记录日志但不阻断（允许在无 DB 环境下启动用于调试）。
2. **路由挂载**：
   - FF001 report_router + webhook_router（通过 create_report_router / create_webhook_router 工厂）
   - FF002 gap_router（模块级 router，依赖通过 dependency_overrides 注入）
3. **健康检查**：GET /health → {"status": "ok"}
4. **CORS**：开发环境允许所有源（生产环境应通过环境变量收紧）
5. **/openapi.json**：FastAPI 内置，作为前后端契约源
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Callable, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.api.routers.gap_router import get_gap_store, get_reflow_manager, router as gap_router
from agent.api.routers.report_router import (
    _Deps as ReportDeps,
    create_report_router,
    create_webhook_router,
)

logger = logging.getLogger(__name__)

__all__ = ["create_app", "app"]


# ---------------------------------------------------------------------------
# 默认依赖占位（生产环境通过 create_app 参数注入，测试用 mock）
# ---------------------------------------------------------------------------
def _default_gap_store() -> Any:  # pragma: no cover
    """默认 GapStore 占位——生产环境由 create_app 覆盖。"""
    raise NotImplementedError("GapStore dependency not configured")


def _default_reflow_manager() -> Any:  # pragma: no cover
    """默认 ReflowManager 占位——生产环境由 create_app 覆盖。"""
    raise NotImplementedError("ReflowManager dependency not configured")


# ---------------------------------------------------------------------------
# 应用工厂
# ---------------------------------------------------------------------------
def create_app(
    *,
    orchestrator: Any = None,
    reflow_manager: Any = None,
    session_factory: Optional[Callable[[], Any]] = None,
    bug_report_repo: Any = None,
    metric_point_repo: Any = None,
    trajectory_repo: Any = None,
    clarify_option_provider: Optional[Callable[[str], list[dict]]] = None,
    gap_store: Any = None,
    webhook_platforms: Optional[set[str]] = None,
    enable_db_init: bool = True,
    enable_cors: bool = True,
) -> FastAPI:
    """构造 FastAPI 应用实例。

    所有依赖参数均为可选（默认 None），允许在无 DB / LLM 环境下启动用于调试。
    生产环境应传入真实依赖；测试环境传入 mock。

    Args:
        orchestrator: ORB01 Orchestrator 实例。
        reflow_manager: BB011 ReflowManager 实例。
        session_factory: DB session 工厂。
        bug_report_repo: BugReport 仓储。
        metric_point_repo: MetricPoint 仓储。
        trajectory_repo: Trajectory 仓储。
        clarify_option_provider: 追问候选提供者。
        gap_store: BF008 GapStore 实例。
        webhook_platforms: 允许的 webhook 平台白名单。
        enable_db_init: 是否在启动时初始化 DB（测试可关闭）。
        enable_cors: 是否启用 CORS 中间件（测试可关闭）。

    Returns:
        FastAPI 应用实例。
    """
    # -----------------------------------------------------------------
    # lifespan：DB 初始化（建表 + pgvector 扩展）
    # -----------------------------------------------------------------
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if enable_db_init:
            try:
                from agent.infra.db import Base, engine, init_vector_extension

                init_vector_extension(engine)
                Base.metadata.create_all(bind=engine)
                logger.info("Database initialized (pgvector extension + tables)")
            except Exception as exc:
                logger.warning(
                    "Database initialization failed (app will start anyway): %s",
                    exc,
                )
        yield

    app = FastAPI(
        title="Client Bug Fix Agent",
        version="1.0.0",
        lifespan=lifespan,
    )

    # -----------------------------------------------------------------
    # CORS 中间件（开发环境允许所有源）
    # -----------------------------------------------------------------
    if enable_cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # -----------------------------------------------------------------
    # FF001：report_router + webhook_router（工厂函数注入）
    # -----------------------------------------------------------------
    report_deps = ReportDeps(
        orchestrator=orchestrator,
        reflow_manager=reflow_manager,
        session_factory=session_factory,
        bug_report_repo=bug_report_repo,
        metric_point_repo=metric_point_repo,
        trajectory_repo=trajectory_repo,
        clarify_option_provider=clarify_option_provider,
        webhook_platforms=webhook_platforms,
    )
    app.include_router(create_report_router(report_deps))
    app.include_router(create_webhook_router(report_deps))

    # -----------------------------------------------------------------
    # FF002：gap_router（dependency_overrides 注入）
    # -----------------------------------------------------------------
    app.include_router(gap_router)
    if gap_store is not None:
        app.dependency_overrides[get_gap_store] = lambda: gap_store
    if reflow_manager is not None:
        app.dependency_overrides[get_reflow_manager] = lambda: reflow_manager

    # -----------------------------------------------------------------
    # 健康检查端点
    # -----------------------------------------------------------------
    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """健康检查端点。"""
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# 模块级 app 实例（供 uvicorn 直接引用：uvicorn agent.main:app）
# ---------------------------------------------------------------------------
def _wire_production_deps() -> dict[str, Any]:
    """从环境装配生产依赖（DB-backed GapStore + BugReportDbRepository + SessionLocal）。

    失败时返回空 dict，由 create_app 用各参数默认值（None）启动，
    保留「无 DB 调试模式」兼容性。
    """
    try:
        from agent.gap.gap_store import GapStore
        from agent.gap_mgmt.reflow_manager import ReflowManager
        from agent.infra.db import SessionLocal
        from agent.infra.db_repositories import MetricPointDbRepository
        from agent.intake.bug_report_db_store import BugReportDbRepository

        return {
            "gap_store": GapStore(SessionLocal),
            "reflow_manager": ReflowManager(),
            "bug_report_repo": BugReportDbRepository(SessionLocal),
            "metric_point_repo": MetricPointDbRepository(SessionLocal),
            "session_factory": SessionLocal,
            "clarify_option_provider": lambda rid: [],
            "webhook_platforms": {"sentry", "crashlytics", "bugly"},
        }
    except Exception as exc:  # pragma: no cover
        logger.warning("Production deps wiring failed: %s", exc)
        return {}


app = create_app(**_wire_production_deps())
