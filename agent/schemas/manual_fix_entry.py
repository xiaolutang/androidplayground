"""ManualFixEntry Schema（R001-SCH02，BB015 人工修复录入 → KB pattern）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 ManualFixEntry 表（第 653-665 行）
- 任务包 R001-SCH02（BB015→KB pattern 写入契约）

设计要点：
1. **BB015 契约**：人工修复（PR 合并 / 手动修复）后，结构化录入此表，
   trigger_conditions + patch_diff 作为 KB pattern 层写入素材
   （经沉淀写入 KBEntry(layer=pattern)，kb_pattern_id 反向引用）。
2. **trigger_conditions 为 JSON**（design 第 662 行）：触发条件（症状 + 信号特征），
   pattern 检索用——KBEntry(pattern) 写入时作为 trigger_conditions 字段来源。
3. **trajectory_id FK**（design 第 660 行）：关联排查轨迹（即使是人工修复，
   通常也有 agent 先尝试过的轨迹，关联便于回溯）。
4. **kb_pattern_id FK**（design 第 663 行）：沉淀进的 KBEntry(pattern) 引用，
   KBEntry 同表（layer 区分），FK 指向 kb_entries.id。
5. **git_commit_anchor**（design 第 664 行）：代码版本绑定，D5 陈旧失效管理。
6. 字段一一对应 design 4.1 ManualFixEntry 表。
"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class ManualFixEntry(Base):
    """ManualFixEntry（BB015 人工修复录入，design 4.1 第 653-665 行）。

    人工修复结构化录入载体：patch_diff + root_cause_text + trigger_conditions
    三要素，沉淀进 KBEntry(pattern) 后 kb_pattern_id 反向引用。
    """

    __tablename__ = "manual_fix_entries"

    # 主键（design: str(PK)）
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 关联 bug（design 第 658 行：bug_report_id / source_bug_id）
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )
    # 原始 source bug id（跨平台上报 id，未经 BB001 归一化）
    source_bug_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # 人修 patch（自动抓取自 commit，design 第 659 行）
    patch_diff: Mapped[str | None] = mapped_column(String, nullable=True)

    # 关联排查轨迹（design 第 660 行）
    trajectory_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("trajectories.id"), nullable=True
    )

    # 根因解释（design 第 661 行：引导式填写，防噪声）
    root_cause_text: Mapped[str | None] = mapped_column(String, nullable=True)

    # 触发条件（design 第 662 行：json，症状 + 信号特征，pattern 检索用）
    trigger_conditions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 沉淀进的 KBEntry(pattern) 引用（design 第 663 行）
    kb_pattern_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("kb_entries.id"), nullable=True
    )

    # 代码版本绑定（design 第 664 行，D5 陈旧失效管理）
    git_commit_anchor: Mapped[str | None] = mapped_column(String, nullable=True)

    # 录入者（design 第 665 行）
    recorder: Mapped[str | None] = mapped_column(String, nullable=True)
    # 录入时间
    recorded_at: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["ManualFixEntry"]
