"""自动修复器（R001-BB007）。

依据：
- Sprint Contract R001-BB007（status: agreed，11 AC）
- design 5.1 Tier1/Tier2 修复流程（analysis 第 746-778 行）
- design 5.3 KB 降级对修复策略影响（第 821 行）
- D2（LLM provider：glm-5.1 经 New API 网关）
- D6（KB 混合检索：BB007 套历史 patch）
- D7（步数/token 预算：FIX_RETRY_MAX 重试上限）

设计要点：
1. **三策略优先级**：template（KB pattern 套用）→ llm（LLMGateway fix_patch）
   → history_calibration（KB 历史校准）。首个成功的策略产出 patch 并终止。
2. **strategy_chain 审计链**（list，记录每策略 attempt，含 latency_ms /
   tokens_used / pattern_id 等元数据），供审计/换策略回溯。
3. **Tier1 产出 is_draft=False；Tier2 产出 is_draft=True + rationale**。
4. **降级规则**：每策略尝试失败（空 patch / 异常 / similarity 不达标）→ 降级到下一策略；
   三策略全失败 → 返回 FixPatch（patch_content=None, strategy_chain 记录全部失败）。
5. **LLM/KB 不可用时降级**到下一策略，不抛异常（冷启动优雅降级）。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from agent.infra.config import get_settings
from agent.infra.llm_gateway import LLMError, LLMGateway, LLMResponse
from agent.kb.retriever import RetrievalResult

logger = logging.getLogger(__name__)

# 阈值常量（MVP 用模块级常量，后续可迁 config）
TEMPLATE_SIMILARITY_THRESHOLD = 0.7
HISTORY_SIMILARITY_THRESHOLD = 0.6

TIER2_RATIONALE = "低置信度，需人工 review"

# LLM system prompt（角色 + unified diff 格式约束）
_LLM_SYSTEM_PROMPT = (
    "你是 Android 客户端 bug 修复专家。\n"
    "输出格式：unified diff（git apply 兼容），格式如下：\n"
    "--- a/path/to/file\n"
    "+++ b/path/to/file\n"
    "@@ -line,count +line,count @@\n"
    "-old line\n"
    "+new line\n"
    "只输出 diff，不要解释。"
)

__all__ = [
    "AutoFixer",
    "FixPatch",
    "StrategyAttempt",
    "TEMPLATE_SIMILARITY_THRESHOLD",
    "HISTORY_SIMILARITY_THRESHOLD",
    "TIER2_RATIONALE",
]


@dataclass
class StrategyAttempt:
    """单策略尝试记录（strategy_chain 元素）。

    Attributes:
        strategy_name: 策略名（template / llm / history_calibration）。
        succeeded: 是否成功。
        error: 失败原因（成功时为 None）。
        latency_ms: 该策略耗时（毫秒）。
        tokens_used: LLM token 使用量（仅 llm 策略有值）。
        pattern_id: 命中的 KBEntry id（仅 template/history_calibration 有值）。
        attempt_no: 尝试序号（从 1 递增）。
    """

    strategy_name: str
    succeeded: bool
    error: str | None = None
    latency_ms: int = 0
    tokens_used: int | None = None
    pattern_id: str | None = None
    attempt_no: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转为 dict（写入 strategy_chain）。"""
        return {
            "strategy_name": self.strategy_name,
            "succeeded": self.succeeded,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "tokens_used": self.tokens_used,
            "pattern_id": self.pattern_id,
            "attempt_no": self.attempt_no,
        }


@dataclass
class FixPatch:
    """修复补丁（内存表示，与 SCH01.3 FixPatch ORM 字段对齐）。

    Attributes:
        patch_content: unified diff 内容（git apply 兼容）；全失败时 None。
        files_changed: 变更文件列表（从 patch_content 解析）。
        strategy: 最终成功策略名（全失败时为最后尝试的策略名）。
        strategy_chain: 每策略 attempt 记录列表。
        pattern_id: template/history_calibration 命中的 KBEntry id。
        is_draft: Tier1=False / Tier2=True。
        rationale: Tier2 固定文案；Tier1 为 None。
        tier: 从入参透传（1 或 2）。
        kb_history_ref: history_calibration 命中的 KBEntry id（同 pattern_id）。
    """

    patch_content: str | None
    files_changed: list[str] = field(default_factory=list)
    strategy: str = ""
    strategy_chain: list[dict] = field(default_factory=list)
    pattern_id: str | None = None
    is_draft: bool = False
    rationale: str | None = None
    tier: int = 1
    kb_history_ref: str | None = None


class AutoFixer:
    """自动修复器：三策略优先级 template -> llm -> history_calibration。

    接收根因定位结果 + Tier 分级 + KB 检索上下文，产出 FixPatch。
    纯业务逻辑，不持久化（持久化由调用方 Orchestrator 负责）。
    """

    def __init__(
        self,
        *,
        llm_gateway: LLMGateway | None = None,
        settings: Any = None,
    ) -> None:
        """初始化自动修复器。

        Args:
            llm_gateway: LLMGateway 实例（INF04），可为 None（llm 策略降级跳过）。
            settings: 配置对象（INF06），None 时用 get_settings()。
        """
        self._llm_gateway = llm_gateway
        self._settings = settings or get_settings()

    def generate_patch(
        self,
        *,
        bug_report_summary: str,
        root_cause_location: str,
        symptom_type: str,
        tier: int,
        kb_context: RetrievalResult | None = None,
    ) -> FixPatch:
        """三策略优先级生成 FixPatch。

        Args:
            bug_report_summary: BugReport 摘要（复现步骤/堆栈/版本）。
            root_cause_location: 根因定位（文件:行号 + 描述）。
            symptom_type: 症状类型。
            tier: 置信度 Tier（1 或 2，由 BB006 传入）。
            kb_context: KB 检索结果（pattern + patch_history 层）。

        Returns:
            FixPatch 对象（含 strategy_chain 审计链）。
        """
        strategy_chain: list[StrategyAttempt] = []
        patch_content: str | None = None
        final_strategy: str = ""
        pattern_id: str | None = None
        kb_history_ref: str | None = None
        attempt_no = 0

        # ---- 策略 1: template ----
        attempt_no += 1
        attempt, tmpl_patch, tmpl_pid = self._try_template(
            kb_context, root_cause_location, symptom_type, attempt_no
        )
        strategy_chain.append(attempt)
        if attempt.succeeded:
            patch_content = tmpl_patch
            final_strategy = "template"
            pattern_id = tmpl_pid

        # ---- 策略 2: llm（仅 template 失败时尝试）----
        if patch_content is None:
            attempt_no += 1
            attempt, llm_patch = self._try_llm(
                bug_report_summary,
                root_cause_location,
                symptom_type,
                kb_context,
                attempt_no,
            )
            strategy_chain.append(attempt)
            if attempt.succeeded:
                patch_content = llm_patch
                final_strategy = "llm"

        # ---- 策略 3: history_calibration（仅前两策略失败时尝试）----
        if patch_content is None:
            attempt_no += 1
            attempt, hist_patch, hist_pid = self._try_history_calibration(
                kb_context, attempt_no
            )
            strategy_chain.append(attempt)
            if attempt.succeeded:
                patch_content = hist_patch
                final_strategy = "history_calibration"
                pattern_id = hist_pid
                kb_history_ref = hist_pid

        # 全失败兜底
        if patch_content is None:
            final_strategy = strategy_chain[-1].strategy_name

        files_changed = (
            self._extract_files_changed(patch_content) if patch_content else []
        )

        return FixPatch(
            patch_content=patch_content,
            files_changed=files_changed,
            strategy=final_strategy,
            strategy_chain=[a.to_dict() for a in strategy_chain],
            pattern_id=pattern_id,
            is_draft=(tier == 2),
            rationale=TIER2_RATIONALE if tier == 2 else None,
            tier=tier,
            kb_history_ref=kb_history_ref,
        )

    # ------------------------------------------------------------------
    # 策略 1：template（KB pattern 套用）
    # ------------------------------------------------------------------
    def _try_template(
        self,
        kb_context: RetrievalResult | None,
        root_cause_location: str,
        symptom_type: str,
        attempt_no: int,
    ) -> tuple[StrategyAttempt, str | None, str | None]:
        """template 策略：KB pattern 套用。

        Returns:
            (attempt, patch_content, pattern_id)。
        """
        start = time.time()
        error: str | None = None
        patch_content: str | None = None
        pattern_id: str | None = None

        try:
            if kb_context is None:
                error = "kb_context unavailable"
            elif kb_context.degraded:
                error = "kb degraded"
            else:
                top1 = self._kb_layer_top1(
                    kb_context, "pattern", TEMPLATE_SIMILARITY_THRESHOLD
                )
                if top1 is None:
                    # 区分：无命中 vs 相似度不足
                    raw_top = self._kb_layer_top1(
                        kb_context, "pattern", 0.0
                    )
                    if raw_top is None:
                        error = "no pattern hit"
                    else:
                        error = "similarity below threshold"
                else:
                    entry, _sim = top1
                    content = entry.content or {}
                    tmpl = content.get("patch_template") if isinstance(
                        content, dict
                    ) else None
                    if not tmpl:
                        error = "no patch_template in entry"
                    else:
                        patch_content = self._render_template(
                            tmpl,
                            root_cause_location=root_cause_location,
                            symptom_type=symptom_type,
                        )
                        pattern_id = entry.id
        except Exception as e:  # noqa: BLE001 — 降级不抛
            error = f"{type(e).__name__}: {e}"

        latency_ms = max(1, int((time.time() - start) * 1000))
        succeeded = patch_content is not None
        return (
            StrategyAttempt(
                strategy_name="template",
                succeeded=succeeded,
                error=None if succeeded else error,
                latency_ms=latency_ms,
                tokens_used=None,
                pattern_id=pattern_id,
                attempt_no=attempt_no,
            ),
            patch_content,
            pattern_id,
        )

    # ------------------------------------------------------------------
    # 策略 2：llm（LLMGateway fix_patch）
    # ------------------------------------------------------------------
    def _try_llm(
        self,
        bug_report_summary: str,
        root_cause_location: str,
        symptom_type: str,
        kb_context: RetrievalResult | None,
        attempt_no: int,
    ) -> tuple[StrategyAttempt, str | None]:
        """llm 策略：LLMGateway fix_patch。

        Returns:
            (attempt, patch_content)。
        """
        start = time.time()
        error: str | None = None
        patch_content: str | None = None
        tokens_used: int | None = None

        if self._llm_gateway is None:
            error = "llm_gateway unavailable"
        else:
            try:
                import asyncio

                messages = self._build_llm_messages(
                    bug_report_summary,
                    root_cause_location,
                    symptom_type,
                    kb_context,
                )
                resp: LLMResponse = asyncio.run(
                    self._llm_gateway.complete(  # type: ignore[arg-type]
                        prompt_type="fix_patch",
                        messages=messages,
                    )
                )
                diff = self._parse_diff(resp.content)
                if diff is None:
                    error = "empty or invalid diff content"
                else:
                    patch_content = diff
                    usage = resp.usage or {}
                    tokens_used = usage.get("total_tokens")
            except LLMError as e:
                error = str(e)
            except Exception as e:  # noqa: BLE001 — 非 LLMError 也降级
                error = f"{type(e).__name__}: {e}"

        latency_ms = max(1, int((time.time() - start) * 1000))
        succeeded = patch_content is not None
        return (
            StrategyAttempt(
                strategy_name="llm",
                succeeded=succeeded,
                error=None if succeeded else error,
                latency_ms=latency_ms,
                tokens_used=tokens_used,
                pattern_id=None,
                attempt_no=attempt_no,
            ),
            patch_content,
        )

    # ------------------------------------------------------------------
    # 策略 3：history_calibration（KB patch_history 校准）
    # ------------------------------------------------------------------
    def _try_history_calibration(
        self,
        kb_context: RetrievalResult | None,
        attempt_no: int,
    ) -> tuple[StrategyAttempt, str | None, str | None]:
        """history_calibration 策略：KB patch_history 校准。

        Returns:
            (attempt, patch_content, pattern_id)。
        """
        start = time.time()
        error: str | None = None
        patch_content: str | None = None
        pattern_id: str | None = None

        try:
            if kb_context is None:
                error = "kb_context unavailable"
            elif kb_context.degraded:
                error = "kb degraded"
            else:
                top1 = self._kb_layer_top1(
                    kb_context, "patch_history", HISTORY_SIMILARITY_THRESHOLD
                )
                if top1 is None:
                    raw_top = self._kb_layer_top1(
                        kb_context, "patch_history", 0.0
                    )
                    if raw_top is None:
                        error = "no patch_history hit"
                    else:
                        error = "similarity below threshold"
                else:
                    entry, _sim = top1
                    content = entry.content or {}
                    hist_patch = None
                    if isinstance(content, dict):
                        hist_patch = content.get("patch") or content.get(
                            "patch_content"
                        )
                    if not hist_patch:
                        error = "no history patch in entry"
                    else:
                        patch_content = hist_patch
                        pattern_id = entry.id
        except Exception as e:  # noqa: BLE001 — 降级不抛
            error = f"{type(e).__name__}: {e}"

        latency_ms = max(1, int((time.time() - start) * 1000))
        succeeded = patch_content is not None
        return (
            StrategyAttempt(
                strategy_name="history_calibration",
                succeeded=succeeded,
                error=None if succeeded else error,
                latency_ms=latency_ms,
                tokens_used=None,
                pattern_id=pattern_id,
                attempt_no=attempt_no,
            ),
            patch_content,
            pattern_id,
        )

    # ------------------------------------------------------------------
    # LLM prompt 构造
    # ------------------------------------------------------------------
    def _build_llm_messages(
        self,
        bug_report_summary: str,
        root_cause_location: str,
        symptom_type: str,
        kb_context: RetrievalResult | None,
    ) -> list[dict]:
        """构造 LLM prompt messages（system + user）。

        user message 含 root_cause_location + symptom_type + BugReport 摘要 +
        历史 patch 参考（若有 kb_context patch_history top1）。
        """
        user_parts: list[str] = []
        user_parts.append(f"根因定位：{root_cause_location}")
        user_parts.append(f"症状类型：{symptom_type}")
        user_parts.append(f"BugReport 摘要：\n{bug_report_summary}")

        # 历史 patch 参考（few-shot）
        if kb_context is not None and not kb_context.degraded:
            hist_top1 = self._kb_layer_top1(
                kb_context, "patch_history", HISTORY_SIMILARITY_THRESHOLD
            )
            if hist_top1 is not None:
                entry, _sim = hist_top1
                content = entry.content or {}
                if isinstance(content, dict):
                    ref_patch = content.get("patch") or content.get(
                        "patch_content"
                    )
                    if ref_patch:
                        user_parts.append(
                            f"历史 patch 参考（few-shot）：\n{ref_patch}"
                        )

        return [
            {"role": "system", "content": _LLM_SYSTEM_PROMPT},
            {"role": "user", "content": "\n\n".join(user_parts)},
        ]

    # ------------------------------------------------------------------
    # diff 解析（strip markdown 代码块）
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_diff(content: str) -> str | None:
        """解析 LLM 输出为 unified diff（strip markdown 代码块）。

        Returns:
            纯 diff 字符串；空内容或非 diff 格式返回 None。
        """
        if not content or not content.strip():
            return None
        text = content.strip()
        # strip markdown 代码块标记 ```diff ... ``` 或 ``` ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            # 去首行（```diff / ```）
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            # 去尾行（```）
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        # 校验是否为 diff 格式（含 --- / +++ 或 @@ 标记）
        if "---" not in text and "@@" not in text:
            return None
        return text

    # ------------------------------------------------------------------
    # files_changed 提取（+++ b/xxx）
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_files_changed(patch_content: str) -> list[str]:
        """从 unified diff 提取变更文件列表（+++ b/xxx）。

        去重，保留顺序。
        """
        files: list[str] = []
        seen: set[str] = set()
        for line in patch_content.splitlines():
            if line.startswith("+++ b/"):
                path = line[6:].strip()
                # 去除可能的 \t 前缀和后续内容
                path = path.split("\t")[0].strip()
                if path and path not in seen:
                    seen.add(path)
                    files.append(path)
        return files

    # ------------------------------------------------------------------
    # KB 层 top1 检索辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _kb_layer_top1(
        kb_context: RetrievalResult | None,
        target_layer: str,
        threshold: float,
    ) -> tuple[Any, float] | None:
        """取 kb_context 指定层 top1（similarity >= threshold）。

        kb_context.entries 按 similarity 降序排列（BF005 保证）。

        Args:
            kb_context: 检索结果集。
            target_layer: 目标层（pattern / patch_history）。
            threshold: 相似度阈值。

        Returns:
            (KBEntry, similarity) 或 None。
        """
        if kb_context is None or kb_context.degraded:
            return None
        for re in kb_context.entries:
            if re.entry.layer == target_layer and re.similarity >= threshold:
                return (re.entry, re.similarity)
        return None

    # ------------------------------------------------------------------
    # 模板渲染
    # ------------------------------------------------------------------
    @staticmethod
    def _render_template(
        template: str, **kwargs: str
    ) -> str:
        """渲染 patch_template（简单变量替换）。

        支持 {root_cause_location} / {symptom_type} 等占位符替换。
        未匹配的占位符保留原样（避免 KeyError）。
        """
        try:
            return template.format_map(_SafeDict(kwargs))
        except Exception:  # noqa: BLE001 — 渲染失败返回原模板
            return template


class _SafeDict(dict):  # noqa: SLOT000 — dict subclass for format_map
    """安全 dict：format_map 缺 key 时返回空串（不抛 KeyError）。"""

    def __missing__(self, key: str) -> str:
        return ""
