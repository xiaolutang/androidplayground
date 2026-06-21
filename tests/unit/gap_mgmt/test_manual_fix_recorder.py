"""ManualFixRecorder 单元测试（R001-BB015）。

覆盖人工修复录入器的 20+ 场景：

1. 正常录入全流程（capture patch → validate → dedup → write pattern）
2. patch 抓取正常（unified diff 格式正确）
3. patch 抓取 diff_range（base_sha + head_sha 区间）
4. patch 抓取 git_client=None（抛 RuntimeError）
5. patch 抓取 git_client.diff 异常（抛 PatchCaptureError）
6. 校验 root_cause 缺失（抛 ValueError）
7. 校验 trigger_conditions 缺失（抛 ValueError）
8. 校验 patch_content 为空（抛 ValueError）
9. 校验 source_bug_id 缺失（抛 ValueError）
10. 校验全部通过（无异常）
11. 去重——已有相同 patch（skipped=True）
12. 去重——无重复（正常写入）
13. 去重——KBRetriever 查询异常（降级 + 继续写入）
14. pattern 写入——kb_retriever=None（抛 RuntimeError）
15. pattern 写入——add_pattern 异常（抛 PatternWriteError）
16. INV-3 守护——available_operations 返回 ["add_pattern"]
17. INV-3 守护——不调用 add_negative_knowledge / add_raw_trajectory
18. ManualFixResult asdict 序列化
19. IngestResult 结构正确性
20. source_bug_id=None 校验
21. root_cause="" 校验（空字符串）
22. trigger_conditions=None 校验

使用 FakeGitClient / FakeKBRetriever（in-memory）避免真实 git / DB 依赖。
"""
from __future__ import annotations

import ast
import inspect
from dataclasses import asdict
from typing import Any

import pytest

from agent.gap_mgmt.manual_fix_recorder import (
    IngestResult,
    ManualFixRecorder,
    ManualFixResult,
    PatchCaptureError,
    PatternWriteError,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------
_SAMPLE_PATCH = """\
diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -10,5 +10,7 @@ def bar():
     x = 1
-    return x.size()
+    if x is None:
+        return 0
+    return len(x)
"""


class FakeGitClient:
    """in-memory git_client 双。"""

    def __init__(
        self,
        *,
        diff_result: str = _SAMPLE_PATCH,
        diff_range_result: str | None = None,
        diff_failure: Exception | None = None,
        diff_range_failure: Exception | None = None,
    ) -> None:
        self.diff_result = diff_result
        self.diff_range_result = (
            diff_range_result if diff_range_result is not None else diff_result
        )
        self.diff_failure = diff_failure
        self.diff_range_failure = diff_range_failure
        self.diff_calls: list[str] = []
        self.diff_range_calls: list[tuple[str, str]] = []

    def diff(self, sha: str) -> str:
        self.diff_calls.append(sha)
        if self.diff_failure is not None:
            raise self.diff_failure
        return self.diff_result

    def diff_range(self, base: str, head: str) -> str:
        self.diff_range_calls.append((base, head))
        if self.diff_range_failure is not None:
            raise self.diff_range_failure
        return self.diff_range_result


class FakeKBRetriever:
    """in-memory KBRetriever 双。"""

    def __init__(
        self,
        *,
        add_pattern_result: str = "pattern-001",
        add_pattern_failure: Exception | None = None,
        existing_patch: str | None = None,
        find_failure: Exception | None = None,
    ) -> None:
        self.add_pattern_result = add_pattern_result
        self.add_pattern_failure = add_pattern_failure
        self._existing_patch = existing_patch
        self.find_failure = find_failure
        self.add_pattern_calls: list[dict[str, Any]] = []
        self.find_calls: list[str] = []

    def add_pattern(self, **kwargs: Any) -> str:
        self.add_pattern_calls.append(kwargs)
        if self.add_pattern_failure is not None:
            raise self.add_pattern_failure
        return self.add_pattern_result

    def find_pattern_by_patch(self, patch_content: str) -> Any:
        self.find_calls.append(patch_content)
        if self.find_failure is not None:
            raise self.find_failure
        if self._existing_patch is None:
            return None
        return self._existing_patch == patch_content


# ---------------------------------------------------------------------------
# AC-1：抓取人修 commit patch
# ---------------------------------------------------------------------------
class TestCaptureFixPatch:
    def test_capture_single_commit_returns_unified_diff(self) -> None:
        git = FakeGitClient(diff_result=_SAMPLE_PATCH)
        recorder = ManualFixRecorder(git_client=git, kb_retriever=FakeKBRetriever())
        patch = recorder.capture_fix_patch(commit_sha="abc123")

        assert patch == _SAMPLE_PATCH
        assert git.diff_calls == ["abc123"]
        # unified diff 关键标记
        assert "--- a/" in patch and "+++ b/" in patch and "@@" in patch

    def test_capture_diff_range_uses_diff_range(self) -> None:
        git = FakeGitClient()
        recorder = ManualFixRecorder(git_client=git, kb_retriever=FakeKBRetriever())
        patch = recorder.capture_fix_patch(commit_sha="head123", base_sha="base456")

        assert git.diff_range_calls == [("base456", "head123")]
        assert git.diff_calls == []
        assert patch == _SAMPLE_PATCH

    def test_capture_raises_runtime_error_when_git_client_is_none(self) -> None:
        recorder = ManualFixRecorder(git_client=None, kb_retriever=FakeKBRetriever())
        with pytest.raises(RuntimeError, match="git_client not configured"):
            recorder.capture_fix_patch(commit_sha="abc123")

    def test_capture_wraps_git_exception_as_patch_capture_error(self) -> None:
        git = FakeGitClient(diff_failure=ValueError("commit not found"))
        recorder = ManualFixRecorder(git_client=git, kb_retriever=FakeKBRetriever())
        with pytest.raises(PatchCaptureError, match="capture_fix_patch failed"):
            recorder.capture_fix_patch(commit_sha="abc123")


# ---------------------------------------------------------------------------
# AC-2 / AC-6：引导填元数据 + 校验
# ---------------------------------------------------------------------------
class TestCollectMetadata:
    def test_collect_metadata_returns_validated_record(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        record = recorder.collect_metadata(
            patch_content=_SAMPLE_PATCH,
            root_cause="null deref",
            trigger_conditions="empty input",
            source_bug_id="bug-1",
            symptom_type="null_pointer",
        )
        assert record.patch_content == _SAMPLE_PATCH
        assert record.root_cause == "null deref"
        assert record.trigger_conditions == "empty input"
        assert record.source_bug_id == "bug-1"
        assert record.symptom_type == "null_pointer"

    def test_collect_metadata_symptom_type_optional(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        record = recorder.collect_metadata(
            patch_content=_SAMPLE_PATCH,
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
        )
        assert record.symptom_type is None

    def test_validate_raises_when_root_cause_empty_string(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="root_cause is required"):
            recorder.collect_metadata(
                patch_content=_SAMPLE_PATCH,
                root_cause="",
                trigger_conditions="t",
                source_bug_id="bug-1",
            )

    def test_validate_raises_when_root_cause_none(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="root_cause is required"):
            recorder._validate_input(
                ManualFixResult(
                    patch_content=_SAMPLE_PATCH,
                    root_cause=None,  # type: ignore[arg-type]
                    trigger_conditions="t",
                    source_bug_id="bug-1",
                )
            )

    def test_validate_raises_when_trigger_conditions_empty(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="trigger_conditions is required"):
            recorder.collect_metadata(
                patch_content=_SAMPLE_PATCH,
                root_cause="r",
                trigger_conditions="",
                source_bug_id="bug-1",
            )

    def test_validate_raises_when_trigger_conditions_none(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="trigger_conditions is required"):
            recorder._validate_input(
                ManualFixResult(
                    patch_content=_SAMPLE_PATCH,
                    root_cause="r",
                    trigger_conditions=None,  # type: ignore[arg-type]
                    source_bug_id="bug-1",
                )
            )

    def test_validate_raises_when_patch_content_empty(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="patch_content is empty"):
            recorder.collect_metadata(
                patch_content="",
                root_cause="r",
                trigger_conditions="t",
                source_bug_id="bug-1",
            )

    def test_validate_raises_when_patch_content_none(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="patch_content is empty"):
            recorder._validate_input(
                ManualFixResult(
                    patch_content=None,  # type: ignore[arg-type]
                    root_cause="r",
                    trigger_conditions="t",
                    source_bug_id="bug-1",
                )
            )

    def test_validate_raises_when_source_bug_id_empty(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="source_bug_id is required"):
            recorder.collect_metadata(
                patch_content=_SAMPLE_PATCH,
                root_cause="r",
                trigger_conditions="t",
                source_bug_id="",
            )

    def test_validate_raises_when_source_bug_id_none(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        with pytest.raises(ValueError, match="source_bug_id is required"):
            recorder._validate_input(
                ManualFixResult(
                    patch_content=_SAMPLE_PATCH,
                    root_cause="r",
                    trigger_conditions="t",
                    source_bug_id=None,  # type: ignore[arg-type]
                )
            )

    def test_validate_passes_when_all_required_fields_present(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        record = ManualFixResult(
            patch_content=_SAMPLE_PATCH,
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
        )
        # 不抛异常即通过
        recorder._validate_input(record)


# ---------------------------------------------------------------------------
# AC-3 / AC-7：去重检查
# ---------------------------------------------------------------------------
class TestCheckDuplicate:
    def test_check_duplicate_returns_true_when_patch_exists(self) -> None:
        kb = FakeKBRetriever(existing_patch=_SAMPLE_PATCH)
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=kb)
        assert recorder._check_duplicate(_SAMPLE_PATCH) is True

    def test_check_duplicate_returns_false_when_patch_absent(self) -> None:
        kb = FakeKBRetriever(existing_patch="different")
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=kb)
        assert recorder._check_duplicate(_SAMPLE_PATCH) is False

    def test_check_duplicate_degrades_on_query_exception(self) -> None:
        kb = FakeKBRetriever(find_failure=RuntimeError("kb unavailable"))
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=kb)
        # 查询异常 → 降级返回 False（不阻断）
        assert recorder._check_duplicate(_SAMPLE_PATCH) is False

    def test_check_duplicate_returns_false_when_kb_retriever_none(self) -> None:
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=None)
        assert recorder._check_duplicate(_SAMPLE_PATCH) is False


# ---------------------------------------------------------------------------
# AC-3：写 KBEntry(pattern)
# ---------------------------------------------------------------------------
class TestWritePattern:
    def test_write_pattern_calls_add_pattern_with_full_record(self) -> None:
        kb = FakeKBRetriever(add_pattern_result="pat-xyz")
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=kb)
        record = ManualFixResult(
            patch_content=_SAMPLE_PATCH,
            root_cause="null deref",
            trigger_conditions="empty input",
            source_bug_id="bug-1",
            symptom_type="null_pointer",
        )
        pattern_id = recorder._write_pattern(record)

        assert pattern_id == "pat-xyz"
        assert kb.add_pattern_calls == [
            {
                "patch_content": _SAMPLE_PATCH,
                "root_cause": "null deref",
                "trigger_conditions": "empty input",
                "symptom_type": "null_pointer",
                "source_bug_id": "bug-1",
            }
        ]

    def test_write_pattern_raises_runtime_error_when_kb_retriever_none(self) -> None:
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=None)
        record = ManualFixResult(
            patch_content=_SAMPLE_PATCH,
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
        )
        with pytest.raises(RuntimeError, match="kb_retriever not configured"):
            recorder._write_pattern(record)

    def test_write_pattern_wraps_exception_as_pattern_write_error(self) -> None:
        kb = FakeKBRetriever(add_pattern_failure=RuntimeError("db down"))
        recorder = ManualFixRecorder(git_client=FakeGitClient(), kb_retriever=kb)
        record = ManualFixResult(
            patch_content=_SAMPLE_PATCH,
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
        )
        with pytest.raises(PatternWriteError, match="add_pattern failed") as exc_info:
            recorder._write_pattern(record)
        # 错误消息含 record 内容（便于排障）
        assert "source_bug_id=bug-1" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 端到端 ingest 流程
# ---------------------------------------------------------------------------
class TestIngestFlow:
    def test_ingest_happy_path(self) -> None:
        git = FakeGitClient()
        kb = FakeKBRetriever(add_pattern_result="pat-1", existing_patch=None)
        recorder = ManualFixRecorder(git_client=git, kb_retriever=kb)

        result = recorder.ingest(
            commit_sha="abc",
            root_cause="null",
            trigger_conditions="empty",
            source_bug_id="bug-1",
            symptom_type="null_pointer",
        )

        assert result.success is True
        assert result.skipped is False
        assert result.pattern_id == "pat-1"
        assert result.reason is None
        assert result.record is not None
        assert result.record.root_cause == "null"
        # add_pattern 被调一次
        assert len(kb.add_pattern_calls) == 1
        # 去重查询被调一次
        assert len(kb.find_calls) == 1

    def test_ingest_skips_on_duplicate(self) -> None:
        git = FakeGitClient()
        kb = FakeKBRetriever(existing_patch=_SAMPLE_PATCH)
        recorder = ManualFixRecorder(git_client=git, kb_retriever=kb)

        result = recorder.ingest(
            commit_sha="abc",
            root_cause="null",
            trigger_conditions="empty",
            source_bug_id="bug-1",
        )

        assert result.success is False
        assert result.skipped is True
        assert result.reason == "duplicate_pattern"
        assert result.pattern_id is None
        # 重复时不应调 add_pattern
        assert kb.add_pattern_calls == []

    def test_ingest_propagates_validation_error(self) -> None:
        git = FakeGitClient()
        kb = FakeKBRetriever()
        recorder = ManualFixRecorder(git_client=git, kb_retriever=kb)

        with pytest.raises(ValueError, match="root_cause is required"):
            recorder.ingest(
                commit_sha="abc",
                root_cause="",
                trigger_conditions="empty",
                source_bug_id="bug-1",
            )

    def test_ingest_with_base_sha_uses_diff_range(self) -> None:
        git = FakeGitClient()
        kb = FakeKBRetriever()
        recorder = ManualFixRecorder(git_client=git, kb_retriever=kb)

        recorder.ingest(
            commit_sha="head",
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
            base_sha="base",
        )
        assert git.diff_range_calls == [("base", "head")]
        assert git.diff_calls == []


# ---------------------------------------------------------------------------
# AC-4 / AP-3：INV-3 守护（唯一 pattern 写入入口）
# ---------------------------------------------------------------------------
def _count_method_calls(class_node: ast.ClassDef, method_name: str) -> int:
    """AST 统计类内对某方法的实际调用次数（忽略注释/docstring/字符串字面量）。"""
    count = 0
    for node in ast.walk(class_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == method_name:
                count += 1
    return count


class TestINV3Guard:
    def test_available_operations_returns_only_add_pattern(self) -> None:
        recorder = ManualFixRecorder(
            git_client=FakeGitClient(), kb_retriever=FakeKBRetriever()
        )
        assert recorder.available_operations == ["add_pattern"]

    def test_source_file_does_not_call_add_negative_knowledge(self) -> None:
        source = inspect.getsource(ManualFixRecorder)
        tree = ast.parse(source)
        class_node = next(
            n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        )
        assert _count_method_calls(class_node, "add_negative_knowledge") == 0, (
            "INV-3 violation: ManualFixRecorder must not call add_negative_knowledge"
        )

    def test_source_file_does_not_call_add_raw_trajectory(self) -> None:
        source = inspect.getsource(ManualFixRecorder)
        tree = ast.parse(source)
        class_node = next(
            n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        )
        assert _count_method_calls(class_node, "add_raw_trajectory") == 0, (
            "INV-3 violation: ManualFixRecorder must not call add_raw_trajectory"
        )

    def test_write_pattern_is_the_only_add_pattern_call_site(self) -> None:
        # AST 统计：ManualFixRecorder 类内 add_pattern 调用恰好 1 次
        # （在 _write_pattern 内调 kb_retriever.add_pattern；忽略注释/docstring）
        source = inspect.getsource(ManualFixRecorder)
        tree = ast.parse(source)
        class_node = next(
            n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)
        )
        assert _count_method_calls(class_node, "add_pattern") == 1


# ---------------------------------------------------------------------------
# AC-5 / AC-8：dataclass 序列化 + 结构
# ---------------------------------------------------------------------------
class TestDataclasses:
    def test_manual_fix_result_asdict_roundtrip(self) -> None:
        record = ManualFixResult(
            patch_content=_SAMPLE_PATCH,
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="bug-1",
            symptom_type="crash",
        )
        d = asdict(record)
        assert d == {
            "patch_content": _SAMPLE_PATCH,
            "root_cause": "r",
            "trigger_conditions": "t",
            "source_bug_id": "bug-1",
            "symptom_type": "crash",
        }

    def test_manual_fix_result_symptom_type_defaults_none(self) -> None:
        record = ManualFixResult(
            patch_content="p",
            root_cause="r",
            trigger_conditions="t",
            source_bug_id="b",
        )
        assert record.symptom_type is None

    def test_ingest_result_defaults(self) -> None:
        result = IngestResult(success=True)
        assert result.skipped is False
        assert result.reason is None
        assert result.pattern_id is None
        assert result.record is None

    def test_ingest_result_skipped_shape(self) -> None:
        result = IngestResult(
            success=False, skipped=True, reason="duplicate_pattern"
        )
        assert result.success is False
        assert result.skipped is True
        assert result.reason == "duplicate_pattern"
