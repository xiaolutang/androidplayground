"""FixPatch Schema（R001-SCH01.3，修复补丁）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 FixPatch 表
- 任务包 R001-SCH01.3（patch_diff/tier/pr_url）
- D4

设计要点：
1. **strategy** 三选一：template / llm / history_calibration（按可解决性优先级）。
2. **is_draft** 区分 Tier1（false，直接 PR）与 Tier2（true，draft PR 落点）；
   统一由 BugReport.fix_patch_id 指向本条，draft 与否由此字段区分（不另设字段）。
3. 字段一一对应 design 4.1 FixPatch 表（第 589-600 行）。
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class FixPatch(Base):
    """FixPatch（修复补丁，design 4.1 第 589-600 行）。

    一个 BugReport 关联一个 FixPatch（通过 BugReport.fix_patch_id）；
    Tier1 直接 PR（is_draft=false），Tier2 走 draft PR（is_draft=true）。
    """

    __tablename__ = "fix_patches"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 反向关联 BugReport
    bug_report_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )

    # template / llm / history_calibration（按可解决性优先级）
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)

    # Tier2=true（draft PR 落点，区别于 Tier1）
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 补丁内容
    patch_diff: Mapped[str | None] = mapped_column(String, nullable=True)

    # 目标文件 / 行号
    target_file: Mapped[str | None] = mapped_column(String, nullable=True)
    target_lines: Mapped[str | None] = mapped_column(String, nullable=True)

    # KB 历史校准引用
    kb_history_ref: Mapped[str | None] = mapped_column(
        String, ForeignKey("kb_entries.id"), nullable=True
    )

    # 尝试历史（F4a 换策略）
    attempt_no: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    strategy_chain: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 三关结果
    verification_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # PR URL（design 4.1 BugReport 表 pr_url 同义，此处为 patch 自身 PR 链接）
    pr_url: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["FixPatch"]
