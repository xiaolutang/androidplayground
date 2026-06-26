---
date: 2026-06-27
type: brainstorm
status: concluded
requirement_cycle: R002
topic: vertical-key-scope-isolation
---

# 左导航上下键焦点跨区域 Bug Fix

## 背景
iOS 模拟器横屏，焦点在左导航"设置"按下键，焦点跳到右内容区"账户信息"（同行 Y 距离=0，几何排序胜出"关于"）。

## 结论
- **要做什么**：SmartFocusTraversalPolicy 的 `_findDirectionalCandidate` 对**垂直方向键**（上/下）增加 X 坐标列聚类过滤 —— 只在与 anchor 同一列（X 坐标相近）的节点中搜索候选。
- **不做什么**：
  - 不改 scope 树结构（左导航不加 FocusScope）
  - 不改 FocusTraversalGroup 结构
  - 不改跨 scope 三层降级逻辑（水平方向键行为不变）
- **关键约束**：不破坏场景 A/B/C 已有测试（28 unit + 3 integration 全绿）
- **核心场景**：
  - 左导航上下键 → 只在左导航 3 个按钮间移动（同列 X 坐标过滤）
  - 右内容区上下键 → 只在右内容区按钮间移动（同列 X 坐标过滤）
  - 左→右 / 右→左（水平键）→ 跨 scope 三层降级（不变）
- **边缘行为**：左导航在"关于"按下键（已到底部）→ 停留不动（super.inDirection 返回 false）

## 最终选择：方案 2（几何聚类）
- **列判断规则**：垂直方向键时，候选节点 rect 与 anchor rect 在 X 轴上有重叠（水平区间相交），视为"同一列"
- **实现位置**：`_findDirectionalCandidate` 方法内，垂直方向（up/down）分支增加 X 重叠过滤条件
- **水平方向不受影响**：左/右键仍在整个 scope 内按 X 轴距离搜索

## 关键讨论
- 排除"每个区域各自 FocusTraversalGroup"：Flutter SDK 跨 group 方向键行为不可靠（R002 已踩坑）
- 排除"左导航加 FocusScope"：会破坏 `_isDescendantScope` 判断，绕过三层降级，场景 A/B 回归
- 排除"policy 内 scope 感知"：左导航无 FocusScope，nearestScope=根scope（含所有节点），垂直键限制后仍搜到右边
- **选择"几何聚类"**：用 X 坐标重叠判断同列，零结构改动、零副作用、不依赖 scope 树
