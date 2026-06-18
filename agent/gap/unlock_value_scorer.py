"""unlock_value 评分：estimated_unlock_value = 频率 x 可修复比例。

依据：
- .dev-flow/R001/analysis/2026-06-16--client-bug-fix-agent-backend.md D12（第 861 行）
- D12 公式：estimated_unlock_value = 同类 bug 历史频率 x 补齐后可修复比例
- 两因子均从 MetricPoint / 历史 trajectory 统计

设计要点：
1. **frequency（频率因子）**：同一 gap_type 在 MetricPoint（ref_gap_type 字段）中
   出现的归一化频率 = 该 gap_type 的 MetricPoint 数 / 全部 MetricPoint 数。
   反映该类能力缺口出现的频繁程度。
2. **fix_ratio（可修复比例因子）**：同一 gap_type 下，MetricPoint 中 effectiveness
   维度（修复成功率）记录的 value 均值。effectiveness 的 value 本身就是
   修复成功率（0.0~1.0），取均值即为"补齐后可修复比例"的统计估计。
   若无 effectiveness 数据，退化为 0.0（保守估计：无历史数据不支持可修复判断）。
3. **estimated_unlock_value = frequency x fix_ratio**，两因子均裁剪到 [0, 1]。
4. 数据来源忠于 D12："两因子均从 MetricPoint / 历史 trajectory 统计"。
   - frequency 用 MetricPoint.ref_gap_type 统计出现频率
   - fix_ratio 用 MetricPoint(effectiveness) 的 value 均值（即历史修复成功率）

字段映射确认：
- MetricPoint.metric_type: 五维枚举（effectiveness/safety/coverage/growth/cost）
- MetricPoint.value: 指标值（float）
- MetricPoint.ref_gap_type: 成长性专用，关联缺口类型（信息/设施/模式/模型）
- CapabilityGap.gap_type: 信息/设施/模式/模型
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from agent.schemas.capability_gap import CapabilityGap
from agent.schemas.metric_point import MetricPoint, MetricType

__all__ = [
    "UnlockFactors",
    "UnlockValueScorer",
]


@dataclass(frozen=True)
class UnlockFactors:
    """unlock_value 的两个因子及乘积。

    Attributes:
        frequency: 归一化频率 [0.0, 1.0]，同类 bug 历史出现频率。
        fix_ratio: 可修复比例 [0.0, 1.0]，补齐后可修复比例。
        estimated_unlock_value: frequency x fix_ratio。
    """

    frequency: float
    fix_ratio: float
    estimated_unlock_value: float

    @classmethod
    def compute(cls, frequency: float, fix_ratio: float) -> "UnlockFactors":
        """裁剪输入到 [0, 1] 并计算乘积。

        Args:
            frequency: 原始频率值（可能超出 [0,1]，会被裁剪）。
            fix_ratio: 原始可修复比例（可能超出 [0,1]，会被裁剪）。

        Returns:
            UnlockFactors，frequency/fix_ratio 已裁剪，estimated_unlock_value 为乘积。
        """
        f = max(0.0, min(1.0, frequency))
        r = max(0.0, min(1.0, fix_ratio))
        return cls(
            frequency=f,
            fix_ratio=r,
            estimated_unlock_value=f * r,
        )


class UnlockValueScorer:
    """从 MetricPoint 统计 frequency 与 fix_ratio，计算 unlock_value。

    D12 两因子统计口径：
    - frequency: gap.gap_type 在 MetricPoint.ref_gap_type 中的出现频率
    - fix_ratio: 同 gap_type 下 MetricPoint(effectiveness).value 的均值
    """

    def __init__(self, session_factory: sessionmaker):
        self._session_factory = session_factory

    def score(self, gap: CapabilityGap) -> UnlockFactors:
        """计算一个 gap 的 unlock_value。

        Args:
            gap: 目标 CapabilityGap（需有 gap_type 字段）。

        Returns:
            UnlockFactors，含 frequency / fix_ratio / estimated_unlock_value。

        Note:
            若 gap.gap_type 为 None，frequency 和 fix_ratio 均返回 0.0
            （无法分类则无法统计同类频率与可修复比例）。
        """
        gap_type = gap.gap_type
        if not gap_type:
            # 无 gap_type 无法做"同类"统计，保守返回 0
            return UnlockFactors.compute(frequency=0.0, fix_ratio=0.0)

        frequency = self._compute_frequency(gap_type)
        fix_ratio = self._compute_fix_ratio(gap_type)
        return UnlockFactors.compute(frequency=frequency, fix_ratio=fix_ratio)

    def _compute_frequency(self, gap_type: str) -> float:
        """该 gap_type 在 MetricPoint.ref_gap_type 中的归一化频率。

        frequency = count(ref_gap_type == gap_type) / count(all MetricPoint)

        若 MetricPoint 表为空，返回 0.0（无历史数据）。
        """
        with self._session_factory() as session:
            total = session.scalar(
                select(func.count(MetricPoint.id))
            )
            if not total:
                return 0.0
            same = session.scalar(
                select(func.count(MetricPoint.id)).where(
                    MetricPoint.ref_gap_type == gap_type
                )
            )
            return (same or 0) / total

    def _compute_fix_ratio(self, gap_type: str) -> float:
        """同 gap_type 下 effectiveness 维度的 value 均值。

        fix_ratio = avg(MetricPoint.value) where metric_type=effectiveness
                    and ref_gap_type=gap_type

        effectiveness 的 value 语义为修复成功率（design 4.1 第 639 行 + 5.5），
        取均值即为"补齐后可修复比例"的统计估计。

        若无匹配数据，返回 0.0（保守：无历史可修复证据）。
        """
        with self._session_factory() as session:
            avg_value = session.scalar(
                select(func.avg(MetricPoint.value)).where(
                    MetricPoint.metric_type == MetricType.EFFECTIVENESS.value,
                    MetricPoint.ref_gap_type == gap_type,
                )
            )
            if avg_value is None:
                return 0.0
            return float(avg_value)
