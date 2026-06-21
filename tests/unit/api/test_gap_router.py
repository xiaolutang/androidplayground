"""Gap Router 单元测试（R001-FF002）。

覆盖 2 个端点的验收标准：

GET /gaps:
- AC-1: 按 estimated_unlock_value 降序排列
- AC-1: 分页（page/page_size）
- AC-1: GapSummary 字段完整性
- AC-1: 空列表

POST /gaps/{id}/unblock:
- AC-2: waiting -> unblocked 状态迁移成功
- AC-2: 触发 BB011 ReflowManager（路径 A）
- AC-2: reflow_scheduled 正确反映回流触发结果
- AC-2: 状态非 waiting 返回 409
- AC-2: gap 不存在返回 404
- AC-2: 请求体验证（空字段 400）

全 mock（FakeGapStore + FakeReflowManager + FastAPI TestClient），无 DB 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.api.routers.gap_router import (
    get_gap_store,
    get_reflow_manager,
    router,
)
from agent.gap_mgmt.reflow_manager import ReflowResult
from agent.schemas.capability_gap import CapabilityGapStatus


# ---------------------------------------------------------------------------
# FakeGapStore（in-memory，避免真实 DB / ORM 依赖）
# ---------------------------------------------------------------------------
@dataclass
class FakeGap:
    """in-memory CapabilityGap 双。"""

    id: str
    gap_type: Optional[str] = None
    description: Optional[str] = None
    estimated_unlock_value: Optional[float] = None
    status: str = CapabilityGapStatus.IDENTIFIED.value
    linked_bug_ids: list[str] = field(default_factory=list)


class FakeGapStore:
    """FakeGapStore——模拟 GapStore 行为，in-memory。

    支持的接口：get / list / transition。
    """

    def __init__(self, gaps: list[FakeGap] | None = None) -> None:
        self._gaps: dict[str, FakeGap] = {}
        if gaps:
            for g in gaps:
                self._gaps[g.id] = g
        # 记录调用历史
        self.transition_calls: list[tuple[str, str, str]] = []

    def get(self, gap_id: str) -> FakeGap | None:
        return self._gaps.get(gap_id)

    def list(self, *, status: Any = None) -> list[FakeGap]:
        all_gaps = list(self._gaps.values())
        if status is not None:
            return [g for g in all_gaps if g.status == status.value]
        return all_gaps

    def transition(
        self,
        gap_id: str,
        to_status: CapabilityGapStatus,
        *,
        reason: str = "",
    ) -> FakeGap:
        self.transition_calls.append((gap_id, to_status.value, reason))
        gap = self._gaps[gap_id]
        gap.status = to_status.value
        return gap


# ---------------------------------------------------------------------------
# FakeReflowManager（模拟 BB011 回流）
# ---------------------------------------------------------------------------
class FakeReflowManager:
    """FakeReflowManager——模拟 ReflowManager.trigger_by_gap_fixed。

    可配置返回的 ReflowResult，记录所有调用参数。
    """

    def __init__(
        self,
        *,
        reflowed: bool = True,
        skipped: bool = False,
        wont_reflow: bool = False,
        raise_exc: Exception | None = None,
    ) -> None:
        self._reflowed = reflowed
        self._skipped = skipped
        self._wont_reflow = wont_reflow
        self._raise_exc = raise_exc
        self.trigger_calls: list[dict[str, Any]] = []

    def trigger_by_gap_fixed(
        self,
        bug_report: Any,
        gap_id: str,
    ) -> ReflowResult:
        self.trigger_calls.append(
            {
                "bug_report_id": getattr(bug_report, "id", None),
                "gap_id": gap_id,
            }
        )
        if self._raise_exc is not None:
            raise self._raise_exc
        return ReflowResult(
            reflowed=self._reflowed,
            trigger_path="gap_fixed",
            wont_reflow=self._wont_reflow,
            skipped=self._skipped,
            reflow_count=1,
        )


# ---------------------------------------------------------------------------
# Fixture：构建 TestClient + 注入 fake 依赖
# ---------------------------------------------------------------------------
def _build_app(
    gap_store: FakeGapStore,
    reflow_manager: FakeReflowManager,
) -> tuple[TestClient, FakeGapStore, FakeReflowManager]:
    """构建 FastAPI app + 注入 fake 依赖，返回 TestClient。"""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_gap_store] = lambda: gap_store
    app.dependency_overrides[get_reflow_manager] = lambda: reflow_manager
    return TestClient(app), gap_store, reflow_manager


# ---------------------------------------------------------------------------
# 测试数据工厂
# ---------------------------------------------------------------------------
def _make_gap(
    gap_id: str = "gap-001",
    *,
    gap_type: str | None = "info",
    description: str | None = "missing crash log",
    estimated_unlock_value: float | None = 50,
    status_val: str = CapabilityGapStatus.WAITING.value,
    linked_bug_ids: list[str] | None = None,
) -> FakeGap:
    return FakeGap(
        id=gap_id,
        gap_type=gap_type,
        description=description,
        estimated_unlock_value=estimated_unlock_value,
        status=status_val,
        linked_bug_ids=linked_bug_ids or [],
    )


# ===================================================================
# GET /gaps 测试
# ===================================================================

class TestListGaps:
    """GET /gaps 端点测试。"""

    def test_empty_list(self) -> None:
        """空列表返回 200 + 空 items。"""
        store = FakeGapStore(gaps=[])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps")

        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["page_size"] == 20

    def test_sorted_by_estimated_unlock_value_desc(self) -> None:
        """AC-1: 按 estimated_unlock_value 降序排列。"""
        gaps = [
            _make_gap("gap-1", estimated_unlock_value=10),
            _make_gap("gap-3", estimated_unlock_value=90),
            _make_gap("gap-2", estimated_unlock_value=50),
        ]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps")

        assert resp.status_code == 200
        items = resp.json()["items"]
        # 降序：90 -> 50 -> 10
        assert items[0]["id"] == "gap-3"
        assert items[1]["id"] == "gap-2"
        assert items[2]["id"] == "gap-1"

    def test_none_value_sorted_last(self) -> None:
        """estimated_unlock_value 为 None 的 gap 排在末尾。"""
        gaps = [
            _make_gap("gap-none", estimated_unlock_value=None),
            _make_gap("gap-5", estimated_unlock_value=5),
            _make_gap("gap-100", estimated_unlock_value=100),
        ]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps")

        items = resp.json()["items"]
        assert items[0]["id"] == "gap-100"
        assert items[1]["id"] == "gap-5"
        assert items[2]["id"] == "gap-none"

    def test_pagination(self) -> None:
        """分页：page=1, page_size=2 返回前 2 条。"""
        gaps = [
            _make_gap(f"gap-{i}", estimated_unlock_value=float(i * 10))
            for i in range(1, 6)  # 5 个 gap
        ]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page": 1, "page_size": 2})

        data = resp.json()
        assert data["total"] == 5
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) == 2
        # 降序前 2 条：gap-5(50), gap-4(40)
        assert data["items"][0]["id"] == "gap-5"
        assert data["items"][1]["id"] == "gap-4"

    def test_pagination_page2(self) -> None:
        """分页：page=2 返回第 3~4 条。"""
        gaps = [
            _make_gap(f"gap-{i}", estimated_unlock_value=float(i * 10))
            for i in range(1, 6)
        ]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page": 2, "page_size": 2})

        data = resp.json()
        assert data["page"] == 2
        assert len(data["items"]) == 2
        # 降序第 3~4 条：gap-3(30), gap-2(20)
        assert data["items"][0]["id"] == "gap-3"
        assert data["items"][1]["id"] == "gap-2"

    def test_pagination_last_page(self) -> None:
        """分页：最后一页只有 1 条。"""
        gaps = [
            _make_gap(f"gap-{i}", estimated_unlock_value=float(i * 10))
            for i in range(1, 6)
        ]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page": 3, "page_size": 2})

        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "gap-1"

    def test_pagination_beyond_total(self) -> None:
        """分页超出 total 返回空 items。"""
        gaps = [_make_gap("gap-1", estimated_unlock_value=10)]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page": 99, "page_size": 10})

        data = resp.json()
        assert data["total"] == 1
        assert data["items"] == []

    def test_default_page_and_page_size(self) -> None:
        """默认 page=1, page_size=20。"""
        gaps = [_make_gap(f"gap-{i}", estimated_unlock_value=float(i)) for i in range(5)]
        store = FakeGapStore(gaps=gaps)
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps")

        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert len(data["items"]) == 5

    def test_invalid_page_zero(self) -> None:
        """page=0 返回 422（验证错误，page 必须 >=1）。"""
        store = FakeGapStore(gaps=[])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page": 0})

        assert resp.status_code == 422

    def test_invalid_page_size_zero(self) -> None:
        """page_size=0 返回 422。"""
        store = FakeGapStore(gaps=[])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps", params={"page_size": 0})

        assert resp.status_code == 422

    def test_gap_summary_fields(self) -> None:
        """AC-1: GapSummary 包含所有必填字段。"""
        gap = _make_gap(
            "gap-full",
            gap_type="facility",
            description="no emulator",
            estimated_unlock_value=75,
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-a", "bug-b"],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.get("/gaps")

        item = resp.json()["items"][0]
        assert item["id"] == "gap-full"
        assert item["gap_type"] == "facility"
        assert item["waiting_reason"] == "no emulator"
        assert item["estimated_unlock_value"] == 75
        assert item["status"] == "waiting"
        assert item["linked_bug_ids"] == ["bug-a", "bug-b"]


# ===================================================================
# POST /gaps/{id}/unblock 测试
# ===================================================================

class TestUnblockGap:
    """POST /gaps/{id}/unblock 端点测试。"""

    def test_unblock_success(self) -> None:
        """AC-2: waiting -> unblocked 状态迁移成功。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager(reflowed=True)
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "log attached", "action_taken": "added emulator"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["gap_id"] == "gap-1"
        assert data["status_before"] == "waiting"
        assert data["status_after"] == "unblocked"

    def test_unblock_calls_transition(self) -> None:
        """验证调用了 GapStore.transition(waiting -> unblocked)。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        assert len(store.transition_calls) == 1
        gap_id, to_status, reason = store.transition_calls[0]
        assert gap_id == "gap-1"
        assert to_status == "unblocked"
        assert "evidence='ev'" in reason

    def test_unblock_triggers_reflow(self) -> None:
        """AC-2: 触发 BB011 ReflowManager（路径 A）。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-a", "bug-b"],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager(reflowed=True)
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        data = resp.json()
        assert data["reflow_scheduled"] is True
        # 确认对每个 linked_bug_id 调用了 trigger_by_gap_fixed
        assert len(rm.trigger_calls) == 2
        bug_ids_called = [c["bug_report_id"] for c in rm.trigger_calls]
        assert "bug-a" in bug_ids_called
        assert "bug-b" in bug_ids_called

    def test_unblock_reflow_scheduled_false_when_skipped(self) -> None:
        """reflow_scheduled=False 当 ReflowManager 返回 skipped。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-a"],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager(reflowed=False, skipped=True)
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        data = resp.json()
        assert data["reflow_scheduled"] is False

    def test_unblock_reflow_scheduled_partial(self) -> None:
        """多个 linked_bug 中部分触发成功时 reflow_scheduled=True。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-ok", "bug-skip"],
        )
        store = FakeGapStore(gaps=[gap])

        # 用自定义 RM：第一个 reflowed=True，第二个 skipped
        class PartialRM:
            def __init__(self):
                self.trigger_calls = []
                self._count = 0

            def trigger_by_gap_fixed(self, bug_report, gap_id):
                self.trigger_calls.append(
                    {"bug_report_id": bug_report.id, "gap_id": gap_id}
                )
                self._count += 1
                if self._count == 1:
                    return ReflowResult(
                        reflowed=True,
                        trigger_path="gap_fixed",
                        reflow_count=1,
                    )
                return ReflowResult(
                    reflowed=False,
                    trigger_path="gap_fixed",
                    skipped=True,
                )

        rm = PartialRM()
        client, _, _ = _build_app(store, rm)  # type: ignore[arg-type]

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        data = resp.json()
        assert data["reflow_scheduled"] is True

    def test_unblock_no_linked_bugs(self) -> None:
        """无 linked_bug_ids 时 reflow_scheduled=False，不调 ReflowManager。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=[],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        data = resp.json()
        assert data["reflow_scheduled"] is False
        assert len(rm.trigger_calls) == 0

    def test_unblock_reflow_exception_degraded(self) -> None:
        """ReflowManager 异常不阻断 unblock 响应（降级：reflow_scheduled=False）。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-a"],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager(raise_exc=RuntimeError("eventbus down"))
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        # unblock 本身成功（状态迁移完成），只是回流失败
        assert resp.status_code == 200
        data = resp.json()
        assert data["status_after"] == "unblocked"
        assert data["reflow_scheduled"] is False

    def test_unblock_404_not_found(self) -> None:
        """AC-2: gap 不存在返回 404。"""
        store = FakeGapStore(gaps=[])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/nonexistent/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_unblock_409_identified(self) -> None:
        """AC-2: identified 状态返回 409（仅 waiting 可 unblock）。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.IDENTIFIED.value,
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "identified" in detail

    def test_unblock_409_unblocked(self) -> None:
        """已 unblocked 状态返回 409。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.UNBLOCKED.value,
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        assert resp.status_code == 409

    def test_unblock_409_resolved(self) -> None:
        """resolved 终态返回 409。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.RESOLVED.value,
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        assert resp.status_code == 409

    def test_unblock_400_empty_evidence(self) -> None:
        """AC: evidence 为空返回 422（验证错误）。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "", "action_taken": "act"},
        )

        assert resp.status_code == 422

    def test_unblock_400_empty_action_taken(self) -> None:
        """AC: action_taken 为空返回 422。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": ""},
        )

        assert resp.status_code == 422

    def test_unblock_400_missing_evidence(self) -> None:
        """AC: 缺少 evidence 字段返回 422。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"action_taken": "act"},
        )

        assert resp.status_code == 422

    def test_unblock_400_missing_action_taken(self) -> None:
        """AC: 缺少 action_taken 字段返回 422。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev"},
        )

        assert resp.status_code == 422

    def test_unblock_response_fields(self) -> None:
        """AC-2: UnblockResponse 包含所有 4 个字段。"""
        gap = _make_gap(
            "gap-1",
            status_val=CapabilityGapStatus.WAITING.value,
            linked_bug_ids=["bug-a"],
        )
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager(reflowed=True)
        client, _, _ = _build_app(store, rm)

        resp = client.post(
            "/gaps/gap-1/unblock",
            json={"evidence": "ev", "action_taken": "act"},
        )

        data = resp.json()
        assert set(data.keys()) == {
            "gap_id",
            "status_before",
            "status_after",
            "reflow_scheduled",
        }

    def test_unblock_reason_in_transition(self) -> None:
        """验证 transition 调用时 reason 包含 evidence 和 action_taken。"""
        gap = _make_gap("gap-1", status_val=CapabilityGapStatus.WAITING.value)
        store = FakeGapStore(gaps=[gap])
        rm = FakeReflowManager()
        client, _, _ = _build_app(store, rm)

        client.post(
            "/gaps/gap-1/unblock",
            json={
                "evidence": "screenshot.png",
                "action_taken": "added device farm",
            },
        )

        _, _, reason = store.transition_calls[0]
        assert "screenshot.png" in reason
        assert "added device farm" in reason
