"""StalenessChecker（R001-BF005，陈旧检测 + 降权标记）。

检测 kb_entries 的 git_commit_anchor 与当前 HEAD 的差异：
- 注入式 commit_distance_fn：返回 commit 间距离（int）；None 表示无法判定。
- 距离 > threshold → 差异判定为"漂移"。
- revalidate_fn 钩子（可选）：漂移后调用，返回 True 则保持原状，False 标 stale。
- 不删数据，只 update validity_status='stale'（保留审计）。

祖先链归属判定（注入式，不依赖 git 子进程）：
- distance_fn(anchor, head) 返回 0 或小值 → fresh
- distance_fn 返回 > threshold → stale
- distance_fn 返回 None → 无法判定 → fresh（保守不标）
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy.orm import Session, sessionmaker

from agent.schemas.kb_entry import KBEntry, KBValidityStatus

#: commit 距离函数类型：返回两 commit 间距离（int），None 表示无法判定。
CommitDistanceFn = Callable[[str, str], Optional[int]]

#: revalidate 函数类型：传入 entry_id，返回 True（内容仍有效）或 False（标 stale）。
RevalidateFn = Callable[[str], bool]


class StalenessChecker:
    """KB 条目陈旧检测器。

    通过注入的 commit_distance_fn 判定 git_commit_anchor 与当前 HEAD 的差异，
    差异超过阈值时标记 validity_status='stale'（不删数据）。

    可选注入 revalidate_fn：差异判定为漂移后调用，返回 True 则不标 stale。
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        commit_distance_fn: CommitDistanceFn,
        staleness_distance_threshold: int = 100,
        revalidate_fn: RevalidateFn | None = None,
    ) -> None:
        """初始化 StalenessChecker。

        Args:
            session_factory: SQLAlchemy session 工厂。
            commit_distance_fn: commit 距离函数 (anchor, head) → int | None。
            staleness_distance_threshold: 距离阈值，超过则判定为漂移（默认 100）。
            revalidate_fn: 可选 revalidate 钩子，返回 False 则最终标 stale。
        """
        self._session_factory = session_factory
        self._commit_distance_fn = commit_distance_fn
        self._threshold = staleness_distance_threshold
        self._revalidate_fn = revalidate_fn

    def check_and_mark(self, *, head_commit: str) -> list[str]:
        """扫描 kb_entries，对陈旧条目标记 validity_status='stale'。

        判定逻辑：
        1. git_commit_anchor 为 None → 不标 stale（无 anchor 无法判定）
        2. commit_distance_fn(anchor, head) 返回 None → 不标 stale（无法判定）
        3. distance > threshold → 差异判定为"漂移"
           - 若 revalidate_fn 存在且返回 True → 不标 stale（内容仍有效）
           - 否则 → 标 stale
        4. distance <= threshold → 不标 stale（fresh）

        标 stale 操作：update validity_status='stale', last_revalidated_at=now()
        不删 root_cause_signals / content（保留审计）。

        Args:
            head_commit: 当前 HEAD commit hash。

        Returns:
            被标记为 stale 的 entry_id 列表。
        """
        stale_ids: list[str] = []

        with self._session_factory() as session:
            # 查所有有条目（不限于特定 layer）
            entries = session.query(KBEntry).all()

            for entry in entries:
                # git_commit_anchor 为 None → 不标 stale
                anchor = entry.git_commit_anchor
                if anchor is None:
                    continue

                # 已经是 stale 的跳过（幂等）
                if entry.validity_status == KBValidityStatus.STALE.value:
                    continue

                # 计算距离
                distance = self._commit_distance_fn(anchor, head_commit)

                # None → 无法判定 → 不标 stale（保守不标）
                if distance is None:
                    continue

                # 距离 <= 阈值 → fresh
                if distance <= self._threshold:
                    continue

                # 差异判定为"漂移" → 调 revalidate_fn（若有）
                if self._revalidate_fn is not None:
                    if self._revalidate_fn(entry.id):
                        # revalidate 通过 → 不标 stale
                        continue

                # 标 stale
                entry.validity_status = KBValidityStatus.STALE.value
                entry.last_revalidated_at = datetime.now(timezone.utc).isoformat()
                stale_ids.append(entry.id)

            session.commit()

        return stale_ids


__all__ = ["StalenessChecker", "CommitDistanceFn", "RevalidateFn"]
