"""StalenessChecker 单元测试（R001-BF005，无真实 DB，用 mock session）。

覆盖：
1. 祖先链归属判定（distance_fn 返回小/大/None）
2. revalidate_fn 返回 True/False 时的 stale 标记
3. git_commit_anchor 为 None 不标 stale
4. 已是 stale 的条目幂等跳过

注意：用 SimpleNamespace 替代 ORM KBEntry，避免 SQLAlchemy mapped attribute
在 detached 状态下无法赋值的问题。StalenessChecker 只读写 id / git_commit_anchor /
validity_status / last_revalidated_at 属性，SimpleNamespace 足以覆盖。
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Optional

from agent.kb.staleness_checker import StalenessChecker
from agent.schemas.kb_entry import KBValidityStatus


def _make_entry(
    *,
    eid: str = "e1",
    git_commit_anchor: str | None = "abc123",
    validity_status: str = KBValidityStatus.VALID.value,
    layer: str = "pattern",
) -> SimpleNamespace:
    """构建一个测试用 entry mock（SimpleNamespace，模拟 KBEntry 的属性）。"""
    return SimpleNamespace(
        id=eid,
        layer=layer,
        symptom_type="crash",
        root_cause_signals=[1.0, 0.0, 0.0],
        content={},
        git_commit_anchor=git_commit_anchor,
        validity_status=validity_status,
        conflicting_entry_ids=None,
        source="test",
        last_revalidated_at=None,
    )


def _make_mock_session(entries: list) -> MagicMock:
    """构建 mock session，query 返回指定 entries 列表。"""
    session = MagicMock()
    query_mock = MagicMock()
    query_mock.all.return_value = entries
    session.query.return_value = query_mock
    return session


def _make_mock_session_factory(session: MagicMock):
    """构建 mock session_factory（context manager）。"""
    factory = MagicMock()
    factory.return_value.__enter__ = MagicMock(return_value=session)
    factory.return_value.__exit__ = MagicMock(return_value=False)
    return factory


class TestStalenessCheckerDistance:
    """祖先链归属判定（distance_fn 返回值不同场景）。"""

    def test_small_distance_not_stale(self) -> None:
        """distance_fn 返回 5（< threshold=100）→ 不标 stale。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 5,
            staleness_distance_threshold=100,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []
        assert entry.validity_status == KBValidityStatus.VALID.value

    def test_large_distance_stale(self) -> None:
        """distance_fn 返回 200（> threshold=100）→ 标 stale。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 200,
            staleness_distance_threshold=100,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == ["e1"]
        assert entry.validity_status == KBValidityStatus.STALE.value
        assert entry.last_revalidated_at is not None

    def test_none_distance_not_stale(self) -> None:
        """distance_fn 返回 None（无法判定）→ 不标 stale。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: None,
            staleness_distance_threshold=100,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []
        assert entry.validity_status == KBValidityStatus.VALID.value

    def test_distance_at_threshold_not_stale(self) -> None:
        """distance == threshold（100）→ 不标 stale（<= 不算漂移）。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 100,
            staleness_distance_threshold=100,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []


class TestStalenessCheckerNoAnchor:
    """git_commit_anchor 为 None 的条目不标 stale。"""

    def test_null_anchor_not_stale(self) -> None:
        """git_commit_anchor=None → 不标 stale（无 anchor 无法判定）。"""
        entry = _make_entry(eid="e1", git_commit_anchor=None)
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 999,  # 即使大也不标
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []
        assert entry.validity_status == KBValidityStatus.VALID.value


class TestStalenessCheckerRevalidate:
    """revalidate_fn 钩子测试。"""

    def test_revalidate_true_not_stale(self) -> None:
        """revalidate_fn 返回 True → 即使差异判定为漂移，也不标 stale。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 200,
            staleness_distance_threshold=100,
            revalidate_fn=lambda eid: True,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []
        assert entry.validity_status == KBValidityStatus.VALID.value

    def test_revalidate_false_stale(self) -> None:
        """revalidate_fn 返回 False → 标 stale。"""
        entry = _make_entry(eid="e1", git_commit_anchor="abc123")
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 200,
            staleness_distance_threshold=100,
            revalidate_fn=lambda eid: False,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == ["e1"]
        assert entry.validity_status == KBValidityStatus.STALE.value


class TestStalenessCheckerIdempotent:
    """已是 stale 的条目幂等跳过。"""

    def test_already_stale_skipped(self) -> None:
        """validity_status 已是 stale → 跳过（不重复处理）。"""
        entry = _make_entry(
            eid="e1",
            git_commit_anchor="abc123",
            validity_status=KBValidityStatus.STALE.value,
        )
        session = _make_mock_session([entry])
        factory = _make_mock_session_factory(session)

        checker = StalenessChecker(
            factory,
            commit_distance_fn=lambda a, b: 200,
        )
        stale_ids = checker.check_and_mark(head_commit="def456")

        assert stale_ids == []


class TestStalenessCheckerMixed:
    """混合场景：多个条目，部分标 stale。"""

    def test_mixed_entries(self) -> None:
        """三个条目：一个 fresh、一个 stale（大距离）、一个 null anchor → 只标第二个。"""
        e1 = _make_entry(eid="e1", git_commit_anchor="fresh_commit")
        e2 = _make_entry(eid="e2", git_commit_anchor="old_commit")
        e3 = _make_entry(eid="e3", git_commit_anchor=None)

        session = _make_mock_session([e1, e2, e3])
        factory = _make_mock_session_factory(session)

        def distance_fn(anchor: str, head: str) -> Optional[int]:
            if anchor == "fresh_commit":
                return 5
            if anchor == "old_commit":
                return 200
            return None

        checker = StalenessChecker(
            factory,
            commit_distance_fn=distance_fn,
            staleness_distance_threshold=100,
        )
        stale_ids = checker.check_and_mark(head_commit="head123")

        assert stale_ids == ["e2"]
        assert e1.validity_status == KBValidityStatus.VALID.value
        assert e2.validity_status == KBValidityStatus.STALE.value
        assert e3.validity_status == KBValidityStatus.VALID.value
