"""诊断报告生成器（R001-BB012）。

依据：
- Sprint Contract R001-BB012（status: direct, mode: Mode 2 直接验收）
- 任务包 R001-BB012（JSON + markdown 双输出；字段缺失降级输出不崩）
- SCH02 Trajectory / BugReport / HypothesisNode / ConfidenceScore / CapabilityGap 关联

设计要点：
1. **双格式输出**：``to_json`` 返回 API 友好的 JSON 字符串；``to_markdown`` 返回人可读
   markdown。两种格式基于同一 ``DiagnosisReport`` 内存表示。
2. **字段缺失降级**：任何输入字段缺失或读取异常 → 用 None / "N/A" 占位，不抛错。
   每个字段独立 try/except，确保单字段异常不影响整体输出。
3. **duck typing**：``_safe_get`` 统一处理 ORM 对象（getattr）/ dict（.get）/ dataclass
   （getattr），调用方无需关心输入类型。
4. **Tier3/4 主产出**：Tier1/2 走修复 PR 不生成报告，但 Orchestrator 可选生成。
5. **MVP 简化**：不引入 jinja2 / 模板引擎，markdown 手写拼接（足够 MVP 场景）。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

__all__ = [
    "DiagnosisReport",
    "DiagnosisReportGenerator",
]


# ---------------------------------------------------------------------------
# DiagnosisReport dataclass（内存表示）
# ---------------------------------------------------------------------------


@dataclass
class DiagnosisReport:
    """诊断报告（内存表示）。

    所有字段已在 generate 阶段降级处理，此 dataclass 只承载最终结果。

    Attributes:
        bug_id: BugReport.id（None 降级为 "unknown"）。
        symptom_type: 症状类型（crash/blank/loading/...）。
        root_cause: 根因字典 {file, line, function, snippet, confidence}；未定位为 None。
        confirmed_hypotheses: confirmed 假设摘要列表。
        trajectory_summary: 轨迹摘要 {total_steps, total_budget, mode}。
        confidence_score: 置信度字典 {tier, score, dimensions}；None 表示无评估。
        gaps: CapabilityGap 摘要列表。
        is_located: root_cause 是否已定位。
        generated_at: ISO 8601 时间戳。
    """

    bug_id: str
    symptom_type: Optional[str]
    root_cause: Optional[dict]
    confirmed_hypotheses: list[dict]
    trajectory_summary: dict
    confidence_score: Optional[dict]
    gaps: list[dict]
    is_located: bool
    generated_at: str


# ---------------------------------------------------------------------------
# DiagnosisReportGenerator
# ---------------------------------------------------------------------------


class DiagnosisReportGenerator:
    """诊断报告生成器：聚合多源数据 -> JSON + markdown。

    Tier3/4 主产出（Tier1/2 走修复 PR 不生成报告，但 Orchestrator 可选生成）。
    字段缺失降级输出不崩：任何字段缺失/异常 -> 用 None / "N/A" 占位，不抛错。

    Usage:
        gen = DiagnosisReportGenerator()
        report = gen.generate(
            bug_report=bug, trajectory=traj,
            confirmed_hypotheses=hyps, confidence_score=cs,
            gaps=gaps_list, root_cause=rc,
        )
        json_str = gen.to_json(report)
        md_str = gen.to_markdown(report)
    """

    def __init__(
        self,
        *,
        timestamp_provider: Optional[Callable[[], str]] = None,
    ) -> None:
        """初始化报告生成器。

        Args:
            timestamp_provider: 自定义时间戳提供函数（测试注入用）；默认 UTC ISO 8601。
        """
        self._timestamp_provider = timestamp_provider or self._default_timestamp

    @staticmethod
    def _default_timestamp() -> str:
        """默认时间戳：UTC ISO 8601。"""
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _fmt_num(value: Any, precision: int = 2) -> str:
        """格式化数值：float -> f".{precision}f"，其他 -> str，None -> "N/A"。"""
        if value is None:
            return "N/A"
        if isinstance(value, (int, float)):
            return f"{value:.{precision}f}"
        return str(value)

    # ------------------------------------------------------------------
    # duck typing 辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_get(
        obj: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        """duck typing 读字段（异常返回 default）。

        - dict 输入：``obj.get(key, default)``
        - 其他（ORM / dataclass / SimpleNamespace）：``getattr(obj, key, default)``
        - 任何异常（包括 ``__getattr__`` 抛错）→ default

        Args:
            obj: 输入对象（dict / ORM / dataclass / SimpleNamespace）。
            key: 字段名。
            default: 读取失败时的默认值。

        Returns:
            字段值或 default。
        """
        try:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)
        except Exception:
            return default

    # ------------------------------------------------------------------
    # _build_xxx_dict 系列（每个独立 try/except，单字段异常不崩）
    # ------------------------------------------------------------------

    def _build_root_cause_dict(
        self,
        root_cause: Any,
    ) -> Optional[dict]:
        """RootCauseLocation -> dict。

        读 located / file / line / function / snippet / confidence 字段。
        located=False 或读取异常 -> None。
        """
        if root_cause is None:
            return None
        try:
            located = self._safe_get(root_cause, "located", False)
            if not located:
                return None
            return {
                "file": self._safe_get(root_cause, "file"),
                "line": self._safe_get(root_cause, "line"),
                "function": self._safe_get(root_cause, "function"),
                "snippet": self._safe_get(root_cause, "snippet"),
                "confidence": self._safe_get(root_cause, "confidence"),
            }
        except Exception:
            return None

    def _build_hypothesis_summary(
        self,
        hypothesis: Any,
    ) -> dict:
        """HypothesisNode -> dict（confirmed 假设摘要）。

        读 id / content / status / step_used 字段。
        """
        try:
            return {
                "id": self._safe_get(hypothesis, "id", "unknown"),
                "content": self._safe_get(hypothesis, "content")
                or self._safe_get(hypothesis, "hypothesis_text")
                or "N/A",
                "status": (
                    # HypothesisStatus enum 或 str
                    self._safe_get(hypothesis, "status", "confirmed").value
                    if hasattr(
                        self._safe_get(hypothesis, "status", "confirmed"),
                        "value",
                    )
                    else self._safe_get(hypothesis, "status", "confirmed")
                ),
                "step_used": self._safe_get(hypothesis, "step_used", 0),
            }
        except Exception:
            return {
                "id": "unknown",
                "content": "N/A",
                "status": "confirmed",
                "step_used": 0,
            }

    def _build_confidence_dict(
        self,
        confidence_score: Any,
    ) -> Optional[dict]:
        """ConfidenceScore -> dict。

        读 tier / score / dim_info_completeness / dim_verification_feasibility /
        dim_patternability 字段。
        """
        if confidence_score is None:
            return None
        try:
            return {
                "tier": self._safe_get(confidence_score, "tier"),
                "score": self._safe_get(confidence_score, "score"),
                "dim_info": self._safe_get(
                    confidence_score, "dim_info_completeness"
                ),
                "dim_verify": self._safe_get(
                    confidence_score, "dim_verification_feasibility"
                ),
                "dim_pattern": self._safe_get(
                    confidence_score, "dim_patternability"
                ),
            }
        except Exception:
            return None

    def _build_gap_dict(
        self,
        gap: Any,
    ) -> dict:
        """CapabilityGap -> dict（缺口摘要）。

        读 id / gap_type / description 字段。
        """
        try:
            return {
                "id": self._safe_get(gap, "id", "unknown"),
                "gap_type": self._safe_get(gap, "gap_type", "N/A"),
                "description": self._safe_get(gap, "description", "N/A"),
            }
        except Exception:
            return {
                "id": "unknown",
                "gap_type": "N/A",
                "description": "N/A",
            }

    def _build_trajectory_summary(
        self,
        trajectory: Any,
    ) -> dict:
        """Trajectory -> dict（轨迹摘要）。

        读 total_step_used / total_step_budget 字段。
        """
        if trajectory is None:
            return {}
        try:
            return {
                "total_steps": self._safe_get(trajectory, "total_step_used", 0),
                "total_budget": self._safe_get(
                    trajectory, "total_step_budget"
                ),
                "mode": "standard",
            }
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # generate（主入口）
    # ------------------------------------------------------------------

    def generate(
        self,
        *,
        bug_report: Any,
        trajectory: Any,
        confirmed_hypotheses: Optional[list[Any]],
        confidence_score: Any | None,
        gaps: Optional[list[Any]],
        root_cause: Any | None,
    ) -> DiagnosisReport:
        """聚合多源数据生成报告。每个字段独立 try/except，缺失降级。

        Args:
            bug_report: BugReport ORM / dict / SimpleNamespace；None 降级 bug_id="unknown"。
            trajectory: Trajectory ORM / dict / None。
            confirmed_hypotheses: list[HypothesisNode]；None/[] 降级空列表。
            confidence_score: ConfidenceScore / None。
            gaps: list[CapabilityGap]；None/[] 降级空列表。
            root_cause: RootCauseLocation / None。

        Returns:
            DiagnosisReport 内存表示。
        """
        # bug_report 降级
        try:
            if bug_report is None:
                bug_id = "unknown"
                symptom_type = None
            else:
                bug_id = self._safe_get(bug_report, "id", "unknown")
                symptom_type = self._safe_get(bug_report, "symptom_type")
        except Exception:
            bug_id = "unknown"
            symptom_type = None

        # trajectory 降级
        traj_summary = self._build_trajectory_summary(trajectory)

        # confirmed_hypotheses 降级
        try:
            if not confirmed_hypotheses:
                hyp_summaries: list[dict] = []
            else:
                hyp_summaries = [
                    self._build_hypothesis_summary(h) for h in confirmed_hypotheses
                ]
        except Exception:
            hyp_summaries = []

        # confidence_score 降级
        conf_dict = self._build_confidence_dict(confidence_score)

        # gaps 降级
        try:
            if not gaps:
                gap_summaries: list[dict] = []
            else:
                gap_summaries = [self._build_gap_dict(g) for g in gaps]
        except Exception:
            gap_summaries = []

        # root_cause 降级
        rc_dict = self._build_root_cause_dict(root_cause)
        is_located = rc_dict is not None

        # timestamp
        try:
            generated_at = self._timestamp_provider()
        except Exception:
            generated_at = self._default_timestamp()

        return DiagnosisReport(
            bug_id=bug_id,
            symptom_type=symptom_type,
            root_cause=rc_dict,
            confirmed_hypotheses=hyp_summaries,
            trajectory_summary=traj_summary,
            confidence_score=conf_dict,
            gaps=gap_summaries,
            is_located=is_located,
            generated_at=generated_at,
        )

    # ------------------------------------------------------------------
    # to_json
    # ------------------------------------------------------------------

    def to_json(self, report: DiagnosisReport) -> str:
        """JSON 格式输出（API 友好）。

        Args:
            report: DiagnosisReport 内存表示。

        Returns:
            JSON 字符串（``json.dumps`` with indent=2, ensure_ascii=False）。
        """
        return json.dumps(asdict(report), indent=2, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------
    # to_markdown
    # ------------------------------------------------------------------

    def to_markdown(self, report: DiagnosisReport) -> str:
        """Markdown 格式输出（人可读）。

        每个章节独立生成，缺失章节标注 "N/A"。

        结构：
        # 诊断报告 - {bug_id}
        ## 症状
        ## 根因（如 located）
        ## 诊断路径（confirmed 假设）
        ## 置信度
        ## 缺口（如有）
        ## 元数据

        Args:
            report: DiagnosisReport 内存表示。

        Returns:
            markdown 字符串。
        """
        lines: list[str] = []

        # 标题块
        lines.append(f"# 诊断报告 - {report.bug_id}")
        lines.append("")
        lines.append(f"**生成时间**: {report.generated_at}")
        lines.append(
            f"**症状类型**: {report.symptom_type or 'N/A'}"
        )
        lines.append(
            f"**根因定位**: {'已定位' if report.is_located else '未定位'}"
        )
        lines.append("")

        # 根因（如 located）
        lines.append("## 根因")
        if report.is_located and report.root_cause:
            rc = report.root_cause
            file_val = rc.get("file") or "N/A"
            line_val = rc.get("line") or "N/A"
            func_val = rc.get("function") or "N/A"
            conf_str = self._fmt_num(rc.get("confidence"))
            snippet = rc.get("snippet")
            lines.append(f"- 文件: `{file_val}:{line_val}`")
            lines.append(f"- 函数: `{func_val}`")
            lines.append(f"- 置信度: {conf_str}")
            if snippet:
                lines.append("- 代码片段:")
                lines.append("  ```")
                for snippet_line in str(snippet).splitlines():
                    lines.append(f"  {snippet_line}")
                lines.append("  ```")
            else:
                lines.append("- 代码片段: N/A")
        else:
            lines.append("N/A")
        lines.append("")

        # 诊断路径
        lines.append("## 诊断路径")
        if report.confirmed_hypotheses:
            for hyp in report.confirmed_hypotheses:
                hid = hyp.get("id", "unknown")
                content = hyp.get("content", "N/A")
                status = hyp.get("status", "confirmed")
                step = hyp.get("step_used", 0)
                lines.append(
                    f"- **{hid}** (status={status}, steps={step}): {content}"
                )
        else:
            lines.append("N/A")
        lines.append("")

        # 置信度
        lines.append("## 置信度")
        if report.confidence_score:
            cs = report.confidence_score
            tier = cs.get("tier", "N/A")
            lines.append(f"- Tier: {tier}")
            lines.append(f"- 综合: {self._fmt_num(cs.get('score'))}")
            lines.append(f"- 信息维度: {self._fmt_num(cs.get('dim_info'))}")
            lines.append(f"- 验证维度: {self._fmt_num(cs.get('dim_verify'))}")
            lines.append(f"- 模式维度: {self._fmt_num(cs.get('dim_pattern'))}")
        else:
            lines.append("N/A")
        lines.append("")

        # 缺口
        lines.append("## 缺口")
        if report.gaps:
            for gap in report.gaps:
                gid = gap.get("id", "unknown")
                gtype = gap.get("gap_type", "N/A")
                gdesc = gap.get("description", "N/A")
                lines.append(f"- **{gid}** (type={gtype}): {gdesc}")
        else:
            lines.append("N/A")
        lines.append("")

        # 元数据
        lines.append("## 元数据")
        ts = report.trajectory_summary
        total_steps = ts.get("total_steps", "N/A") if ts else "N/A"
        total_budget = ts.get("total_budget", "N/A") if ts else "N/A"
        mode = ts.get("mode", "N/A") if ts else "N/A"
        lines.append(f"- 总步数: {total_steps} / {total_budget}")
        lines.append(f"- 模式: {mode}")
        lines.append("")

        return "\n".join(lines)
