"""CapabilityGap Schema（R001-SCH01.3，能力缺口）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 CapabilityGap 表
- 任务包 R001-SCH01.3（status 7 态）
- D4 / D5（git_commit_anchor 代码版本绑定，陈旧失效管理）

设计要点：
1. **status 7 态枚举**（design 4.1 第 616 行）：
   identified / waiting / unblocked / resolved / invalid_unblock / wont_reflow / wont_fix
2. **git_commit_anchor**（D5）：代码版本绑定，用于陈旧失效管理（KB / Gap 绑定具体 commit）。
3. 字段一一对应 design 4.1 CapabilityGap 表（第 602-617 行）。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class CapabilityGapStatus(str, Enum):
    """CapabilityGap 状态 7 态枚举（design 4.1 第 616 行）。

    状态语义：
    - identified：新识别的缺口
    - waiting：等待补齐（排队中）
    - unblocked：已补齐，待回流验证
    - resolved：回流验证通过，缺口关闭
    - invalid_unblock：补齐无效（重识别真实缺口）
    - wont_reflow：超回流上限，不再重跑
    - wont_fix：决定不修（成本/优先级）
    """

    IDENTIFIED = "identified"
    WAITING = "waiting"
    UNBLOCKED = "unblocked"
    RESOLVED = "resolved"
    INVALID_UNBLOCK = "invalid_unblock"
    WONT_REFLOW = "wont_reflow"
    WONT_FIX = "wont_fix"


class CapabilityGap(Base):
    """CapabilityGap（能力缺口，design 4.1 第 602-617 行）。

    记录阻塞 bug 修复的能力缺口（信息/设施/模式/模型），补齐后触发回流重跑。
    """

    __tablename__ = "capability_gaps"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 信息 / 设施 / 模式 / 模型
    gap_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # 缺口描述
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    # 来源 bug
    source_bug_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("bug_reports.id"), nullable=True
    )

    # 补齐动作
    unlock_action: Mapped[str | None] = mapped_column(String, nullable=True)

    # 价值评分
    estimated_unlock_value: Mapped[float | None] = mapped_column(
        # design 4.1 未标类型，语义为评分（FB003 按 estimated_unlock_value 排序）
        Integer,
        nullable=True,
    )

    # 关联 bug 列表（JSON 存 id 数组）
    linked_bug_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 补齐证据 / 补齐时间
    unblock_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    unblocked_at: Mapped[str | None] = mapped_column(String, nullable=True)

    # resolved 终态：解决的 bug 列表 / 沉淀的 KB pattern
    resolved_bug_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    kb_pattern_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("kb_entries.id"), nullable=True
    )

    # 重识别真实缺口
    invalid_unblock_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    reflection: Mapped[str | None] = mapped_column(String, nullable=True)

    # 回流相关
    wont_reflow_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    reflow_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)

    # 决定不修
    wont_fix_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String, nullable=True)

    # 7 态状态机
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=CapabilityGapStatus.IDENTIFIED.value
    )

    # 代码版本绑定（D5 陈旧失效管理）
    git_commit_anchor: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["CapabilityGap", "CapabilityGapStatus"]
