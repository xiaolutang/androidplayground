"""Trajectory + Hypothesis Schema（R001-SCH01.2，排查轨迹树）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Trajectory / Hypothesis 表
- 任务包 R001-SCH01.2（root_hypothesis_id/total_step_budget/kb_reads；Hypothesis 自引用树）
- D4

设计要点：
1. **Hypothesis 自引用树**：parent_id → Hypothesis.id（外键自引用，nullable，根假设无 parent）。
2. **Hypothesis.status 4 态**：proposed/verifying/confirmed/refuted（design 4.1 第 570 行）。
   - 注意：overturning 不作为独立 status 值，通过 overturning_signal/overturning_stage
     字段表达（design 4.1 第 572 行："被推翻时（fixing/verifying/regression）"）。
3. **INV-2 业务约束**：refuted 节点（含被推翻的 confirmed）永久保留，作负向知识。
   - Schema 层用注释标注，**不加 onDelete cascade 删除 refuted**。
   - parent_id 外键的 ondelete 用 RESTRICT（默认），防止误删父节点导致 refuted 子树孤立。
4. 字段一一对应 design 4.1 Trajectory（第 554-560 行）/ Hypothesis（第 564-573 行）表。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class HypothesisStatus(str, Enum):
    """Hypothesis 节点状态 4 态（design 4.1 第 570 行）。

    注意：overturning 不是独立 status，通过 overturning_signal / overturning_stage
    字段表达"被推翻"语义（design 4.1 第 572 行）。
    """

    PROPOSED = "proposed"
    VERIFYING = "verifying"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"


class Trajectory(Base):
    """Trajectory（排查轨迹树聚合，design 4.1 第 554-560 行）。

    一个 BugReport 对应一个 Trajectory，聚合该次排查的假设树根与全局预算。
    """

    __tablename__ = "trajectories"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 反向关联 BugReport（design: bug_report_id str FK）
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )

    # 假设树根（Hypothesis 自引用树的 entry point）
    root_hypothesis_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("hypotheses.id"), nullable=True
    )

    # 全局步数预算（耗尽转缺口诊断）
    total_step_used: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    total_step_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 本次排查读了哪些 KB（埋点，供 MetricPoint）
    kb_reads: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Hypothesis(Base):
    """Hypothesis 节点（自引用树，design 4.1 第 564-573 行）。

    INV-2 约束：refuted 节点（含被推翻的 confirmed）永久保留，作负向知识。
    本 Schema 不对 refuted 节点加 cascade 删除；parent_id 外键 ondelete=RESTRICT
    （SQLAlchemy 默认 NO ACTION，等效禁止级联删除），配合业务层禁止物理删除 refuted。
    """

    __tablename__ = "hypotheses"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 自引用树：parent_id → Hypothesis.id（nullable，根假设无 parent）
    # ondelete 默认 NO ACTION：禁止级联删除，保护 refuted 子树（INV-2）。
    parent_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("hypotheses.id"), nullable=True
    )

    # 假设描述
    hypothesis_text: Mapped[str | None] = mapped_column(String, nullable=True)

    # 预测的可证伪信号
    expected_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 验证动作
    verify_action: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 验证步数预算
    step_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    step_used: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # 4 态（proposed/verifying/confirmed/refuted）
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=HypothesisStatus.PROPOSED.value
    )

    # 验证证据
    confirming_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 证伪信号
    falsifying_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 被推翻时的信号（design 4.1 第 572 行：fixing/verifying/regression 阶段被推翻）
    overturning_signal: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 被推翻时所处的阶段（fixing / verifying / regression）
    overturning_stage: Mapped[str | None] = mapped_column(String, nullable=True)

    # 是否定为根因
    is_rootcause: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


__all__ = ["Trajectory", "Hypothesis", "HypothesisStatus"]
