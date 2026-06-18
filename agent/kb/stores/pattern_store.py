"""PatternStore（R001-BF005，pattern 层 + 写入权限校验）。

共表 kb_entries，强制 layer="pattern"。
写入操作（create/update/delete）需要 caller_id 在白名单中，
仅允许 ``bb015_manual_fix_recorder`` 写入。
读操作（get/list）不校验 caller_id。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from agent.kb.exceptions import KBPermissionError
from agent.schemas.kb_entry import KBEntry, KBLayer

_PATTERN_LAYER = KBLayer.PATTERN.value

#: pattern 层写入权限白名单（AC-2 / INV-3 / AP-3）
#: 仅 BB015 ManualFixRecorder 允许写入 pattern 层。
PATTERN_WRITE_ALLOWLIST: frozenset[str] = frozenset({"bb015_manual_fix_recorder"})


class PatternStore:
    """pattern 层 store（修复模式 CRUD + 写入权限校验）。

    所有写入强制 layer="pattern"（防串层）。
    写操作（create/update/delete）需要传 caller_id 且在白名单中；
    读操作（get/list）不需要 caller_id。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # 权限校验
    # ------------------------------------------------------------------
    @staticmethod
    def _check_write_permission(caller_id: str) -> None:
        """校验 caller_id 是否有 pattern 层写入权限。

        Raises:
            KBPermissionError: caller_id 不在白名单中。
        """
        if caller_id not in PATTERN_WRITE_ALLOWLIST:
            raise KBPermissionError(
                f"pattern_store write denied for caller={caller_id!r}; "
                f"allowed={sorted(PATTERN_WRITE_ALLOWLIST)}"
            )

    # ------------------------------------------------------------------
    # 写操作（需要 caller_id）
    # ------------------------------------------------------------------
    def create(self, *, caller_id: str, entry_data: dict[str, Any]) -> KBEntry:
        """写入一条 pattern 层条目。

        强制覆写 layer="pattern"（防串层）。

        Args:
            caller_id: 调用方标识，必须在 PATTERN_WRITE_ALLOWLIST 中。
            entry_data: 条目数据（layer 字段会被强制覆写为 "pattern"）。

        Raises:
            KBPermissionError: caller_id 不在白名单中。
        """
        self._check_write_permission(caller_id)
        data = {**entry_data, "layer": _PATTERN_LAYER}
        with self._session_factory() as session:
            entry = KBEntry(**data)
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry

    def update(
        self, *, caller_id: str, entry_id: str, patch: dict[str, Any]
    ) -> KBEntry | None:
        """更新一条 pattern 层条目。

        不允许通过 update 改 layer（防串层）。

        Args:
            caller_id: 调用方标识，必须在白名单中。
            entry_id: 条目 id。
            patch: 更新字段（layer 会被忽略）。

        Raises:
            KBPermissionError: caller_id 不在白名单中。
        """
        self._check_write_permission(caller_id)
        clean_patch = {k: v for k, v in patch.items() if k != "layer"}
        with self._session_factory() as session:
            entry = (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _PATTERN_LAYER,
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

    def delete(self, *, caller_id: str, entry_id: str) -> bool:
        """硬删一条 pattern 层条目。

        Args:
            caller_id: 调用方标识，必须在白名单中。
            entry_id: 条目 id。

        Raises:
            KBPermissionError: caller_id 不在白名单中。
        """
        self._check_write_permission(caller_id)
        with self._session_factory() as session:
            entry = (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _PATTERN_LAYER,
                )
                .one_or_none()
            )
            if entry is None:
                return False
            session.delete(entry)
            session.commit()
            return True

    # ------------------------------------------------------------------
    # 读操作（不需要 caller_id）
    # ------------------------------------------------------------------
    def get(self, entry_id: str) -> KBEntry | None:
        """按 id 读取一条 pattern 层条目（读权限不校验）。"""
        with self._session_factory() as session:
            return (
                session.query(KBEntry)
                .filter(
                    KBEntry.id == entry_id,
                    KBEntry.layer == _PATTERN_LAYER,
                )
                .one_or_none()
            )

    def list(
        self, *, symptom_type: str | None = None, limit: int = 100
    ) -> list[KBEntry]:
        """列出 pattern 层条目，可选按 symptom_type 过滤（读权限不校验）。"""
        with self._session_factory() as session:
            q = session.query(KBEntry).filter(KBEntry.layer == _PATTERN_LAYER)
            if symptom_type is not None:
                q = q.filter(KBEntry.symptom_type == symptom_type)
            return q.limit(limit).all()


__all__ = ["PatternStore", "PATTERN_WRITE_ALLOWLIST"]
