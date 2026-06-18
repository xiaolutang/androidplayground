"""KB 存储包（R001-BF005）。

三层 KB 存储（共表 kb_entries，按 layer 字段区分）：
- TrajectoryStore（raw_trajectory 层）
- NegativeKnowledgeStore（negative_knowledge 层）
- PatternStore（pattern 层，含写入权限校验）

KBRetriever：两阶段检索 + 负向知识反查。
StalenessChecker：陈旧检测 + 降权标记。
"""
from __future__ import annotations

from agent.kb.exceptions import KBPermissionError
from agent.kb.retriever import (
    HypothesisInput,
    KBRetriever,
    NegativeVerdict,
    RetrievalResult,
    RetrievedEntry,
)
from agent.kb.staleness_checker import StalenessChecker
from agent.kb.stores.negative_knowledge_store import NegativeKnowledgeStore
from agent.kb.stores.pattern_store import PatternStore
from agent.kb.stores.trajectory_store import TrajectoryStore

__all__ = [
    "KBPermissionError",
    "KBRetriever",
    "RetrievedEntry",
    "RetrievalResult",
    "HypothesisInput",
    "NegativeVerdict",
    "StalenessChecker",
    "TrajectoryStore",
    "NegativeKnowledgeStore",
    "PatternStore",
]
