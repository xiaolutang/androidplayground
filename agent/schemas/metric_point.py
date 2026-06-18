"""MetricPoint Schema（R001-SCH01.3，验收埋点）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 MetricPoint 表
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 5.5（五维统计口径）
- 任务包 R001-SCH01.3（五维 metric_type + bucket_dim）
- D4

设计要点：
1. **metric_type 五维**（design 4.1 第 639 行 / 5.5）：
   - effectiveness：有效性（修复成功率）
   - safety：安全性（回归率，5.5 只计已合并 PR 的回归）
   - coverage：覆盖面（按 period 桶：cold_start / kb_accumulated）
   - growth：成长性（按 gap_type 桶，previous_tier → new_tier 跃迁）
   - cost：成本（按 tier 桶，step/token 消耗）
2. **bucket_dim / bucket_value**：分桶维度与值（design 4.1 第 643 行）。
3. **period**：cold_start / kb_accumulated（基线区分，5.5 有效性/覆盖面按 period 分基线）。
4. 字段一一对应 design 4.1 MetricPoint 表（第 634-647 行）。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class MetricType(str, Enum):
    """MetricPoint 五维 metric_type 枚举（design 4.1 第 639 行 / 5.5）。

    - effectiveness：有效性（修复成功率，分母为已合并 PR 数）
    - safety：安全性（回归率，5.5 只计已合并 PR 的回归）
    - coverage：覆盖面（症状/symptom_type 覆盖率，按 period 分基线）
    - growth：成长性（缺口补齐后 Tier 跃迁，按 gap_type 分桶）
    - cost：成本（step/token 消耗，按 tier 分桶）
    """

    EFFECTIVENESS = "effectiveness"
    SAFETY = "safety"
    COVERAGE = "coverage"
    GROWTH = "growth"
    COST = "cost"


class MetricPeriod(str, Enum):
    """MetricPoint period 枚举（design 4.1 第 642 行）。

    - cold_start：冷启动期（KB 累积量不足 KB_COLD_START_N）
    - kb_accumulated：KB 累积期（KB 累积量达标后）
    有效性 / 覆盖面维度按 period 分基线对比（5.5）。
    """

    COLD_START = "cold_start"
    KB_ACCUMULATED = "kb_accumulated"


class MetricPoint(Base):
    """MetricPoint（验收埋点，design 4.1 第 634-647 行）。

    多节点写入（BB006/BB008/BB011 等按 metric_type 写不同维度），
    用于第 5.5 节五维统计与 Capability Gap 反馈。
    """

    __tablename__ = "metric_points"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 关联 bug / trajectory
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )
    trajectory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("trajectories.id"), nullable=True
    )

    # 五维（effectiveness/safety/coverage/growth/cost）
    metric_type: Mapped[str] = mapped_column(String, nullable=False)

    # 指标值
    value: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 写入时的 Tier
    tier_at_time: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 基线区分（cold_start / kb_accumulated）
    period: Mapped[str | None] = mapped_column(String, nullable=True)

    # 分桶维度（tier / gap_type / null）
    # design 4.1 第 643 行：有效性·覆盖面按 period 桶，成长性按 gap_type，成本按 tier
    bucket_dim: Mapped[str | None] = mapped_column(String, nullable=True)

    # 分桶值
    bucket_value: Mapped[str | None] = mapped_column(String, nullable=True)

    # 成长性专用：缺口补齐前 / 回流后 Tier
    previous_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 成长性专用：关联缺口
    ref_gap_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("capability_gaps.id"), nullable=True
    )
    ref_gap_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # 时间戳（ISO8601 字符串，design 4.1 第 647 行原文未标具体类型）
    timestamp: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["MetricPoint", "MetricType", "MetricPeriod"]
