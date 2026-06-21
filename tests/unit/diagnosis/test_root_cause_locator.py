"""RootCauseLocator 单元测试（R001-BB005）。

全 mock，覆盖 16 个测试场景矩阵（AC：命中信号反溯 / 多信号优先级 / 无匹配转缺口）：
- TestStackLocate：stack 命中（logcat/flutter）、缺 stack_top
- TestLogKeywordLocate：grep 命中、无 git_client、grep 无匹配
- TestVisualAnchorLocate：anchor 命中、无 anchor_library、空返回
- TestGitBlameFallback：兜底命中
- TestUnmatchedAndGap：全未命中转缺口、gap_store=None 降级、create 异常降级
- TestPriorityAndDemote：多信号短路、demote_factor 继承
- TestExceptionDegradation：git_client 异常降级

无 DB / LLM 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from agent.diagnosis.root_cause_locator import RootCauseLocator
from agent.diagnosis.hypothesis_engine import HypothesisNode
from agent.schemas.trajectory import HypothesisStatus


# ---------------------------------------------------------------------------
# 工厂辅助
# ---------------------------------------------------------------------------


def _make_locator(
    *,
    git_client=None,
    anchor_library=None,
    gap_store=None,
    repo_root: str = ".",
) -> RootCauseLocator:
    """构造 RootCauseLocator（依赖可注入 mock）。"""
    return RootCauseLocator(
        git_client=git_client,
        anchor_library=anchor_library,
        gap_store=gap_store,
        repo_root=repo_root,
    )


def _make_confirmed_hypothesis(
    *,
    demote_factor: float = 1.0,
    verifying_action: dict | None = None,
    confirming_evidence: dict | None = None,
) -> HypothesisNode:
    """构造一个 confirmed HypothesisNode（BB004 输出格式）。"""
    return HypothesisNode(
        id="hyp_test_001",
        parent_id=None,
        content="test hypothesis",
        status=HypothesisStatus.CONFIRMED,
        demote_factor=demote_factor,
        verifying_action=verifying_action,
        confirming_evidence=confirming_evidence,
    )


def _logcat_signal_with_stack(stack_top: str | None) -> dict:
    """构造 logcat Signal 行字典（pattern.stack_top 格式）。"""
    return {
        "id": "sig_logcat_1",
        "signal_type": "logcat",
        "severity": "crash",
        "pattern": {"matched": "FATAL EXCEPTION", "stack_top": stack_top},
        "source_config": {"tag": "AndroidRuntime", "message": "FATAL EXCEPTION"},
    }


def _flutter_signal_with_stack(stack_top: str | None, error_class: str | None = "StateError") -> dict:
    """构造 flutter_error Signal 行字典。"""
    return {
        "id": "sig_flutter_1",
        "signal_type": "flutter_error",
        "severity": "error",
        "pattern": {"matched": "StateError", "error_class": error_class, "stack_top": stack_top},
        "source_config": {"channel": "flutter/lib/ui", "message": "StateError: bad state"},
    }


def _visual_signal_with_vector(vec: list[float] | None) -> dict:
    """构造 visual Signal 行字典。"""
    return {
        "id": "sig_visual_1",
        "signal_type": "visual",
        "severity": "error",
        "pattern": {"matched": "blank_screen", "visual_type": "blank_screen", "visual_features": vec},
        "source_config": {"metrics": {"avg_brightness": 250.0, "variance": 10.0}},
    }


@dataclass(frozen=True)
class _MockGrepMatch:
    """模拟 GrepMatch（agent.infra.git_client.GrepMatch）。"""
    file: str
    line_no: int
    content: str


@dataclass(frozen=True)
class _MockBlameLine:
    """模拟 BlameLine（agent.infra.git_client.BlameLine）。"""
    commit: str = "abc1234"
    author: str = "tester"
    author_mail: str = "tester@example.com"
    author_time: str = "2026-06-01T00:00:00+00:00"
    summary: str = "test commit"
    line_no: int = 1
    content: str = "val x = compute()"


@dataclass
class _MockAnchor:
    """模拟 Anchor（agent.schemas.anchor.Anchor）。"""
    id: str = "anchor_1"
    page_id: str = "src/main/MainActivity.kt"
    screenshot_ref: str | None = None
    text_expectation: str | None = None
    visual_features: list | None = None
    git_commit_anchor: str | None = None


# ---------------------------------------------------------------------------
# AC-1：stack 信号命中（命中信号 -> file:line 反溯）
# ---------------------------------------------------------------------------


class TestStackLocate:
    """stack 路径（最高优先级，confidence=0.9）。"""

    def test_logcat_stack_hit(self):
        """场景 1：logcat FATAL + stack_top → located=True, file:line 正确, confidence=0.9。"""
        locator = _make_locator()
        hyp = _make_confirmed_hypothesis()
        sig = _logcat_signal_with_stack(
            "com.example.app.MainActivity.onCreate(MainActivity.java:42)"
        )
        result = locator.locate(hyp, [sig])

        assert result.located is True
        assert result.file == "MainActivity.java"
        assert result.line == 42
        assert result.function == "com.example.app.MainActivity.onCreate"
        assert result.source == "stack"
        assert result.confidence == pytest.approx(0.9)
        assert result.demote_factor == 1.0
        assert "stack[hit]" in result.reasoning

    def test_flutter_dart_stack_hit(self):
        """场景 2：flutter Dart 异常 + Dart stack → located=True。"""
        locator = _make_locator()
        hyp = _make_confirmed_hypothesis()
        sig = _flutter_signal_with_stack("#0      build (package:flutter_app/main.dart:15:5)")
        result = locator.locate(hyp, [sig])

        assert result.located is True
        assert "main.dart" in (result.file or "")
        assert result.line == 15
        assert result.function == "build"
        assert result.source == "stack"
        assert result.confidence == pytest.approx(0.9)

    def test_stack_missing_stack_top_returns_none_and_falls_through(self):
        """场景 3：stack 信号缺 stack_top → 该信号 stack 路径不命中，走下一路径。

        构造：只有 logcat 信号无 stack_top，且无 git_client/anchor_library → 全未命中。
        断言 stack 路径不命中（最终 located=False）。
        """
        locator = _make_locator()  # 无 git_client / anchor_library / gap_store
        hyp = _make_confirmed_hypothesis()
        sig = _logcat_signal_with_stack(None)
        result = locator.locate(hyp, [sig])

        assert result.located is False
        assert result.source == "unmatched"
        # reasoning 应记录 stack 路径尝试过但未命中
        assert "stack" in result.reasoning


# ---------------------------------------------------------------------------
# AC-1：log_keyword 信号命中
# ---------------------------------------------------------------------------


class TestLogKeywordLocate:
    """log_keyword 路径（confidence=0.6）。"""

    def test_log_keyword_hit_via_grep(self):
        """场景 4：mock git_client.grep 返回文件 → located=True, source=log_keyword, conf=0.6。"""
        git_client = MagicMock()
        git_client.grep.return_value = [_MockGrepMatch("src/Foo.kt", 10, "throw StateError()")]
        locator = _make_locator(git_client=git_client)
        hyp = _make_confirmed_hypothesis()
        # 无 stack_top 的 flutter 信号，有 error_class → 走 log_keyword
        sig = _flutter_signal_with_stack(stack_top=None, error_class="StateError")
        result = locator.locate(hyp, [sig])

        assert result.located is True
        assert result.file == "src/Foo.kt"
        assert result.line == 10
        assert result.source == "log_keyword"
        assert result.confidence == pytest.approx(0.6)
        assert result.snippet == "throw StateError()"
        git_client.grep.assert_called_once()

    def test_log_keyword_no_git_client_skipped(self):
        """场景 5：log_keyword 无 git_client → 跳过（返回 None 走下一路径）。"""
        locator = _make_locator()  # 无 git_client
        hyp = _make_confirmed_hypothesis()
        sig = _flutter_signal_with_stack(stack_top=None, error_class="StateError")
        result = locator.locate(hyp, [sig])

        # 无 git_client → log_keyword 跳过 → 无 anchor/gap → unmatched
        assert result.located is False
        assert result.source == "unmatched"

    def test_log_keyword_grep_no_match_returns_none(self):
        """场景 6：log_keyword grep 无匹配 → 返回 None 走下一路径。"""
        git_client = MagicMock()
        git_client.grep.return_value = []
        locator = _make_locator(git_client=git_client)
        hyp = _make_confirmed_hypothesis()
        sig = _flutter_signal_with_stack(stack_top=None, error_class="UnknownError")
        result = locator.locate(hyp, [sig])

        assert result.located is False
        assert result.source == "unmatched"
        git_client.grep.assert_called_once()


# ---------------------------------------------------------------------------
# AC-1：visual_anchor 信号命中
# ---------------------------------------------------------------------------


class TestVisualAnchorLocate:
    """visual_anchor 路径（confidence=0.7）。"""

    def test_visual_anchor_hit(self):
        """场景 7：mock anchor_library.match_by_visual_features → located=True, conf=0.7。"""
        anchor_library = MagicMock()
        anchor_library.match_by_visual_features.return_value = [
            (_MockAnchor(page_id="src/main/HomeScreen.kt"), 0.95),
        ]
        locator = _make_locator(anchor_library=anchor_library)
        hyp = _make_confirmed_hypothesis()
        sig = _visual_signal_with_vector([0.1, 0.9, 0.0])
        result = locator.locate(hyp, [sig])

        assert result.located is True
        assert result.file == "src/main/HomeScreen.kt"
        assert result.source == "visual_anchor"
        assert result.confidence == pytest.approx(0.7)
        anchor_library.match_by_visual_features.assert_called_once()

    def test_visual_anchor_no_library_skipped(self):
        """场景 8：visual_anchor 无 anchor_library → 跳过。"""
        locator = _make_locator()  # 无 anchor_library
        hyp = _make_confirmed_hypothesis()
        sig = _visual_signal_with_vector([0.1, 0.9, 0.0])
        result = locator.locate(hyp, [sig])

        assert result.located is False
        assert result.source == "unmatched"

    def test_visual_anchor_empty_result_skipped(self):
        """场景 9：anchor_library 返回空列表 → 跳过。"""
        anchor_library = MagicMock()
        anchor_library.match_by_visual_features.return_value = []
        locator = _make_locator(anchor_library=anchor_library)
        hyp = _make_confirmed_hypothesis()
        sig = _visual_signal_with_vector([0.1, 0.9, 0.0])
        result = locator.locate(hyp, [sig])

        assert result.located is False
        assert result.source == "unmatched"


# ---------------------------------------------------------------------------
# AC-3：无匹配转缺口
# ---------------------------------------------------------------------------


class TestUnmatchedAndGap:
    """全未命中 → located=False + 转缺口。"""

    def test_all_unmatched_creates_gap(self):
        """场景 10：全部未命中 → located=False + gap_store.create 被调（gap_type=reasoning）。"""
        gap_store = MagicMock()
        locator = _make_locator(gap_store=gap_store)
        hyp = _make_confirmed_hypothesis()
        sig = _logcat_signal_with_stack(None)  # 无 stack_top，无 git_client → unmatched
        result = locator.locate(hyp, [sig], symptom_type="crash")

        assert result.located is False
        assert result.source == "unmatched"
        gap_store.create.assert_called_once()
        call_args = gap_store.create.call_args[0][0]
        assert call_args["gap_type"] == "reasoning"
        assert "not locatable" in call_args["description"]
        assert call_args["linked_bug_ids"] == []

    def test_gap_store_none_degraded(self):
        """场景 11：gap_store=None 降级 → located=False 不崩。"""
        locator = _make_locator()  # 全 None
        hyp = _make_confirmed_hypothesis()
        result = locator.locate(hyp, [_logcat_signal_with_stack(None)])

        assert result.located is False
        assert result.source == "unmatched"

    def test_gap_store_create_exception_degraded(self):
        """场景 12：gap_store.create 异常降级 → warning + located=False 返回（不崩）。"""
        gap_store = MagicMock()
        gap_store.create.side_effect = RuntimeError("db down")
        locator = _make_locator(gap_store=gap_store)
        hyp = _make_confirmed_hypothesis()
        # 不应抛异常
        result = locator.locate(hyp, [_logcat_signal_with_stack(None)])

        assert result.located is False
        assert result.source == "unmatched"
        gap_store.create.assert_called_once()


# ---------------------------------------------------------------------------
# AC-2：多信号优先级
# ---------------------------------------------------------------------------


class TestPriorityAndDemote:
    """多信号优先级短路 + demote_factor 继承。"""

    def test_multi_signal_stack_short_circuits(self):
        """场景 13：同时有 stack + log_keyword 信号 → 走 stack（短路）。

        构造两个信号：signal_a 有 stack_top（stack 路径会命中），
        signal_b 有 error_class（log_keyword 路径会命中）。
        断言最终 source=stack（优先级最高，短路）。
        """
        git_client = MagicMock()
        git_client.grep.return_value = [_MockGrepMatch("src/Bar.kt", 5, "throw Exception()")]
        locator = _make_locator(git_client=git_client)
        hyp = _make_confirmed_hypothesis()

        sig_stack = _logcat_signal_with_stack("com.foo.Bar.baz(Bar.java:99)")
        sig_keyword = _flutter_signal_with_stack(stack_top=None, error_class="StateError")
        result = locator.locate(hyp, [sig_stack, sig_keyword])

        assert result.located is True
        assert result.source == "stack"
        assert result.line == 99
        # git_client.grep 不应被调用（stack 已短路）
        git_client.grep.assert_not_called()

    def test_demote_factor_inherited(self):
        """场景 14：hypothesis.demote_factor=0.5 → confidence 折半。

        stack base=0.9 × demote=0.5 = 0.45。
        """
        locator = _make_locator()
        hyp = _make_confirmed_hypothesis(demote_factor=0.5)
        sig = _logcat_signal_with_stack("com.foo.A.b(A.java:1)")
        result = locator.locate(hyp, [sig])

        assert result.located is True
        assert result.source == "stack"
        assert result.confidence == pytest.approx(0.45)
        assert result.demote_factor == 0.5


# ---------------------------------------------------------------------------
# git_blame 兜底
# ---------------------------------------------------------------------------


class TestGitBlameFallback:
    """git_blame 兜底路径（confidence=0.4）。"""

    def test_git_blame_fallback_hit(self):
        """场景 15：已知 file（hypothesis.verifying_action.file）→ mock git blame 取最近行。"""
        git_client = MagicMock()
        git_client.blame.return_value = [_MockBlameLine(line_no=7, content="val x = bug()")]
        locator = _make_locator(git_client=git_client)
        hyp = _make_confirmed_hypothesis(
            verifying_action={"file": "src/Buggy.kt", "action": "inspect"},
        )
        # 无信号的 case（空列表）→ stack/log_keyword/visual 全跳过 → 走 git_blame
        result = locator.locate(hyp, [])

        assert result.located is True
        assert result.file == "src/Buggy.kt"
        assert result.line == 7
        assert result.source == "git_blame"
        assert result.confidence == pytest.approx(0.4)
        assert result.snippet == "val x = bug()"
        git_client.blame.assert_called_once_with("src/Buggy.kt")


# ---------------------------------------------------------------------------
# 异常降级
# ---------------------------------------------------------------------------


class TestExceptionDegradation:
    """子方法抛异常 → 降级到下一策略。"""

    def test_git_client_grep_exception_falls_through(self):
        """场景 16：git_client.grep 抛异常 → log_keyword 降级 → 走下一路径。"""
        git_client = MagicMock()
        git_client.grep.side_effect = RuntimeError("git binary crashed")
        locator = _make_locator(git_client=git_client)
        hyp = _make_confirmed_hypothesis()
        sig = _flutter_signal_with_stack(stack_top=None, error_class="StateError")
        result = locator.locate(hyp, [sig])

        # grep 异常被捕获 → log_keyword 跳过 → 全未命中
        assert result.located is False
        assert result.source == "unmatched"
        # reasoning 应记录 log_keyword 异常
        assert "log_keyword" in result.reasoning
