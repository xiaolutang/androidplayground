"""信息完备度评估器 ISM（R001-BB001）。

依据：
- Sprint Contract R001-BB001（status: agreed，8 AC）
- 依赖 INF04（LLMGateway）/ BF005（RetrievalResult / RetrievedEntry）/ SCH01（BugReport）

设计要点：
1. **三档分级**（ISMLevel）：score >= 0.8 SUFFICIENT / 0.5..0.8 BORDERLINE / <0.5 INSUFFICIENT。
   level **由 score + 阈值重算**（AC-2），不信任 LLM 返回的 level 字段，防止幻觉。
2. **临界追问**（AC-3）：BORDERLINE 时 clarify_questions 非空（从 KB 派生或 LLM 生成）；
   SUFFICIENT / INSUFFICIENT 时 clarify_questions 清空（[]）。
3. **不足降级**（AC-4）：INSUFFICIENT → degraded=True，Orchestrator 据此转 Tier3/4。
4. **LLM 失败降级**（AC-8）：LLMGateway 抛 LLMError 时，返回
   ISMResult(level=INSUFFICIENT, score=0.0, gaps=[], clarify_questions=[],
   degraded=True, reasoning="LLM failure: ...")，不向调用方抛异常。
5. **KB 派生 gaps 候选**（AC-6）：从 kb_context.entries 派生 A/B/C/D 候选，
   注入 user prompt 辅助 LLM 判断；kb_context=None 时候选为空，不阻塞。
6. **gaps 分类**（AC-7）：A=复现 / B=环境 / C=日志 / D=预期；非 A/B/C/D 元素被过滤。
7. **duck typing**（AC-1）：bug_report 接受 BugReport ORM 对象或 dict，
   通过 _get_field 辅助函数统一访问字段。
8. **JSON 解析容错**（AC-5）：支持 ```json``` 围栏与裸 JSON；解析失败 / 缺 score →
   降级 insufficient + degraded=True；gaps 非法元素过滤。

边界：
- 不更新 BugReport 状态（Orchestrator 负责）。
- 不实现用户交互（FF001 / FB004 负责）。
- 不持久化（纯计算函数）。
- 不自行检索 KB（消费传入的 kb_context）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agent.infra.llm_gateway import LLMError, LLMGateway
from agent.kb.retriever import RetrievedEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 阈值常量（MVP design 默认值，可通过构造参数覆盖）
# ---------------------------------------------------------------------------
ISM_THRESHOLD_SUFFICIENT: float = 0.8
ISM_THRESHOLD_BORDERLINE: float = 0.5

# 合法 gaps 标签
_GAP_LABELS: frozenset[str] = frozenset({"A", "B", "C", "D"})

# gap 类别 → 默认追问模板（KB 候选或 LLM 未生成时兜底）
_GAP_CLARIFY_TEMPLATES: dict[str, str] = {
    "A": "请提供详细的复现步骤或触发条件",
    "B": "请补充环境信息（版本号 / 设备型号 / OS 版本）",
    "C": "请附上崩溃堆栈或 logcat 日志",
    "D": "请描述期望行为与实际行为的对比",
}


class ISMLevel(str, Enum):
    """信息完备度三档枚举（AC-2）。

    ISMResult.level 输出枚举值字符串（"sufficient" / "borderline" / "insufficient"），
    便于 JSON 序列化与跨模块比较。
    """

    SUFFICIENT = "sufficient"
    BORDERLINE = "borderline"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class ISMResult:
    """信息完备度评估结果（AC-1）。

    Attributes:
        level: 评估等级（ISMLevel.*.value，"sufficient"/"borderline"/"insufficient"）。
        score: 完备度分数 [0.0, 1.0]。
        gaps: 信息缺口分类列表（元素为 "A"/"B"/"C"/"D"）。
        clarify_questions: 追问问题列表（仅 borderline 时非空）。
        degraded: 是否降级（仅 insufficient 时 True）。
        reasoning: LLM 推理摘要或降级原因。
    """

    level: str
    score: float
    gaps: list[str] = field(default_factory=list)
    clarify_questions: list[str] = field(default_factory=list)
    degraded: bool = False
    reasoning: str = ""


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """duck typing 字段访问（AC-1）。

    优先 getattr（ORM 对象），失败回退 dict.get（dict 输入）。
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _compute_level(
    score: float,
    threshold_sufficient: float,
    threshold_borderline: float,
) -> ISMLevel:
    """根据 score + 阈值重算 level（AC-2，>= 语义）。

    - score >= threshold_sufficient → SUFFICIENT
    - threshold_borderline <= score < threshold_sufficient → BORDERLINE
    - score < threshold_borderline → INSUFFICIENT
    """
    if score >= threshold_sufficient:
        return ISMLevel.SUFFICIENT
    if score >= threshold_borderline:
        return ISMLevel.BORDERLINE
    return ISMLevel.INSUFFICIENT


def _filter_gaps(raw: Any) -> list[str]:
    """过滤 gaps：仅保留 A/B/C/D（AC-7）。"""
    if not isinstance(raw, list):
        return []
    seen: list[str] = []
    for g in raw:
        if isinstance(g, str) and g in _GAP_LABELS and g not in seen:
            seen.append(g)
    return seen


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_llm_json(content: str) -> dict | None:
    """解析 LLM 返回的 JSON（AC-5）。

    支持格式：
    - ```json ... ``` 围栏
    - 裸 JSON 对象

    Returns:
        解析后的 dict；失败返回 None。
    """
    if not content or not content.strip():
        return None

    # 优先尝试围栏提取
    m = _JSON_FENCE_RE.search(content)
    candidate = m.group(1) if m else content

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # 围栏失败 → 尝试从裸文本中提取首个 {...}
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(content[start : end + 1])
            except (json.JSONDecodeError, ValueError):
                return None
        else:
            return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _extract_score(parsed: dict) -> float | None:
    """提取 score（AC-5 缺 score → None，由调用方降级）。"""
    raw = parsed.get("score")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    # 钳制到 [0.0, 1.0]
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def _derive_gaps_from_kb(kb_context: list[RetrievedEntry] | None) -> list[str]:
    """从 KB 检索结果派生 gaps 候选（AC-6）。

    策略（MVP 简化）：
    - 遍历 entries，从 KBEntry.content.metadata.gap_hint 或 content.gap_hint 提取候选。
    - kb_context=None 或空 → 候选为空（不阻塞 LLM 评估）。
    - 检索质量低（kb_context 对应的 RetrievalResult.degraded=True）不影响提取：
      只要 entries 非空且含 gap_hint，候选就会被提取（AC-6 Contract 语义）。

    Returns:
        去重后的 A/B/C/D 候选列表（可能为空）。
    """
    if not kb_context:
        return []

    candidates: list[str] = []
    for retrieved in kb_context:
        entry = getattr(retrieved, "entry", None)
        if entry is None:
            continue
        content = getattr(entry, "content", None)
        if not isinstance(content, dict):
            continue
        # 优先读 metadata.gap_hint / gap_hint 字段
        metadata = content.get("metadata") or {}
        hint = metadata.get("gap_hint") or content.get("gap_hint")
        if isinstance(hint, list):
            for g in hint:
                if isinstance(g, str) and g in _GAP_LABELS and g not in candidates:
                    candidates.append(g)
        elif isinstance(hint, str) and hint in _GAP_LABELS and hint not in candidates:
            candidates.append(hint)

    return candidates


def _build_clarify_questions(
    gaps: list[str],
    llm_questions: list[str] | None,
) -> list[str]:
    """构造 clarify_questions（AC-3）。

    仅在 borderline 时由调用方调用：
    - 优先使用 LLM 生成的非空问题；
    - LLM 未生成 → 从 gaps 派生默认模板。
    """
    if llm_questions:
        # 过滤空字符串
        cleaned = [q.strip() for q in llm_questions if isinstance(q, str) and q.strip()]
        if cleaned:
            return cleaned
    # 从 gaps 派生兜底问题
    return [_GAP_CLARIFY_TEMPLATES[g] for g in gaps if g in _GAP_CLARIFY_TEMPLATES]


# ---------------------------------------------------------------------------
# InfoSufficiencyEvaluator
# ---------------------------------------------------------------------------
class InfoSufficiencyEvaluator:
    """信息完备度评估器（ISM）。

    输入 BugReport + KB 检索结果，调 LLMGateway 评估信息完备度，
    输出 ISMResult（level 由 score + 阈值重算，不信任 LLM 返回的 level）。

    Usage:
        evaluator = InfoSufficiencyEvaluator(llm_gateway)
        result = await evaluator.evaluate(bug_report, kb_context=kb_entries)
        if result.level == ISMLevel.BORDERLINE.value:
            # 触发追问子回路
            ...
    """

    def __init__(
        self,
        llm: LLMGateway,
        threshold_sufficient: float = ISM_THRESHOLD_SUFFICIENT,
        threshold_borderline: float = ISM_THRESHOLD_BORDERLINE,
    ) -> None:
        self._llm = llm
        self._threshold_sufficient = threshold_sufficient
        self._threshold_borderline = threshold_borderline

    async def evaluate(
        self,
        bug_report: Any,
        kb_context: list[RetrievedEntry] | None = None,
    ) -> ISMResult:
        """评估信息完备度（AC-1 主入口）。

        Args:
            bug_report: BugReport ORM 对象或 dict（duck typing）。
            kb_context: KB 检索结果条目列表（None 时 gaps 候选为空）。

        Returns:
            ISMResult（level / score / gaps / clarify_questions / degraded / reasoning）。

        Notes:
            - LLMError 被内部捕获，降级为 insufficient + degraded=True（AC-8）。
            - 非法 JSON / 缺 score 同样降级（AC-5）。
            - level 由 score + 阈值重算，不信任 LLM 返回的 level（AC-2）。
        """
        # AC-6：从 KB 派生 gaps 候选（None → 空）
        kb_gaps = _derive_gaps_from_kb(kb_context)

        # 构造 prompt 并调 LLM（AC-5）
        messages = self._build_messages(bug_report, kb_gaps)
        try:
            # NOTE: prompt_type="symptom_classify" 是 Contract AC-5 的约定值。
            # INF04 _PROMPT_TYPE_TO_CHANNEL 将其路由到 text 通道（glm-5.1）。
            # 语义上是信息完备度评估而非症状分类，但 INF04 未定义 info_sufficiency
            # prompt_type，text 通道下各 prompt_type 功能等价，故沿用 Contract 约定。
            resp = await self._llm.complete(
                prompt_type="symptom_classify",
                messages=messages,
            )
        except LLMError as e:
            # AC-8：LLM 失败降级
            logger.warning("ISM LLM call failed, degrading: %s", e)
            return ISMResult(
                level=ISMLevel.INSUFFICIENT.value,
                score=0.0,
                gaps=[],
                clarify_questions=[],
                degraded=True,
                reasoning=f"LLM failure: {e}",
            )

        # AC-5：解析 JSON
        parsed = _parse_llm_json(resp.content)
        if parsed is None:
            logger.warning("ISM LLM returned non-JSON content, degrading")
            return ISMResult(
                level=ISMLevel.INSUFFICIENT.value,
                score=0.0,
                gaps=[],
                clarify_questions=[],
                degraded=True,
                reasoning="LLM failure: invalid JSON response",
            )

        # AC-5：提取 score（缺失 → 降级）
        score = _extract_score(parsed)
        if score is None:
            logger.warning("ISM LLM JSON missing score field, degrading")
            return ISMResult(
                level=ISMLevel.INSUFFICIENT.value,
                score=0.0,
                gaps=[],
                clarify_questions=[],
                degraded=True,
                reasoning="LLM failure: missing score in JSON response",
            )

        # AC-7：过滤 gaps
        gaps = _filter_gaps(parsed.get("gaps"))

        # AC-2：level 由 score 重算（不信任 LLM level）
        level = _compute_level(
            score, self._threshold_sufficient, self._threshold_borderline
        )

        # reasoning
        reasoning = parsed.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        # AC-3：clarify_questions 仅 borderline 时非空
        if level is ISMLevel.BORDERLINE:
            raw_qs = parsed.get("clarify_questions")
            llm_qs = raw_qs if isinstance(raw_qs, list) else None
            clarify_questions = _build_clarify_questions(gaps, llm_qs)
            # 若派生仍为空（无 gaps 也无 LLM 问题），兜底一条通用追问
            if not clarify_questions:
                clarify_questions = ["请补充更多 bug 相关信息以便进一步分诊"]
            degraded = False
        else:
            # sufficient / insufficient → 清空
            clarify_questions = []
            degraded = level is ISMLevel.INSUFFICIENT

        return ISMResult(
            level=level.value,
            score=score,
            gaps=gaps,
            clarify_questions=clarify_questions,
            degraded=degraded,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # prompt 构造
    # ------------------------------------------------------------------
    def _build_messages(
        self,
        bug_report: Any,
        kb_gaps: list[str],
    ) -> list[dict]:
        """构造 LLM messages（AC-5 system + user）。

        Args:
            bug_report: BugReport 或 dict。
            kb_gaps: 从 KB 派生的 gaps 候选（A/B/C/D）。

        Returns:
            [{"role": "system", ...}, {"role": "user", ...}]
        """
        system = (
            "你是 bug 分诊专家。评估 bug 报告的信息完备度。"
            "根据提供的 bug 报告内容和 KB 检索候选，判断信息是否足够进入自动修复流程。\n\n"
            "评估维度（gaps 分类）：\n"
            "- A: 复现信息（步骤/触发条件）\n"
            "- B: 环境信息（版本/设备型号/OS）\n"
            "- C: 日志信息（堆栈/logcat/crash log）\n"
            "- D: 预期信息（期望行为/实际行为对比）\n\n"
            "仅输出 JSON："
            '{"score": 0.0-1.0, "gaps": ["A","B","C","D"], '
            '"clarify_questions": ["..."], "reasoning": "..."}'
        )

        # duck typing 提取 BugReport 摘要字段
        version_code = _get_field(bug_report, "version_code", "")
        symptom_type = _get_field(bug_report, "symptom_type", "")
        raw_report = _get_field(bug_report, "raw_report", "")
        raw_report_str = json.dumps(
            raw_report, ensure_ascii=False
        ) if isinstance(raw_report, (dict, list)) else str(raw_report)
        # 截断超长 raw_report
        if len(raw_report_str) > 500:
            raw_report_str = raw_report_str[:500] + "...(truncated)"

        kb_gaps_str = ", ".join(kb_gaps) if kb_gaps else "(无)"

        user = (
            f"Bug 报告摘要：\n"
            f"- version_code: {version_code}\n"
            f"- symptom_type: {symptom_type}\n"
            f"- raw_report: {raw_report_str}\n\n"
            f"KB 检索候选 gaps：{kb_gaps_str}"
        )

        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]


__all__ = [
    "ISMLevel",
    "ISMResult",
    "InfoSufficiencyEvaluator",
    "ISM_THRESHOLD_SUFFICIENT",
    "ISM_THRESHOLD_BORDERLINE",
]
