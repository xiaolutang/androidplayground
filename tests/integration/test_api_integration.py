"""API 集成测试（R001-INT01）—— 9 端点 + 28 case 矩阵 + 全链路。

依据：
- Sprint Contract R001-INT01（mode: direct）
- 依赖 FF001（report_router 7 端点 + webhook）/ FF002（gap_router 2 端点）
- 9 端点集成：GET /reports, GET /reports/{id}, GET .../trajectory,
  GET .../clarify-options, POST .../clarify, POST .../regression-feedback,
  POST /webhook, GET /gaps, POST /gaps/{id}/unblock
- regression-feedback 28 case 矩阵（5 allowed × 2 outcome + 9 disallowed × 2 outcome = 28）

设计要点：
1. **真实 HTTP 层**：用 TestClient 包装 FastAPI app，走完整的 ASGI 协议栈。
2. **DI 注入 fake 依赖**：不依赖真实 LLM/ADB，但模拟端到端行为。
3. **Testcontainers 隔离**：DB 测试用 PG + pgvector（conftest fixture 提供）。
4. **28 case 矩阵**：参数化覆盖 14 status × 2 outcome 的完整组合。
5. **全链路测试**：webhook → list → detail → trajectory → clarify → regression。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from agent.schemas.bug_report import (
    STATUS_ALLOWED_REGRESSION_FEEDBACK,
    BugReportStatus,
)
from tests.integration.conftest import make_bug

# ---------------------------------------------------------------------------
# 共享：状态枚举常量
# ---------------------------------------------------------------------------
ALL_STATUSES = [s.value for s in BugReportStatus]
ALLOWED = sorted(STATUS_ALLOWED_REGRESSION_FEEDBACK)
DISALLOWED = sorted(set(ALL_STATUSES) - STATUS_ALLOWED_REGRESSION_FEEDBACK)
REFLOW_TRIGGER = [BugReportStatus.CONCLUDED.value, BugReportStatus.REFLECTED.value]
NO_REFLOW = [
    BugReportStatus.PR_OPEN.value,
    BugReportStatus.DRAFT_PR.value,
    BugReportStatus.REFLOWED.value,
]


# ===================================================================
# 9 端点集成测试
# ===================================================================
class TestNineEndpointsIntegration:
    """9 个端点的集成测试——每端点至少一个 happy path。

    验证：路由注册、DI 注入、DTO 序列化、HTTP 状态码、响应结构。
    """

    # --- 1. GET /reports ---
    def test_get_reports_list(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports 返回分页列表。"""
        from tests.integration.conftest import make_bug

        for i in range(3):
            b = make_bug(id=f"bug-{i:03d}", status="received", tier=1)
            app_fixture["bug_repo"].add(b)

        client = app_fixture["client"]
        resp = client.get("/reports?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1

    def test_get_reports_status_filter(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports?status=concluded 过滤。"""
        app_fixture["bug_repo"].add(make_bug(id="b1", status="received"))
        app_fixture["bug_repo"].add(make_bug(id="b2", status="concluded"))

        resp = app_fixture["client"].get("/reports?status=concluded")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["status"] == "concluded"

    def test_get_reports_tier_filter(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports?tier=2 过滤。"""
        app_fixture["bug_repo"].add(make_bug(id="b1", status="received", tier=1))
        app_fixture["bug_repo"].add(make_bug(id="b2", status="received", tier=2))

        resp = app_fixture["client"].get("/reports?tier=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["tier"] == 2

    # --- 2. GET /reports/{id} ---
    def test_get_report_detail(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports/{id} 返回详情。"""
        app_fixture["bug_repo"].add(
            make_bug(
                id="bug-001",
                status="concluded",
                tier=1,
                symptom_type="crash",
                root_cause="NPE in MainActivity",
            )
        )

        resp = app_fixture["client"].get("/reports/bug-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "bug-001"
        assert data["status"] == "concluded"
        assert data["root_cause"] == "NPE in MainActivity"

    # --- 3. GET /reports/{id}/trajectory ---
    def test_get_trajectory(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports/{id}/trajectory 返回假设树。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001"))
        # 设置 trajectory
        app_fixture["traj_repo"]._traj = SimpleNamespace(
            nodes=[{"id": "h1", "label": "hypo", "status": "confirmed", "confidence": 0.9}],
            edges=[{"from": "h1", "to": "h2", "label": "follow-up"}],
        )

        resp = app_fixture["client"].get("/reports/bug-001/trajectory")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 1
        assert len(data["edges"]) == 1
        assert data["edges"][0]["from"] == "h1"

    # --- 4. GET /reports/{id}/clarify-options ---
    def test_get_clarify_options(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports/{id}/clarify-options 返回追问候选。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001"))

        resp = app_fixture["client"].get("/reports/bug-001/clarify-options")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["options"]) == 1
        assert data["options"][0]["id"] == "opt1"

    # --- 5. POST /reports/{id}/clarify ---
    def test_post_clarify(self, app_fixture: dict[str, Any]) -> None:
        """POST /reports/{id}/clarify 在 assessing 态接受。"""
        app_fixture["bug_repo"].add(
            make_bug(id="bug-001", status=BugReportStatus.ASSESSING.value)
        )

        resp = app_fixture["client"].post(
            "/reports/bug-001/clarify",
            json={"answers": [{"option_id": "opt1", "value": "Pixel 6"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    # --- 6. POST /reports/{id}/regression-feedback ---
    def test_post_regression_feedback_safe(self, app_fixture: dict[str, Any]) -> None:
        """POST /reports/{id}/regression-feedback outcome=safe 在 allowed 态成功。"""
        app_fixture["bug_repo"].add(
            make_bug(id="bug-001", status=BugReportStatus.PR_OPEN.value)
        )

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == "pr_open"
        assert data["status_after"] == "pr_open"
        assert data["reflow_scheduled"] is False

    # --- 7. POST /webhook/{platform} ---
    def test_post_webhook(self, app_fixture: dict[str, Any]) -> None:
        """POST /webhook/sentry 上报 bug。"""
        resp = app_fixture["client"].post(
            "/webhook/sentry",
            json={"event_id": "evt-001", "exception": "NPE"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["accepted"] is True
        assert data["bug_report_id"]

    # --- 8. GET /gaps ---
    def test_get_gaps(self, app_fixture: dict[str, Any]) -> None:
        """GET /gaps 返回排序列表。"""
        # 覆盖 gap_store 为有数据的 mock
        gap1 = SimpleNamespace(
            id="gap-1", gap_type="info", description="missing log",
            estimated_unlock_value=10, status="waiting", linked_bug_ids=[],
        )
        gap2 = SimpleNamespace(
            id="gap-2", gap_type="info", description="no emulator",
            estimated_unlock_value=90, status="waiting", linked_bug_ids=[],
        )
        app_fixture["gap_store"].list = lambda *a, **kw: [gap1, gap2]

        resp = app_fixture["client"].get("/gaps")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        # 按 estimated_unlock_value 降序：gap-2(90) 先于 gap-1(10)
        assert data["items"][0]["id"] == "gap-2"
        assert data["items"][1]["id"] == "gap-1"

    # --- 9. POST /gaps/{id}/unblock ---
    def test_post_gap_unblock(self, app_fixture: dict[str, Any]) -> None:
        """POST /gaps/{id}/unblock waiting → unblocked。"""
        gap = SimpleNamespace(
            id="gap-1", gap_type="info", description="missing",
            estimated_unlock_value=50, status="waiting",
            linked_bug_ids=["bug-a"],
        )
        app_fixture["gap_store"].get = lambda gid: gap if gid == "gap-1" else None
        app_fixture["gap_store"].transition = lambda gid, to, **kw: SimpleNamespace(
            id=gid, status=getattr(to, "value", str(to)),
            linked_bug_ids=["bug-a"],
        )

        resp = app_fixture["client"].post(
            "/gaps/gap-1/unblock",
            json={"evidence": "log attached", "action_taken": "added emulator"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["gap_id"] == "gap-1"
        assert data["status_before"] == "waiting"
        assert data["status_after"] == "unblocked"
        assert data["reflow_scheduled"] is True


# ===================================================================
# regression-feedback 28 case 矩阵（核心验收项）
# ===================================================================
class TestRegressionFeedback28Cases:
    """28 case 矩阵：14 status × 2 outcome。

    - 5 allowed × 2 outcome = 10 case
    - 9 disallowed × 2 outcome = 18 case → 409
    总计 28 case。
    """

    # --- safe × allowed 5 态 → 200，状态不变 ---
    @pytest.mark.parametrize("status", ALLOWED)
    def test_safe_allowed_no_change(self, status: str, app_fixture: dict[str, Any]) -> None:
        """outcome=safe × allowed 5 态 → 200，status 不变，reflow_scheduled=False。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001", status=status))

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == status
        assert data["status_after"] == status
        assert data["reflow_scheduled"] is False
        assert data["metric_point_id"]

    # --- regression × {concluded, reflected} → reflowed + reflow ---
    @pytest.mark.parametrize("status", REFLOW_TRIGGER)
    def test_regression_reflow_states(self, status: str, app_fixture: dict[str, Any]) -> None:
        """outcome=regression × {concluded, reflected} → reflowed + reflow_scheduled=True。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001", status=status))

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "regression detected"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == status
        assert data["status_after"] == "reflowed"
        assert data["reflow_scheduled"] is True
        # 验证 BB011 被调用
        assert len(app_fixture["reflow_mgr"].regression_calls) == 1

    # --- regression × {pr_open, draft_pr, reflowed} → 仅 MetricPoint ---
    @pytest.mark.parametrize("status", NO_REFLOW)
    def test_regression_no_reflow_states(self, status: str, app_fixture: dict[str, Any]) -> None:
        """outcome=regression × {pr_open, draft_pr, reflowed} → 仅 MetricPoint，不触发回流。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001", status=status))

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "log"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == status
        assert data["status_after"] == status
        assert data["reflow_scheduled"] is False
        assert len(app_fixture["reflow_mgr"].regression_calls) == 0

    # --- safe × disallowed 9 态 → 409 ---
    @pytest.mark.parametrize("status", DISALLOWED)
    def test_safe_disallowed_409(self, status: str, app_fixture: dict[str, Any]) -> None:
        """outcome=safe × disallowed 9 态 → 409。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001", status=status))

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 409

    # --- regression × disallowed 9 态 → 409 ---
    @pytest.mark.parametrize("status", DISALLOWED)
    def test_regression_disallowed_409(self, status: str, app_fixture: dict[str, Any]) -> None:
        """outcome=regression × disallowed 9 态 → 409。"""
        app_fixture["bug_repo"].add(make_bug(id="bug-001", status=status))

        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "log"},
        )
        assert resp.status_code == 409


# ===================================================================
# 全链路测试：webhook → list → detail → trajectory → clarify → regression
# ===================================================================
class TestFullLifecycle:
    """全链路端到端测试。

    场景：webhook 上报 → 创建 BugReport → GET /reports 列表 →
    GET /reports/{id} 详情 → trajectory → clarify → regression-feedback。
    """

    def test_full_lifecycle(self, app_fixture: dict[str, Any]) -> None:
        """全链路：webhook → list → detail → trajectory → clarify → regression。"""
        client = app_fixture["client"]
        bug_repo = app_fixture["bug_repo"]

        # 1. webhook 上报
        resp = client.post(
            "/webhook/sentry",
            json={"event_id": "evt-lifecycle", "exception": "NPE in onCreate"},
        )
        assert resp.status_code == 202
        bug_id = resp.json()["bug_report_id"]
        assert bug_id

        # 2. 模拟 orchestrator 创建 BugReport（实际中由 webhook 异步触发）
        bug = make_bug(
            id=bug_id,
            status=BugReportStatus.ASSESSING.value,
            tier=1,
            symptom_type="crash",
            root_cause="NPE in MainActivity.onCreate",
            pr_url="https://github.com/repo/pull/1",
        )
        bug_repo.add(bug)

        # 3. GET /reports 列表
        resp = client.get("/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert any(item["id"] == bug_id for item in data["items"])

        # 4. GET /reports/{id} 详情
        resp = client.get(f"/reports/{bug_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == bug_id
        assert detail["status"] == "assessing"

        # 5. GET /reports/{id}/trajectory
        app_fixture["traj_repo"]._traj = SimpleNamespace(
            nodes=[{"id": "h1", "label": "NPE hypothesis", "status": "confirmed", "confidence": 0.9}],
            edges=[],
        )
        resp = client.get(f"/reports/{bug_id}/trajectory")
        assert resp.status_code == 200
        traj = resp.json()
        assert len(traj["nodes"]) == 1

        # 6. GET /reports/{id}/clarify-options
        resp = client.get(f"/reports/{bug_id}/clarify-options")
        assert resp.status_code == 200
        opts = resp.json()
        assert len(opts["options"]) >= 1

        # 7. POST /reports/{id}/clarify（assessing 态）
        resp = client.post(
            f"/reports/{bug_id}/clarify",
            json={"answers": [{"option_id": "opt1", "value": "Pixel 6"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

        # 8. 模拟状态前进到 pr_open（实际由 orchestrator 推进）
        bug_repo.save_status(bug_id, BugReportStatus.PR_OPEN.value)

        # 9. POST /reports/{id}/regression-feedback
        resp = client.post(
            f"/reports/{bug_id}/regression-feedback",
            json={"outcome": "safe", "evidence": "verified in production"},
        )
        assert resp.status_code == 200
        fb = resp.json()
        assert fb["status_before"] == "pr_open"
        assert fb["status_after"] == "pr_open"
        assert fb["reflow_scheduled"] is False
        assert fb["metric_point_id"]

    def test_lifecycle_concluded_regression_triggers_reflow(
        self, app_fixture: dict[str, Any]
    ) -> None:
        """concluded 态收到 regression → reflowed + 触发回流。"""
        client = app_fixture["client"]
        bug_repo = app_fixture["bug_repo"]

        # 准备一个 concluded 态的 bug
        bug_id = "bug-concluded-reflow"
        bug_repo.add(make_bug(id=bug_id, status=BugReportStatus.CONCLUDED.value))

        # regression-feedback(outcome=regression)
        resp = client.post(
            f"/reports/{bug_id}/regression-feedback",
            json={"outcome": "regression", "evidence": "regression in v2.0"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == "concluded"
        assert data["status_after"] == "reflowed"
        assert data["reflow_scheduled"] is True

        # 验证 BugReport 状态已被 router 更新为 reflowed
        updated = bug_repo.get(bug_id)
        assert updated.status == "reflowed"

        # 验证 BB011 被调用
        assert len(app_fixture["reflow_mgr"].regression_calls) == 1


# ===================================================================
# 404/400 边界测试（集成层）
# ===================================================================
class TestIntegrationBoundaries:
    """集成层边界测试：404 / 400 / 422。"""

    def test_get_report_404(self, app_fixture: dict[str, Any]) -> None:
        """GET /reports/nonexistent → 404。"""
        resp = app_fixture["client"].get("/reports/nonexistent")
        assert resp.status_code == 404

    def test_regression_feedback_404(self, app_fixture: dict[str, Any]) -> None:
        """POST /reports/none/regression-feedback → 404。"""
        resp = app_fixture["client"].post(
            "/reports/none/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 404

    def test_webhook_unknown_platform_400(self, app_fixture: dict[str, Any]) -> None:
        """POST /webhook/unknown → 400。"""
        resp = app_fixture["client"].post(
            "/webhook/unknown",
            json={"event_id": "x"},
        )
        assert resp.status_code == 400

    def test_regression_feedback_invalid_outcome_422(self, app_fixture: dict[str, Any]) -> None:
        """POST regression-feedback outcome=invalid → 422。"""
        app_fixture["bug_repo"].add(
            make_bug(id="bug-001", status=BugReportStatus.PR_OPEN.value)
        )
        resp = app_fixture["client"].post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "invalid", "evidence": "log"},
        )
        assert resp.status_code == 422


# ===================================================================
# Case count 验证（确保 28 case 完整）
# ===================================================================
class TestCaseCount:
    """验证 28 case 矩阵的完整性。"""

    def test_allowed_has_5_states(self) -> None:
        """STATUS_ALLOWED_REGRESSION_FEEDBACK 必须有 5 个状态。"""
        assert len(STATUS_ALLOWED_REGRESSION_FEEDBACK) == 5

    def test_disallowed_has_9_states(self) -> None:
        """disallowed 状态必须有 9 个（14 - 5 = 9）。"""
        assert len(DISALLOWED) == 9

    def test_total_14_statuses(self) -> None:
        """BugReportStatus 必须有 14 个状态。"""
        assert len(ALL_STATUSES) == 14

    def test_28_case_logic(self) -> None:
        """14 status × 2 outcome = 28 case。"""
        assert len(ALL_STATUSES) * 2 == 28


# ===================================================================
# Testcontainers PG + pgvector 隔离验证
# ===================================================================
# Testcontainers 启动需拉镜像 + PG 初始化，给充足超时（300s）
_tc_timeout = pytest.mark.timeout(300)


@_tc_timeout
class TestTestcontainersIsolation:
    """验证 Testcontainers PG + pgvector 容器隔离正常。

    Docker 不可用或容器启动失败时，conftest.pg_container fixture 会 skip，
    整个 class 的测试自动跳过（非 error）。
    """

    def test_db_session_can_query(self, db_session: Any) -> None:
        """db_session fixture 能执行 SQL 查询（验证 Testcontainers 链路）。"""
        from sqlalchemy import text as sa_text

        result = db_session.execute(sa_text("SELECT 1")).scalar()
        assert result == 1

    def test_pgvector_extension_available(self, db_session: Any) -> None:
        """pgvector 扩展已安装（Testcontainers pgvector/pgvector:pg16 自带）。"""
        from sqlalchemy import text as sa_text

        row = db_session.execute(
            sa_text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        assert row is not None
        assert row[0] == "vector"

    def test_business_tables_created(self, db_session: Any) -> None:
        """所有业务表已在 Testcontainers 中创建。"""
        from sqlalchemy import text as sa_text

        tables = db_session.execute(
            sa_text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
                "ORDER BY tablename"
            )
        ).fetchall()
        table_names = {r[0] for r in tables}
        # 核心业务表
        assert "bug_reports" in table_names
        assert "capability_gaps" in table_names
