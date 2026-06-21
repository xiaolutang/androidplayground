"""人工修复录入器（R001-BB015）—— 人修 commit patch → KB pattern。

依据：
- Sprint Contract R001-BB015（status: agreed，mode: negotiated / business 层）
- architecture INV-3（知识分层：BB015 是唯一允许写 pattern 层的入口）
- architecture AP-3（KB 模式层必须经 BB015 人工录入，禁止 agent 直接写入）
- 依赖 BF005 KBRetriever（add_pattern 写入 + 查询去重）

设计要点：
1. **唯一 pattern 写入入口**（INV-3/AP-3）：ManualFixRecorder 是全系统唯一调用
   ``kb_retriever.add_pattern`` 的模块。``available_operations`` 返回
   ``["add_pattern"]``，与 BB013（反思 agent）的
   ``["add_negative_knowledge", "add_raw_trajectory"]`` 完全不重叠。
2. **patch 抓取**（``capture_fix_patch``）：通过 git_client（INF06）的
   ``diff`` / ``diff_range`` 获取 unified diff，输出标准
   ``--- a/`` / ``+++ b/`` / ``@@`` 格式。
3. **结构化元数据**（``collect_metadata``）：接收人工 API 填入的
   root_cause / trigger_conditions / source_bug_id（必填）+ symptom_type（可选）。
4. **校验**（``_validate_input``）：root_cause / trigger_conditions /
   patch_content / source_bug_id 任一缺失抛 ValueError（附字段名，便于 API 回显）。
5. **去重**（``_check_duplicate``）：基于 patch_content 精确匹配查询 KB，
   已有 → skipped=True；查询异常降级为不去重（宁可重复也不阻断录入）。
6. **写入失败封装**：git_client 异常 → PatchCaptureError；kb_retriever
   add_pattern 异常 → PatternWriteError（附 record 内容便于排障）。
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ManualFixResult",
    "ManualFixRecorder",
    "PatchCaptureError",
    "PatternWriteError",
]


class PatchCaptureError(Exception):
    """Patch 抓取失败（git_client.diff / diff_range 抛异常时包装抛出）。"""


class PatternWriteError(Exception):
    """Pattern 写入失败（kb_retriever.add_pattern 抛异常时包装抛出）。"""


@dataclass
class ManualFixResult:
    """人工修复 pattern 录入记录（写入 pattern 层的核心载体）。

    Attributes:
        patch_content: unified diff 文本（git_client 产出，可含多文件 diff）。
        root_cause: 人工判定的根因描述（必填）。
        trigger_conditions: 触发该 bug 的条件描述（必填）。
        source_bug_id: 对应的 BugReport id，用于追溯（必填）。
        symptom_type: 症状分类（可选，如 "null_pointer" / "race_condition"）。
    """

    patch_content: str
    root_cause: str
    trigger_conditions: str
    source_bug_id: str
    symptom_type: Optional[str] = None


@dataclass
class IngestResult:
    """录入结果。

    Attributes:
        success: 是否写入成功。
        skipped: 是否被去重跳过（True 时 reason="duplicate_pattern"）。
        reason: 跳过/失败原因（人类可读）。
        pattern_id: 写入成功后的 KBEntry(pattern) id；未写入时为 None。
        record: 录入记录（ManualFixResult），便于审计/日志。
    """

    success: bool
    skipped: bool = False
    reason: Optional[str] = None
    pattern_id: Optional[str] = None
    record: Optional[ManualFixResult] = None


class ManualFixRecorder:
    """人工修复录入器：人修 patch → KB pattern。

    INV-3/AP-3：全系统唯一允许写 pattern 层的入口。

    Usage:
        recorder = ManualFixRecorder(git_client=git, kb_retriever=kb)
        result = recorder.ingest(
            commit_sha="abc123",
            root_cause="null check missing before .size()",
            trigger_conditions="empty list from network on timeout",
            source_bug_id="bug-001",
        )
        if result.success:
            # result.pattern_id 已写入 KBEntry(pattern)
            ...

    Args:
        git_client: INF git_client，需提供 ``diff(sha)`` / ``diff_range(base, head)``。
        kb_retriever: BF005 KBRetriever，需提供 ``add_pattern(...)`` 和
            ``find_pattern_by_patch(patch_content)``（或等价查询接口）。
    """

    # INV-3/AP-3：唯一操作是 add_pattern（与 BB013 形成互补且不重叠）
    AVAILABLE_OPERATIONS = frozenset({"add_pattern"})

    def __init__(
        self,
        *,
        git_client: Any,
        kb_retriever: Optional[Any] = None,
    ) -> None:
        self._git_client = git_client
        self._kb_retriever = kb_retriever

    @property
    def available_operations(self) -> list[str]:
        """返回可用写入操作（INV-3/AP-3：仅 add_pattern）。"""
        return sorted(self.AVAILABLE_OPERATIONS)

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def ingest(
        self,
        *,
        commit_sha: str,
        root_cause: str,
        trigger_conditions: str,
        source_bug_id: str,
        symptom_type: Optional[str] = None,
        base_sha: Optional[str] = None,
    ) -> IngestResult:
        """主入口：抓取 patch → 校验 → 去重 → 写 pattern。

        Args:
            commit_sha: 人修 commit sha（head）。
            root_cause: 人工填写的根因（必填）。
            trigger_conditions: 触发条件描述（必填）。
            source_bug_id: 对应 BugReport id（必填）。
            symptom_type: 症状分类（可选）。
            base_sha: 区间 diff 的 base sha；None 时走单 commit diff。

        Returns:
            IngestResult：success/skipped/pattern_id 等齐全。
        """
        # 1. 抓取 patch
        patch_content = self.capture_fix_patch(
            commit_sha=commit_sha,
            base_sha=base_sha,
        )

        # 2. 收集元数据 + 校验（校验失败抛 ValueError，由调用方处理）
        record = self.collect_metadata(
            patch_content=patch_content,
            root_cause=root_cause,
            trigger_conditions=trigger_conditions,
            source_bug_id=source_bug_id,
            symptom_type=symptom_type,
        )

        # 3. 去重检查
        if self._check_duplicate(patch_content):
            logger.info(
                "ManualFixRecorder: duplicate pattern skipped "
                "(source_bug_id=%s commit=%s)",
                source_bug_id,
                commit_sha,
            )
            return IngestResult(
                success=False,
                skipped=True,
                reason="duplicate_pattern",
                record=record,
            )

        # 4. 写 pattern（全系统唯一 add_pattern 调用入口）
        pattern_id = self._write_pattern(record)

        return IngestResult(
            success=True,
            skipped=False,
            pattern_id=pattern_id,
            record=record,
        )

    # ------------------------------------------------------------------
    # patch 抓取
    # ------------------------------------------------------------------
    def capture_fix_patch(
        self,
        *,
        commit_sha: str,
        base_sha: Optional[str] = None,
    ) -> str:
        """抓取人修 commit 的 unified diff patch。

        - base_sha 非空 → ``git_client.diff_range(base_sha, commit_sha)``
        - base_sha 为空 → ``git_client.diff(commit_sha)``

        Args:
            commit_sha: 人修 commit sha。
            base_sha: 可选区间 base。

        Returns:
            unified diff 文本。

        Raises:
            RuntimeError: git_client 未注入。
            PatchCaptureError: git_client.diff / diff_range 抛异常时包装抛出。
        """
        if self._git_client is None:
            raise RuntimeError("git_client not configured")

        try:
            if base_sha is not None:
                patch = self._git_client.diff_range(base_sha, commit_sha)
            else:
                patch = self._git_client.diff(commit_sha)
        except Exception as exc:
            logger.warning(
                "ManualFixRecorder: capture_fix_patch failed "
                "(commit=%s base=%s): %s",
                commit_sha,
                base_sha,
                exc,
            )
            raise PatchCaptureError(
                f"capture_fix_patch failed for commit={commit_sha} "
                f"base={base_sha}: {exc}"
            ) from exc

        return patch

    # ------------------------------------------------------------------
    # 元数据收集 + 校验
    # ------------------------------------------------------------------
    def collect_metadata(
        self,
        *,
        patch_content: str,
        root_cause: str,
        trigger_conditions: str,
        source_bug_id: str,
        symptom_type: Optional[str] = None,
    ) -> ManualFixResult:
        """收集人工填写的元数据 + 内联校验。

        校验失败抛 ValueError，附明确字段名（便于 API 返回前端错误提示）。

        Args:
            patch_content: unified diff 文本（必填非空）。
            root_cause: 根因描述（必填非空）。
            trigger_conditions: 触发条件（必填非空）。
            source_bug_id: BugReport id（必填非空）。
            symptom_type: 症状分类（可选）。

        Returns:
            ManualFixResult（已通过校验）。

        Raises:
            ValueError: 任一必填字段为空/None。
        """
        record = ManualFixResult(
            patch_content=patch_content,
            root_cause=root_cause,
            trigger_conditions=trigger_conditions,
            source_bug_id=source_bug_id,
            symptom_type=symptom_type,
        )
        self._validate_input(record)
        return record

    def _validate_input(self, record: ManualFixResult) -> None:
        """校验必填字段：root_cause / trigger_conditions / patch_content / source_bug_id。

        - None 或空字符串均视为缺失。
        - 错误消息明确指出缺失字段名（便于人工 API 回显）。

        Raises:
            ValueError: 任一必填字段为空/None。
        """
        if record.patch_content is None or record.patch_content == "":
            raise ValueError("patch_content is empty")
        if record.root_cause is None or record.root_cause == "":
            raise ValueError("root_cause is required")
        if record.trigger_conditions is None or record.trigger_conditions == "":
            raise ValueError("trigger_conditions is required")
        if record.source_bug_id is None or record.source_bug_id == "":
            raise ValueError("source_bug_id is required")

    # ------------------------------------------------------------------
    # 去重检查
    # ------------------------------------------------------------------
    def _check_duplicate(self, patch_content: str) -> bool:
        """去重检查：KB 已有相同 patch_content → True。

        基于 patch_content 精确文本匹配（MVP 阶段不做模糊/归一化）。

        降级策略：KBRetriever 查询抛异常时降级为"不去重"（返回 False +
        logging.warning）——宁可重复录入也不阻断人工录入。

        Args:
            patch_content: 待检查的 unified diff 文本。

        Returns:
            True 表示已有相同 patch（应跳过）；False 表示无重复或查询失败降级。
        """
        if self._kb_retriever is None:
            # 无 kb_retriever 无法查询 → 降级为不去重
            logger.warning(
                "ManualFixRecorder: kb_retriever not configured; "
                "skip duplicate check"
            )
            return False

        try:
            existing = self._kb_retriever.find_pattern_by_patch(patch_content)
        except Exception as exc:
            logger.warning(
                "ManualFixRecorder: duplicate check failed, "
                "degraded to no-dedup: %s",
                exc,
            )
            return False

        # truthy 判定：KBRetriever 可能返回 KBEntry 对象、id 字符串或 bool
        # （约定 None/空 表示不存在；任何 truthy 值表示已存在）
        return bool(existing)

    # ------------------------------------------------------------------
    # 写 pattern（INV-3/AP-3：全系统唯一 add_pattern 调用入口）
    # ------------------------------------------------------------------
    def _write_pattern(self, record: ManualFixResult) -> str:
        """写 KBEntry(pattern) —— 全系统唯一 add_pattern 调用入口。

        Args:
            record: 已校验的录入记录。

        Returns:
            写入的 pattern_id（KBEntry.id）。

        Raises:
            RuntimeError: kb_retriever 未注入。
            PatternWriteError: add_pattern 抛异常时包装抛出（附 record 内容）。
        """
        if self._kb_retriever is None:
            raise RuntimeError("kb_retriever not configured")

        try:
            pattern_id = self._kb_retriever.add_pattern(
                patch_content=record.patch_content,
                root_cause=record.root_cause,
                trigger_conditions=record.trigger_conditions,
                symptom_type=record.symptom_type,
                source_bug_id=record.source_bug_id,
            )
        except Exception as exc:
            logger.error(
                "ManualFixRecorder: add_pattern failed "
                "(source_bug_id=%s): %s; record=%s",
                record.source_bug_id,
                exc,
                asdict(record),
            )
            raise PatternWriteError(
                f"add_pattern failed for source_bug_id={record.source_bug_id}: "
                f"{exc}; record={asdict(record)}"
            ) from exc

        return pattern_id

    # INV-3 守护：显式不提供 add_negative_knowledge / add_raw_trajectory
    # 这些是 BB013（反思 agent）的职责，BB015 专注 pattern 层。
