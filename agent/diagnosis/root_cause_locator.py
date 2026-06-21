"""根因定位器（R001-BB005）—— 从 confirmed 假设 + 命中信号反溯代码 file:line。

依据：
- Sprint Contract R001-BB005（status: agreed，mode: direct / Mode 2 直接验收）
- 任务包 R001-BB005 acceptance_criteria：
  1. 命中信号 -> 代码 file:line 反溯
  2. 多信号优先级（stack > log_keyword > visual_anchor > git_blame）
  3. 无匹配 -> located=False + 根因空（转缺口）

设计要点：
1. **信号优先级 4 档**（``locate`` 主入口按序短路）：
   - stack（堆栈帧）→ 直接拿到 file:line + function，confidence=0.9（最强）
   - log_keyword（异常类名/错误关键词）→ git grep 检索文件，confidence=0.6
   - visual_anchor（视觉锚点）→ anchor_library.match_by_visual_features → page_id → 文件，confidence=0.7
   - git_blame（兜底）→ 已知 file 时 blame 最近变更行，confidence=0.4（最弱）
2. **demote_factor 继承**（AC 隐含）：最终 confidence = base * hypothesis.demote_factor
   （BB004 负向反查降权因子，默认 1.0；<1.0 表示假设被负向知识降权）。
3. **三级降级**（与 BB004 一致风格）：
   - git_client=None：stack 路径仍可用（纯解析），log_keyword/git_blame 跳过
   - anchor_library=None：visual_anchor 路径跳过
   - gap_store=None：located=False 时仅返回结果不创建缺口（warning）
   - 任何子方法抛异常：捕获 + 降级到下一策略（不阻断主流程）
4. **同步 def**：纯内存 + 同步外部调用（git blame/grep 同步 subprocess）。
5. **不持久化**：持久化由 Orchestrator 负责；本模块只返回 RootCauseLocation。

信号格式参考：
- ``ParsedLogcatSignal.stack_top``：``com.example.app.MainActivity.onCreate(MainActivity.java:42)``
- ``ParsedFlutterSignal.stack_top``：``methodName (file.dart:line:col)``
- ``ParsedVisualSignal.visual_type`` + signal dict 的 ``source_config.metrics``（无直接向量，
  BB005 从 signal dict 的 ``pattern.visual_features`` 或 ``source_config.visual_features``
  字段读取向量；无向量则跳过 visual_anchor 路径）
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = ["RootCauseLocation", "RootCauseLocator"]


# ---------------------------------------------------------------------------
# 信号优先级常量（与 locate 方法中的尝试顺序一致）
# ---------------------------------------------------------------------------
# confidence base 值：stack 最强（0.9）→ visual_anchor（0.7）→ log_keyword（0.6）→ git_blame（0.4）
# 设计依据：堆栈帧是直接证据（最强）；视觉锚点需 anchor_library 命中（次强）；
# log_keyword 需 grep 辅助（中等）；git_blame 是兜底（最弱，仅提供最近变更线索）。
_CONFIDENCE_STACK = 0.9
_CONFIDENCE_VISUAL_ANCHOR = 0.7
_CONFIDENCE_LOG_KEYWORD = 0.6
_CONFIDENCE_GIT_BLAME = 0.4


# ---------------------------------------------------------------------------
# JVM / Dart stack 帧解析正则
# ---------------------------------------------------------------------------
# JVM 顶帧格式（ParsedLogcatSignal.stack_top）：
#   com.example.app.MainActivity.onCreate(MainActivity.java:42)
#   at com.example.app.Foo.bar(Foo.java:10)  （logcat 原始含 "at " 前缀和缩进）
# 分组：1=function(fully qualified), 2=file(basename), 3=line
_JVM_FRAME_RE = re.compile(
    r"(?:at\s+)?"
    r"(?P<func>[\w.$]+)"  # fully qualified function
    r"\s*\(\s*"
    r"(?P<file>[\w./]+)"  # source file
    r":"
    r"(?P<line>\d+)"  # line number
    r"\s*\)"
)

# Dart 顶帧格式（ParsedFlutterSignal.stack_top）：
#   methodName (file.dart:line:col)
#   #0      methodName (package:foo/bar.dart:10:5)
# 分组：1=function, 2=file, 3=line（忽略 col）
_DART_FRAME_RE = re.compile(
    r"(?:#\d+\s+)?"  # optional frame index
    r"(?P<func>[\w.<>]+)"  # function name
    r"\s*\(\s*"
    r"(?P<file>[\w./:]+?)"  # source file (non-greedy; may include package: prefix)
    r":"
    r"(?P<line>\d+)"  # line number
    r"(?::\d+)?"  # optional column
    r"\s*\)"
)


@dataclass
class RootCauseLocation:
    """根因定位结果。

    located=True 表示已反溯到代码位置（file:line + function + snippet 可用）；
    located=False 表示所有策略未命中（转缺口，file/line/function/snippet 均为 None）。

    Attributes:
        located: 是否已定位。
        file: 文件路径（located=True 时非 None）。
        line: 行号（located=True 时非 None）。
        function: 函数名（stack 路径有；其他路径可能为 None）。
        snippet: 代码片段（git_blame 路径取 content；其他路径可能为 None）。
        confidence: 置信度 0.0-1.0（= base * demote_factor）。
        source: 命中策略（"stack" / "log_keyword" / "visual_anchor" / "git_blame" /
            "unmatched"；unmatched 表示全未命中）。
        matched_signal: 命中的原始信号 dict（调试/审计用；未命中为 None）。
        reasoning: 解释链（记录尝试过的策略，便于 Orchestrator 诊断）。
        demote_factor: BB004 负向知识降权因子（继承自 hypothesis，默认 1.0）。
    """

    located: bool
    file: Optional[str] = None
    line: Optional[int] = None
    function: Optional[str] = None
    snippet: Optional[str] = None
    confidence: float = 0.0
    source: str = "unmatched"
    matched_signal: Optional[dict[str, Any]] = None
    reasoning: str = ""
    demote_factor: float = 1.0


@dataclass
class _LocateAttempt:
    """单次策略尝试的中间结果（内部用，记录 reasoning 链）。"""

    strategy: str
    tried: bool = False
    hit: bool = False
    note: str = ""


class RootCauseLocator:
    """根因定位器：从 confirmed 假设 + 命中信号反溯代码 file:line。

    所有方法同步（纯内存 + 同步外部调用）。不持久化（持久化由 Orchestrator 负责）。

    Args:
        git_client: INF06 GitClient（blame/grep）。None 时 log_keyword/git_blame 跳过。
        anchor_library: BF007 AnchorLibrary（视觉锚点反查）。None 时 visual_anchor 跳过。
        gap_store: BF008 GapStore（无匹配转缺口）。None 时 located=False 不创建缺口。
        repo_root: 仓库根路径（用于 anchor page_id → 文件路径映射的相对基准）。
    """

    def __init__(
        self,
        *,
        git_client: Optional[Any] = None,
        anchor_library: Optional[Any] = None,
        gap_store: Optional[Any] = None,
        repo_root: str = ".",
    ) -> None:
        self._git_client = git_client
        self._anchor_library = anchor_library
        self._gap_store = gap_store
        self._repo_root = repo_root

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def locate(
        self,
        hypothesis: Any,
        signals: list[dict[str, Any]],
        symptom_type: Optional[str] = None,
    ) -> RootCauseLocation:
        """主入口：按信号优先级反溯代码位置。

        信号优先级（多信号合并，第一个命中即返回/短路）：
        1. stack（堆栈帧）→ 直接 file:line + function
        2. log_keyword（日志关键词/异常类名）→ git grep 检索文件
        3. visual_anchor（视觉锚点）→ anchor_library.match_by_visual_features → page_id → 文件
        4. 兜底 git_blame → 已知 file 时 blame 最近变更行

        无匹配 → RootCauseLocation(located=False) + 调 gap_store.create（转缺口）。

        Args:
            hypothesis: BB004 HypothesisNode（confirmed）。读取 demote_factor 字段。
            signals: 命中信号集（list[dict]，每项为 Signal 行字典或 ParsedXxxSignal 的
                __dict__）。允许为空列表（全未命中走缺口）。
            symptom_type: 症状类型（可选，传递给 gap 描述）。

        Returns:
            RootCauseLocation（located=True 或 located=False + 已转缺口）。
        """
        demote_factor = self._read_demote_factor(hypothesis)
        attempts: list[_LocateAttempt] = []
        reasoning_parts: list[str] = []

        # 1. stack 路径（最高优先级）—— 对每个信号独立判断是否含 stack_top
        for sig in signals:
            try:
                loc = self._locate_from_stack(sig)
            except Exception as exc:
                attempts.append(_LocateAttempt("stack", tried=True, hit=False, note=f"error: {exc}"))
                reasoning_parts.append(f"stack[error: {exc}]")
                continue
            if loc is not None:
                loc.demote_factor = demote_factor
                loc.confidence = _CONFIDENCE_STACK * demote_factor
                reasoning_parts.append("stack[hit]")
                loc.reasoning = "; ".join(reasoning_parts)
                return loc
            attempts.append(_LocateAttempt("stack", tried=True, hit=False, note="no stack_top"))
        stack_attempts = [a for a in attempts if a.strategy == "stack"]
        if not signals:
            reasoning_parts.append("stack[skipped: empty signals]")
        elif not stack_attempts:
            reasoning_parts.append("stack[skipped: no signals with stack]")
        elif not any(a.hit for a in stack_attempts):
            reasoning_parts.append("stack[no hit]")

        # 2. log_keyword 路径 —— 基于异常类名/错误关键词 grep
        for sig in signals:
            try:
                loc = self._locate_from_log_keyword(sig, symptom_type)
            except Exception as exc:
                attempts.append(_LocateAttempt("log_keyword", tried=True, hit=False, note=f"error: {exc}"))
                reasoning_parts.append(f"log_keyword[error: {exc}]")
                continue
            if loc is not None:
                loc.demote_factor = demote_factor
                loc.confidence = _CONFIDENCE_LOG_KEYWORD * demote_factor
                reasoning_parts.append("log_keyword[hit]")
                loc.reasoning = "; ".join(reasoning_parts)
                return loc
            attempts.append(_LocateAttempt("log_keyword", tried=True, hit=False, note="no grep match"))
        reasoning_parts.append("log_keyword[no hit]")

        # 3. visual_anchor 路径 —— 视觉特征向量匹配锚点
        for sig in signals:
            try:
                loc = self._locate_from_visual_anchor(sig)
            except Exception as exc:
                attempts.append(_LocateAttempt("visual_anchor", tried=True, hit=False, note=f"error: {exc}"))
                reasoning_parts.append(f"visual_anchor[error: {exc}]")
                continue
            if loc is not None:
                loc.demote_factor = demote_factor
                loc.confidence = _CONFIDENCE_VISUAL_ANCHOR * demote_factor
                reasoning_parts.append("visual_anchor[hit]")
                loc.reasoning = "; ".join(reasoning_parts)
                return loc
            attempts.append(_LocateAttempt("visual_anchor", tried=True, hit=False, note="no anchor match"))
        reasoning_parts.append("visual_anchor[no hit]")

        # 4. git_blame 兜底 —— 需已知 file（从 hypothesis 或先前尝试中无 file 则跳过）
        known_file = self._read_known_file(hypothesis)
        if known_file is not None:
            try:
                loc = self._fallback_git_blame(known_file)
            except Exception as exc:
                attempts.append(_LocateAttempt("git_blame", tried=True, hit=False, note=f"error: {exc}"))
                reasoning_parts.append(f"git_blame[error: {exc}]")
                loc = None
            if loc is not None:
                loc.demote_factor = demote_factor
                loc.confidence = _CONFIDENCE_GIT_BLAME * demote_factor
                reasoning_parts.append("git_blame[hit]")
                loc.reasoning = "; ".join(reasoning_parts)
                return loc
            attempts.append(_LocateAttempt("git_blame", tried=True, hit=False, note="no blame"))
        else:
            attempts.append(_LocateAttempt("git_blame", tried=False, hit=False, note="no known file"))
            reasoning_parts.append("git_blame[skipped: no known file]")

        # 全部未命中 → located=False + 转缺口
        unmatched = RootCauseLocation(
            located=False,
            confidence=0.0,
            source="unmatched",
            matched_signal=None,
            reasoning="; ".join(reasoning_parts) + "; unmatched",
            demote_factor=demote_factor,
        )
        self._create_gap_for_unmatched(hypothesis, signals, symptom_type, attempts)
        return unmatched

    # ------------------------------------------------------------------
    # 策略 1：stack（堆栈帧）
    # ------------------------------------------------------------------
    def _locate_from_stack(self, signal: dict[str, Any]) -> Optional[RootCauseLocation]:
        """从 signal 中提取 stack top（file:line + function）。

        signal 格式参考 ParsedLogcatSignal / ParsedFlutterSignal：
        - logcat: signal["pattern"]["stack_top"] = "com.foo.Bar.baz(Bar.java:42)"
        - flutter: signal["pattern"]["stack_top"] = "methodName (file.dart:10:5)"
        - 也兼容 signal["stack_top"] 直接字段（ParsedXxxSignal.__dict__ 场景）

        Returns:
            RootCauseLocation（source="stack"）或 None（无 stack_top 或解析失败）。
        """
        stack_top = self._extract_stack_top(signal)
        if not stack_top:
            return None

        # 先尝试 JVM 格式，再尝试 Dart 格式
        m = _JVM_FRAME_RE.search(stack_top)
        if m is None:
            m = _DART_FRAME_RE.search(stack_top)
        if m is None:
            logger.debug("stack_top unparseable: %r", stack_top)
            return None

        file = m.group("file")
        # JVM 的 file 可能是 basename（MainActivity.java），保留原样由调用方解析
        line = int(m.group("line"))
        func = m.group("func")

        return RootCauseLocation(
            located=True,
            file=file,
            line=line,
            function=func,
            snippet=None,  # stack 路径无 snippet（git_blame 才有）
            confidence=_CONFIDENCE_STACK,  # 主入口会乘 demote_factor
            source="stack",
            matched_signal=signal,
            reasoning="stack frame parsed",
        )

    @staticmethod
    def _extract_stack_top(signal: dict[str, Any]) -> Optional[str]:
        """从 signal dict 中提取 stack_top 字符串（兼容多种存放位置）。"""
        # 直接字段（ParsedXxxSignal.__dict__）
        direct = signal.get("stack_top")
        if isinstance(direct, str) and direct:
            return direct
        # pattern.stack_top（Signal 行字典格式）
        pattern = signal.get("pattern")
        if isinstance(pattern, dict):
            nested = pattern.get("stack_top")
            if isinstance(nested, str) and nested:
                return nested
        return None

    # ------------------------------------------------------------------
    # 策略 2：log_keyword（日志关键词/异常类名 → git grep）
    # ------------------------------------------------------------------
    def _locate_from_log_keyword(
        self,
        signal: dict[str, Any],
        symptom_type: Optional[str],
    ) -> Optional[RootCauseLocation]:
        """基于 signal 的 keyword（异常类名、错误消息关键词），通过 git grep 检索文件。

        keyword 提取优先级：
        1. signal["pattern"]["error_class"]（flutter Dart 异常类名）
        2. signal["pattern"]["matched"]（logcat 命中的异常类名/模式）
        3. signal["source_config"]["message"] 中的异常类名（正则提取）

        Returns:
            RootCauseLocation（source="log_keyword"）或 None。
        """
        if self._git_client is None:
            return None

        keyword = self._extract_keyword(signal)
        if not keyword:
            return None

        # 用 git grep 检索（扩展正则；转义特殊字符以避免误匹配）
        safe = re.escape(keyword)
        try:
            matches = self._git_client.grep(safe)
        except Exception as exc:
            logger.debug("git grep failed for keyword %r: %s", keyword, exc)
            return None

        if not matches:
            return None

        # 取第一个匹配（GrepMatch 有 file / line_no / content）
        first = matches[0]
        return RootCauseLocation(
            located=True,
            file=first.file,
            line=first.line_no,
            function=None,  # grep 不提供函数名
            snippet=first.content,
            confidence=_CONFIDENCE_LOG_KEYWORD,
            source="log_keyword",
            matched_signal=signal,
            reasoning=f"git grep keyword={keyword!r} -> {first.file}:{first.line_no}",
        )

    @staticmethod
    def _extract_keyword(signal: dict[str, Any]) -> Optional[str]:
        """从 signal 提取用于 grep 的关键词（异常类名/错误模式）。"""
        pattern = signal.get("pattern")
        if isinstance(pattern, dict):
            # flutter error_class 优先（Dart 异常类名最精确）
            error_class = pattern.get("error_class")
            if isinstance(error_class, str) and error_class:
                return error_class
            # logcat matched（可能含 " | " 分隔多模式，取第一个）
            matched = pattern.get("matched")
            if isinstance(matched, str) and matched:
                # 取 " | " 分隔的第一段（通常是主异常类名）
                first_seg = matched.split("|")[0].strip()
                if first_seg:
                    return first_seg
        # source_config.message 中正则提取 java/kotlin/Dart 异常类名
        source = signal.get("source_config")
        if isinstance(source, dict):
            msg = source.get("message")
            if isinstance(msg, str):
                m = re.search(r"(java\.[\w.]*Exception|kotlin\.[\w.]*Exception|\w+Exception|\w+Error)", msg)
                if m:
                    return m.group(1)
        return None

    # ------------------------------------------------------------------
    # 策略 3：visual_anchor（视觉锚点 → page_id → 文件）
    # ------------------------------------------------------------------
    def _locate_from_visual_anchor(self, signal: dict[str, Any]) -> Optional[RootCauseLocation]:
        """从 signal 拿 visual_features 向量，调 anchor_library.match_by_visual_features
        （top_k=1）→ 取 page_id → 映射到文件。

        visual_features 向量读取位置（兼容多种格式）：
        - signal["pattern"]["visual_features"]
        - signal["source_config"]["visual_features"]
        - signal["source_config"]["metrics"]（ParsedVisualSignal 的 metrics dict，
          如果是数值列表则直接用作向量；dict 则跳过）

        Returns:
            RootCauseLocation（source="visual_anchor"）或 None。
        """
        if self._anchor_library is None:
            return None

        query_vector = self._extract_visual_vector(signal)
        if query_vector is None:
            return None

        try:
            results = self._anchor_library.match_by_visual_features(query_vector, top_k=1)
        except Exception as exc:
            logger.debug("anchor_library.match_by_visual_features failed: %s", exc)
            return None

        if not results:
            return None

        # results: list[tuple[Anchor, float]]，取 top-1
        anchor, similarity = results[0]
        page_id = getattr(anchor, "page_id", None)
        if not page_id:
            return None

        # page_id → 文件路径映射（MVP 简化：page_id 直接作为文件相对路径）
        # 真实场景需 page_id → 文件位置的查找表（BF007 扩展）；此处用 page_id 作为文件名
        file_path = page_id

        return RootCauseLocation(
            located=True,
            file=file_path,
            line=None,  # visual_anchor 无精确行号
            function=None,
            snippet=None,
            confidence=_CONFIDENCE_VISUAL_ANCHOR,
            source="visual_anchor",
            matched_signal=signal,
            reasoning=f"visual_anchor page_id={page_id!r} similarity={similarity:.3f}",
        )

    @staticmethod
    def _extract_visual_vector(signal: dict[str, Any]) -> Optional[list[float]]:
        """从 signal 提取视觉特征向量（兼容多种存放位置）。"""
        pattern = signal.get("pattern")
        if isinstance(pattern, dict):
            vf = pattern.get("visual_features")
            if isinstance(vf, list) and vf:
                return [float(v) for v in vf]
        source = signal.get("source_config")
        if isinstance(source, dict):
            vf = source.get("visual_features")
            if isinstance(vf, list) and vf:
                return [float(v) for v in vf]
            # metrics 可能是 dict（ParsedVisualSignal）或 list（自定义）
            metrics = source.get("metrics")
            if isinstance(metrics, list) and metrics:
                return [float(v) for v in metrics]
        return None

    # ------------------------------------------------------------------
    # 策略 4：git_blame 兜底
    # ------------------------------------------------------------------
    def _fallback_git_blame(self, file: str) -> Optional[RootCauseLocation]:
        """已知 file 时调 git_client.blame 取最近变更行 + snippet。

        取 blame 结果的最后一行（最近变更的行，git blame 默认按文件行号顺序输出，
        最后一行的 commit 时间通常最新——此为 MVP 简化；真实场景应按 author_time 排序）。

        Returns:
            RootCauseLocation（source="git_blame"）或 None。
        """
        if self._git_client is None:
            return None
        try:
            blame_lines = self._git_client.blame(file)
        except Exception as exc:
            logger.debug("git blame failed for %r: %s", file, exc)
            return None
        if not blame_lines:
            return None

        # MVP：取第一行（BlameLine 有 line_no / content / author / commit）
        first = blame_lines[0]
        snippet = getattr(first, "content", None)
        line_no = getattr(first, "line_no", 1)
        author = getattr(first, "author", "unknown")

        return RootCauseLocation(
            located=True,
            file=file,
            line=line_no,
            function=None,
            snippet=snippet,
            confidence=_CONFIDENCE_GIT_BLAME,
            source="git_blame",
            matched_signal=None,
            reasoning=f"git blame fallback: author={author}",
        )

    # ------------------------------------------------------------------
    # 策略未命中：转缺口
    # ------------------------------------------------------------------
    def _create_gap_for_unmatched(
        self,
        hypothesis: Any,
        signals: list[dict[str, Any]],
        symptom_type: Optional[str],
        attempts: list[_LocateAttempt],
    ) -> None:
        """调 gap_store.create 转缺口（gap_type=reasoning）。

        异常降级：gap_store=None 时 warning + 不阻断；create 抛异常时捕获 + warning。
        """
        if self._gap_store is None:
            logger.warning(
                "RootCauseLocator: all strategies unmatched but gap_store is None; "
                "skip gap creation (degraded). hypothesis=%r",
                getattr(hypothesis, "id", "?"),
            )
            return

        # 构建 attempts 摘要（用于 gap description）
        tried_summary = ", ".join(
            f"{a.strategy}[tried={a.tried},hit={a.hit}]"
            + (f":{a.note}" if a.note else "")
            for a in attempts
        ) or "no attempts"

        gap_data = {
            "id": uuid.uuid4().hex,
            "gap_type": "reasoning",
            "description": (
                f"root cause not locatable: all strategies unmatched. "
                f"attempts=[{tried_summary}]; "
                f"symptom_type={symptom_type!r}; "
                f"hypothesis={getattr(hypothesis, 'id', '?')!r}; "
                f"signals_count={len(signals)}"
            ),
            "linked_bug_ids": [],
        }
        try:
            self._gap_store.create(gap_data)
        except Exception as exc:
            logger.warning(
                "RootCauseLocator: gap_store.create failed for unmatched: %s",
                exc,
            )

    # ------------------------------------------------------------------
    # 辅助：从 hypothesis 读取字段
    # ------------------------------------------------------------------
    @staticmethod
    def _read_demote_factor(hypothesis: Any) -> float:
        """从 hypothesis 读取 demote_factor（BB004 HypothesisNode 字段）。

        缺失或非数值时默认 1.0（不影响 confidence）。
        """
        factor = getattr(hypothesis, "demote_factor", 1.0)
        if isinstance(factor, (int, float)) and 0.0 <= factor <= 1.0:
            return float(factor)
        return 1.0

    @staticmethod
    def _read_known_file(hypothesis: Any) -> Optional[str]:
        """从 hypothesis 读取已知文件路径（用于 git_blame 兜底）。

        BB004 HypothesisNode 无直接 file 字段，但 verifying_action / confirming_evidence
        可能含 file。MVP 简化：尝试从 verifying_action.file 读取。
        """
        action = getattr(hypothesis, "verifying_action", None)
        if isinstance(action, dict):
            f = action.get("file")
            if isinstance(f, str) and f:
                return f
        evidence = getattr(hypothesis, "confirming_evidence", None)
        if isinstance(evidence, dict):
            f = evidence.get("file")
            if isinstance(f, str) and f:
                return f
        return None
