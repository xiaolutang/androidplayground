# 视觉决策 Golden 报告

> 生成时间: 2026-06-22 02:18:46
> 截图样本数: 12（共生成 12 张）
> 检测模式: **像素方差检测**（D11 冷启动，锚点库空）

## 冷启动准确率

- **整体准确率: 75.0%**（阈值 >=50%）
- 状态: PASS
- 白屏/黑屏检出率: 4/4

## 混淆矩阵

| 实际 \ 预测 |abnormal|blank_black|blank_white|loading|normal|
|---|---|---|---|---|---|
| abnormal | 0 | 0 | 0 | 0 | 3 |
| blank_black | 0 | 2 | 0 | 0 | 0 |
| blank_white | 0 | 0 | 2 | 0 | 0 |
| loading | 0 | 0 | 0 | 2 | 0 |
| normal | 0 | 0 | 0 | 0 | 3 |

## 检测逻辑（D11 冷启动）

```
  均值 > 240 且 方差 < 50     -> blank_white
  均值 < 15  且 方差 < 50     -> blank_black
  方差 < 500  且 均值 > 200   -> loading
  方差 > 5000                -> abnormal
  其他                        -> normal
```

## 样本明细

| 文件名 | 人工标注 | 检测结果 | 正确 |
|--------|---------|---------|------|
| white_01.png | blank_white | blank_white | YES |
| white_02.png | blank_white | blank_white | YES |
| black_01.png | blank_black | blank_black | YES |
| black_02.png | blank_black | blank_black | YES |
| loading_01.png | loading | loading | YES |
| loading_02.png | loading | loading | YES |
| normal_01.png | normal | normal | YES |
| normal_02.png | normal | normal | YES |
| normal_03.png | normal | normal | YES |
| abnormal_01.png | abnormal | normal | NO |
| abnormal_02.png | abnormal | normal | NO |
| abnormal_03.png | abnormal | normal | NO |

## 结论

- 冷启动像素方差检测准确率: 75.0%
- MVP 阶段：方法可执行 + 报告产出即 pass。
- D11 锚点库录入后，BF003 VisualDecisionEngine 会切换到锚点对照模式，准确率将提升。
