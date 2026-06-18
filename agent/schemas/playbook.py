"""Playbook Schema（R001-SCH01.2，方法论层）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Playbook 表
- 任务包 R001-SCH01.2（symptom_type/detection_actions/hypothesis_space/passive）
- D4

设计要点：
1. **symptom_type 为主键**（design 4.1: str(PK 索引)）—— 5 类症状各一份 Playbook。
2. **passive** 标志区分崩溃型（被动等信号）与症状型（主动探测）。
3. 字段一一对应 design 4.1 Playbook 表（第 539-550 行）。
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base


class Playbook(Base):
    """Playbook（方法论，design 4.1 第 539-550 行）。

    按 symptom_type 检索（registry 按 symptom_type 路由），5 类症状各一份配置。
    """

    __tablename__ = "playbooks"

    # 5 类症状（crash/blank/loading/no_response/data_error），主键索引
    symptom_type: Mapped[str] = mapped_column(String, primary_key=True)

    # 判定信号（design 4.1 第 544 行：judgment_signals，复数）
    judgment_signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 锚点来源（BF007）
    anchor_source: Mapped[str | None] = mapped_column(String, nullable=True)

    # 探测动作集
    detection_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 根因假设空间（假设种子）
    root_cause_hypothesis_space: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 诱发动作集（症状型主动诱发）
    triggering_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 单假设验证步数上限
    step_budget_per_hypothesis: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 崩溃型=被动等信号（true）；症状型=主动探测（false）
    passive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


__all__ = ["Playbook"]
