"""report_router 请求/响应 DTO（Pydantic v2）。

依据：
- Sprint Contract R001-FF001（status: agreed，10 AC）
- backend design 4.3 接口契约（第 720-742 行）

DTO 清单：
- ReportSummary：列表项（AC-1）
- ReportListResponse：列表分页响应（AC-1）
- ReportDetail：报告详情（AC-2）
- TrajectoryNode / TrajectoryEdge / TrajectoryResponse：假设树（AC-3）
- ClarifyOption / ClarifyOptionsResponse：追问候选（AC-4）
- ClarifyAnswerItem / ClarifyRequest / ClarifyResponse：提交追问（AC-5）
- RegressionFeedbackRequest / RegressionFeedbackResponse：回归反馈（AC-6/AC-9）
- WebhookRequest / WebhookResponse：平台上报（AC-7）
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AC-1 GET /reports（列表）
# ---------------------------------------------------------------------------
class ReportSummary(BaseModel):
    """报告列表项（AC-1）。"""

    id: str
    title: Optional[str] = None
    status: str
    tier: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReportListResponse(BaseModel):
    """报告列表分页响应（AC-1）。"""

    items: list[ReportSummary] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20


# ---------------------------------------------------------------------------
# AC-2 GET /reports/{id}（详情）
# ---------------------------------------------------------------------------
class ReportDetail(BaseModel):
    """报告详情（AC-2）。

    字段从 BugReport ORM 投影，宽松类型允许部分字段缺失。
    """

    id: str
    title: Optional[str] = None
    status: str
    tier: Optional[int] = None
    symptom_type: Optional[str] = None
    root_cause: Optional[str] = None
    root_cause_location: Optional[str] = None
    confidence_score_id: Optional[str] = None
    fix_patch_id: Optional[str] = None
    pr_url: Optional[str] = None
    reflow_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    raw_report: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# AC-3 GET /reports/{id}/trajectory（假设树）
# ---------------------------------------------------------------------------
class TrajectoryNode(BaseModel):
    """假设树节点。"""

    id: str
    label: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[float] = None


class TrajectoryEdge(BaseModel):
    """假设树边。

    Python 关键字 from 用 model_dump(by_alias=True) 序列化为 "from"。
    """

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    label: Optional[str] = None

    model_config = {"populate_by_name": True}


class TrajectoryResponse(BaseModel):
    """假设树响应（AC-3）。"""

    nodes: list[TrajectoryNode] = Field(default_factory=list)
    edges: list[TrajectoryEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AC-4 GET /reports/{id}/clarify-options（追问候选）
# ---------------------------------------------------------------------------
class ClarifyOption(BaseModel):
    """追问候选项。"""

    id: str
    question: str
    context: Optional[str] = None


class ClarifyOptionsResponse(BaseModel):
    """追问候选响应（AC-4）。"""

    options: list[ClarifyOption] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AC-5 POST /reports/{id}/clarify（提交追问）
# ---------------------------------------------------------------------------
class ClarifyAnswerItem(BaseModel):
    """追问答案项。"""

    option_id: str
    value: str


class ClarifyRequest(BaseModel):
    """提交追问答案请求体（AC-5）。"""

    answers: list[ClarifyAnswerItem]


class ClarifyResponse(BaseModel):
    """提交追问响应（AC-5）。"""

    accepted: bool


# ---------------------------------------------------------------------------
# AC-6 POST /reports/{id}/regression-feedback（回归反馈）
# ---------------------------------------------------------------------------
class RegressionOutcome(str, Enum):
    """回归反馈 outcome 枚举（AC-6）。"""

    REGRESSION = "regression"
    SAFE = "safe"


class RegressionFeedbackRequest(BaseModel):
    """回归反馈请求体（AC-6）。

    outcome: regression | safe
    evidence: 日志/截图/issue 链接
    bucket_dim / bucket_value: 可选分桶
    """

    outcome: RegressionOutcome
    evidence: str
    bucket_dim: Optional[str] = None
    bucket_value: Optional[str] = None


class RegressionFeedbackResponse(BaseModel):
    """回归反馈响应体（AC-6/AC-9）。

    四字段必须全部存在。
    """

    metric_point_id: str
    status_before: str
    status_after: str
    reflow_scheduled: bool


# ---------------------------------------------------------------------------
# AC-7 POST /webhook/{platform}（上报入口）
# ---------------------------------------------------------------------------
class WebhookRequest(BaseModel):
    """webhook 上报请求体（AC-7）。

    平台原始格式，BF001 适配器负责归一化。宽松模型允许任意字段。
    """

    model_config = {"extra": "allow"}


class WebhookResponse(BaseModel):
    """webhook 上报响应（AC-7）。"""

    bug_report_id: str
    accepted: bool = True


__all__ = [
    "ReportSummary",
    "ReportListResponse",
    "ReportDetail",
    "TrajectoryNode",
    "TrajectoryEdge",
    "TrajectoryResponse",
    "ClarifyOption",
    "ClarifyOptionsResponse",
    "ClarifyAnswerItem",
    "ClarifyRequest",
    "ClarifyResponse",
    "RegressionOutcome",
    "RegressionFeedbackRequest",
    "RegressionFeedbackResponse",
    "WebhookRequest",
    "WebhookResponse",
]
