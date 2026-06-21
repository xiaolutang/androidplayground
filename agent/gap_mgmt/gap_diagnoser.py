"""缺口诊断器（R001-BB010）—— 四类缺口识别 + 写 CapabilityGap(waiting)。

依据：
- Sprint Contract R001-BB010（status: agreed，mode: direct / Mode 2）
- 依赖 BF008 GapStore（7 态状态机 + INV-2 软删）
- 信息缺口来源：BB001 ISM INSUFFICIENT
- 模式缺口来源：BB006 dim_patternability 低
- 设施缺口来源：emulator/ADB/LLM 不可用
- 模型缺口来源：LLM 推理失败/超限/拒绝

设计要点：
1. **四类缺口映射**（``_GAP_CLASSIFICATION``）：trigger_source →
   (gap_type, waiting_reason, suggested_action) 规则映射表。
   MVP 不引入 ML 分类器，规则映射足够（见 Phase 2 简化审查）。
2. **GapDiagnosisResult**：dataclass 统一返回结构，含 gap_id / gap_type /
   description / waiting_reason / linked_bug_ids / suggested_action / reasoning。
3. **写 CapabilityGap(waiting)**：``GapStore.create`` 强制初始 status=IDENTIFIED，
   故先 create 后 transition(WAITING)（IDENTIFIED -> WAITING 在状态矩阵中合法）。
4. **降级**：
   - ``gap_store=None`` → 抛 ValueError（必须注入）
   - ``gap_store.create`` / ``transition`` 异常 → 返回 ``diagnosed=False``
   - 未知 ``trigger_source`` → 默认 information 类型 + warning
5. **不持久化 reasoning**：reasoning 仅放在返回结果，CapabilityGap schema 无
   对应字段（description 已含人类可读摘要）。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from agent.gap.gap_store import GapStore
from agent.schemas.capability_gap import CapabilityGapStatus

logger = logging.getLogger(__name__)

__all__ = [
    "GapDiagnosisResult",
    "GapDiagnoser",
]


# ---------------------------------------------------------------------------
# 四类缺口分类规则表
# ---------------------------------------------------------------------------
# trigger_source -> (gap_type, waiting_reason, suggested_action)
#
# gap_type 四类（design 4.1 CapabilityGap.gap_type）：
# - information：信息缺口（需人工补复现步骤/环境/日志）
# - facility：设施缺口（emulator/ADB/LLM 不可用）
# - pattern：模式缺口（KB pattern 未学到，需 BB015 人修录入）
# - model：模型缺口（LLM 推理失败/超限/拒绝）
#
# step_exhausted 兜底映射到 coverage（与 HypothesisEngine._create_budget_gap
# gap_type 口径一致：非被推翻根因 → coverage）。
_GAP_CLASSIFICATION: dict[str, tuple[str, str, str]] = {
    "ism_insufficient": (
        "information",
        "information_missing",
        "等待人工补充复现步骤/环境/日志等信息",
    ),
    "emulator_unavailable": (
        "facility",
        "facility_unavailable",
        "等待 emulator 可用后重跑",
    ),
    "adb_offline": (
        "facility",
        "facility_unavailable",
        "检查 ADB 连接 / 等待设备上线",
    ),
    "kb_pattern_miss": (
        "pattern",
        "pattern_not_learned",
        "由 BB015 人工录入 pattern / 补充 KB",
    ),
    "llm_failure": (
        "model",
        "model_unable",
        "换模型 / 降级到规则路径",
    ),
    "llm_timeout": (
        "model",
        "model_unable",
        "换模型或调超时上限 / 降级",
    ),
    "step_exhausted": (
        "coverage",
        "budget_exhausted",
        "提升步数预算 / 细化 playbook 覆盖",
    ),
}

# 默认分类（未知 trigger_source）：information + warning
_DEFAULT_CLASSIFICATION: tuple[str, str, str] = (
    "information",
    "information_missing",
    "人工排查后补充信息或修复触发源",
)


@dataclass
class GapDiagnosisResult:
    """缺口诊断结果。

    Attributes:
        diagnosed: True=已写入 CapabilityGap；False=写入失败（gap_store 异常等）。
        gap_id: 写入的 CapabilityGap id；未写入时为 None。
        gap_type: 缺口类型（information/facility/pattern/model/coverage）。
        description: 人类可读的缺口描述。
        waiting_reason: 等待原因（information_missing/facility_unavailable/
                        pattern_not_learned/model_unable/budget_exhausted）。
        linked_bug_ids: 关联的 bug_report ids（含触发 bug_report_id）。
        suggested_action: 建议补齐动作（人类可读）。
        reasoning: 解释链（人类可读；不持久化到 CapabilityGap）。
    """

    diagnosed: bool
    gap_id: Optional[str]
    gap_type: str
    description: str
    waiting_reason: str
    linked_bug_ids: list[str] = field(default_factory=list)
    suggested_action: str = ""
    reasoning: str = ""


class GapDiagnoser:
    """缺口诊断器：识别四类缺口 + 写 CapabilityGap(waiting)。

    四类 gap_type：
    1. information（信息缺口）：ISMLevel.INSUFFICIENT，需人工补信息
       （复现步骤/环境/日志）。
    2. facility（设施缺口）：emulator 不可用 / LLM 不可达 / ADB offline。
    3. pattern（模式缺口）：KB pattern 未学到（dim_pattern 低），需 BB015 人修录入。
    4. model（模型缺口）：LLM 推理失败/超限/拒绝，需换模型或降级。

    Usage:
        diagnoser = GapDiagnoser(gap_store=gap_store)
        result = diagnoser.diagnose(
            bug_report_id="bug-001",
            trigger_context={"trigger_source": "ism_insufficient", ...},
        )
        if result.diagnosed:
            # result.gap_id 已写入 CapabilityGap(status=waiting)
            ...

    Args:
        gap_store: BF008 GapStore（必需；None 抛 ValueError）。
    """

    def __init__(self, *, gap_store: Any) -> None:
        if gap_store is None:
            raise ValueError("gap_store is required (got None)")
        # 运行时再次校验类型 duck typing：必须有 create + transition 方法
        if not (hasattr(gap_store, "create") and hasattr(gap_store, "transition")):
            raise ValueError(
                f"gap_store must have create() and transition() methods, "
                f"got {type(gap_store).__name__}"
            )
        self._gap_store: GapStore = gap_store

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def diagnose(
        self,
        *,
        bug_report_id: str,
        trigger_context: dict,
        symptom_type: Optional[str] = None,
    ) -> GapDiagnosisResult:
        """识别缺口类型并写入 CapabilityGap。

        Args:
            bug_report_id: 触发缺口的 BugReport id。
            trigger_context: 触发上下文，格式::

                {
                    "trigger_source": "ism_insufficient" /
                                      "emulator_unavailable" /
                                      "adb_offline" /
                                      "kb_pattern_miss" /
                                      "llm_failure" /
                                      "llm_timeout" /
                                      "step_exhausted" / ...,
                    "ism_result": {...},            # 可选
                    "facility_error": str,          # 可选
                    "kb_retrieval_result": {...},   # 可选
                    "llm_error": str,               # 可选
                    "hypothesis_id": str,           # 可选
                }

            symptom_type: 症状类型（可选，仅用于 description 上下文）。

        Returns:
            GapDiagnosisResult（diagnosed=True 表示已写入 CapabilityGap(waiting)）。
        """
        # 1. 分类
        gap_type, waiting_reason, suggested_action = self._classify_gap(trigger_context)

        # 2. 构造人类可读描述
        description = self._build_description(
            trigger_context=trigger_context,
            gap_type=gap_type,
            bug_report_id=bug_report_id,
            symptom_type=symptom_type,
        )

        # 3. 构造 reasoning（解释链）
        reasoning = self._build_reasoning(
            trigger_context=trigger_context,
            gap_type=gap_type,
            waiting_reason=waiting_reason,
        )

        # 4. 写入 CapabilityGap(waiting)
        gap_id = self._write_gap(
            bug_report_id=bug_report_id,
            gap_type=gap_type,
            description=description,
            waiting_reason=waiting_reason,
        )

        return GapDiagnosisResult(
            diagnosed=gap_id is not None,
            gap_id=gap_id,
            gap_type=gap_type,
            description=description,
            waiting_reason=waiting_reason,
            linked_bug_ids=[bug_report_id] if gap_id is not None else [],
            suggested_action=suggested_action,
            reasoning=reasoning,
        )

    # ------------------------------------------------------------------
    # 内部辅助：分类
    # ------------------------------------------------------------------
    def _classify_gap(
        self,
        trigger_context: dict,
    ) -> tuple[str, str, str]:
        """trigger_source → (gap_type, waiting_reason, suggested_action)。

        未知 trigger_source → 默认 information + warning。
        """
        trigger_source = trigger_context.get("trigger_source")
        if trigger_source is None:
            logger.warning(
                "GapDiagnoser: trigger_context missing 'trigger_source' field; "
                "defaulting to information gap (ctx keys=%s)",
                list(trigger_context.keys()),
            )
            return _DEFAULT_CLASSIFICATION

        classification = _GAP_CLASSIFICATION.get(trigger_source)
        if classification is None:
            logger.warning(
                "GapDiagnoser: unknown trigger_source=%r; "
                "defaulting to information gap",
                trigger_source,
            )
            return _DEFAULT_CLASSIFICATION

        return classification

    # ------------------------------------------------------------------
    # 内部辅助：描述构造
    # ------------------------------------------------------------------
    def _build_description(
        self,
        *,
        trigger_context: dict,
        gap_type: str,
        bug_report_id: str,
        symptom_type: Optional[str],
    ) -> str:
        """构造人类可读的缺口描述。

        描述必须含 trigger_source 上下文（测试 14 验证）。
        """
        trigger_source = trigger_context.get("trigger_source", "unknown")
        parts: list[str] = [
            f"[{gap_type}] gap for bug={bug_report_id}",
            f"trigger_source={trigger_source}",
        ]
        if symptom_type:
            parts.append(f"symptom={symptom_type}")

        # 附加 trigger_context 中的关键上下文字段（人类可读）
        facility_error = trigger_context.get("facility_error")
        if facility_error:
            parts.append(f"facility_error={facility_error}")
        llm_error = trigger_context.get("llm_error")
        if llm_error:
            parts.append(f"llm_error={llm_error}")
        hypothesis_id = trigger_context.get("hypothesis_id")
        if hypothesis_id:
            parts.append(f"hypothesis={hypothesis_id}")
        ism_result = trigger_context.get("ism_result")
        if isinstance(ism_result, dict):
            ism_level = ism_result.get("level") or ism_result.get("degraded")
            parts.append(f"ism_level={ism_level}")

        return "; ".join(parts)

    # ------------------------------------------------------------------
    # 内部辅助：reasoning 构造
    # ------------------------------------------------------------------
    def _build_reasoning(
        self,
        *,
        trigger_context: dict,
        gap_type: str,
        waiting_reason: str,
    ) -> str:
        """构造解释链（人类可读，不持久化）。"""
        trigger_source = trigger_context.get("trigger_source", "unknown")
        return (
            f"trigger_source={trigger_source} → classified as gap_type={gap_type} "
            f"(waiting_reason={waiting_reason})"
        )

    # ------------------------------------------------------------------
    # 内部辅助：写入 CapabilityGap(waiting)
    # ------------------------------------------------------------------
    def _write_gap(
        self,
        *,
        bug_report_id: str,
        gap_type: str,
        description: str,
        waiting_reason: str,
    ) -> Optional[str]:
        """写入 CapabilityGap(status=waiting)。

        GapStore.create 强制初始 status=IDENTIFIED，故先 create 再
        transition(WAITING)。两步任一失败均返回 None（不抛异常）。

        Args:
            bug_report_id: 关联的 bug_report id。
            gap_type: 缺口类型。
            description: 人类可读描述。
            waiting_reason: 等待原因（记录到 description 末尾，schema 无独立字段）。

        Returns:
            写入成功的 gap_id；失败返回 None。
        """
        gap_id = uuid.uuid4().hex
        # waiting_reason schema 无独立字段，附在 description 后便于后续追溯
        full_description = f"{description}; waiting_reason={waiting_reason}"

        gap_data = {
            "id": gap_id,
            "gap_type": gap_type,
            "description": full_description,
            "source_bug_id": bug_report_id,
            "linked_bug_ids": [bug_report_id],
        }

        try:
            self._gap_store.create(gap_data)
        except Exception as exc:
            logger.warning(
                "GapDiagnoser: gap_store.create failed for bug=%s "
                "gap_type=%s trigger_source context: %s",
                bug_report_id,
                gap_type,
                exc,
            )
            return None

        # create 成功后 transition IDENTIFIED -> WAITING
        try:
            self._gap_store.transition(
                gap_id,
                CapabilityGapStatus.WAITING,
                reason=f"diagnosed by GapDiagnoser: {waiting_reason}",
            )
        except Exception as exc:
            logger.warning(
                "GapDiagnoser: gap_store.transition(IDENTIFIED->WAITING) "
                "failed for gap=%s (created but not transitioned): %s",
                gap_id,
                exc,
            )
            # gap 已创建但未迁到 WAITING：返回 gap_id 但调用方应感知 status 可能仍是 IDENTIFIED
            # 为保持契约清晰（diagnosed=True 意味着 status=waiting），
            # 此处返回 None 让调用方重试 / 记录失败。
            return None

        return gap_id
