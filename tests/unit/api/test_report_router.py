"""report_router 单元测试（R001-FF001）。

覆盖：
- AC-1 GET /reports 分页 + status 过滤 + tier 过滤 + 空列表
- AC-2 GET /reports/{id} 正常 + 404
- AC-3 GET /reports/{id}/trajectory 正常 + 404
- AC-4 GET /reports/{id}/clarify-options 正常 + 404
- AC-5 POST /reports/{id}/clarify 正常 + 404 + 409
- AC-6 POST /reports/{id}/regression-feedback（28 case 矩阵）
- AC-7 POST /webhook/{platform} 正常 + 未知 platform 400
- AC-8 错误码 400/404/409
- AC-9 响应四字段
- AC-10 >= 30 测试

测试使用 FastAPI TestClient，mock ORB01/BB011/仓储（不依赖真实 DB/LLM）。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.routers.report_router import _Deps, create_report_router, create_webhook_router
from agent.schemas.bug_report import BugReportStatus, STATUS_ALLOWED_REGRESSION_FEEDBACK


# ---------------------------------------------------------------------------
# Mock 仓储
# ---------------------------------------------------------------------------
class MockBugReportRepo:
    """BugReport 仓储 mock。

    内部 dict 存储，duck typing 兼容 router 的 get/list/save_status 调用。
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
            items = [r for r in items if _g(r, "status") == status]
        if tier is not None:
            items = [r for r in items if _g(r, "tier") == tier]
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        return items[start:end], total

    def save_status(self, report_id: str, new_status: str) -> None:
        if report_id in self._store:
            r = self._store[report_id]
            if isinstance(r, dict):
                r["status"] = new_status
            else:
                r.status = new_status


class MockMetricPointRepo:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create(self, **kwargs: Any) -> Any:
        self.created.append(kwargs)
        return SimpleNamespace(id=kwargs.get("id", "mp-test"))


class MockTrajectoryRepo:
    def __init__(self, traj: Any = None) -> None:
        self._traj = traj

    def get(self, report_id: str) -> Any:
        return self._traj


class MockReflowManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def trigger_by_regression(
        self, bug_report: Any, regression_signal: dict
    ) -> Any:
        self.calls.append(("regression", regression_signal))
        return SimpleNamespace(reflowed=True)


class MockOrchestrator:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def run(self, bug_report: Any) -> Any:
        self.calls.append(bug_report)
        return SimpleNamespace(status="received")


def _g(obj: Any, name: str, default: Any = None) -> Any:
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
# fixture：构造带 mock 依赖的 TestClient
# ---------------------------------------------------------------------------
def make_app(
    *,
    reports: Optional[dict[str, Any]] = None,
    traj: Any = None,
    clarify_options: Optional[list[dict]] = None,
    webhook_platforms: Optional[set[str]] = None,
) -> tuple[TestClient, _Deps]:
    """构造 FastAPI app + TestClient，注入 mock 依赖。"""
    bug_repo = MockBugReportRepo(reports)
    mp_repo = MockMetricPointRepo()
    traj_repo = MockTrajectoryRepo(traj)
    reflow_mgr = MockReflowManager()
    orchestrator = MockOrchestrator()

    deps = _Deps(
        orchestrator=orchestrator,
        reflow_manager=reflow_mgr,
        bug_report_repo=bug_repo,
        metric_point_repo=mp_repo,
        trajectory_repo=traj_repo,
        clarify_option_provider=(
            (lambda rid: clarify_options) if clarify_options else None
        ),
        webhook_platforms=webhook_platforms,
    )

    app = FastAPI()
    app.include_router(create_report_router(deps))
    app.include_router(create_webhook_router(deps))
    return TestClient(app), deps


# ---------------------------------------------------------------------------
# AC-1：GET /reports（列表）
# ---------------------------------------------------------------------------
class TestAC1ListReports:
    def test_list_pagination(self):
        reports = {
            f"bug-{i:03d}": make_bug(id=f"bug-{i:03d}", status="received", tier=1)
            for i in range(25)
        }
        client, _ = make_app(reports=reports)

        resp = client.get("/reports?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 25
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["items"]) == 10

        resp2 = client.get("/reports?page=3&page_size=10")
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 5

    def test_list_status_filter(self):
        reports = {
            "bug-a": make_bug(id="bug-a", status="received", tier=1),
            "bug-b": make_bug(id="bug-b", status="concluded", tier=2),
            "bug-c": make_bug(id="bug-c", status="concluded", tier=3),
        }
        client, _ = make_app(reports=reports)

        resp = client.get("/reports?status=concluded")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(item["status"] == "concluded" for item in data["items"])

    def test_list_tier_filter(self):
        reports = {
            "bug-a": make_bug(id="bug-a", status="received", tier=1),
            "bug-b": make_bug(id="bug-b", status="concluded", tier=2),
            "bug-c": make_bug(id="bug-c", status="located", tier=1),
        }
        client, _ = make_app(reports=reports)

        resp = client.get("/reports?tier=1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(item["tier"] == 1 for item in data["items"])

    def test_list_empty(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_list_invalid_page(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports?page=0")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC-2：GET /reports/{id}（详情）
# ---------------------------------------------------------------------------
class TestAC2GetReport:
    def test_get_existing(self):
        reports = {
            "bug-001": make_bug(
                id="bug-001",
                status="concluded",
                tier=1,
                symptom_type="crash",
                root_cause="NPE in MainActivity",
                pr_url="https://github.com/repo/pull/1",
                reflow_count=0,
            ),
        }
        client, _ = make_app(reports=reports)
        resp = client.get("/reports/bug-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "bug-001"
        assert data["status"] == "concluded"
        assert data["tier"] == 1
        assert data["symptom_type"] == "crash"
        assert data["root_cause"] == "NPE in MainActivity"

    def test_get_404(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Report not found"


# ---------------------------------------------------------------------------
# AC-3：GET /reports/{id}/trajectory
# ---------------------------------------------------------------------------
class TestAC3Trajectory:
    def test_trajectory_ok(self):
        traj = SimpleNamespace(
            nodes=[
                {"id": "h1", "label": "hypo 1", "status": "confirmed", "confidence": 0.9},
                {"id": "h2", "label": "hypo 2", "status": "refuted", "confidence": 0.2},
            ],
            edges=[
                {"from": "h1", "to": "h2", "label": "follow-up"},
            ],
        )
        reports = {"bug-001": make_bug(id="bug-001")}
        client, _ = make_app(reports=reports, traj=traj)
        resp = client.get("/reports/bug-001/trajectory")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
        assert data["edges"][0]["from"] == "h1"

    def test_trajectory_404(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports/none/trajectory")
        assert resp.status_code == 404

    def test_trajectory_empty(self):
        reports = {"bug-001": make_bug(id="bug-001")}
        client, _ = make_app(reports=reports, traj=None)
        resp = client.get("/reports/bug-001/trajectory")
        assert resp.status_code == 200
        assert resp.json()["nodes"] == []


# ---------------------------------------------------------------------------
# AC-4：GET /reports/{id}/clarify-options
# ---------------------------------------------------------------------------
class TestAC4ClarifyOptions:
    def test_clarify_options_ok(self):
        reports = {"bug-001": make_bug(id="bug-001")}
        options = [
            {"id": "opt1", "question": "What device?", "context": "device info"},
            {"id": "opt2", "question": "App version?", "context": "version"},
        ]
        client, _ = make_app(reports=reports, clarify_options=options)
        resp = client.get("/reports/bug-001/clarify-options")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["options"]) == 2
        assert data["options"][0]["id"] == "opt1"

    def test_clarify_options_404(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports/none/clarify-options")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC-5：POST /reports/{id}/clarify
# ---------------------------------------------------------------------------
class TestAC5Clarify:
    def test_clarify_ok(self):
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.ASSESSING.value),
        }
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/clarify",
            json={"answers": [{"option_id": "opt1", "value": "Pixel 6"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] is True

    def test_clarify_404(self):
        client, _ = make_app(reports={})
        resp = client.post(
            "/reports/none/clarify",
            json={"answers": [{"option_id": "opt1", "value": "x"}]},
        )
        assert resp.status_code == 404

    def test_clarify_409_non_assessing(self):
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.CONCLUDED.value),
        }
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/clarify",
            json={"answers": [{"option_id": "opt1", "value": "x"}]},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# AC-6/AC-9：POST /reports/{id}/regression-feedback（28 case 矩阵）
# ---------------------------------------------------------------------------
# 14 status × 2 outcome = 28 case
ALL_STATUSES = [s.value for s in BugReportStatus]
ALLOWED = sorted(STATUS_ALLOWED_REGRESSION_FEEDBACK)
DISALLOWED = sorted(set(ALL_STATUSES) - STATUS_ALLOWED_REGRESSION_FEEDBACK)
REFLOW_TRIGGER = [BugReportStatus.CONCLUDED.value, BugReportStatus.REFLECTED.value]
NO_REFLOW = [
    BugReportStatus.PR_OPEN.value,
    BugReportStatus.DRAFT_PR.value,
    BugReportStatus.REFLOWED.value,
]


class TestAC6RegressionFeedback:
    # --- safe × allowed 5 态 → 200，status 不变 ---
    @pytest.mark.parametrize("s", ALLOWED)
    def test_safe_allowed_no_change(self, s):
        reports = {"bug-001": make_bug(id="bug-001", status=s)}
        client, deps = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == s
        assert data["status_after"] == s
        assert data["reflow_scheduled"] is False
        assert data["metric_point_id"]

    # --- safe × disallowed 9 态 → 409 ---
    @pytest.mark.parametrize("s", DISALLOWED)
    def test_safe_disallowed_409(self, s):
        reports = {"bug-001": make_bug(id="bug-001", status=s)}
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 409

    # --- regression × {concluded, reflected} → reflowed + reflow_scheduled ---
    @pytest.mark.parametrize("s", REFLOW_TRIGGER)
    def test_regression_reflow_states(self, s):
        reports = {"bug-001": make_bug(id="bug-001", status=s)}
        client, deps = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "regression detected"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == s
        assert data["status_after"] == "reflowed"
        assert data["reflow_scheduled"] is True
        # 验证调用了 BB011 trigger_by_regression
        assert len(deps.reflow_manager.calls) == 1

    # --- regression × {pr_open, draft_pr, reflowed} → 仅 MetricPoint ---
    @pytest.mark.parametrize("s", NO_REFLOW)
    def test_regression_no_reflow_states(self, s):
        reports = {"bug-001": make_bug(id="bug-001", status=s)}
        client, deps = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "log"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_before"] == s
        assert data["status_after"] == s
        assert data["reflow_scheduled"] is False
        # 不应触发 BB011
        assert len(deps.reflow_manager.calls) == 0

    # --- regression × disallowed 9 态 → 409 ---
    @pytest.mark.parametrize("s", DISALLOWED)
    def test_regression_disallowed_409(self, s):
        reports = {"bug-001": make_bug(id="bug-001", status=s)}
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "log"},
        )
        assert resp.status_code == 409

    def test_regression_404(self):
        client, _ = make_app(reports={})
        resp = client.post(
            "/reports/none/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 404

    def test_regression_writes_metric_point(self):
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.PR_OPEN.value),
        }
        client, deps = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={
                "outcome": "safe",
                "evidence": "ok",
                "bucket_dim": "tier",
                "bucket_value": "1",
            },
        )
        assert resp.status_code == 200
        assert len(deps.metric_point_repo.created) == 1
        mp = deps.metric_point_repo.created[0]
        assert mp["metric_type"] == "safety"
        assert mp["bug_report_id"] == "bug-001"


# ---------------------------------------------------------------------------
# AC-7：POST /webhook/{platform}
# ---------------------------------------------------------------------------
class TestAC7Webhook:
    def test_webhook_ok(self):
        client, _ = make_app(webhook_platforms={"sentry", "crashlytics"})
        resp = client.post(
            "/webhook/sentry",
            json={"event_id": "evt-001", "exception": "NPE"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["accepted"] is True
        assert data["bug_report_id"]

    def test_webhook_unknown_platform_400(self):
        client, _ = make_app(webhook_platforms={"sentry"})
        resp = client.post(
            "/webhook/unknown",
            json={"event_id": "evt-002"},
        )
        assert resp.status_code == 400

    def test_webhook_crashlytics(self):
        client, _ = make_app(webhook_platforms={"crashlytics"})
        resp = client.post(
            "/webhook/crashlytics",
            json={"crash_id": "c-001"},
        )
        assert resp.status_code == 202
        assert resp.json()["accepted"] is True


# ---------------------------------------------------------------------------
# AC-8：错误码统一（400 / 404 / 409 覆盖断言）
# ---------------------------------------------------------------------------
class TestAC8ErrorCodes:
    def test_400_validation_error(self):
        # Pydantic 校验失败（outcome 非法枚举）
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.PR_OPEN.value),
        }
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "invalid", "evidence": "log"},
        )
        assert resp.status_code == 422  # Pydantic 校验

    def test_404_report_not_found(self):
        client, _ = make_app(reports={})
        resp = client.get("/reports/none")
        assert resp.status_code == 404

    def test_409_state_conflict(self):
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.RECEIVED.value),
        }
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "safe", "evidence": "log"},
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# AC-9：响应四字段断言
# ---------------------------------------------------------------------------
class TestAC9FourFields:
    def test_regression_response_has_all_fields(self):
        reports = {
            "bug-001": make_bug(id="bug-001", status=BugReportStatus.CONCLUDED.value),
        }
        client, _ = make_app(reports=reports)
        resp = client.post(
            "/reports/bug-001/regression-feedback",
            json={"outcome": "regression", "evidence": "log"},
        )
        data = resp.json()
        assert set(data.keys()) == {
            "metric_point_id",
            "status_before",
            "status_after",
            "reflow_scheduled",
        }


# ---------------------------------------------------------------------------
# AC-10：测试覆盖（>= 30 测试）— 由 parametrize 自动满足
# ---------------------------------------------------------------------------
# 统计：
#   AC-1: 5 test methods（含分页/status/tier/empty/invalid = 5）
#   AC-2: 2
#   AC-3: 3
#   AC-4: 2
#   AC-5: 3
#   AC-6: 5 parametrized × (5+9+2+3+9=28 case) + 2 = 30 cases
#   AC-7: 3
#   AC-8: 3
#   AC-9: 1
#   总计（含 parametrize 展开）远超 30。
