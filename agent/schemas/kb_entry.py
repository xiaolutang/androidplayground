"""KBEntry Schema（R001-SCH01.3，知识库条目）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 KBEntry 表
- 任务包 R001-SCH01.3（root_cause_signals = Vector(dim)；validity_status=valid/stale/conflicting）
- D4 / D9（KB 冲突：valid / stale / conflicting 三态标记）

设计要点：
1. **root_cause_signals 为 pgvector Vector 类型**（根因信号向量，堆栈/代码路径关键词 embedding）。
   - dim 不在 Schema 层锁死：pgvector 支持可变长向量（Vector() 无参），具体维度由
     embedding 模型决定，迁移/调用方负责对齐。
2. **validity_status 三态**（D9）：valid / stale / conflicting。
   - valid：有效
   - stale：陈旧（git_commit_anchor 与当前代码不匹配，D5）
   - conflicting：冲突（与其他条目冲突，conflicting_entry_ids 记录冲突对）
3. **layer 层级**（design 4.1 第 624 行）：
   - raw_trajectory：原始排查轨迹
   - negative_knowledge：负向知识（refuted 假设）
   - pattern：沉淀的修复模式（trigger_conditions / patch_template / fix_example）
   - aggregated：跨 bug 聚合知识（design 第 913 行预留，BB014；Schema 可消费）
4. 字段一一对应 design 4.1 KBEntry 表（第 619-632 行）。
"""
from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from agent.infra.db import Base, Vector


class KBValidityStatus(str, Enum):
    """KBEntry 有效性三态（design 4.1 第 629 行 / D9）。

    - valid：有效
    - stale：陈旧（代码版本漂移，D5 git_commit_anchor 不匹配）
    - conflicting：冲突（与其他条目冲突，需人工/自动仲裁）
    """

    VALID = "valid"
    STALE = "stale"
    CONFLICTING = "conflicting"


class KBLayer(str, Enum):
    """KBEntry 层级（design 4.1 第 624 行 + design 第 913 行 aggregated 预留）。

    - raw_trajectory：原始排查轨迹（BB014 写入）
    - negative_knowledge：负向知识（refuted 假设，INV-2 永久保留）
    - pattern：沉淀的修复模式（BB015 / BB013 写入）
    - aggregated：跨 bug 聚合知识（design 第 913 行预留，BB014；Schema 可消费）
    """

    RAW_TRAJECTORY = "raw_trajectory"
    NEGATIVE_KNOWLEDGE = "negative_knowledge"
    PATTERN = "pattern"
    AGGREGATED = "aggregated"


class KBEntry(Base):
    """KBEntry（知识库条目，design 4.1 第 619-632 行）。

    三层同表（layer 字段区分），retriever 按 layer 分流检索。
    pgvector 向量检索 + symptom_type 预过滤（D4 混合检索）。
    """

    __tablename__ = "kb_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True)

    # 层级（raw_trajectory / negative_knowledge / pattern / aggregated）
    layer: Mapped[str] = mapped_column(String, nullable=False)

    # 症状索引（预过滤键）
    symptom_type: Mapped[str | None] = mapped_column(String, nullable=True)

    # 根因信号向量（堆栈/代码路径关键词 embedding）
    # pgvector Vector 类型，dim 不锁死（可变长，由 embedding 模型决定）
    root_cause_signals: Mapped[list | None] = mapped_column(Vector(), nullable=True)

    # 层相关内容；pattern 层含 trigger_conditions/patch_template/fix_example
    content: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 代码版本绑定（D5 陈旧失效管理）
    git_commit_anchor: Mapped[str | None] = mapped_column(String, nullable=True)

    # 有效性三态（valid / stale / conflicting，D9）
    validity_status: Mapped[str] = mapped_column(
        String, nullable=False, default=KBValidityStatus.VALID.value
    )

    # 冲突条目（conflicting 时记录冲突对）
    conflicting_entry_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 来源：agent_auto / bb015_manual / bb013_reflection
    source: Mapped[str | None] = mapped_column(String, nullable=True)

    # 最后复核时间
    last_revalidated_at: Mapped[str | None] = mapped_column(String, nullable=True)


__all__ = ["KBEntry", "KBValidityStatus", "KBLayer"]
