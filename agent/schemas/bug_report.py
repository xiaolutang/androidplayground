"""BugReport 核心 Schema + 14 态状态枚举（R001-SCH01.1）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 BugReport 表
- 任务包 R001-SCH01.1（14 态 status 唯一定义于此；STATUS_ALLOWED_REGRESSION_FEEDBACK 5 态）
- D4（PostgreSQL + pgvector 同库）

设计要点：
1. **14 态 status 枚举唯一定义于此**（BugReportStatus），全项目（INT02 状态机、
   契约测试表、frontend）均引用本模块的枚举值，禁止在其他位置重复定义。
2. **STATUS_ALLOWED_REGRESSION_FEEDBACK**：regression-feedback 允许的 5 态集合
   （INV-3 契约基础：concluded 不可回退除经 reflowed 显式触发）。
3. **clarify_requested** 不是独立状态：status 保持在 assessing，置 clarify_requested=true
   表示卡在 FB004 追问子回路（design 4.1 第 537 行明确语义）。
4. 主键用 String（UUID 字符串），便于外部 webhook 上报时传入或由 BB001 生成。
5. 字段一一对应 design 4.1 BugReport 表（第 497-522 行）。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class BugReportStatus(str, Enum):
    """BugReport 状态机 14 态枚举（唯一定义，design 4.1 第 524-527 行）。

    完整列表：
        received, assessing, degraded, reproducing, located, fixing, verified,
        pr_open, draft_pr, gap_pending, wont_reflow, concluded, reflowed, reflected

    状态流转要点（design 4.1 第 525-535 行）：
    - 主路径：received → assessing | degraded → reproducing → located → fixing →
      verified → pr_open | draft_pr → concluded → reflected
    - 分支：located → gap_pending → wont_reflow | received（缺口补齐回流，路径 A）
    - 路径 B（已合并后回归）：concluded / reflected → reflowed → received
      （regression-feedback(outcome=regression) 触发，INV-3 唯一允许的 concluded 后迁移）
    - INV-3：concluded 不可回退除经 reflowed 显式触发
    - clarifying 不是独立状态（assessing + clarify_requested=true 子回路）
    """

    RECEIVED = "received"
    ASSESSING = "assessing"
    DEGRADED = "degraded"
    REPRODUCING = "reproducing"
    LOCATED = "located"
    FIXING = "fixing"
    VERIFIED = "verified"
    PR_OPEN = "pr_open"
    DRAFT_PR = "draft_pr"
    GAP_PENDING = "gap_pending"
    WONT_REFLOW = "wont_reflow"
    CONCLUDED = "concluded"
    REFLOWED = "reflowed"
    REFLECTED = "reflected"


# regression-feedback 允许的 5 态（design 4.3 第 740 行 + 任务包 SCH01.1）
# INV-3 契约基础：concluded 不可回退除经 reflowed 显式触发；
# 这 5 态是"PR 已提交后任一阶段"，其他 9 态返回 409（未提 PR 不应反馈）。
STATUS_ALLOWED_REGRESSION_FEEDBACK: frozenset[str] = frozenset(
    {
        BugReportStatus.PR_OPEN.value,
        BugReportStatus.DRAFT_PR.value,
        BugReportStatus.CONCLUDED.value,
        BugReportStatus.REFLECTED.value,
        BugReportStatus.REFLOWED.value,
    }
)


class BugReport(Base):
    """BugReport（工单核心，design 4.1 第 497-522 行）。

    字段一一对应 design 4.1，未做任何增删。字段语义见 design 对应说明列。
    """

    __tablename__ = "bug_reports"

    # 主键（design: str(PK)）— UUID 字符串，由 BB001 或 webhook 入口生成
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # BF001 归一化后的原始上报
    raw_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # bugly/sentry/...
    source_platform: Mapped[str | None] = mapped_column(String, nullable=True)

    # BF001 幂等 key（平台级唯一 event_id，如 Sentry event_id）
    # nullable=True：允许无 event_id 的上报进入，由 FF001 router 决定是否拒绝。
    # 不加 DB unique constraint（nullable + 多平台组合，约束由 FF001 查询逻辑保证）。
    external_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # 客户端版本（INV-1 必携）
    version_code: Mapped[str | None] = mapped_column(String, nullable=True)
    version_name: Mapped[str | None] = mapped_column(String, nullable=True)

    # BB001 打分
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 信息缺口分类 A/B/C/D
    gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # crash/blank/loading/no_response/data_error
    symptom_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # root_cause / root_cause_location（file:line）
    root_cause: Mapped[str | None] = mapped_column(String, nullable=True)
    root_cause_location: Mapped[str | None] = mapped_column(String, nullable=True)

    # 被推翻的根因（换方向留存）
    refuted_rootcause_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # BB006 分流（1-4）
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 外键：ConfidenceScore / FixPatch / Trajectory
    confidence_score_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("confidence_scores.id"), nullable=True
    )
    fix_patch_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("fix_patches.id"), nullable=True
    )
    trajectory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("trajectories.id"), nullable=True
    )

    # BB008 三关结果
    verification_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # BB009
    pr_url: Mapped[str | None] = mapped_column(String, nullable=True)
    pr_diff: Mapped[str | None] = mapped_column(String, nullable=True)

    # CapabilityGap 外键列表（JSON 存 id 数组，避免多对多关联表，design 4.1 原文为 list[str] FK）
    gap_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 回流次数
    reflow_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # 超上限原因
    wont_reflow_reason: Mapped[str | None] = mapped_column(String, nullable=True)

    # 成本埋点
    step_budget_used: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    token_used: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # 临界态追问标记（非独立状态，见模块 docstring 第 3 点）
    clarify_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # 14 态状态机（枚举值字符串持久化，便于 SQL 查询与跨语言对齐）
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=BugReportStatus.RECEIVED.value
    )

    # 终态字段
    concluded_at: Mapped[str | None] = mapped_column(String, nullable=True)
    merge_commit: Mapped[str | None] = mapped_column(String, nullable=True)

    # 相似历史 issue（Schema 预留，MVP 不填充；design 第 914 行明确）
    similar_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)


__all__ = ["BugReport", "BugReportStatus", "STATUS_ALLOWED_REGRESSION_FEEDBACK"]
