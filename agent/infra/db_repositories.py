"""DB-backed MetricPoint 仓储（R001 真实端到端集成补齐）。

实现 report_router `_Deps.metric_point_repo` 期望的 duck typing 接口：
- create(**kwargs) → MetricPoint

之前 main.py 不注入此 repo，导致 regression-feedback 返回 metric_point_id
但实际未写 DB（隐藏 bug，由真实集成测试 test_regression_feedback_writes_db 暴露）。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from agent.schemas.metric_point import MetricPoint


class MetricPointDbRepository:
    """MetricPoint DB 仓储（duck typing 兼容 report_router._Deps）。

    create() 接受任意字段，过滤出 MetricPoint 已知列写入。
    """

    # MetricPoint 表的有效字段（schema 定义）
    _ALLOWED_FIELDS = frozenset({
        "id",
        "bug_report_id",
        "trajectory_id",
        "metric_type",
        "value",
        "tier_at_time",
        "period",
        "bucket_dim",
        "bucket_value",
        "previous_tier",
    })

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, **kwargs: Any) -> MetricPoint:
        """新建 MetricPoint，过滤未知字段后写入 DB。

        Args:
            **kwargs: MetricPoint 字段（id / bug_report_id / metric_type / value 等）。

        Returns:
            创建后的 MetricPoint（已 commit + refresh）。
        """
        filtered = {k: v for k, v in kwargs.items() if k in self._ALLOWED_FIELDS}
        with self._session_factory() as session:
            mp = MetricPoint(**filtered)
            session.add(mp)
            session.commit()
            session.refresh(mp)
            return mp
