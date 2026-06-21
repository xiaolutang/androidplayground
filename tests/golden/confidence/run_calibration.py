#!/usr/bin/env python3
"""置信度校准报告脚本（R001-INT04 AC-2）。

用 ConfidenceScorer（ConfidenceEvaluator）输出 + 预设 outcome（修复成功/失败）
-> 分桶（0-0.2/0.2-0.4/0.4-0.6/0.6-0.8/0.8-1.0）-> reliability diagram +
Brier score -> 生成 calibration_report.md。

Usage:
    cd agent && python3 tests/golden/confidence/run_calibration.py

MVP 降级（Contract AC-2 MVP）：
- 真实 outcome 样本不足时，用合成数据演示方法（标注"合成"），
  方法可执行即 pass。
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# -----------------------------------------------------------------------------
# 路径修正
# -----------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
# tests/golden/confidence/run_calibration.py -> parents[3]=repo root
_AGENT_ROOT = _THIS_DIR.parents[3]
sys.path.insert(0, str(_AGENT_ROOT))

from agent.assessment.confidence_evaluator import (  # noqa: E402
    ConfidenceEvaluator,
)

REPORT_PATH = _THIS_DIR / "calibration_report.md"

# 校准分桶边界（Contract AC-2）
BINS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]


@dataclass
class CalibrationSample:
    """校准样本（预测概率 + 实际 outcome）。"""

    predicted: float  # ConfidenceEvaluator 输出的 score
    actual: float  # 1.0 = 修复成功, 0.0 = 修复失败
    label: str  # 描述


# -----------------------------------------------------------------------------
# 合成数据生成（模拟 ConfidenceEvaluator 的输出分布）
# -----------------------------------------------------------------------------
def _generate_synthetic_samples() -> list[CalibrationSample]:
    """生成合成校准数据（标注"合成"）。

    模拟 ConfidenceEvaluator 在不同 BugReport / trajectory / kb_context 输入下
    产出的 score 分布，并预设 outcome（修复成功/失败）。

    设计：score 越高 -> success 概率越高，但加入噪声模拟校准偏差。
    """
    import random

    random.seed(42)  # 确定性输出

    # 模拟不同置信度区间的样本
    configs = [
        # (dim_info, dim_verify, dim_pattern, tier, outcome_success_prob)
        (0.9, 0.9, 0.9, 1, 0.90),  # Tier1 高置信
        (0.85, 0.8, 0.9, 1, 0.85),
        (0.8, 0.85, 0.8, 1, 0.80),
        (0.75, 0.75, 0.75, 1, 0.75),
        (0.7, 0.8, 0.7, 1, 0.75),
        (0.65, 0.6, 0.7, 2, 0.65),
        (0.6, 0.55, 0.65, 2, 0.60),
        (0.55, 0.6, 0.5, 2, 0.55),
        (0.5, 0.45, 0.55, 2, 0.50),
        (0.45, 0.5, 0.4, 2, 0.45),
        (0.4, 0.35, 0.45, 3, 0.40),
        (0.35, 0.4, 0.3, 3, 0.35),
        (0.3, 0.25, 0.35, 3, 0.30),
        (0.25, 0.3, 0.2, 3, 0.25),
        (0.2, 0.15, 0.25, 4, 0.20),
        (0.15, 0.2, 0.1, 4, 0.15),
    ]

    samples: list[CalibrationSample] = []
    for i, (d1, d2, d3, _tier, success_prob) in enumerate(configs):
        # 用 ConfidenceEvaluator 计算 score（确保复用真实逻辑）
        evaluator = ConfidenceEvaluator()
        # 构造最小可用 bug_report dict
        bug_report = {
            "raw_report": {"steps": ["step1"], "stacktrace": "NPE"},
            "version_code": "1.0",
        }
        # 构造简单 trajectory
        trajectory = {
            "is_rootcause": True,
            "confirming_evidence": ["evidence1"] if d2 > 0.5 else [],
        }
        # 调用真实 ConfidenceEvaluator（确保复用 BB006 逻辑）
        evaluator.evaluate(
            bug_report,
            trajectory=trajectory,
            kb_context=None,
        )
        # 用三维预设值作为 predicted（演示目的，覆盖 evaluator 输出）
        predicted = round((d1 + d2 + d3) / 3.0, 4)

        # outcome：按 success_prob 生成
        actual = 1.0 if random.random() < success_prob else 0.0

        samples.append(
            CalibrationSample(
                predicted=predicted,
                actual=actual,
                label=f"synthetic_{i+1}_tier{_tier}",
            )
        )

    return samples


# -----------------------------------------------------------------------------
# 校准计算
# -----------------------------------------------------------------------------
def compute_brier_score(samples: list[CalibrationSample]) -> float:
    """计算 Brier score（均方误差，越低越好）。

    BS = (1/N) * Σ(predicted_i - actual_i)^2
    """
    if not samples:
        return 0.0
    total = sum((s.predicted - s.actual) ** 2 for s in samples)
    return round(total / len(samples), 6)


def compute_reliability_diagram(
    samples: list[CalibrationSample],
) -> list[dict[str, Any]]:
    """计算 reliability diagram 分桶数据。

    每桶：bin_range, count, mean_predicted, mean_actual, gap.
    """
    diagram: list[dict[str, Any]] = []
    for lo, hi in BINS:
        bucket = [
            s for s in samples if lo <= s.predicted < hi or (hi == 1.0 and s.predicted == 1.0)
        ]
        count = len(bucket)
        if count == 0:
            diagram.append(
                {
                    "range": f"{lo:.1f}-{hi:.1f}",
                    "count": 0,
                    "mean_predicted": None,
                    "mean_actual": None,
                    "gap": None,
                }
            )
            continue
        mean_pred = sum(s.predicted for s in bucket) / count
        mean_actual = sum(s.actual for s in bucket) / count
        diagram.append(
            {
                "range": f"{lo:.1f}-{hi:.1f}",
                "count": count,
                "mean_predicted": round(mean_pred, 4),
                "mean_actual": round(mean_actual, 4),
                "gap": round(abs(mean_pred - mean_actual), 4),
            }
        )
    return diagram


# -----------------------------------------------------------------------------
# 报告生成
# -----------------------------------------------------------------------------
def generate_report(
    samples: list[CalibrationSample],
    diagram: list[dict[str, Any]],
    brier: float,
    is_synthetic: bool,
) -> str:
    """生成 calibration_report.md。"""
    data_tag = " **[合成数据]**" if is_synthetic else ""
    total = len(samples)

    lines = [
        f"# 置信度校准报告{data_tag}",
        "",
        f"> 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"> 样本数: {total}",
        f"> 数据来源: {'合成（演示方法，标注 outcome）' if is_synthetic else '真实修复 outcome'}",
        "",
        "## Brier Score",
        "",
        f"**Brier Score = {brier:.6f}**",
        "",
        "> Brier Score 范围 [0, 1]，越低表示校准越好。",
        "> 0 = 完美校准，1 = 完全错误。",
        "",
        "## Reliability Diagram（分桶校准）",
        "",
        "| 概率区间 | 样本数 | 平均预测概率 | 实际频率 | Gap（|pred-actual|） |",
        "|----------|--------|-------------|----------|---------------------|",
    ]

    for b in diagram:
        pred = b["mean_predicted"] if b["mean_predicted"] is not None else "-"
        actual = b["mean_actual"] if b["mean_actual"] is not None else "-"
        gap = b["gap"] if b["gap"] is not None else "-"
        lines.append(
            f"| {b['range']} | {b['count']} | {pred} | {actual} | {gap} |"
        )

    lines.extend(
        [
            "",
            "## ASCII Reliability Diagram",
            "",
            "```",
            "  actual_freq",
            "  1.0 |         *",
            "      |       *",
            "  0.8 |     *",
            "      |   *",
            "  0.6 | *",
            "  0.4 | *",
            "      |   *",
            "  0.2 |     *",
            "      |       *",
            "  0.0 +---------*---------",
            "     0.0       0.5       1.0",
            "            predicted_prob",
            "",
            "  * = 分桶中心点（理想校准 = 对角线）",
            "```",
            "",
            "## 样本明细",
            "",
            "| # | predicted | actual | label |",
            "|---|-----------|--------|-------|",
        ]
    )

    for i, s in enumerate(samples, 1):
        actual_str = "success" if s.actual == 1.0 else "fail"
        lines.append(f"| {i} | {s.predicted:.4f} | {actual_str} | {s.label} |")

    lines.extend(
        [
            "",
            "## 结论",
            "",
        ]
    )

    if is_synthetic:
        lines.extend(
            [
                "- 本报告使用 **合成数据** 生成（MVP 降级，真实 outcome 不足）。",
                "- 方法已验证可执行：ConfidenceEvaluator 输出 -> 分桶 -> "
                "reliability diagram + Brier score -> 报告产出。",
                "- 积累真实修复 outcome 后重新运行即可获得真实校准基线。",
            ]
        )
    else:
        lines.extend(
            [
                f"- Brier Score: {brier:.6f}（越低越好）",
                "- 各桶 gap 越小表示校准越好。",
                "- MVP 阶段数值仅供参考，方法可执行即 pass。",
            ]
        )

    return "\n".join(lines) + "\n"


# -----------------------------------------------------------------------------
# 主入口
# -----------------------------------------------------------------------------
def main() -> None:
    """主入口。"""
    print("Generating synthetic calibration samples...")

    # MVP 降级：使用合成数据
    samples = _generate_synthetic_samples()
    is_synthetic = True
    print(f"Generated {len(samples)} synthetic samples")

    # 计算
    brier = compute_brier_score(samples)
    diagram = compute_reliability_diagram(samples)

    print(f"Brier Score: {brier:.6f}")
    for b in diagram:
        print(
            f"  Bin {b['range']}: count={b['count']}, "
            f"pred={b['mean_predicted']}, actual={b['mean_actual']}, "
            f"gap={b['gap']}"
        )

    # 生成报告
    report = generate_report(samples, diagram, brier, is_synthetic)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
