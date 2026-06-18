"""ConfidenceScore Schema（R001-SCH01.3，修复置信度三维评分）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 ConfidenceScore 表
- 任务包 R001-SCH01.3（三维字段名）
- D4

设计要点：
1. **三维字段**（design 4.1 第 582-584 行明确命名）：
   - dim_info_completeness（信息完备度）
   - dim_verification_feasibility（验证可行性）
   - dim_patternability（模式化程度）
   三维组合 → Tier（1-4）。
2. 字段一一对应 design 4.1 ConfidenceScore 表（第 579-587 行）。
"""
from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class ConfidenceScore(Base):
    """ConfidenceScore（修复置信度，design 4.1 第 579-587 行）。

    三维评分（0-1）组合映射到 Tier 1-4，决定修复路径（自动/降级/诊断）。
    """

    __tablename__ = "confidence_scores"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 反向关联 BugReport
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )

    # 三维评分（design 4.1 第 582-584 行）
    dim_info_completeness: Mapped[float | None] = mapped_column(Float, nullable=True)
    dim_verification_feasibility: Mapped[float | None] = mapped_column(Float, nullable=True)
    dim_patternability: Mapped[float | None] = mapped_column(Float, nullable=True)

    # KB 模式命中情况
    kb_pattern_hit: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 三维组合→Tier（1-4）
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 校准用 score / rationale
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    rationale: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["ConfidenceScore"]
