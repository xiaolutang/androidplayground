"""Integration test conftest（R001-INT01）.

依据：
- Sprint Contract R001-INT01（mode: direct，9 端点集成全过 + 28 case 矩阵）
- 依赖 FF001（report_router）/ FF002（gap_router）/ ORB01（Orchestrator）
- Testcontainers PG + pgvector 隔离

设计要点：
1. Docker 可用 → Testcontainers PG + pgvector 容器（真实 DB 隔离）。
2. Docker 不可用 → pytest.skip 模块级标记，测试整体跳过（非 error）。
3. **FakeLLMGateway / FakeReproduceEngine / FakeADBTools**：集成测试不需真实
   LLM/ADB，使用预设响应驱动 ORB01 行为。
4. **app fixture**：用 TestClient 包装 FastAPI app，同时挂载 report_router +
   gap_router，DI 注入 fake 依赖（bug_report_repo / metric_point_repo / 等）。
5. **session 级容器复用**：整个测试文件共享一个 PG 容器（减少启动开销）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Iterator, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# Docker 可用性探测（模块级，早于任何 fixture 评估）
# ---------------------------------------------------------------------------
_DOCKER_AVAILABLE: Optional[bool] = None


def _check_docker() -> bool:
    """探测 Docker 是否可用（缓存结果）。

    用 subprocess 调 ``docker info``，返回 0 视为可用。
    任何异常（FileNotFoundError / CalledProcessError / timeout）→ False。
    """
    global _DOCKER_AVAILABLE
    if _DOCKER_AVAILABLE is not None:
        return _DOCKER_AVAILABLE
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=False,
            timeout=10,
        )
        _DOCKER_AVAILABLE = result.returncode == 0
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
    ):
        _DOCKER_AVAILABLE = False
    return _DOCKER_AVAILABLE


# ---------------------------------------------------------------------------
# Testcontainers fixture（session 级，复用容器）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def pg_container() -> Iterator[Any]:
    """启动 pgvector/pgvector:pg16 容器，session 结束自动 stop。

    若 Docker 不可用或容器启动失败（Colima 资源不足等），
    pytest.skip 跳过而非 error（符合 INT01 设计约束）。
    """
    if not _check_docker():
        pytest.skip("Docker not available; skipping integration tests")

    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers not installed: {exc}")

    container = PostgresContainer(
        image="pgvector/pgvector:pg16",
        driver="psycopg",
        username="test",
        password="test",
        dbname="test",
    )
    try:
        container.start()
    except Exception as exc:
        # 容器启动失败（镜像拉取超时 / Colima 资源不足 / 端口冲突等）
        # → skip 而非 error（CI 环境可能无 Docker）
        pytest.skip(f"Testcontainers PG start failed: {exc}")

    try:
        yield container
    finally:
        try:
            container.stop()
        except Exception:
            pass  # stop 失败不阻塞 session 结束


@pytest.fixture(scope="session")
def pg_url(pg_container: Any) -> str:
    """返回 Testcontainers 的动态连接串。"""
    return pg_container.get_connection_url()


# ---------------------------------------------------------------------------
# DB engine + schema 初始化（session 级，建表一次）
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def pg_engine(pg_url: str) -> Iterator[Engine]:
    """session 级 engine：启动时创建 pgvector 扩展 + 所有业务表。"""
    eng = create_engine(pg_url, pool_pre_ping=True, future=True)

    # CREATE EXTENSION vector
    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    # 注册 pgvector 适配器
    try:
        from pgvector.psycopg import register_vector
        from sqlalchemy import event

        @event.listens_for(eng, "connect")
        def _register(dbapi_conn: Any, _record: Any) -> None:
            register_vector(dbapi_conn)
    except ImportError:
        pass  # pgvector 不可用时降级（纯 SQL 测试仍可运行）

    # 创建所有业务表（从 agent.schemas 导入 Base）
    from agent.infra.db import Base
    # 触发所有 schema 模块加载，确保 Base.metadata 注册所有表
    import agent.schemas.bug_report  # noqa: F401
    import agent.schemas.capability_gap  # noqa: F401
    import agent.schemas.confidence  # noqa: F401
    import agent.schemas.diagnosis_report  # noqa: F401
    import agent.schemas.fix_patch  # noqa: F401
    import agent.schemas.kb_entry  # noqa: F401
    import agent.schemas.manual_fix_entry  # noqa: F401
    import agent.schemas.metric_point  # noqa: F401
    import agent.schemas.playbook  # noqa: F401
    import agent.schemas.repro_step  # noqa: F401
    import agent.schemas.signal  # noqa: F401
    import agent.schemas.trajectory  # noqa: F401

    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def db_session(pg_engine: Engine) -> Iterator[Session]:
    """每个测试用独立 session（事务隔离），测试结束 rollback + close。

    用 begin() 嵌套事务 + rollback 确保测试间数据隔离。
    """
    connection = pg_engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Fake LLM Gateway（按 prompt_type 分发预设响应）
# ---------------------------------------------------------------------------
@dataclass
class FakeLLMGateway:
    """FakeLLMGateway——按 prompt_type 分发预设响应。

    覆盖 fix_patch / diagnose / classify / reflection 四类 prompt。
    """

    responses: dict[str, Any] = field(default_factory=lambda: {
        "fix_patch": {"patch": "diff --git a/Foo.java b/Foo.java", "confidence": 0.85},
        "diagnose": {"root_cause": "NPE in MainActivity.onCreate", "location": "Foo.java:42"},
        "classify": {"symptom": "crash", "tier": 1},
        "reflection": {"summary": "fixed", "learnings": []},
    })
    calls: list[dict[str, Any]] = field(default_factory=list)

    def complete(self, prompt: str, *, prompt_type: str = "diagnose", **kwargs: Any) -> Any:
        """模拟 LLM 调用，按 prompt_type 返回预设响应。"""
        self.calls.append({"prompt": prompt, "prompt_type": prompt_type, "kwargs": kwargs})
        return self.responses.get(prompt_type, {"text": "fake"})


# ---------------------------------------------------------------------------
# Fake Reproduce Engine（模拟复现模式）
# ---------------------------------------------------------------------------
@dataclass
class FakeReproduceEngine:
    """FakeReproduceEngine——模拟复现模式，返回预设截图序列。"""

    screenshot_sequence: list[str] = field(default_factory=lambda: [
        "screenshot://blank.png",
        "screenshot://error.png",
        "screenshot://normal.png",
    ])
    calls: list[dict[str, Any]] = field(default_factory=list)

    def reproduce(self, bug_report: Any, **kwargs: Any) -> Any:
        """模拟复现，返回截图序列。"""
        self.calls.append({"bug_id": getattr(bug_report, "id", None), "kwargs": kwargs})
        return SimpleNamespace(
            screenshots=list(self.screenshot_sequence),
            reproduced=True,
            steps=[{"action": "launch", "result": "crash"}],
        )


# ---------------------------------------------------------------------------
# Fake ADB Tools（探测模式预设截图序列）
# ---------------------------------------------------------------------------
@dataclass
class FakeADBTools:
    """FakeADBTools——探测模式预设截图序列（白屏/正常/异常等）。"""

    probe_sequence: list[str] = field(default_factory=lambda: [
        "screenshot://white.png",  # 白屏
        "screenshot://normal.png",  # 正常
        "screenshot://crash.png",  # 异常（crash）
    ])
    calls: list[str] = field(default_factory=list)

    def capture_screenshot(self, device_id: str = "emulator-5554") -> str:
        """返回下一张预设截图（循环）。"""
        self.calls.append(device_id)
        idx = len(self.calls) % len(self.probe_sequence)
        return self.probe_sequence[idx]

    def list_devices(self) -> list[str]:
        return ["emulator-5554"]


# ---------------------------------------------------------------------------
# In-memory BugReport 仓储（用于 app fixture，duck typing）
# ---------------------------------------------------------------------------
class InMemoryBugReportRepo:
    """In-memory BugReport 仓储，duck typing 兼容 report_router。

    支持 get / list / save_status 接口。
    """

    def __init__(self, reports: Optional[dict[str, Any]] = None) -> None:
        self._store: dict[str, Any] = dict(reports or {})

    def get(self, report_id: str) -> Any:
        return self._store.get(report_id)

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        tier: Optional[int] = None,
    ) -> tuple[list[Any], int]:
        items = list(self._store.values())
        if status is not None:
            items = [r for r in items if _get_attr(r, "status") == status]
        if tier is not None:
            items = [r for r in items if _get_attr(r, "tier") == tier]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def save_status(self, report_id: str, new_status: str) -> None:
        r = self._store.get(report_id)
        if r is not None:
            if isinstance(r, dict):
                r["status"] = new_status
            else:
                r.status = new_status

    def add(self, report: Any) -> None:
        """添加报告（测试辅助）。"""
        rid = _get_attr(report, "id")
        if rid:
            self._store[rid] = report


class InMemoryMetricPointRepo:
    """In-memory MetricPoint 仓储。"""

    def __init__(self) -> None:
        self.created: list[dict] = []

    def create(self, **kwargs: Any) -> Any:
        self.created.append(kwargs)
        return SimpleNamespace(id=kwargs.get("id", "mp-test"))


class InMemoryTrajectoryRepo:
    """In-memory Trajectory 仓储。"""

    def __init__(self, traj: Any = None) -> None:
        self._traj = traj

    def get(self, report_id: str) -> Any:
        return self._traj


class FakeReflowManager:
    """Fake ReflowManager——记录 trigger_by_regression / trigger_by_gap_fixed 调用。"""

    def __init__(self) -> None:
        self.regression_calls: list[tuple[Any, dict]] = []
        self.gap_calls: list[tuple[Any, str]] = []

    def trigger_by_regression(self, bug_report: Any, regression_signal: dict) -> Any:
        self.regression_calls.append((bug_report, regression_signal))
        return SimpleNamespace(reflowed=True)

    def trigger_by_gap_fixed(self, bug_report: Any, gap_id: str) -> Any:
        self.gap_calls.append((bug_report, gap_id))
        return SimpleNamespace(reflowed=True, skipped=False)


class FakeOrchestrator:
    """Fake Orchestrator——记录 run 调用。"""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def run(self, bug_report: Any) -> Any:
        self.calls.append(bug_report)
        return SimpleNamespace(status="received")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def make_bug(
    *,
    id: str = "bug-001",
    status: str = "received",
    tier: Optional[int] = None,
    symptom_type: str = "crash",
    title: Optional[str] = None,
    root_cause: Optional[str] = None,
    reflow_count: int = 0,
    pr_url: Optional[str] = None,
    created_at: str = "2026-06-01T00:00:00Z",
    updated_at: str = "2026-06-01T00:00:00Z",
    **extra: Any,
) -> SimpleNamespace:
    """构造 BugReport mock（SimpleNamespace duck typing）。"""
    return SimpleNamespace(
        id=id,
        status=status,
        tier=tier,
        symptom_type=symptom_type,
        title=title,
        root_cause=root_cause,
        reflow_count=reflow_count,
        pr_url=pr_url,
        created_at=created_at,
        updated_at=updated_at,
        **extra,
    )


# ---------------------------------------------------------------------------
# app fixture：FastAPI TestClient + DI 注入
# ---------------------------------------------------------------------------
@pytest.fixture
def app_fixture() -> dict[str, Any]:
    """构造 FastAPI app + TestClient + 所有 fake 依赖。

    返回 dict 包含：
        client: TestClient
        bug_repo: InMemoryBugReportRepo
        mp_repo: InMemoryMetricPointRepo
        traj_repo: InMemoryTrajectoryRepo
        reflow_mgr: FakeReflowManager
        orchestrator: FakeOrchestrator
        llm: FakeLLMGateway
        reproduce: FakeReproduceEngine
        adb: FakeADBTools
    """
    from agent.api.routers.gap_router import (
        get_gap_store,
        get_reflow_manager,
        router as gap_router,
    )
    from agent.api.routers.report_router import (
        _Deps,
        create_report_router,
        create_webhook_router,
    )

    bug_repo = InMemoryBugReportRepo()
    mp_repo = InMemoryMetricPointRepo()
    traj_repo = InMemoryTrajectoryRepo()
    reflow_mgr = FakeReflowManager()
    orchestrator = FakeOrchestrator()
    llm = FakeLLMGateway()
    reproduce = FakeReproduceEngine()
    adb = FakeADBTools()

    deps = _Deps(
        orchestrator=orchestrator,
        reflow_manager=reflow_mgr,
        bug_report_repo=bug_repo,
        metric_point_repo=mp_repo,
        trajectory_repo=traj_repo,
        clarify_option_provider=lambda rid: [
            {"id": "opt1", "question": "What device?", "context": "device"},
        ],
        webhook_platforms={"sentry", "crashlytics"},
    )

    app = FastAPI()
    app.include_router(create_report_router(deps))
    app.include_router(create_webhook_router(deps))
    app.include_router(gap_router)

    # gap_router 使用 dependency_overrides
    fake_gap_store = SimpleNamespace(
        list=lambda *a, **kw: [],
        get=lambda gid: None,
        transition=lambda gid, to, **kw: SimpleNamespace(
            id=gid, status=getattr(to, "value", str(to)),
            linked_bug_ids=[],
        ),
    )
    app.dependency_overrides[get_gap_store] = lambda: fake_gap_store
    app.dependency_overrides[get_reflow_manager] = lambda: reflow_mgr

    client = TestClient(app)

    return {
        "client": client,
        "bug_repo": bug_repo,
        "mp_repo": mp_repo,
        "traj_repo": traj_repo,
        "reflow_mgr": reflow_mgr,
        "orchestrator": orchestrator,
        "llm": llm,
        "reproduce": reproduce,
        "adb": adb,
        "gap_store": fake_gap_store,
        "app": app,
    }
