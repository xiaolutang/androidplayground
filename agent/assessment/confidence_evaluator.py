"""修复置信度评估器（R001-BB006）。

依据：
- Sprint Contract R001-BB006（status: agreed，8 AC）
- design 5.1 Tier 分流（第 759-762 行）/ 5.3 KB 降级对 pattern 维影响（第 821 行）
- 5.5 验收维度 tier 口径（第 832-844 行）/ ConfidenceScore schema（第 577-587 行）

设计要点：
1. **纯计算函数**（不调 LLM）：三维打分基于规则（BugReport 字段 + trajectory 状态 + KB 检索结果），
   确定性，无随机性。
2. **三维打分**：
   - dim_info_completeness（信息完备度）：优先复用 BB001 ISMResult.score，否则 BugReport 字段检查。
   - dim_verification_feasibility（验证可行性）：从 trajectory 推断根因 confirmed + 证据状态。
   - dim_patternability（模式化程度）：从 KB pattern 层命中条目数/top1 similarity/degraded 推断。
3. **Tier 分级**（确定性阈值，参数化待校准）：
   - Tier 1（自动修复）：三维均 >= 0.7
   - Tier 2（draft PR）：平均 >= 0.5 且无维度 < 0.3
   - Tier 3（缺口诊断）：平均 >= 0.3
   - Tier 4（仅记录）：其他
4. **KB 模式命中加成**（design 5.3 第 821 行）：
   - degraded/None → 0.2
   - 有 KB 无 pattern → 0.4
   - 1 条命中 → top1 similarity
   - >=2 条命中 → min(top1 + 0.1, 1.0)
5. **不持久化**：返回内存中的 ConfidenceScore 对象，调用方负责 DB 写入。
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any
from uuid import uuid4

from agent.schemas.confidence import ConfidenceScore

# ---------------------------------------------------------------------------
# 阈值常量（协商确定，参数化待校准，design 第 826 行）
# ---------------------------------------------------------------------------
TIER1_DIM_THRESHOLD: float = 0.7  # Tier1: 三维均 >= 此值
TIER2_AVG_THRESHOLD: float = 0.5  # Tier2: 三维平均 >= 此值
TIER2_DIM_FLOOR: float = 0.3  # Tier2: 无维度 < 此值
TIER3_AVG_THRESHOLD: float = 0.3  # Tier3: 三维平均 >= 此值

# KB pattern 维度打分
KB_PATTERN_BONUS: float = 0.1  # pattern 命中 >= 2 条的加成
KB_DEGRADED_PATTERN_SCORE: float = 0.2  # KB 降级 / None 时的 pattern 维度低分
KB_NO_PATTERN_HIT_SCORE: float = 0.4  # 有 KB 但无 pattern 命中的中低分

# trajectory=None 兜底分
NO_TRAJECTORY_VERIFY_SCORE: float = 0.3


class ConfidenceTier(IntEnum):
    """置信度分级（design 5.1 第 759-762 行）。

    - TIER_1：自动修复，提普通 PR（高置信）。
    - TIER_2：中置信，提 draft PR。
    - TIER_3：低置信，仅诊断建议。
    - TIER_4：极低置信，仅记录。
    """

    TIER_1 = 1
    TIER_2 = 2
    TIER_3 = 3
    TIER_4 = 4


_TIER_REASONS: dict[int, str] = {
    1: "all dims >= 0.7",
    2: "avg >= 0.5, no dim < 0.3",
    3: "avg >= 0.3",
    4: "avg < 0.3",
}


# ---------------------------------------------------------------------------
# 辅助函数（duck typing）
# ---------------------------------------------------------------------------
def _get_field(obj: Any, name: str, default: Any = None) -> Any:
    """duck typing 字段访问。

    优先 getattr（ORM 对象），失败回退 dict.get（dict 输入）。
    """
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """钳制 value 到 [lo, hi]。"""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ---------------------------------------------------------------------------
# 三维打分（纯函数，可独立单元测试）
# ---------------------------------------------------------------------------
def compute_dim_info(
    bug_report: Any,
    ism_result: Any | None = None,
) -> float:
    """dim_info_completeness 计算（AC-2）。

    优先级：
    1. ism_result 非 None → 复用 ism_result.score（BB001 LLM 精细评估）。
    2. 否则 → 规则简化版（检查 BugReport 字段）：
       - 有 reproduction_steps / raw_report 含步骤 → +0.3
       - 有 version_code / device_model → +0.2
       - 有 stacktrace / logs → +0.3
       - 有 expected_behavior → +0.2
       - 总分 clamp [0, 1]
    """
    # 优先复用 ISMResult.score
    if ism_result is not None:
        ism_score = _get_field(ism_result, "score", None)
        if isinstance(ism_score, int | float):
            return _clamp(float(ism_score))

    raw_report = _get_field(bug_report, "raw_report", None)
    version_code = _get_field(bug_report, "version_code", None)

    score = 0.0

    # 复现步骤（raw_report 中可能有 reproduction_steps / steps 字段）
    has_steps = False
    if isinstance(raw_report, dict):
        if raw_report.get("reproduction_steps") or raw_report.get("steps"):
            has_steps = True
    if not has_steps and isinstance(raw_report, str) and "step" in raw_report.lower():
        has_steps = True
    if has_steps:
        score += 0.3

    # 版本 / 设备信息
    has_env = bool(version_code)
    if not has_env and isinstance(raw_report, dict) and (
        raw_report.get("device_model") or raw_report.get("os_version")
    ):
        has_env = True
    if has_env:
        score += 0.2

    # 堆栈 / 日志
    stacktrace = _get_field(bug_report, "stacktrace", None)
    has_stack = bool(stacktrace)
    if not has_stack and isinstance(raw_report, dict) and (
        raw_report.get("stacktrace") or raw_report.get("logs")
    ):
        has_stack = True
    if not has_stack and isinstance(raw_report, str) and (
        "stack" in raw_report.lower() or "exception" in raw_report.lower()
    ):
        has_stack = True
    if has_stack:
        score += 0.3

    # 预期行为
    has_expected = False
    if isinstance(raw_report, dict) and (
        raw_report.get("expected_behavior") or raw_report.get("expected")
    ):
        has_expected = True
    if has_expected:
        score += 0.2

    return _clamp(score)


def compute_dim_verify(trajectory: Any | None) -> float:
    """dim_verification_feasibility 计算（AC-2）。

    从 trajectory 状态推断：
    - 有 confirmed hypothesis（is_rootcause=True 或 status="confirmed"）→ 基线 0.6
    - 有 confirming_evidence → +0.2
    - 无 falsifying_signal → +0.1
    - 无 overturning_signal → +0.1
    - trajectory=None → 0.3（低分兜底，无验证证据）
    - 总分 clamp [0, 1]
    """
    if trajectory is None:
        return NO_TRAJECTORY_VERIFY_SCORE

    # 检查是否有 hypotheses 字段（list[dict] 或 list[Hypothesis]）
    hypotheses = _get_field(trajectory, "hypotheses", None)
    if not hypotheses or not isinstance(hypotheses, list):
        # trajectory 本身可能是 Hypothesis 对象（简化输入）
        root = _get_field(trajectory, "root_hypothesis", None)
        if root is not None:
            hypotheses = [root]
        else:
            # 无 hypotheses 字段 → 检查 trajectory 自身字段
            hypotheses = [trajectory]

    score = 0.0
    has_confirmed = False

    for hyp in hypotheses:
        if hyp is None:
            continue
        is_rootcause = _get_field(hyp, "is_rootcause", None)
        status = _get_field(hyp, "status", None)
        if is_rootcause is True or status == "confirmed":
            has_confirmed = True
            confirming = _get_field(hyp, "confirming_evidence", None)
            falsifying = _get_field(hyp, "falsifying_signal", None)
            overturning = _get_field(hyp, "overturning_signal", None)

            base = 0.6
            bonus = 0.0
            if confirming:
                bonus += 0.2
            if not falsifying:
                bonus += 0.1
            if not overturning:
                bonus += 0.1
            score = max(score, base + bonus)

    if not has_confirmed:
        score = 0.3

    return _clamp(score)


def compute_dim_pattern(
    kb_context: Any | None,
) -> tuple[float, dict | None]:
    """dim_patternability 计算（AC-4，KB 模式命中加成）。

    返回 (dim_score, kb_pattern_hit)：
    - kb_context=None → (0.2, None)
    - degraded=True → (0.2, dict with degraded=True)
    - 有 entries 但无 pattern 层命中 → (0.4, dict)
    - pattern 命中 1 条 → (top1_similarity, dict)
    - pattern 命中 >= 2 条 → (min(top1 + 0.1, 1.0), dict)
    """
    if kb_context is None:
        return (KB_DEGRADED_PATTERN_SCORE, None)

    degraded = _get_field(kb_context, "degraded", False)
    entries = _get_field(kb_context, "entries", None) or []

    if degraded:
        return (
            KB_DEGRADED_PATTERN_SCORE,
            {
                "layer": "pattern",
                "top1_similarity": None,
                "hit_count": 0,
                "degraded": True,
            },
        )

    # 筛选 pattern 层命中
    pattern_entries: list[float] = []
    for entry in entries:
        if entry is None:
            continue
        kb_entry = _get_field(entry, "entry", entry)
        layer = _get_field(kb_entry, "layer", None)
        if layer == "pattern":
            sim = _get_field(entry, "similarity", 0.0)
            if not isinstance(sim, int | float):
                sim = 0.0
            pattern_entries.append(float(sim))

    hit_count = len(pattern_entries)

    if hit_count == 0:
        return (
            KB_NO_PATTERN_HIT_SCORE,
            {
                "layer": "pattern",
                "top1_similarity": None,
                "hit_count": 0,
                "degraded": False,
            },
        )

    pattern_entries.sort(reverse=True)
    top1_sim = pattern_entries[0]

    if hit_count >= 2:
        dim_score = min(top1_sim + KB_PATTERN_BONUS, 1.0)
    else:
        dim_score = _clamp(top1_sim)

    return (
        dim_score,
        {
            "layer": "pattern",
            "top1_similarity": round(top1_sim, 6),
            "hit_count": hit_count,
            "degraded": False,
        },
    )


def classify_tier(
    d1: float,
    d2: float,
    d3: float,
) -> int:
    """三维分数 → Tier 分级（AC-3，确定性阈值规则）。

    - Tier 1：三维均 >= TIER1_DIM_THRESHOLD(0.7)
    - Tier 2：不满足 Tier1，平均 >= TIER2_AVG_THRESHOLD(0.5) 且无维度 < TIER2_DIM_FLOOR(0.3)
    - Tier 3：不满足 Tier2，平均 >= TIER3_AVG_THRESHOLD(0.3)
    - Tier 4：其他
    """
    avg = (d1 + d2 + d3) / 3.0

    # Tier 1
    if d1 >= TIER1_DIM_THRESHOLD and d2 >= TIER1_DIM_THRESHOLD and d3 >= TIER1_DIM_THRESHOLD:
        return ConfidenceTier.TIER_1

    # Tier 2
    if avg >= TIER2_AVG_THRESHOLD and min(d1, d2, d3) >= TIER2_DIM_FLOOR:
        return ConfidenceTier.TIER_2

    # Tier 3
    if avg >= TIER3_AVG_THRESHOLD:
        return ConfidenceTier.TIER_3

    # Tier 4
    return ConfidenceTier.TIER_4


def build_rationale(
    tier: int,
    d1: float,
    d2: float,
    d3: float,
    avg: float,
) -> str:
    """构造 rationale 字符串（AC-5）。

    格式：dim_info=X, dim_verify=Y, dim_pattern=Z, avg=A → Tier N (reason)
    """
    reason = _TIER_REASONS.get(tier, "unknown")
    return (
        f"dim_info={d1:.2f}, dim_verify={d2:.2f}, dim_pattern={d3:.2f}, "
        f"avg={avg:.2f} → Tier {tier} ({reason})"
    )


# ---------------------------------------------------------------------------
# ConfidenceEvaluator
# ---------------------------------------------------------------------------
class ConfidenceEvaluator:
    """修复置信度评估器（纯规则计算，不调 LLM）。

    三维打分（info/verify/pattern）→ Tier 1-4 分级。

    Usage:
        evaluator = ConfidenceEvaluator()
        score = evaluator.evaluate(
            bug_report, trajectory=traj, kb_context=kb_result,
        )
        if score.tier == 1:
            # 自动修复路径
            ...
    """

    def evaluate(
        self,
        bug_report: Any,
        *,
        trajectory: Any | None = None,
        kb_context: Any | None = None,
        ism_result: Any | None = None,
    ) -> ConfidenceScore:
        """评估修复置信度，返回 ConfidenceScore（不持久化）。

        Args:
            bug_report: BugReport ORM 对象或 dict（duck typing）。
            trajectory: Trajectory 对象 / dict / Hypothesis dict / None。
            kb_context: RetrievalResult 对象或 None。
            ism_result: BB001 ISM 评估结果（可选，复用 info 维度评分）。

        Returns:
            ConfidenceScore 对象（内存中，调用方负责持久化）。
        """
        # 三维打分
        d1 = compute_dim_info(bug_report, ism_result)
        d2 = compute_dim_verify(trajectory)
        d3, kb_pattern_hit = compute_dim_pattern(kb_context)

        # Tier 分级
        tier = classify_tier(d1, d2, d3)

        # 校准用 score（三维平均）
        avg = round((d1 + d2 + d3) / 3.0, 4)

        # rationale
        rationale = build_rationale(tier, d1, d2, d3, avg)

        return ConfidenceScore(
            id=str(uuid4()),
            bug_report_id=None,
            dim_info_completeness=d1,
            dim_verification_feasibility=d2,
            dim_patternability=d3,
            kb_pattern_hit=kb_pattern_hit,
            tier=tier,
            score=avg,
            rationale=rationale,
        )


__all__ = [
    "ConfidenceTier",
    "ConfidenceEvaluator",
    "ConfidenceScore",
    # 阈值常量
    "TIER1_DIM_THRESHOLD",
    "TIER2_AVG_THRESHOLD",
    "TIER2_DIM_FLOOR",
    "TIER3_AVG_THRESHOLD",
    "KB_PATTERN_BONUS",
    "KB_DEGRADED_PATTERN_SCORE",
    "KB_NO_PATTERN_HIT_SCORE",
    "NO_TRAJECTORY_VERIFY_SCORE",
    # 纯函数（单元测试直接调用）
    "compute_dim_info",
    "compute_dim_verify",
    "compute_dim_pattern",
    "classify_tier",
    "build_rationale",
]
