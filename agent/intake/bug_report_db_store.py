"""DB-backed BugReport 仓储（R001 真实端到端集成补齐）。

实现 report_router `_Deps.bug_report_repo` 期望的 duck typing 接口：
- get(report_id) → BugReport | None
- list(page, page_size, status, tier) → (list, total)
- save_status(report_id, new_status) → None

之前 main.py 模块级 create_app() 不注入此 repo，导致 /reports 永远空。
本模块补齐 DB 装配，使 /reports /reports/{id} regression-feedback 真实连 DB。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session, sessionmaker

from agent.schemas.bug_report import BugReport, BugReportStatus


class BugReportDbRepository:
    """BugReport DB 仓储（duck typing 兼容 report_router._Deps）。

    所有读写经 session_factory 开启事务，commit + expire_on_commit=False。
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, report_id: str) -> Optional[BugReport]:
        """按主键查询 BugReport。"""
        with self._session_factory() as session:
            return session.get(BugReport, report_id)

    def list(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        tier: Optional[int] = None,
    ) -> tuple[list[BugReport], int]:
        """分页 + 过滤查询，返回 (items, total)。"""
        with self._session_factory() as session:
            q = session.query(BugReport)
            if status is not None:
                q = q.filter(BugReport.status == status)
            if tier is not None:
                q = q.filter(BugReport.tier == tier)
            total = q.count()
            items = (
                q.offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            # detach 让对象在 session 关闭后仍可访问属性
            for item in items:
                session.expunge(item)
            return items, total

    def save_status(self, report_id: str, new_status: str) -> None:
        """更新 status 字段（regression-feedback 等场景使用）。

        不校验状态迁移合法性（由上层状态机保证）。
        """
        # 校验是合法的 BugReportStatus 值
        try:
            BugReportStatus(new_status)
        except ValueError as exc:
            raise ValueError(f"Invalid BugReportStatus: {new_status}") from exc

        with self._session_factory() as session:
            report = session.get(BugReport, report_id)
            if report is None:
                return
            report.status = new_status
            session.commit()

    def create(self, bug_report: BugReport) -> BugReport:
        """新建 BugReport（webhook 持久化路径使用）。

        id 由调用方提供（webhook 已生成），不存在则视为新建。
        """
        with self._session_factory() as session:
            session.add(bug_report)
            session.commit()
            session.refresh(bug_report)
            return bug_report

    def exists_by_external_id(self, source_platform: str, external_id: str) -> bool:
        """BF001 Protocol 契约：幂等查询。"""
        with self._session_factory() as session:
            return (
                session.query(BugReport)
                .filter(
                    BugReport.source_platform == source_platform,
                    BugReport.external_id == external_id,
                )
                .first()
                is not None
            )


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    """兼容 dict / dataclass / ORM 的属性取值（防 utils 循环导入）。"""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
