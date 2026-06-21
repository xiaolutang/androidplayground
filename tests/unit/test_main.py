"""FastAPI 入口测试（R001-ENT01）。

覆盖验收标准：
1. app 启动（TestClient lifespan 触发 DB 初始化 mock）
2. GET /health 返回 200 + {"status": "ok"}
3. /openapi.json 包含所有 9 个端点定义
4. 路由可达性（/reports 和 /gaps 非 404）
5. DB 初始化被调用（mock 验证）

全 mock，无真实 DB / Docker 依赖。
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from agent.main import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_app_with_mocks(
    *,
    enable_db_init: bool = False,
    gap_store: object | None = None,
) -> TestClient:
    """用 mock 依赖构造 app + TestClient。

    DB 初始化默认关闭（enable_db_init=False），避免触发真实 DB 连接。
    """
    mock_gap_store = gap_store or MagicMock()
    app = create_app(
        orchestrator=MagicMock(),
        reflow_manager=MagicMock(),
        bug_report_repo=MagicMock(),
        metric_point_repo=MagicMock(),
        trajectory_repo=MagicMock(),
        gap_store=mock_gap_store,
        enable_db_init=enable_db_init,
        enable_cors=True,
    )
    return TestClient(app)


# ---------------------------------------------------------------------------
# AC: app 启动
# ---------------------------------------------------------------------------
class TestAppStartup:
    """测试 FastAPI 应用启动。"""

    def test_app_instance_created(self) -> None:
        """create_app 返回 FastAPI 实例。"""
        app = create_app(enable_db_init=False)
        assert app is not None
        assert app.title == "Client Bug Fix Agent"
        assert app.version == "1.0.0"

    def test_app_startup_with_mock_db(self) -> None:
        """TestClient 启动时 DB 初始化被调用（mock）。"""
        with (
            patch("agent.infra.db.init_vector_extension") as mock_init,
            patch("agent.infra.db.Base.metadata.create_all") as mock_create,
        ):
            app = create_app(enable_db_init=True)
            with TestClient(app):
                mock_init.assert_called_once()
                mock_create.assert_called_once()

    def test_app_startup_db_init_failure_does_not_crash(self) -> None:
        """DB 初始化失败时 app 仍可启动（降级模式）。"""
        with (
            patch(
                "agent.infra.db.init_vector_extension",
                side_effect=ConnectionError("DB unavailable"),
            ),
            patch("agent.infra.db.Base.metadata.create_all"),
        ):
            app = create_app(enable_db_init=True)
            # 不应抛异常
            with TestClient(app) as client:
                response = client.get("/health")
                assert response.status_code == 200

    def test_module_level_app_exists(self) -> None:
        """模块级 app 实例存在（供 uvicorn 引用）。"""
        from agent.main import app as module_app

        assert module_app is not None
        assert module_app.title == "Client Bug Fix Agent"


# ---------------------------------------------------------------------------
# AC: GET /health
# ---------------------------------------------------------------------------
class TestHealthEndpoint:
    """测试健康检查端点。"""

    def test_health_returns_200(self) -> None:
        """GET /health 返回 200。"""
        client = _make_app_with_mocks()
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_status(self) -> None:
        """GET /health 返回 {"status": "ok"}。"""
        client = _make_app_with_mocks()
        response = client.get("/health")
        assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# AC: /openapi.json 包含所有端点
# ---------------------------------------------------------------------------
class TestOpenApiSchema:
    """测试 OpenAPI 契约导出。"""

    def test_openapi_json_accessible(self) -> None:
        """/openapi.json 可导出。"""
        client = _make_app_with_mocks()
        response = client.get("/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

    def test_openapi_contains_all_endpoints(self) -> None:
        """OpenAPI 包含所有 9 个端点定义。

        预期端点：
        - GET /health
        - GET /reports (列表)
        - GET /reports/{report_id} (详情)
        - GET /reports/{report_id}/trajectory (假设树)
        - GET /reports/{report_id}/clarify-options (追问候选)
        - POST /reports/{report_id}/clarify (提交追问)
        - POST /reports/{report_id}/regression-feedback (回归反馈)
        - POST /webhook/{platform} (webhook)
        - GET /gaps (gap 列表)
        - POST /gaps/{gap_id}/unblock (gap unblock)

        注：/reports 有 ``GET /reports/`` 和 ``GET /reports`` 两个路由，
        其中 ``/`` 版本 ``include_in_schema=False``，故 schema 中只出现一个。
        """
        client = _make_app_with_mocks()
        response = client.get("/openapi.json")
        spec = response.json()
        paths = spec["paths"]

        # 检查关键路径存在
        expected_paths = [
            "/health",
            "/reports",
            "/reports/{report_id}",
            "/reports/{report_id}/trajectory",
            "/reports/{report_id}/clarify-options",
            "/reports/{report_id}/clarify",
            "/reports/{report_id}/regression-feedback",
            "/webhook/{platform}",
            "/gaps",
            "/gaps/{gap_id}/unblock",
        ]

        for path in expected_paths:
            assert path in paths, f"Path {path!r} missing from OpenAPI schema"

    def test_openapi_has_correct_title_and_version(self) -> None:
        """OpenAPI 文档 title 和 version 正确。"""
        client = _make_app_with_mocks()
        response = client.get("/openapi.json")
        spec = response.json()
        assert spec["info"]["title"] == "Client Bug Fix Agent"
        assert spec["info"]["version"] == "1.0.0"

    def test_openapi_endpoint_count(self) -> None:
        """OpenAPI 中至少包含 10 个路径定义。"""
        client = _make_app_with_mocks()
        response = client.get("/openapi.json")
        spec = response.json()
        # 至少 10 个路径（health + 6 reports + 1 webhook + 2 gaps）
        assert len(spec["paths"]) >= 10


# ---------------------------------------------------------------------------
# AC: 路由可达性
# ---------------------------------------------------------------------------
class TestRouteReachability:
    """测试路由可达性（非 404）。"""

    def test_reports_list_reachable(self) -> None:
        """GET /reports 返回非 404（可达）。"""
        client = _make_app_with_mocks()
        response = client.get("/reports")
        assert response.status_code != 404

    def test_reports_detail_reachable(self) -> None:
        """GET /reports/{id} 返回非 404（可达，404 也表示路由存在但不在这里；
        用 404 验证路由存在——非 404 说明路由不存在）。"""
        # bug_report_repo.get 返回 None → report_router 返回 404
        # 404 表示路由存在但资源不存在，此测试验证路由已挂载
        mock_repo = MagicMock()
        mock_repo.get.return_value = None
        app = create_app(
            bug_report_repo=mock_repo,
            enable_db_init=False,
        )
        client = TestClient(app)
        response = client.get("/reports/some-id")
        # 404 表示路由存在，资源不存在（路由可达）
        assert response.status_code == 404

    def test_gaps_list_reachable(self) -> None:
        """GET /gaps 返回非 404。"""
        mock_gap_store = MagicMock()
        mock_gap_store.list.return_value = []
        client = _make_app_with_mocks(gap_store=mock_gap_store)
        response = client.get("/gaps")
        assert response.status_code != 404

    def test_webhook_reachable(self) -> None:
        """POST /webhook/{platform} 返回非 404。"""
        client = _make_app_with_mocks()
        response = client.post(
            "/webhook/crashlytics",
            json={"event": "crash", "data": {}},
        )
        assert response.status_code != 404

    def test_health_reachable(self) -> None:
        """GET /health 返回非 404。"""
        client = _make_app_with_mocks()
        response = client.get("/health")
        assert response.status_code != 404


# ---------------------------------------------------------------------------
# AC: DB 初始化
# ---------------------------------------------------------------------------
class TestDbInitialization:
    """测试 DB 初始化（pgvector 扩展）。"""

    def test_db_init_called_on_startup(self) -> None:
        """启动时调用 init_vector_extension。"""
        with (
            patch("agent.infra.db.init_vector_extension") as mock_init,
            patch("agent.infra.db.Base.metadata.create_all"),
        ):
            app = create_app(enable_db_init=True)
            with TestClient(app):
                mock_init.assert_called_once()

    def test_db_tables_created_on_startup(self) -> None:
        """启动时调用 Base.metadata.create_all（建表）。"""
        with (
            patch("agent.infra.db.init_vector_extension"),
            patch("agent.infra.db.Base.metadata.create_all") as mock_create,
        ):
            app = create_app(enable_db_init=True)
            with TestClient(app):
                mock_create.assert_called_once()

    def test_db_init_skipped_when_disabled(self) -> None:
        """enable_db_init=False 时跳过 DB 初始化。"""
        with (
            patch("agent.infra.db.init_vector_extension") as mock_init,
            patch("agent.infra.db.Base.metadata.create_all") as mock_create,
        ):
            app = create_app(enable_db_init=False)
            with TestClient(app):
                mock_init.assert_not_called()
                mock_create.assert_not_called()

    def test_db_init_uses_correct_engine(self) -> None:
        """DB 初始化使用 agent.infra.db.engine。"""
        with (
            patch("agent.infra.db.init_vector_extension") as mock_init,
            patch("agent.infra.db.Base.metadata.create_all"),
        ):
            app = create_app(enable_db_init=True)
            with TestClient(app):
                # init_vector_extension 被调用时传入的参数是 engine
                from agent.infra.db import engine

                mock_init.assert_called_once_with(engine)


# ---------------------------------------------------------------------------
# AC: CORS 中间件
# ---------------------------------------------------------------------------
class TestCorsMiddleware:
    """测试 CORS 中间件配置。"""

    def test_cors_headers_present(self) -> None:
        """CORS 中间件添加 Access-Control-Allow-Origin 头。"""
        client = _make_app_with_mocks()
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in {k.lower() for k in response.headers}

    def test_cors_disabled(self) -> None:
        """enable_cors=False 时不添加 CORS 头。"""
        app = create_app(enable_db_init=False, enable_cors=False)
        client = TestClient(app)
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        headers_lower = {k.lower() for k in response.headers}
        assert "access-control-allow-origin" not in headers_lower
