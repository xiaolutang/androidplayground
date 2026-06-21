"""FastAPI report_router（R001-FF001）。

依据：
- Sprint Contract R001-FF001（status: agreed，10 AC）
- backend design 4.3 接口契约（第 720-742 行）
- ORB01 Orchestrator（14 态状态机）
- BB011 ReflowManager（事件驱动回流）
- BugReport schema（14 态 + STATUS_ALLOWED_REGRESSION_FEEDBACK 5 态）

设计要点：
1. **APIRouter prefix="/reports"**（AC-1 ~ AC-6），webhook 单独挂载（AC-7）。
2. **DI 注入依赖**：Orchestrator / ReflowManager / session 工厂通过
   ``get_report_router`` 构造函数注入，测试 mock 时不依赖真实 DB/LLM。
3. **regression-feedback 状态分支**（AC-6 核心）：
   - 状态守卫：仅 5 态 allowed，其他 9 态返回 409。
   - outcome=safe → 仅写 MetricPoint。
   - outcome=regression + {concluded, reflected} → 迁移 reflowed + 触发回流。
   - outcome=regression + {pr_open, draft_pr, reflowed} → 仅写 MetricPoint。
4. **错误码统一**（AC-8）：400（Pydantic 自动）/ 404 / 409。
5. **响应四字段**（AC-9）：metric_point_id / status_before / status_after / reflow_scheduled。
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Request, status

from agent.api.dtos.report_dtos import (
    ClarifyOption,
    ClarifyOptionsResponse,
    ClarifyRequest,
    ClarifyResponse,
    RegressionFeedbackRequest,
    RegressionFeedbackResponse,
    ReportDetail,
    ReportListResponse,
    ReportSummary,
    TrajectoryEdge,
    TrajectoryNode,
    TrajectoryResponse,
    WebhookResponse,
)
from agent.schemas.bug_report import (
    STATUS_ALLOWED_REGRESSION_FEEDBACK,
    BugReportStatus,
)

logger = logging.getLogger(__name__)

__all__ = ["create_report_router", "create_webhook_router"]

# ---------------------------------------------------------------------------
# 回流触发态（路径 B：concluded / reflected）
# ---------------------------------------------------------------------------
_REGRESSION_REFLOW_STATES: frozenset[str] = frozenset(
    {
        BugReportStatus.CONCLUDED.value,
        BugReportStatus.REFLECTED.value,
    }
)

# 仅写 MetricPoint 的 allowed 态（PR 未合并或已在回流中）
_NO_REFLOW_STATES: frozenset[str] = frozenset(
    {
        BugReportStatus.PR_OPEN.value,
        BugReportStatus.DRAFT_PR.value,
        BugReportStatus.REFLOWED.value,
    }
)


# ---------------------------------------------------------------------------
# 依赖容器（持有 Orchestrator / ReflowManager / session 工厂）
# ---------------------------------------------------------------------------
class _Deps:
    """依赖容器（构造函数注入，测试 mock 不碰真实 DB/LLM）。

    Attributes:
        orchestrator: ORB01 实例（可选，webhook 入口用到）。
        reflow_manager: BB011 实例（regression-feedback 路径 B 用到）。
        session_factory: 返回 session 上下文的 callable（不直接 SQL，
            通过 session 查询/写入）。
        bug_report_repo: BugReport 仓储（duck typing：get / list / save）。
        metric_point_repo: MetricPoint 仓储（duck typing：create）。
        trajectory_repo: Trajectory 仓储（duck typing：get）。
        clarify_option_provider: 追问候选提供者 callable。
        webhook_platforms: 允许的 platform 白名单。
    """

    def __init__(
        self,
        *,
        orchestrator: Any = None,
        reflow_manager: Any = None,
        session_factory: Optional[Callable[[], Any]] = None,
        bug_report_repo: Any = None,
        metric_point_repo: Any = None,
        trajectory_repo: Any = None,
        clarify_option_provider: Optional[Callable[[str], list[dict]]] = None,
        webhook_platforms: Optional[set[str]] = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.reflow_manager = reflow_manager
        self.session_factory = session_factory
        self.bug_report_repo = bug_report_repo
        self.metric_point_repo = metric_point_repo
        self.trajectory_repo = trajectory_repo
        self.clarify_option_provider = clarify_option_provider
        self.webhook_platforms = webhook_platforms or {"crashlytics", "sentry"}


# ---------------------------------------------------------------------------
# BugReport 属性读取辅助（duck typing，兼容 ORM/mock/SimpleNamespace）
# ---------------------------------------------------------------------------
def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """读取对象属性（兼容 dict /对象 / None）。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_id(obj: Any) -> str:
    return str(_get_attr(obj, "id", "") or "")


def _get_status(obj: Any) -> str:
    return str(_get_attr(obj, "status", "") or "")


# ---------------------------------------------------------------------------
# 404 helper
# ---------------------------------------------------------------------------
def _require_report(deps: _Deps, report_id: str) -> Any:
    """获取 BugReport，不存在抛 404。"""
    bug = deps.bug_report_repo.get(report_id) if deps.bug_report_repo else None
    if bug is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return bug


# ---------------------------------------------------------------------------
# create_report_router（reports 前缀的 7 个端点中的 6 个）
# ---------------------------------------------------------------------------
def create_report_router(deps: _Deps) -> APIRouter:
    """构造 /reports 前缀的 APIRouter。

    Args:
        deps: 依赖容器（DI 注入 ORB01/BB011/仓储）。

    Returns:
        APIRouter（prefix="/reports", tags=["reports"]）。
    """
    router = APIRouter(prefix="/reports", tags=["reports"])

    # -----------------------------------------------------------------
    # AC-1: GET /reports（列表，分页+过滤）
    # -----------------------------------------------------------------
    @router.get("", response_model=ReportListResponse)
    @router.get("/", response_model=ReportListResponse, include_in_schema=False)
    async def list_reports(
        page: int = 1,
        page_size: int = 20,
        status_filter: Optional[str] = None,
        tier: Optional[int] = None,
        request: Request = None,  # noqa: ARG001  兼容 FastAPI 签名
    ) -> ReportListResponse:
        """报告列表（AC-1）。

        查询参数 status 在 FastAPI 中与 ``status`` 模块冲突，故别名 status_filter
        映射为查询参数 ``status``。
        """
        # 参数别名处理：request.query_params 取 "status"
        if request is not None and status_filter is None:
            status_filter = request.query_params.get("status")

        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page must be >= 1",
            )
        if page_size < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page_size must be >= 1",
            )

        items: list[Any] = []
        total = 0
        if deps.bug_report_repo is not None:
            result = deps.bug_report_repo.list(
                page=page,
                page_size=page_size,
                status=status_filter,
                tier=tier,
            )
            if isinstance(result, tuple):
                items, total = result
            elif isinstance(result, list):
                items = result
                total = len(items)

        summaries = [
            ReportSummary(
                id=_get_id(b),
                title=_get_attr(b, "title") or _get_attr(b, "symptom_type"),
                status=_get_status(b),
                tier=_get_attr(b, "tier"),
                created_at=_get_attr(b, "created_at") or _get_attr(b, "concluded_at"),
                updated_at=_get_attr(b, "updated_at"),
            )
            for b in items
        ]
        return ReportListResponse(
            items=summaries,
            total=total,
            page=page,
            page_size=page_size,
        )

    # -----------------------------------------------------------------
    # AC-2: GET /reports/{id}（详情）
    # -----------------------------------------------------------------
    @router.get("/{report_id}", response_model=ReportDetail)
    async def get_report(report_id: str) -> ReportDetail:
        """报告详情（AC-2）。"""
        bug = _require_report(deps, report_id)
        return ReportDetail(
            id=_get_id(bug),
            title=_get_attr(bug, "title") or _get_attr(bug, "symptom_type"),
            status=_get_status(bug),
            tier=_get_attr(bug, "tier"),
            symptom_type=_get_attr(bug, "symptom_type"),
            root_cause=_get_attr(bug, "root_cause"),
            root_cause_location=_get_attr(bug, "root_cause_location"),
            confidence_score_id=_get_attr(bug, "confidence_score_id"),
            fix_patch_id=_get_attr(bug, "fix_patch_id"),
            pr_url=_get_attr(bug, "pr_url"),
            reflow_count=_get_attr(bug, "reflow_count", 0) or 0,
            created_at=_get_attr(bug, "created_at"),
            updated_at=_get_attr(bug, "updated_at"),
            raw_report=_get_attr(bug, "raw_report"),
        )

    # -----------------------------------------------------------------
    # AC-3: GET /reports/{id}/trajectory（假设树）
    # -----------------------------------------------------------------
    @router.get("/{report_id}/trajectory", response_model=TrajectoryResponse)
    async def get_trajectory(report_id: str) -> TrajectoryResponse:
        """假设树可视化数据（AC-3）。"""
        _require_report(deps, report_id)
        nodes_data: list[dict] = []
        edges_data: list[dict] = []
        if deps.trajectory_repo is not None:
            traj = deps.trajectory_repo.get(report_id)
            if traj is not None:
                nodes_data = list(_get_attr(traj, "nodes", []) or [])
                edges_data = list(_get_attr(traj, "edges", []) or [])

        nodes = [
            TrajectoryNode(
                id=str(n.get("id", "")),
                label=n.get("label"),
                status=n.get("status"),
                confidence=n.get("confidence"),
            )
            for n in nodes_data
        ]
        edges = [
            TrajectoryEdge(
                **{
                    "from": e.get("from", e.get("source", "")),
                    "to": e.get("to", e.get("target", "")),
                    "label": e.get("label"),
                }
            )
            for e in edges_data
        ]
        return TrajectoryResponse(nodes=nodes, edges=edges)

    # -----------------------------------------------------------------
    # AC-4: GET /reports/{id}/clarify-options（追问候选）
    # -----------------------------------------------------------------
    @router.get(
        "/{report_id}/clarify-options", response_model=ClarifyOptionsResponse
    )
    async def get_clarify_options(report_id: str) -> ClarifyOptionsResponse:
        """追问候选（AC-4，从 KB 派生）。"""
        _require_report(deps, report_id)
        options_raw: list[dict] = []
        if deps.clarify_option_provider is not None:
            options_raw = list(deps.clarify_option_provider(report_id) or [])

        options = [
            ClarifyOption(
                id=str(o.get("id", "")),
                question=o.get("question", ""),
                context=o.get("context"),
            )
            for o in options_raw
        ]
        return ClarifyOptionsResponse(options=options)

    # -----------------------------------------------------------------
    # AC-5: POST /reports/{id}/clarify（提交追问答案）
    # -----------------------------------------------------------------
    @router.post("/{report_id}/clarify", response_model=ClarifyResponse)
    async def submit_clarify(
        report_id: str,
        body: ClarifyRequest,
    ) -> ClarifyResponse:
        """提交追问答案（AC-5）。

        - 404：报告不存在
        - 409：状态非 assessing（不接受追问）
        """
        bug = _require_report(deps, report_id)
        current_status = _get_status(bug)
        if current_status != BugReportStatus.ASSESSING.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Clarify not allowed in status "
                    f"'{current_status}' (requires 'assessing')"
                ),
            )
        return ClarifyResponse(accepted=True)

    # -----------------------------------------------------------------
    # AC-6: POST /reports/{id}/regression-feedback（回归反馈）
    # -----------------------------------------------------------------
    @router.post(
        "/{report_id}/regression-feedback",
        response_model=RegressionFeedbackResponse,
    )
    async def submit_regression_feedback(
        report_id: str,
        body: RegressionFeedbackRequest,
    ) -> RegressionFeedbackResponse:
        """回归反馈（AC-6/AC-9）。

        5 态 allowed：pr_open/draft_pr/concluded/reflected/reflowed；
        其他 9 态返回 409。
        outcome=safe → 仅写 MetricPoint。
        outcome=regression + {concluded, reflected} → 迁移 reflowed + 触发回流。
        outcome=regression + {pr_open, draft_pr, reflowed} → 仅写 MetricPoint。
        """
        bug = _require_report(deps, report_id)
        current_status = _get_status(bug)

        # 状态守卫：5 态 allowed，其他 9 态 409
        if current_status not in STATUS_ALLOWED_REGRESSION_FEEDBACK:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "regression-feedback not allowed in status "
                    f"'{current_status}' (allowed: "
                    f"{sorted(STATUS_ALLOWED_REGRESSION_FEEDBACK)})"
                ),
            )

        # 写 MetricPoint（metric_type=safety）
        metric_point_id = f"mp-{uuid.uuid4().hex[:12]}"
        if deps.metric_point_repo is not None:
            try:
                mp = deps.metric_point_repo.create(
                    id=metric_point_id,
                    bug_report_id=report_id,
                    metric_type="safety",
                    value=(
                        1.0 if body.outcome.value == "regression" else 0.0
                    ),
                    bucket_dim=body.bucket_dim,
                    bucket_value=body.bucket_value,
                )
                created_id = _get_id(mp)
                if created_id:
                    metric_point_id = created_id
            except Exception as exc:
                logger.warning(
                    "report_router: metric_point_repo.create failed: %s",
                    exc,
                )

        # 分支：outcome=safe → 状态不变
        if body.outcome.value == "safe":
            return RegressionFeedbackResponse(
                metric_point_id=metric_point_id,
                status_before=current_status,
                status_after=current_status,
                reflow_scheduled=False,
            )

        # outcome=regression 分支
        reflow_scheduled = False
        status_after = current_status

        if current_status in _REGRESSION_REFLOW_STATES:
            # concluded / reflected → reflowed + 触发回流
            status_after = BugReportStatus.REFLOWED.value
            reflow_scheduled = True
            # 更新 BugReport.status
            if deps.bug_report_repo is not None:
                try:
                    deps.bug_report_repo.save_status(report_id, status_after)
                except Exception as exc:
                    logger.warning(
                        "report_router: save_status failed: %s", exc
                    )
            # 触发 BB011 路径 B
            if deps.reflow_manager is not None:
                try:
                    deps.reflow_manager.trigger_by_regression(
                        bug,
                        regression_signal={
                            "outcome": "regression",
                            "evidence": body.evidence,
                            "report_id": report_id,
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "report_router: reflow_manager.trigger_by_regression "
                        "failed: %s",
                        exc,
                    )
        elif current_status in _NO_REFLOW_STATES:
            # pr_open / draft_pr / reflowed → 仅写 MetricPoint
            pass

        return RegressionFeedbackResponse(
            metric_point_id=metric_point_id,
            status_before=current_status,
            status_after=status_after,
            reflow_scheduled=reflow_scheduled,
        )

    return router


# ---------------------------------------------------------------------------
# create_webhook_router（webhook 前缀的 1 个端点）
# ---------------------------------------------------------------------------
def create_webhook_router(deps: _Deps) -> APIRouter:
    """构造 /webhook 前缀的 APIRouter（AC-7）。

    Args:
        deps: 依赖容器。

    Returns:
        APIRouter（prefix="/webhook", tags=["webhook"]）。
    """
    router = APIRouter(prefix="/webhook", tags=["webhook"])

    @router.post(
        "/{platform}",
        response_model=WebhookResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def receive_webhook(
        platform: str,
        payload: dict,
    ) -> WebhookResponse:
        """BF001 上报入口（AC-7）。"""
        if platform not in deps.webhook_platforms:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown platform: {platform}",
            )
        # 生成 bug_report_id（实际场景由 BF001 归一化后创建 BugReport）
        bug_report_id = f"bug-{uuid.uuid4().hex[:12]}"
        if deps.orchestrator is not None:
            try:
                # 编排器异步启动（这里不 await，webhook 立即返回 202）
                import asyncio

                loop = asyncio.get_event_loop()
                # 构造简易 BugReport dict 传入
                raw = {
                    "id": bug_report_id,
                    "source_platform": platform,
                    "raw_report": payload,
                }
                loop.create_task(deps.orchestrator.run(raw))
            except Exception as exc:
                logger.warning(
                    "report_router: orchestrator.run trigger failed: %s",
                    exc,
                )
        return WebhookResponse(bug_report_id=bug_report_id, accepted=True)

    return router


# ---------------------------------------------------------------------------
# 便捷工厂：同时创建 reports + webhook router
# ---------------------------------------------------------------------------
def create_routers(
    *,
    orchestrator: Any = None,
    reflow_manager: Any = None,
    session_factory: Optional[Callable[[], Any]] = None,
    bug_report_repo: Any = None,
    metric_point_repo: Any = None,
    trajectory_repo: Any = None,
    clarify_option_provider: Optional[Callable[[str], list[dict]]] = None,
    webhook_platforms: Optional[set[str]] = None,
) -> tuple[APIRouter, APIRouter]:
    """同时构造 reports_router + webhook_router。

    Returns:
        (report_router, webhook_router)
    """
    deps = _Deps(
        orchestrator=orchestrator,
        reflow_manager=reflow_manager,
        session_factory=session_factory,
        bug_report_repo=bug_report_repo,
        metric_point_repo=metric_point_repo,
        trajectory_repo=trajectory_repo,
        clarify_option_provider=clarify_option_provider,
        webhook_platforms=webhook_platforms,
    )
    return create_report_router(deps), create_webhook_router(deps)
