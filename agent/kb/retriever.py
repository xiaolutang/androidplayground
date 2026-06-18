"""KBRetriever（R001-BF005，两阶段检索 + 负向知识反查）。

两阶段检索算法（design 5.3）：
1. 阶段 1（预过滤）：symptom_type + layer 过滤候选集
2. 阶段 2（pgvector 排序）：余弦距离 <=> 排序 + staleness 降权 + degraded 判定

负向知识反查（BF005.4）：negate_hypotheses 三档判定（prune / demote / unaffected）。

纯算法函数（_apply_stale_demote / _classify_negative / _decide_degraded）
提取为模块级，便于单元测试无 DB 验证。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from agent.infra.config import (
    KB_COLD_START_N,
    KB_NEGATIVE_DEMOTE,
    KB_NEGATIVE_PRUNE,
    KB_SIMILARITY_FLOOR,
    KB_STALE_DEMOTE,
)
from agent.schemas.kb_entry import KBEntry, KBValidityStatus


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RetrievedEntry:
    """单条检索结果。

    Attributes:
        entry: 原始 KBEntry 对象。
        similarity: 已应用 staleness 降权后的最终相似度。
        raw_similarity: 原始 pgvector 余弦相似度（降权前）。
        validity_status: 条目有效性状态（valid/stale/conflicting）。
        conflicting_with: conflicting_entry_ids 原样返回（非 conflicting 条目为 None）。
    """

    entry: KBEntry
    similarity: float
    raw_similarity: float
    validity_status: str
    conflicting_with: list[str] | None


@dataclass(frozen=True)
class RetrievalResult:
    """检索结果集。

    Attributes:
        entries: 检索结果列表（按 similarity 降序）。
        degraded: 是否降级（冷启动或低相似度）。
    """

    entries: list[RetrievedEntry]
    degraded: bool


@dataclass(frozen=True)
class HypothesisInput:
    """假设输入（negate_hypotheses 用）。

    Attributes:
        hypothesis_id: 假设标识。
        root_cause_vector: 根因信号向量（调用方负责向量化）。
    """

    hypothesis_id: str
    root_cause_vector: list[float]


@dataclass(frozen=True)
class NegativeVerdict:
    """负向知识反查判定结果。

    Attributes:
        hypothesis_id: 假设标识。
        max_negative_similarity: 与 negative_knowledge 层最大相似度（无匹配时 None）。
        prune: 是否剪枝（similarity > KB_NEGATIVE_PRUNE）。
        demote_factor: 降权因子（[KB_NEGATIVE_DEMOTE, KB_NEGATIVE_PRUNE] → 0.3，其他 → 1.0）。
    """

    hypothesis_id: str
    max_negative_similarity: float | None
    prune: bool
    demote_factor: float


# ---------------------------------------------------------------------------
# 纯算法函数（单元测试直接调用，无 DB 依赖）
# ---------------------------------------------------------------------------
def _apply_stale_demote(raw_similarity: float, validity_status: str) -> float:
    """staleness 降权系数计算（AC-4）。

    validity_status == "stale" → similarity = raw * KB_STALE_DEMOTE
    其他 → similarity = raw（不变）

    Args:
        raw_similarity: 原始 pgvector 余弦相似度。
        validity_status: 条目有效性状态。

    Returns:
        降权后的相似度。
    """
    if validity_status == KBValidityStatus.STALE.value:
        return raw_similarity * KB_STALE_DEMOTE
    return raw_similarity


def _classify_negative(similarity: float | None) -> tuple[bool, float]:
    """负向知识反查三档分类（AC-8）。

    三档：
    - similarity > KB_NEGATIVE_PRUNE(0.85) → prune=True, demote_factor=1.0
    - KB_NEGATIVE_DEMOTE(0.6) <= similarity <= 0.85 → prune=False, demote_factor=0.3
    - similarity < 0.6 或 None → prune=False, demote_factor=1.0

    Args:
        similarity: 与 negative_knowledge 层的最大相似度（None 表示无匹配）。

    Returns:
        (prune, demote_factor) 元组。
    """
    if similarity is None:
        return (False, 1.0)
    if similarity > KB_NEGATIVE_PRUNE:
        return (True, 1.0)
    if similarity >= KB_NEGATIVE_DEMOTE:
        return (False, 0.3)
    return (False, 1.0)


def _decide_degraded(pool_size: int, top1_raw: float | None) -> bool:
    """冷启动降级判定（AC-7）。

    degraded = (pool_size < KB_COLD_START_N) OR (top1_raw < KB_SIMILARITY_FLOOR)

    Args:
        pool_size: 阶段 1 预过滤后的候选总数。
        top1_raw: top1 的原始相似度（降权前）；None 表示候选池为空。

    Returns:
        是否降级。
    """
    if pool_size < KB_COLD_START_N:
        return True
    if top1_raw is None:
        return True
    return top1_raw < KB_SIMILARITY_FLOOR


def _vector_to_str(vec: list[float]) -> str:
    """将 Python list 转为 pgvector 文本格式字符串。

    pgvector 文本格式：``[1,0,0]`` 或 ``[0.5,0.3,0.1]``。
    psycopg3 会把 Python list[int] 编码为 PG smallint[]，
    无法直接 cast 为 vector；用字符串绕过此限制。

    Args:
        vec: 向量列表。

    Returns:
        pgvector 文本格式字符串，如 ``"[1.0,0.0,0.0]"``。
    """
    return "[" + ",".join(str(float(v)) for v in vec) + "]"


# ---------------------------------------------------------------------------
# KBRetriever
# ---------------------------------------------------------------------------
class KBRetriever:
    """两阶段 KB 检索器 + 负向知识反查。

    两阶段算法：
    1. 预过滤：symptom_type + layer 过滤候选集
    2. pgvector 排序：余弦距离 <=> 排序 + staleness 降权 + degraded 判定
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
    ) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # 两阶段检索
    # ------------------------------------------------------------------
    def retrieve(
        self,
        *,
        query_vector: list[float],
        symptom_type: str,
        layers: list[str] | None = None,
        top_k: int = 10,
    ) -> RetrievalResult:
        """两阶段检索：symptom_type + layer 预过滤 → pgvector 余弦排序。

        Args:
            query_vector: 查询向量（根因信号）。
            symptom_type: 症状类型（预过滤键）。
            layers: 检索的层列表（None 表示所有层）。
            top_k: 返回条数上限。

        Returns:
            RetrievalResult，含降权后的 entries 和 degraded 标志。
        """
        # 阶段 1：预过滤（获取候选池大小）
        # 阶段 2：pgvector 排序
        with self._session_factory() as session:
            # 构造 layers 条件
            if layers is not None and len(layers) > 0:
                layer_placeholders = ", ".join(
                    f":layer_{i}" for i in range(len(layers))
                )
                layer_clause = f"AND layer IN ({layer_placeholders})"
                layer_params: dict[str, Any] = {
                    f"layer_{i}": v for i, v in enumerate(layers)
                }
            else:
                layer_clause = ""
                layer_params = {}

            # 阶段 1：获取候选池大小（只统计总数）
            count_sql = text(
                f"""
                SELECT count(*) FROM kb_entries
                WHERE symptom_type = :symptom_type
                {layer_clause}
                """
            )
            count_params: dict[str, Any] = {
                "symptom_type": symptom_type,
                **layer_params,
            }
            pool_size = session.execute(count_sql, count_params).scalar() or 0

            if pool_size == 0:
                # 候选池为空 → degraded=True，entries=[]
                return RetrievalResult(entries=[], degraded=True)

            # 阶段 2：pgvector 余弦距离排序
            # 距离 = 1 - 余弦相似度；相似度 = 1 - 距离
            # 用文本字符串 + ::vector 转换，绕过 psycopg3 把 list[int] 编码为
            # smallint[] 无法 cast 为 vector 的问题
            vec_str = _vector_to_str(query_vector)
            order_sql = text(
                f"""
                SELECT id,
                       1 - (root_cause_signals <=> (:query_vector)::vector) AS raw_similarity
                FROM kb_entries
                WHERE symptom_type = :symptom_type
                {layer_clause}
                ORDER BY root_cause_signals <=> (:query_vector)::vector
                LIMIT :top_k
                """
            )
            order_params: dict[str, Any] = {
                "query_vector": vec_str,
                "symptom_type": symptom_type,
                "top_k": top_k,
                **layer_params,
            }
            rank_rows = session.execute(order_sql, order_params).fetchall()

            if not rank_rows:
                return RetrievalResult(entries=[], degraded=True)

            # 用 ORM 查回完整 KBEntry 对象（在同一个 session 内）
            ranked_ids = [row._mapping["id"] for row in rank_rows]
            raw_sim_map = {
                row._mapping["id"]: float(row._mapping["raw_similarity"])
                for row in rank_rows
            }
            kb_entries = (
                session.query(KBEntry)
                .filter(KBEntry.id.in_(ranked_ids))
                .all()
            )
            # 按 raw_sim_map 中的 raw_similarity 构建 id → entry 映射
            entry_map = {e.id: e for e in kb_entries}

        # 构建 RetrievedEntry 列表
        entries: list[RetrievedEntry] = []
        for eid in ranked_ids:
            kb_entry = entry_map.get(eid)
            if kb_entry is None:
                continue
            raw_sim = raw_sim_map[eid]
            validity = kb_entry.validity_status
            sim = _apply_stale_demote(raw_sim, validity)

            # conflicting_with 填充
            conflicting_ids = kb_entry.conflicting_entry_ids
            if validity == KBValidityStatus.CONFLICTING.value:
                conflicting_with = conflicting_ids if conflicting_ids else None
            else:
                conflicting_with = None

            entries.append(
                RetrievedEntry(
                    entry=kb_entry,
                    similarity=sim,
                    raw_similarity=raw_sim,
                    validity_status=validity,
                    conflicting_with=conflicting_with,
                )
            )

        # 按 similarity 降序排列
        entries.sort(key=lambda e: e.similarity, reverse=True)

        # degraded 判定（用 raw_similarity 判定）
        top1_raw = entries[0].raw_similarity if entries else None
        degraded = _decide_degraded(pool_size, top1_raw)

        return RetrievalResult(entries=entries, degraded=degraded)

    # ------------------------------------------------------------------
    # 负向知识反查
    # ------------------------------------------------------------------
    def negate_hypotheses(
        self,
        *,
        hypothesis_vectors: list[list[float]],
        symptom_type: str,
        top_k_per_hypothesis: int = 5,
    ) -> list[NegativeVerdict]:
        """对每个候选假设，检索 negative_knowledge 层，返回三档 verdict。

        三档：
        - similarity > KB_NEGATIVE_PRUNE(0.85) → prune=True
        - [KB_NEGATIVE_DEMOTE(0.6), KB_NEGATIVE_PRUNE(0.85)] → demote_factor=0.3
        - < 0.6 或无匹配 → unaffected（demote_factor=1.0）

        Args:
            hypothesis_vectors: 候选假设向量列表。
            symptom_type: 症状类型（预过滤键）。
            top_k_per_hypothesis: 每个假设检索的 top_k（默认 5）。

        Returns:
            每个假设对应的 NegativeVerdict 列表。
        """
        verdicts: list[NegativeVerdict] = []

        for idx, vec in enumerate(hypothesis_vectors):
            # 检索 negative_knowledge 层
            vec_str = _vector_to_str(vec)
            with self._session_factory() as session:
                sql = text(
                    """
                    SELECT id,
                           1 - (root_cause_signals <=> (:query_vector)::vector) AS similarity
                    FROM kb_entries
                    WHERE symptom_type = :symptom_type
                      AND layer = 'negative_knowledge'
                    ORDER BY root_cause_signals <=> (:query_vector)::vector
                    LIMIT :top_k
                    """
                )
                params = {
                    "query_vector": vec_str,
                    "symptom_type": symptom_type,
                    "top_k": top_k_per_hypothesis,
                }
                rows = session.execute(sql, params).fetchall()

            # 取 top1 相似度（最大值）
            if rows:
                max_sim = float(rows[0]._mapping["similarity"])
            else:
                max_sim = None

            prune, demote = _classify_negative(max_sim)
            verdicts.append(
                NegativeVerdict(
                    hypothesis_id=f"hyp_{idx}",
                    max_negative_similarity=max_sim,
                    prune=prune,
                    demote_factor=demote,
                )
            )

        return verdicts


__all__ = [
    "KBRetriever",
    "RetrievedEntry",
    "RetrievalResult",
    "HypothesisInput",
    "NegativeVerdict",
    # 纯算法函数（单元测试用）
    "_apply_stale_demote",
    "_classify_negative",
    "_decide_degraded",
]
