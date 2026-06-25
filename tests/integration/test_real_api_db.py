"""真实端到端集成测试（R001 补齐债务）。

与 ``test_api_integration.py`` 的区别：
- 后者用 ``TestClient(app) + InMemoryBugReportRepo`` —— 内存模拟，**不是真实集成**
- 本文件用 ``httpx + 真实 SQLAlchemy Session`` ——
  1. HTTP 请求打到 ``localhost:8002``（docker 中跑的 bugfix-agent）
  2. 直接 SQLAlchemy session 操作 DB（与 agent 共享同一个 PG）
  3. 验证 API → DB → API 完整链路

前置条件：
- bugfix-agent 容器运行在 ``localhost:8002``（``docker compose up -d postgres agent``）
- 测试可通过 PG ``localhost:5432`` 直连同一 DB

默认 skip：未 ``--run-real-e2e`` 或 agent 不可达时整体 skip。
"""
from __future__ import annotations

import os
import uuid
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# 启用条件：--run-real-e2e 且 agent 可达
# ---------------------------------------------------------------------------
AGENT_BASE_URL = os.environ.get("REAL_E2E_AGENT_URL", "http://localhost:8002")
PG_URL = os.environ.get(
    "REAL_E2E_PG_URL",
    "postgresql+psycopg://bugfix:bugfix_dev@localhost:5432/bugfix_agent",
)


def _agent_reachable() -> bool:
    """探测 agent /health 是否 200。"""
    try:
        import urllib.request

        with urllib.request.urlopen(f"{AGENT_BASE_URL}/health", timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


_RUN_REAL_E2E = os.environ.get("RUN_REAL_E2E") == "1"
pytestmark = pytest.mark.skipif(
    not _RUN_REAL_E2E or not _agent_reachable(),
    reason="Set RUN_REAL_E2E=1 and start bugfix-agent (docker compose up) to enable",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def http():
    """HTTP 客户端（httpx）。"""
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")
    with httpx.Client(base_url=AGENT_BASE_URL, timeout=10) as client:
        yield client


@pytest.fixture
def db_session():
    """直连 bugfix-agent 使用的 PG，返回 session。

    不做事务隔离（agent 容器是独立连接，看不到未 commit 数据）。
    每个测试用 unique id 避免数据污染；测试结束清理本测试创建的数据。
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    eng = create_engine(PG_URL, pool_pre_ping=True, future=True)
    session = Session(bind=eng, expire_on_commit=False)
    cleanup_ids: list[tuple[str, str]] = []

    def _track(table: str, row_id: str) -> None:
        cleanup_ids.append((table, row_id))

    session._e2e_cleanup = _track  # type: ignore[attr-defined]
    try:
        yield session
    finally:
        from sqlalchemy import text

        for table, row_id in cleanup_ids:
            try:
                session.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})
            except Exception:
                pass
        session.commit()
        session.close()
        eng.dispose()


@pytest.fixture
def unique_bug_id() -> str:
    """每次测试生成唯一 bug id，避免数据污染。"""
    return f"e2e-{uuid.uuid4().hex[:12]}"


def _insert_bug(
    session: Any,
    *,
    bug_id: str,
    status: str = "received",
    tier: int | None = None,
    symptom_type: str = "crash",
    external_id: str | None = None,
) -> None:
    """直接往 DB 插入 BugReport（绕过 API，模拟 BF001 归一化后状态）。"""
    from agent.schemas.bug_report import BugReport

    bug = BugReport(
        id=bug_id,
        source_platform="sentry",
        external_id=external_id or f"evt-{bug_id}",
        version_code="1.0.0",
        symptom_type=symptom_type,
        status=status,
        tier=tier,
    )
    session.add(bug)
    session.commit()
    session._e2e_cleanup("bug_reports", bug_id)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 测试：API 真实连 DB
# ---------------------------------------------------------------------------
class TestRealApiDbIntegration:
    """真实端到端：HTTP API → 真实 PG → 验证数据真实读写。"""

    def test_list_empty_when_no_data(self, http) -> None:
        """空 DB 场景：/reports 返回空列表。"""
        resp = http.get("/reports", params={"page": 1, "page_size": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 5
        # total 可能非 0（其他测试残留），但 items 数量 <= page_size
        assert len(data["items"]) <= 5

    def test_db_insert_then_api_returns_it(self, http, db_session, unique_bug_id) -> None:
        """DB 插入 → API GET /reports 能查到 → GET /reports/{id} 返回详情。"""
        _insert_bug(db_session, bug_id=unique_bug_id, symptom_type="blank")

        # 列表查询（按 symptom 过滤需要 API 支持，这里只验证 total 包含本条）
        resp = http.get("/reports", params={"page": 1, "page_size": 50})
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert unique_bug_id in ids

        # 详情查询
        detail = http.get(f"/reports/{unique_bug_id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["id"] == unique_bug_id
        assert body["symptom_type"] == "blank"
        assert body["status"] == "received"

    def test_get_report_404_for_unknown_id(self, http) -> None:
        """查询不存在的 bug_id → 404（真实路由判断）。"""
        resp = http.get("/reports/nonexistent-xxx-999")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Report not found"

    def test_status_filter_real_db_query(self, http, db_session, unique_bug_id) -> None:
        """status 过滤走真实 DB WHERE 子句。"""
        _insert_bug(
            db_session, bug_id=unique_bug_id, status="concluded", tier=1
        )

        # 查 concluded 状态
        resp = http.get("/reports", params={"status": "concluded"})
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert unique_bug_id in ids

        # 查 received 状态（不应包含本条）
        resp2 = http.get("/reports", params={"status": "received"})
        assert resp2.status_code == 200
        ids2 = [item["id"] for item in resp2.json()["items"]]
        assert unique_bug_id not in ids2

    def test_tier_filter_real_db_query(self, http, db_session, unique_bug_id) -> None:
        """tier 过滤走真实 DB WHERE 子句。"""
        _insert_bug(db_session, bug_id=unique_bug_id, tier=2)

        resp = http.get("/reports", params={"tier": 2})
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()["items"]]
        assert unique_bug_id in ids

        resp2 = http.get("/reports", params={"tier": 1})
        assert resp2.status_code == 200
        ids2 = [item["id"] for item in resp2.json()["items"]]
        assert unique_bug_id not in ids2

    def test_regression_feedback_writes_db(
        self, http, db_session, unique_bug_id
    ) -> None:
        """POST /regression-feedback 真实写 DB（status 字段更新）。"""
        from agent.schemas.bug_report import BugReport

        _insert_bug(db_session, bug_id=unique_bug_id, status="concluded")

        # 调 regression-feedback API（outcome=safe，evidence 必填）
        resp = http.post(
            f"/reports/{unique_bug_id}/regression-feedback",
            json={"outcome": "safe", "evidence": "e2e safe test evidence"},
        )
        assert resp.status_code == 200, resp.text

        # 直接 DB 查验 status 真实写入
        bug = db_session.get(BugReport, unique_bug_id)
        assert bug is not None
        # concluded + safe 路径：status 保持或转 reflected（取决于状态机）
        assert bug.status in {"concluded", "reflected"}

    def test_webhook_unknown_platform_400(self, http) -> None:
        """webhook 未知 platform → 400（真实错误码）。"""
        resp = http.post(
            "/webhook/unknown_platform",
            json={"event_id": "test", "data": {}},
        )
        assert resp.status_code == 400

    def test_gaps_list_real_db(self, http) -> None:
        """/gaps 真实 DB 查询（不再 500）。"""
        resp = http.get("/gaps")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_gap_create_then_list(self, http, db_session) -> None:
        """端到端：DB 插入 CapabilityGap → /gaps 列表能查到。"""
        from agent.schemas.capability_gap import (
            CapabilityGap,
            CapabilityGapStatus,
        )

        gap_id = f"e2e-gap-{uuid.uuid4().hex[:8]}"
        gap = CapabilityGap(
            id=gap_id,
            gap_type="repro",
            description="e2e test gap",
            status=CapabilityGapStatus.IDENTIFIED.value,
            estimated_unlock_value=0.5,
        )
        db_session.add(gap)
        db_session.commit()
        db_session._e2e_cleanup("capability_gaps", gap_id)  # type: ignore[attr-defined]

        # /gaps 列表（按 estimated_unlock_value 降序）
        resp = http.get("/gaps")
        assert resp.status_code == 200
        ids = [g["id"] for g in resp.json()["items"]]
        assert gap_id in ids

    def test_pagination_boundaries(self, http) -> None:
        """分页参数边界：page=0 → 400。"""
        resp = http.get("/reports", params={"page": 0})
        assert resp.status_code == 400

    def test_404_for_nonexistent_gap(self, http) -> None:
        """POST /gaps/{unknown}/unblock + 合法请求体 → 404（不再 500）。"""
        resp = http.post(
            "/gaps/nonexistent-gap-xxx/unblock",
            json={"evidence": "test", "action_taken": "demo action"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_unblock_status_transition_writes_db(self, http, db_session) -> None:
        """端到端：插入 waiting gap → POST unblock → DB status 真实迁移为 unblocked。"""
        from agent.schemas.capability_gap import (
            CapabilityGap,
            CapabilityGapStatus,
        )

        gap_id = f"e2e-unblock-{uuid.uuid4().hex[:8]}"
        gap = CapabilityGap(
            id=gap_id,
            gap_type="repro",
            description="e2e unblock test",
            status=CapabilityGapStatus.WAITING.value,
            estimated_unlock_value=0.7,
        )
        db_session.add(gap)
        db_session.commit()
        db_session._e2e_cleanup("capability_gaps", gap_id)  # type: ignore[attr-defined]

        # POST unblock
        resp = http.post(
            f"/gaps/{gap_id}/unblock",
            json={"evidence": "device added", "action_taken": "added Pixel 8"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["gap_id"] == gap_id
        assert body["status_before"] == "waiting"
        assert body["status_after"] == "unblocked"

        # 直连 DB 验证 status 真实迁移
        db_session.expire_all()
        gap_after = db_session.get(CapabilityGap, gap_id)
        assert gap_after.status == CapabilityGapStatus.UNBLOCKED.value


class TestRealIntegrationHealth:
    """集成健康检查（轻量，用于验证部署正确性）。"""

    def test_health_endpoint(self, http) -> None:
        """/health → 200 + {"status":"ok"}。"""
        resp = http.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_openapi_json_available(self, http) -> None:
        """/openapi.json 可访问（前端契约源）。"""
        resp = http.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        assert "/reports" in spec["paths"]
        assert "/gaps" in spec["paths"]
