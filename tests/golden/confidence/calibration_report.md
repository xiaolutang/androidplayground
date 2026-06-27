# 置信度校准报告 **[合成数据]**

> 生成时间: 2026-06-22 09:37:33
> 样本数: 16
> 数据来源: 合成（演示方法，标注 outcome）

## Brier Score

**Brier Score = 0.208420**

> Brier Score 范围 [0, 1]，越低表示校准越好。
> 0 = 完美校准，1 = 完全错误。

## Reliability Diagram（分桶校准）

| 概率区间 | 样本数 | 平均预测概率 | 实际频率 | Gap（|pred-actual|） |
|----------|--------|-------------|----------|---------------------|
| 0.0-0.2 | 1 | 0.15 | 0.0 | 0.15 |
| 0.2-0.4 | 4 | 0.275 | 0.5 | 0.225 |
| 0.4-0.6 | 4 | 0.475 | 1.0 | 0.525 |
| 0.6-0.8 | 4 | 0.6833 | 0.5 | 0.1833 |
| 0.8-1.0 | 3 | 0.8556 | 1.0 | 0.1444 |

## ASCII Reliability Diagram

```
  actual_freq
  1.0 |         *
      |       *
  0.8 |     *
      |   *
  0.6 | *
  0.4 | *
      |   *
  0.2 |     *
      |       *
  0.0 +---------*---------
     0.0       0.5       1.0
            predicted_prob

  * = 分桶中心点（理想校准 = 对角线）
```

## 样本明细

| # | predicted | actual | label |
|---|-----------|--------|-------|
| 1 | 0.9000 | success | synthetic_1_tier1 |
| 2 | 0.8500 | success | synthetic_2_tier1 |
| 3 | 0.8167 | success | synthetic_3_tier1 |
| 4 | 0.7500 | success | synthetic_4_tier1 |
| 5 | 0.7333 | success | synthetic_5_tier1 |
| 6 | 0.6500 | fail | synthetic_6_tier2 |
| 7 | 0.6000 | fail | synthetic_7_tier2 |
| 8 | 0.5500 | success | synthetic_8_tier2 |
| 9 | 0.5000 | success | synthetic_9_tier2 |
| 10 | 0.4500 | success | synthetic_10_tier2 |
| 11 | 0.4000 | success | synthetic_11_tier3 |
| 12 | 0.3500 | fail | synthetic_12_tier3 |
| 13 | 0.3000 | success | synthetic_13_tier3 |
| 14 | 0.2500 | success | synthetic_14_tier3 |
| 15 | 0.2000 | fail | synthetic_15_tier4 |
| 16 | 0.1500 | fail | synthetic_16_tier4 |

## 结论

- 本报告使用 **合成数据** 生成（MVP 降级，真实 outcome 不足）。
- 方法已验证可执行：ConfidenceEvaluator 输出 -> 分桶 -> reliability diagram + Brier score -> 报告产出。
- 积累真实修复 outcome 后重新运行即可获得真实校准基线。
