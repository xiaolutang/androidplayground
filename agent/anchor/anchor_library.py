"""AnchorLibrary（R001-BF007，锚点库能力层）。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md 4.1 Anchor 表 + D11 决策
- 任务包 R001-BF007（D11 能力先建，数据冷启动空）

设计要点（D11 决策）：
1. **能力先建**：本模块提供存储 + 检索 + Schema 能力，MVP 完整。
2. **数据冷启动为空**：无预置数据，用户自跑项目无 App 页面样本；
   到公司后录入锚点即可激活对照（不改代码即可激活数据）。
3. **BF003 降级**：空库时 ``match_by_visual_features`` 返回 ``[]``，
   BF003 据此走纯 LLM 判断；录入锚点后激活视觉对照。
   degraded 判定不在本层（本层只返回结果，BF003 自己判 degraded）。
4. **delete 是硬删**：Anchor 不在 INV-2（不可变写入）范围内，
   故不设软删字段；如有审计需求需另行引入。
   （依据：analysis INV-2 仅覆盖 kb_entries 共表的 raw_trajectory /
   negative_knowledge 写入流；anchors 表独立，不参与不可变写入契约。）

参考：
- ``agent/kb/stores/trajectory_store.py``：CRUD 骨架（session_factory 注入 +
  with session 模式）。anchors 独表，无需 layer 分流。
- ``agent/kb/retriever.py``：pgvector ``<=>`` 余弦距离 + ``_vector_to_str`` +
  ``::vector`` cast，绕过 psycopg3 把 ``list[int]`` 编码为 ``smallint[]``
  无法 cast 为 vector 的问题。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from agent.schemas.anchor import Anchor


def _vector_to_str(vec: list[float]) -> str:
    """将 Python list 转为 pgvector 文本格式字符串。

    pgvector 文本格式：``[1,0,0]`` 或 ``[0.5,0.3,0.1]``。
    psycopg3 会把 Python ``list[int]`` 编码为 PG ``smallint[]``，
    无法直接 cast 为 vector；用字符串绕过此限制。

    与 ``agent.kb.retriever._vector_to_str`` 同源实现（BF005 / BF007 共用模式）。

    Args:
        vec: 向量列表。

    Returns:
        pgvector 文本格式字符串，如 ``"[1.0,0.0,0.0]"``。
    """
    return "[" + ",".join(str(float(v)) for v in vec) + "]"


class AnchorLibrary:
    """锚点库能力层（BF007，D11 能力先建）。

    提供 Anchor CRUD + 按 page_id 检索 + visual_features 向量比对。
    数据冷启动为空（无预置数据），录入锚点后激活 BF003 视觉对照。

    注入 ``session_factory``（与 BF005 三层 store 同一模式）：
    业务层传入 ``SessionLocal``，测试可传入 Testcontainers session_factory。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def create(self, anchor_data: dict[str, Any]) -> Anchor:
        """写入一条 Anchor。

        Args:
            anchor_data: Anchor 字段字典（至少含 id；visual_features 可选）。

        Returns:
            写入后的 Anchor 对象（已 refresh）。
        """
        with self._session_factory() as session:
            anchor = Anchor(**anchor_data)
            session.add(anchor)
            session.commit()
            session.refresh(anchor)
            return anchor

    def get(self, anchor_id: str) -> Anchor | None:
        """按 id 读取一条 Anchor，不存在返回 None。"""
        with self._session_factory() as session:
            return (
                session.query(Anchor).filter(Anchor.id == anchor_id).one_or_none()
            )

    def list(
        self,
        page_id: str | None = None,
        limit: int = 100,
    ) -> list[Anchor]:
        """列出 Anchor，可选按 page_id 过滤。

        Args:
            page_id: 页面标识过滤键（None 表示不过滤，返回所有）。
            limit: 返回条数上限。

        Returns:
            Anchor 列表。
        """
        with self._session_factory() as session:
            q = session.query(Anchor)
            if page_id is not None:
                q = q.filter(Anchor.page_id == page_id)
            return q.limit(limit).all()

    def update(self, anchor_id: str, patch: dict[str, Any]) -> Anchor | None:
        """更新一条 Anchor，不存在返回 None。

        不允许通过 update 改 id（主键不可变）。
        """
        clean_patch = {k: v for k, v in patch.items() if k != "id"}
        with self._session_factory() as session:
            anchor = (
                session.query(Anchor).filter(Anchor.id == anchor_id).one_or_none()
            )
            if anchor is None:
                return None
            for k, v in clean_patch.items():
                setattr(anchor, k, v)
            session.commit()
            session.refresh(anchor)
            return anchor

    def delete(self, anchor_id: str) -> bool:
        """硬删一条 Anchor。

        Anchor 不在 INV-2（不可变写入）范围内，故硬删：
        无软删字段，删除即物理移除。如需审计需另行引入。
        返回是否删除成功（不存在返回 False）。
        """
        with self._session_factory() as session:
            anchor = (
                session.query(Anchor).filter(Anchor.id == anchor_id).one_or_none()
            )
            if anchor is None:
                return False
            session.delete(anchor)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # visual_features 向量比对（pgvector 余弦相似度排序）
    # ------------------------------------------------------------------
    def match_by_visual_features(
        self,
        query_vector: list[float],
        top_k: int = 5,
        page_id: str | None = None,
    ) -> list[tuple[Anchor, float]]:
        """按 visual_features 余弦相似度检索 Anchor。

        pgvector 余弦距离 ``<=>``：距离 = 1 - 余弦相似度；
        相似度 = 1 - 距离。结果按相似度降序。

        空库（或无 visual_features 的锚点）返回 ``[]``：
        BF003 据此走纯 LLM 判断（降级），degraded 判定不在本层。
        （D11：空库降级由 BF003 自行判定，本层只返回结果。）

        Args:
            query_vector: 查询视觉特征向量。
            top_k: 返回条数上限。
            page_id: 可选 page_id 过滤（限定在某个页面内对照）。

        Returns:
            ``(Anchor, similarity)`` 元组列表，按 similarity 降序；
            空库或无匹配返回 ``[]``。
        """
        vec_str = _vector_to_str(query_vector)
        with self._session_factory() as session:
            page_clause = "AND page_id = :page_id" if page_id is not None else ""
            sql = text(
                f"""
                SELECT id,
                       1 - (visual_features <=> (:query_vector)::vector) AS similarity
                FROM anchors
                WHERE visual_features IS NOT NULL
                {page_clause}
                ORDER BY visual_features <=> (:query_vector)::vector
                LIMIT :top_k
                """
            )
            params: dict[str, Any] = {
                "query_vector": vec_str,
                "top_k": top_k,
            }
            if page_id is not None:
                params["page_id"] = page_id
            rows = session.execute(sql, params).fetchall()

            if not rows:
                return []

            ranked_ids = [row._mapping["id"] for row in rows]
            sim_map = {
                row._mapping["id"]: float(row._mapping["similarity"])
                for row in rows
            }
            anchors = (
                session.query(Anchor).filter(Anchor.id.in_(ranked_ids)).all()
            )
            anchor_map = {a.id: a for a in anchors}

        # 按 sim_map 的 similarity 降序构建结果
        results: list[tuple[Anchor, float]] = []
        for aid in ranked_ids:
            anchor = anchor_map.get(aid)
            if anchor is None:
                continue
            results.append((anchor, sim_map[aid]))
        return results

    # ------------------------------------------------------------------
    # BF003 降级判定辅助
    # ------------------------------------------------------------------
    def is_empty(self) -> bool:
        """锚点库是否为空（BF003 降级判定用）。

        D11：空库时 BF003 走纯 LLM 判断（无锚点对照）。
        本方法仅判断总数是否为 0，不判断 visual_features 是否就绪
        （后者由 ``match_by_visual_features`` 返回 ``[]`` 体现）。

        Returns:
            库中无任何 Anchor 返回 True，否则 False。
        """
        with self._session_factory() as session:
            count = session.query(Anchor).count()
            return count == 0


__all__ = ["AnchorLibrary"]
