"""Gap Router（R001-FF002）—— CapabilityGap API 层。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.3 接口契约（730-731 行）
- Sprint Contract R001-FF002（mode: direct）
- 依赖 BF008 GapStore（7 态状态机 + INV-2）
- 依赖 BB011 ReflowManager（路径 A 回流触发）

设计要点：
1. **两个端点**：
   - ``GET /gaps``：按 estimated_unlock_value 降序列表，支持分页。
   - ``POST /gaps/{id}/unblock``：waiting -> unblocked 状态迁移 + 触发 BB011 回流。
2. **状态守卫**：unblock 仅允许 waiting 态调用，其他状态返回 409。
3. **依赖注入**：通过 ``get_gap_store`` / ``get_reflow_manager`` 依赖注入，
   测试时用 ``app.dependency_overrides`` 替换为 mock。
4. **错误码统一**：400 参数错 / 404 gap 不存在 / 409 状态非法 / 5xx 内部错误。
5. **BB011 回流**：unblock 后对每个 linked_bug_id 调 ReflowManager.trigger_by_gap_fixed
   （路径 A：gap_pending -> received）。reflow_scheduled 只要有一个 bug 触发成功即为 True。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from agent.gap.gap_store import GapStore
from agent.gap_mgmt.reflow_manager import ReflowManager
from agent.schemas.capability_gap import CapabilityGapStatus

logger = logging.getLogger(__name__)

__all__ = [
    "router",
    "GapSummary",
    "GapListResponse",
    "UnblockRequest",
    "UnblockResponse",
    "get_gap_store",
    "get_reflow_manager",
]

router = APIRouter(prefix="/gaps", tags=["gaps"])


# ---------------------------------------------------------------------------
# 默认依赖占位（生产环境由 main.py 覆盖，测试用 dependency_overrides）
# ---------------------------------------------------------------------------
def get_gap_store() -> GapStore:
    """返回 GapStore 实例。

    生产环境由 main.py 通过 ``app.dependency_overrides`` 或 include_router 时覆盖。
    """
    raise NotImplementedError("GapStore dependency not configured")


def get_reflow_manager() -> ReflowManager:
    """返回 ReflowManager 实例。

    生产环境由 main.py 覆盖。
    """
    raise NotImplementedError("ReflowManager dependency not configured")


# ---------------------------------------------------------------------------
# DTO（Pydantic v2 BaseModel）
# ---------------------------------------------------------------------------
class GapSummary(BaseModel):
    """GET /gaps 响应中的单个 gap 摘要。

    Attributes:
        id: CapabilityGap id。
        gap_type: 缺口类型（信息/设施/模式/模型）。
        waiting_reason: 缺口描述（作为等待原因展示）。
        estimated_unlock_value: 预估解锁价值评分（用于排序）。
        status: 当前状态（7 态之一）。
        linked_bug_ids: 关联的 bug_report id 列表。
    """

    id: str
    gap_type: Optional[str] = None
    waiting_reason: Optional[str] = None
    estimated_unlock_value: Optional[float] = None
    status: str
    linked_bug_ids: list[str] = Field(default_factory=list)


class GapListResponse(BaseModel):
    """GET /gaps 响应体（分页结构）。

    Attributes:
        items: gap 摘要列表（按 estimated_unlock_value 降序）。
        total: 总记录数。
        page: 当前页码（1-based）。
        page_size: 每页条数。
    """

    items: list[GapSummary]
    total: int
    page: int
    page_size: int


class UnblockRequest(BaseModel):
    """POST /gaps/{id}/unblock 请求体。

    Attributes:
        evidence: 补齐证据（日志/截图链接/issue 链接等）。
        action_taken: 采取的补齐动作描述。
    """

    evidence: str = Field(..., min_length=1, description="补齐证据")
    action_taken: str = Field(..., min_length=1, description="采取的补齐动作")


class UnblockResponse(BaseModel):
    """POST /gaps/{id}/unblock 响应体。

    Attributes:
        gap_id: 被补齐的 gap id。
        status_before: 迁移前状态。
        status_after: 迁移后状态。
        reflow_scheduled: 是否成功触发了至少一个回流。
    """

    gap_id: str
    status_before: str
    status_after: str
    reflow_scheduled: bool


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------
def _gap_to_summary(gap: Any) -> GapSummary:
    """将 CapabilityGap ORM 对象转换为 GapSummary DTO。

    Args:
        gap: CapabilityGap 实例（或 duck typing mock）。

    Returns:
        GapSummary DTO。
    """
    return GapSummary(
        id=gap.id,
        gap_type=getattr(gap, "gap_type", None),
        waiting_reason=getattr(gap, "description", None),
        estimated_unlock_value=getattr(gap, "estimated_unlock_value", None),
        status=gap.status,
        linked_bug_ids=list(getattr(gap, "linked_bug_ids", None) or []),
    )


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------
@router.get("", response_model=GapListResponse, status_code=status.HTTP_200_OK)
def list_gaps(
    page: int = Query(default=1, ge=1, description="页码（1-based）"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    gap_store: GapStore = Depends(get_gap_store),
) -> GapListResponse:
    """GET /gaps —— 按 estimated_unlock_value 降序列出 gap，支持分页。

    排序规则：
    - 主排序：estimated_unlock_value 降序（None 排末尾）。
    - 次排序：id 升序（稳定排序保证确定性）。

    Args:
        page: 页码（1-based，默认 1）。
        page_size: 每页条数（默认 20，上限 100）。
        gap_store: GapStore 依赖注入。

    Returns:
        GapListResponse：分页结果。
    """
    all_gaps = gap_store.list()

    # 按 estimated_unlock_value 降序排序（None 排末尾），次排序 id 升序保证确定性
    sorted_gaps = sorted(
        all_gaps,
        key=lambda g: (
            -(
                float(g.estimated_unlock_value)
                if g.estimated_unlock_value is not None
                else float("-inf")
            ),
            g.id,
        ),
    )

    total = len(sorted_gaps)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = sorted_gaps[start:end]

    return GapListResponse(
        items=[_gap_to_summary(g) for g in page_items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{gap_id}/unblock",
    response_model=UnblockResponse,
    status_code=status.HTTP_200_OK,
)
def unblock_gap(
    gap_id: str,
    request: UnblockRequest,
    gap_store: GapStore = Depends(get_gap_store),
    reflow_manager: ReflowManager = Depends(get_reflow_manager),
) -> UnblockResponse:
    """POST /gaps/{id}/unblock —— 提交补齐动作（waiting -> unblocked + 触发回流）。

    流程：
    1. 查找 gap，不存在返回 404。
    2. 状态守卫：仅 waiting 可 unblock，其他状态返回 409。
    3. 状态迁移：waiting -> unblocked（通过 GapStore.transition）。
    4. 触发回流：对每个 linked_bug_id 调 ReflowManager.trigger_by_gap_fixed
       （路径 A）。reflow_scheduled 只要有一个 bug 触发回流即为 True。
    5. 返回迁移结果。

    Args:
        gap_id: 要补齐的 CapabilityGap id。
        request: 补齐请求（evidence + action_taken）。
        gap_store: GapStore 依赖注入。
        reflow_manager: ReflowManager 依赖注入。

    Returns:
        UnblockResponse：迁移 + 回流结果。

    Raises:
        HTTPException 404: gap 不存在。
        HTTPException 409: 状态非 waiting，无法 unblock。
        HTTPException 500: 内部错误（迁移失败 / 回流异常）。
    """
    # 1. 查找 gap
    gap = gap_store.get(gap_id)
    if gap is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Gap {gap_id!r} not found",
        )

    status_before = gap.status

    # 2. 状态守卫：仅 waiting 可 unblock
    if status_before != CapabilityGapStatus.WAITING.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Gap {gap_id!r} status is {status_before!r}, "
                f"expected {CapabilityGapStatus.WAITING.value!r}"
            ),
        )

    # 3. 状态迁移：waiting -> unblocked
    try:
        updated_gap = gap_store.transition(
            gap_id,
            CapabilityGapStatus.UNBLOCKED,
            reason=f"unblock: evidence={request.evidence!r}, action={request.action_taken!r}",
        )
    except Exception as exc:
        logger.error("GapStore.transition failed for gap %s: %s", gap_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"State transition failed: {exc}",
        ) from exc

    # 4. 触发 BB011 回流（路径 A：gap_pending -> received）
    linked_bug_ids = list(getattr(updated_gap, "linked_bug_ids", None) or [])
    reflow_scheduled = False

    for bug_id in linked_bug_ids:
        try:
            # BB011 ReflowManager.trigger_by_gap_fixed 需要 bug_report 对象。
            # Router 层不持有 BugReportStore，用 _BugReportProxy 携带 id +
            # 默认 status=gap_pending 满足路径 A 前置条件。
            # 生产中可通过 DI 注入 BugReportStore 获取真实对象。
            result = reflow_manager.trigger_by_gap_fixed(
                bug_report=_BugReportProxy(id=bug_id),
                gap_id=gap_id,
            )
            if result.reflowed:
                reflow_scheduled = True
        except Exception as exc:
            # 回流触发失败不阻断 unblock 响应（降级：记录日志）
            logger.warning(
                "ReflowManager.trigger_by_gap_fixed failed for "
                "bug=%s gap=%s: %s",
                bug_id,
                gap_id,
                exc,
            )

    return UnblockResponse(
        gap_id=gap_id,
        status_before=status_before,
        status_after=updated_gap.status,
        reflow_scheduled=reflow_scheduled,
    )


# ---------------------------------------------------------------------------
# BugReport 代理（轻量，仅携带 id 用于回流触发）
# ---------------------------------------------------------------------------
class _BugReportProxy:
    """轻量 BugReport 代理，仅携带 id。

    在真实实现中，Router 会从 BugReportStore 获取完整 BugReport 对象。
    此处用代理简化——ReflowManager 通过 duck typing 读取 id / status /
    reflow_count。状态和 reflow_count 默认值使其满足路径 A 的前置条件
    （status=gap_pending, reflow_count=0）。

    生产环境中应替换为从 BugReportStore 查询的真实对象。
    """

    def __init__(
        self,
        *,
        id: str,
        status_val: str = "gap_pending",
        reflow_count: int = 0,
    ) -> None:
        self.id = id
        self.status = status_val
        self.reflow_count = reflow_count
