"""TrajectoryStore（R001-BF005，raw_trajectory 层）。

共表 kb_entries，强制 layer="raw_trajectory"。
负责轨迹/假设的 CRUD，不做权限校验（权限留给后续 task 约束）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from agent.schemas.kb_entry import KBEntry, KBLayer

_TRAJECTORY_LAYER = KBLayer.RAW_TRAJECTORY.value


class TrajectoryStore:
    """raw_trajectory 层 store（轨迹/假设 CRUD）。

    所有写入强制 layer="raw_trajectory"，即使调用方传 layer="pattern"
    也被覆写，防止误写串层。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, entry_data: dict[str, Any]) -> KBEntry:
        """写入一条 raw_trajectory 层条目。

        强制覆写 layer="raw_trajectory"（防串层）。
        """
        data = {**entry_data, "layer": _TRAJECTORY_LAYER}
        with self._session_factory() as session:
            entry = KBEntry(**data)
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def get(self, entry_id: str) -> KBEntry | None:
        """按 id 读取一条 raw_trajectory 层条目。"""
        with self._session_factory() as session:
            return (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _TRAJECTORY_LAYER,
                )
                .one_or_none()
            )

    def list(
        self, *, symptom_type: str | None = None, limit: int = 100
    ) -> list[KBEntry]:
        """列出 raw_trajectory 层条目，可选按 symptom_type 过滤。"""
        with self._session_factory() as session:
            q = session.query(KBEntry).filter(KBEntry.layer == _TRAJECTORY_LAYER)
            if symptom_type is not None:
                q = q.filter(KBEntry.symptom_type == symptom_type)
            return q.limit(limit).all()

    def update(self, entry_id: str, patch: dict[str, Any]) -> KBEntry | None:
        """更新一条 raw_trajectory 层条目。

        不允许通过 update 改 layer（防串层）。
        """
        clean_patch = {k: v for k, v in patch.items() if k != "layer"}
        with self._session_factory() as session:
            entry = (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _TRAJECTORY_LAYER,
                )
                .one_or_none()
            )
            if entry is None:
                return None
            for k, v in clean_patch.items():
                setattr(entry, k, v)
            session.commit()
            session.refresh(entry)
            return entry

    def delete(self, entry_id: str) -> bool:
        """硬删一条 raw_trajectory 层条目。

        KB 软删由 validity_status 字段承担，不靠 delete 标记。
        返回是否删除成功。
        """
        with self._session_factory() as session:
            entry = (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _TRAJECTORY_LAYER,
                )
                .one_or_none()
            )
            if entry is None:
                return False
            session.delete(entry)
            session.commit()
            return True


__all__ = ["TrajectoryStore"]
