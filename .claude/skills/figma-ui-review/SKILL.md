---
name: figma-ui-review
description: 审查 Figma UI 还原实现的质量，提交前用。6 维度并行 subagent 审查——数据忠实度 / 资源正确性 / 三分离 / 布局 / 验证 / Figma 忠实。触发："审查 UI 还原"、"review figma impl"、"检查还原度"、UI 实现完准备提交。
---

# Figma UI 还原审查

## 何时用
- UI 还原实现完后、提交前
- 用户说"审查 UI"、"review 还原"、"检查质量"

## 工作方式：subagent 并行（强制）

本 skill **必须以独立 subagent 方式工作**，主会话不能静默替代审查：

```yaml
subagents:
  required: true
  roles:
    - name: figma-ui-reviewer
      kind: execution
      isolation: independent_context
      input: [figma_node, impl_code, git_diff]
      output: {format: evidence, status: completed | blocked}
      fallback: blocked   # 缺 subagent/证据时 blocked，不伪造 PASS
      evidence_required: [isolation, subagent_role, dimensions_checked]
```

执行流程：
1. 主会话启动 `figma-ui-reviewer` subagent（独立 context，与 implementer 隔离）
2. subagent 内部 6 维度并行审查（每维度一个子 agent，或串行 6 维度）
3. subagent 返回 evidence（findings + 修复建议）
4. 主会话汇总 + 直接修复高价值项
5. 实现缺陷（触发错/架构错）回 implementer

## 6 审查维度

### 维度 1：数据忠实度
- 代码 `left/top/width/height` == Figma `get_design_context` 数据？
- 颜色（CSS `var(--x,#c)` 取 fallback `#c` 对？）、字体字重（Heavy→w900, Bold→w700）、尺寸逐项对？
- 有没有凭截图猜、漏读节点、用过期/错误来源的数据？

### 维度 2：资源正确性
- 图标用 `download_assets(svg)` 拿节点完整 path？
- 有没有用单个素材 URL（`imgVector`/`imgBtn` 等，Figma 组件复用易下错图标内容）？
- SVG path 直接取自 Figma（没手绘/合成错位置）？
- 多状态/多方向：每态独立资源，不靠 `Transform` 复用？

### 维度 3：三分离（数据驱动）
- 组件**数据驱动**（`List<Item>`/`UiSpec` 注入），还是硬编码 title/icon/坐标？
- 组件按**视觉结构**命名（`DiamondGrid`/`IconTile`），不绑业务（`ABXY`/`登录按钮`）？
- 显示 / 行为 / 组件分离（组件不知道业务语义，换皮肤/换文案只改数据）？
- 重复元素是否使用真实 List/Grid，数量与顺序是否完全由集合决定？
- 焦点/选中/hover 是否复用公共状态组件，所有可交互项是否都能进入状态？

### 维度 4：布局准确性
- 固定画布 + `FittedBox` contain + `Stack/Positioned`（Figma 坐标 1:1）？
- 变换（rotate/scale）处理后 **slot == 视觉**（点 A 触发 A，不因旋转错位）？
- 背景图裁剪因子还原（OverflowBox + Transform）？
- z 轴是否与 Figma 节点顺序一致，尤其是蒙层上下方的按钮和触发器？
- 焦点 wrapper 外扩后是否仍保持 Figma 尺寸，而非被 Grid 紧约束压回普通尺寸？

### 维度 5：验证完整性（数据优先，反对反复 analyze 图片）
- `flutter analyze` 通过？
- golden test 通过（渲染无崩）？
- golden 是否渲染真实整页状态，是否意外重复定位/裁剪？
- 字体是否真实加载，中文是否正常显示而不是方块占位？
- 坐标/尺寸/颜色用 get_metadata 文本对照（**不靠反复 analyze 局部图片找差异**）？
- 图片只整体看一次确认观感，没把 analyze 局部当主要验证手段？
- 有没有错误地用 Figma 截图做像素 diff 基准？

### 维度 6：Figma 忠实（交互/触发）
- 交互（点击/切换/触发键）是否和 **Figma 设计一致**？
  - 例：菜单由哪个按钮触发？是 Figma 设计的那个，还是猜的？
- 有没有读 Figma 确认触发/状态语义，还是凭假设实现？
- 是否识别同一页面的正常态/菜单态/收起态，并逐项检查跨状态差异？

## 产物

frontmatter（机器可读，stop-hook/commit gate 的事实源）：
```yaml
review_status: completed | blocked
blocked_reason: ""
```

正文（人类解释）：
```markdown
## Review Result
- reviewed_files: [...]
- fixed: [{file, issue, how}]
- routing: return_to_implementer | none
- residual: [需人决策的项]
- dimensions: {data: N, asset: N, separation: N, layout: N, verify: N, figma_fidelity: N}  # 各维度问题计数
```

reviewer 只写自己的审查事实，不替 evaluate/visual-verify 伪造 PASS。

## 审查 → 修复规则
- **高价值问题直接修**：坐标错、图标下错、硬编码改数据驱动、旋转错位、SVG path 错
- **实现缺陷回 implementer**：触发键错、漏读节点、架构层问题、三分离彻底违反
- **只修当前 diff 相关**，不扩成大重构
- 修改影响测试则回退 implementer 重跑
