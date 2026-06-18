"""Anchor Schema（R001-SCH02，BF007 锚点库单元）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Anchor 表（第 701-709 行）
- 任务包 R001-SCH02（visual_features 为 Vector 类型）

设计要点：
1. **BF007 锚点库**：每个页面 / 状态一组 Anchor，存"正常态"基线，
   BF003 复现时与实际截图对照（视觉差异即 visual signal）。
2. **visual_features 为 pgvector Vector 类型**（design 第 708 行）：
   视觉特征向量（embedding），供 BF003 视觉对照与近邻检索。
   dim 不在 Schema 层锁死（Vector() 无参），由 embedding 模型决定。
3. **git_commit_anchor**（design 第 709 行）：代码版本绑定，D5 陈旧失效管理
   （commit 变更后锚点可能失效）。
4. 字段一一对应 design 4.1 Anchor 表。
"""
from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base, Vector


class Anchor(Base):
    """Anchor（BF007 锚点库单元，design 4.1 第 701-709 行）。

    每条记录描述一个页面在正常状态下的视觉/文字预期，
    供 BF003 复现时视觉对照（visual signal 来源之一）。
    """

    __tablename__ = "anchors"

    # 主键（design: str(PK)）
    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 页面标识（design 第 705 行）
    page_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # 正常状态截图引用（design 第 706 行）
    screenshot_ref: Mapped[str | None] = mapped_column(String, nullable=True)

    # 文字预期（design 第 707 行）
    text_expectation: Mapped[str | None] = mapped_column(String, nullable=True)

    # 视觉特征向量（design 第 708 行：vector，pgvector）
    # dim 不锁死，由 embedding 模型决定
    visual_features: Mapped[list | None] = mapped_column(Vector(), nullable=True)

    # 代码版本绑定（design 第 709 行，D5 陈旧失效管理）
    git_commit_anchor: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["Anchor"]
