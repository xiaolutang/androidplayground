"""DiagnosisReport Schema（R001-SCH02，BB012 诊断报告输出）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 DiagnosisReport 表（第 689-699 行）
- 任务包 R001-SCH02（format ∈ {json, markdown}；capability_gaps 为 list[str] FK）

设计要点：
1. **BB012 输出**：Tier3/4 排查到尽头（定位失败 / 缺口阻塞）时产出诊断报告，
   总结假设树 / 识别能力缺口 / 给出建议动作。
2. **format 双输出**（design 第 699 行）：json（结构化，供 frontend 渲染）/
   markdown（人类可读，供 PR 描述 / 工单评论）。
   同一份报告可同时存两种格式（两行记录或 report_content 按 format 区分），
   这里以 format 字段标记当前行的输出形态。
3. **capability_gaps 为 list[str] FK**（design 第 696 行）：JSON 存 CapabilityGap id 数组，
   与 BugReport.gap_ids 风格一致（避免多对多关联表）。
4. **similar_issues 预留**（design 第 697 行 + design 第 914 行）：Schema 预留字段，
   MVP 不填充。
5. 字段一一对应 design 4.1 DiagnosisReport 表。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class DiagnosisFormat(str, Enum):
    """DiagnosisReport 输出格式二值枚举（design 4.1 第 699 行）。"""

    JSON = "json"
    MARKDOWN = "markdown"


class DiagnosisReport(Base):
    """DiagnosisReport（BB012 诊断报告，design 4.1 第 689-699 行）。

    Tier3/4 产出：总结假设树、识别能力缺口、给出建议动作。
    同一份报告可输出 json / markdown 两种格式（format 字段区分）。
    """

    __tablename__ = "diagnosis_reports"

    # 主键（design: str(PK)）
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 关联 bug（design 第 693 行）
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )

    # 症状类型（design 第 694 行）
    symptom_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # 根因分析摘要（design 第 694 行）
    root_cause_analysis: Mapped[str | None] = mapped_column(String, nullable=True)

    # 假设树摘要（design 第 695 行：json）
    hypothesis_tree_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 识别的能力缺口（design 第 696 行：list[str] FK，JSON 存 CapabilityGap id 数组）
    capability_gaps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 相似历史 issue（design 第 697 行：Schema 预留，MVP 不填充）
    similar_issues: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 建议动作（design 第 698 行：json）
    recommended_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 输出格式（design 第 699 行：json / markdown）
    format: Mapped[str] = mapped_column(
        String, nullable=False, default=DiagnosisFormat.JSON.value
    )

    # 报告正文（按 format 解释：json 结构化 / markdown 文本）
    report_content: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["DiagnosisReport", "DiagnosisFormat"]
