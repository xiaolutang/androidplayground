"""症状分类器（R001-BB002）。

依据：
- Sprint Contract R001-BB002（status: agreed，AC: crash/blank/loading/no_response/data_error 分类正确）
- 依赖 INF04（LLMGateway）/ SCH01（BugReport）
- 参考同类实现 ``info_sufficiency_evaluator.py``（ISM）：LLM 调用 + JSON 解析 + 规则兜底

设计要点：
1. **5 类症状枚举**（``SymptomType``）：crash / blank / loading / no_response / data_error，
   与 ``playbook.schema.VALID_SYMPTOM_TYPES`` 对齐（design 4.1 第 543 行）。
2. **LLM 主路径**：调 ``llm.complete(prompt_type="symptom_classify", messages=...)``，
   system prompt 限定输出 JSON ``{"symptom_type", "confidence", "reasoning"}``。
3. **JSON 解析容错**（复用 ISM 三路径风格）：```json``` 围栏 / 裸 JSON / `{...}` 子串提取。
4. **LLM 失败 / 非法 symptom_type / JSON 解析失败 → 规则兜底**：
   - 关键字映射表从 ``stacktrace`` + ``error_type`` + ``raw_report`` 文本推断；
   - 兜底结果 ``confidence=0.3, degraded=True, fallback_used=True``；
   - 无匹配关键字 → ``data_error``（AC 默认分类）。
5. **duck typing**：``bug_report`` 接受 BugReport ORM 对象或 dict（与 ISM 一致），
   通过 ``_get_field`` 统一访问；``error_type`` / ``stacktrace`` 既可顶层字段，
   也可嵌在 ``raw_report`` dict 内。

边界：
- 不更新 BugReport.symptom_type（Orchestrator 负责）。
- 不消费 KB 检索结果（BB003 信号匹配负责）。
- 不持久化（纯计算函数）。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from agent.infra.llm_gateway import LLMError, LLMGateway

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 枚举与结果
# ---------------------------------------------------------------------------
class SymptomType(str, Enum):
    """5 类症状枚举（design 4.1 第 543 行）。

    与 ``playbook.schema.VALID_SYMPTOM_TYPES`` 对齐；``str, Enum`` 便于
    JSON 序列化与跨模块字符串比较（``SymptomType.CRASH == "crash"``）。
    """

    CRASH = "crash"
    BLANK = "blank"
    LOADING = "loading"
    NO_RESPONSE = "no_response"
    DATA_ERROR = "data_error"


# 合法 symptom_type 集合（用于 LLM 返回值校验）
_VALID_SYMPTOM_VALUES: frozenset[str] = frozenset(s.value for s in SymptomType)


@dataclass(frozen=True)
class ClassificationResult:
    """症状分类结果。

    Attributes:
        symptom_type: 分类结果（SymptomType.*.value 字符串）。
        confidence: 置信度 [0.0, 1.0]；LLM 路径透传，规则兜底固定 0.3。
        reasoning: LLM 推理摘要或规则兜底原因。
        degraded: 是否降级（LLM 失败 / 非法输出走规则兜底时 True）。
        fallback_used: 是否使用了规则兜底（与 degraded 同时为 True；
            LLM 成功路径均为 False）。
    """

    symptom_type: str
    confidence: float
    reasoning: str
    degraded: bool
    fallback_used: bool


# ---------------------------------------------------------------------------
# 规则兜底关键字映射表
# ---------------------------------------------------------------------------
# 顺序敏感：从前到后匹配，首个命中即返回。
# 关键字同时覆盖英文（stacktrace 常见）与中文（raw_report 常见）。
_FALLBACK_KEYWORDS: list[tuple[tuple[str, ...], SymptomType]] = [
    (
        ("FATAL EXCEPTION", "AndroidRuntime", "SIGSEGV", "SIGABRT",
         "NullPointerException", "crash", "崩溃", "闪退"),
        SymptomType.CRASH,
    ),
    (
        ("white screen", "空白", "blank", "白屏", "黑屏", "empty screen"),
        SymptomType.BLANK,
    ),
    (
        ("loading", "加载", "spinner", "转圈", "进度条", "stuck on loading"),
        SymptomType.LOADING,
    ),
    (
        ("ANR", "no response", "无响应", "not responding", "卡死", "frozen"),
        SymptomType.NO_RESPONSE,
    ),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """duck typing 字段访问。

    优先 getattr（ORM 对象），失败回退 dict.get（dict 输入）。
    与 ISM 的同名辅助函数语义一致。
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_llm_json(content: str) -> dict | None:
    """解析 LLM 返回的 JSON。

    支持格式（与 ISM 三路径风格一致）：
    - ```json ... ``` 围栏
    - 裸 JSON 对象
    - 文本中 ``{...}`` 子串提取

    Returns:
        解析后的 dict；失败返回 None。
    """
    if not content or not content.strip():
        return None

    # 路径 1：围栏提取
    m = _JSON_FENCE_RE.search(content)
    candidate = m.group(1) if m else content

    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        # 路径 2：从裸文本提取首个 {...}
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


def _extract_confidence(parsed: dict) -> float | None:
    """提取 confidence 并钳制到 [0.0, 1.0]。

    缺失 / 非法 → None（由调用方降级）。
    """
    raw = parsed.get("confidence")
    if raw is None:
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def _build_bug_summary(bug_report: Any) -> str:
    """构造 user prompt 中的 bug 摘要（duck typing）。

    提取顺序（兼容 BugReport ORM 与 dict）：
    - ``error_type``：顶层字段优先，回退 raw_report.error_type
    - ``stacktrace``：顶层字段优先，回退 raw_report.stacktrace
    - ``raw_report``：整体摘要（dict/list → JSON，截断 500 字符）

    Returns:
        拼接后的摘要文本（用于 LLM user prompt）。
    """
    error_type = _get_field(bug_report, "error_type", None)
    stacktrace = _get_field(bug_report, "stacktrace", None)
    raw_report = _get_field(bug_report, "raw_report", None)

    # raw_report 内嵌回退（常见于 webhook 上报结构）
    if error_type is None and isinstance(raw_report, dict):
        error_type = raw_report.get("error_type")
    if stacktrace is None and isinstance(raw_report, dict):
        stacktrace = raw_report.get("stacktrace")

    raw_report_str = (
        json.dumps(raw_report, ensure_ascii=False)
        if isinstance(raw_report, (dict, list))
        else str(raw_report or "")
    )
    if len(raw_report_str) > 500:
        raw_report_str = raw_report_str[:500] + "...(truncated)"

    parts: list[str] = []
    if error_type:
        parts.append(f"error_type: {error_type}")
    if stacktrace:
        # stacktrace 可能很长，截断
        st_str = stacktrace if isinstance(stacktrace, str) else str(stacktrace)
        if len(st_str) > 800:
            st_str = st_str[:800] + "...(truncated)"
        parts.append(f"stacktrace: {st_str}")
    parts.append(f"raw_report: {raw_report_str}")
    return "\n".join(parts)


def _rule_fallback(bug_report: Any) -> ClassificationResult:
    """规则兜底分类（LLM 失败 / 非法输出时调用）。

    从 stacktrace / error_type / raw_report 文本中按关键字映射表推断；
    无匹配 → data_error（AC 默认分类）。

    Returns:
        ``ClassificationResult``（confidence=0.3, degraded=True, fallback_used=True）。
    """
    summary = _build_bug_summary(bug_report).lower()
    matched: SymptomType = SymptomType.DATA_ERROR
    for keywords, symptom in _FALLBACK_KEYWORDS:
        if any(kw.lower() in summary for kw in keywords):
            matched = symptom
            break

    return ClassificationResult(
        symptom_type=matched.value,
        confidence=0.3,
        reasoning=f"rule fallback: matched {matched.value} via keywords",
        degraded=True,
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# SymptomClassifier
# ---------------------------------------------------------------------------
class SymptomClassifier:
    """症状分类器（BB002 主入口）。

    输入 BugReport（ORM 或 dict），调 LLMGateway 分类症状类型；
    LLM 失败 / 非法输出时走规则兜底（关键字映射表）。

    Usage:
        classifier = SymptomClassifier(llm_gateway)
        result = await classifier.classify(bug_report)
        if result.symptom_type == SymptomType.CRASH.value:
            # 路由到 crash playbook
            ...
    """

    # system prompt（任务规格指定文案，限定输出 JSON schema）
    _SYSTEM_PROMPT = (
        "你是移动端 bug 分诊专家，分类症状类型。"
        "仅输出 JSON："
        '{"symptom_type": "crash|blank|loading|no_response|data_error", '
        '"confidence": 0.0-1.0, "reasoning": "..."}'
    )

    def __init__(self, llm: LLMGateway) -> None:
        self._llm = llm

    async def classify(self, bug_report: Any) -> ClassificationResult:
        """分类症状类型（AC 主入口）。

        Args:
            bug_report: BugReport ORM 对象或 dict（duck typing）。

        Returns:
            ClassificationResult（symptom_type / confidence / reasoning /
            degraded / fallback_used）。

        Notes:
            - LLMError / 非法 JSON / 非法 symptom_type → 规则兜底
              （degraded=True, fallback_used=True, confidence=0.3）。
            - LLM 成功路径透传 confidence，degraded/fallback_used 均为 False。
        """
        messages = self._build_messages(bug_report)

        # ---- LLM 主路径 ----
        try:
            resp = await self._llm.complete(
                prompt_type="symptom_classify",
                messages=messages,
            )
        except LLMError as e:
            logger.warning("SymptomClassifier LLM call failed, fallback: %s", e)
            return _rule_fallback(bug_report)

        # ---- JSON 解析 ----
        parsed = _parse_llm_json(resp.content)
        if parsed is None:
            logger.warning(
                "SymptomClassifier LLM returned non-JSON, fallback. content=%r",
                resp.content[:200],
            )
            return _rule_fallback(bug_report)

        # ---- symptom_type 校验 ----
        raw_symptom = parsed.get("symptom_type")
        if not isinstance(raw_symptom, str) or raw_symptom not in _VALID_SYMPTOM_VALUES:
            logger.warning(
                "SymptomClassifier LLM returned invalid symptom_type=%r, fallback",
                raw_symptom,
            )
            return _rule_fallback(bug_report)

        # ---- confidence 提取（缺失/非法 → 兜底默认 0.5）----
        confidence = _extract_confidence(parsed)
        if confidence is None:
            logger.warning(
                "SymptomClassifier LLM JSON missing/invalid confidence, use 0.5"
            )
            confidence = 0.5

        reasoning = parsed.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        return ClassificationResult(
            symptom_type=raw_symptom,
            confidence=confidence,
            reasoning=reasoning,
            degraded=False,
            fallback_used=False,
        )

    # ------------------------------------------------------------------
    # prompt 构造
    # ------------------------------------------------------------------
    def _build_messages(self, bug_report: Any) -> list[dict]:
        """构造 LLM messages（system + user）。

        Args:
            bug_report: BugReport 或 dict。

        Returns:
            [{"role": "system", ...}, {"role": "user", ...}]
        """
        summary = _build_bug_summary(bug_report)
        user = f"Bug 报告摘要：\n{summary}"
        return [
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]


__all__ = [
    "SymptomType",
    "ClassificationResult",
    "SymptomClassifier",
]
