---
type: evaluation
requirement_cycle: R005
topic: landscape-save-management
date: 2026-07-22
status: released
---

# R005 横版手柄「存档管理」二级页面 — 验收

## 交付摘要

续接 codex 已完成的横版手柄框架（横版菜单 + 「切换布局」二级页 `LayoutSwitchOverlay`），实现横版菜单中「存档管理」(`MenuAction.saveManagement`) 的二级页 overlay。点击菜单项弹出浅色 picker-panel（443×282），含返回、快速存档区（1 槽）、手动存档区（2 槽），为**有状态 demo**——删除真移除槽位、保存刷新时间、读取上报回调。严格对齐 Figma 3448:30090。

## 模块清单

| 模块 | 任务 ID | 关键产物 |
|------|---------|---------|
| 领域模型 | FB001.1 | `SaveSlot` + `SaveSlotKind`（domain/models.dart）|
| 存档槽卡片 | FB002 | `SaveSlotCard` + `_SlotIconButton`（view/layer/save_slot_card.dart）|
| 存档管理 overlay | FB001 | `SaveManagementOverlay` + `_BackTitle` + `_SectionHeader`（view/save_management_overlay.dart）|
| 横版挂载 | FF002 | landscape_page `_selectMenuItem` 分支 + `saveManagementOpen` 状态 + 渲染分支 |
| 测试 | FF002 | 5 新增 + 1 回归修复（landscape_golden_test.dart）|

## 能力清单

| 能力 | 来源 | 状态 |
|------|------|------|
| 存档管理二级 overlay（蒙层+径向渐变面板+两区+滚动条）| FB001 | released |
| 有状态增删保存读取 | FB001 | released（删除真移除 / 保存刷新时间 / 读取回调）|
| 槽位操作按钮焦点 + FocusRing（Enter/Space 激活）| FB002 | released |
| 横版三态互斥（menu / layout / saveMgmt）| FF002 | released |
| 返回按钮 autofocus（ESC/Enter 可达，焦点框只框箭头）| FB001 | released |

## 验收基线

| 维度 | 数据 |
|------|------|
| 全量测试 | 81 passed（5 新增 + 1 回归修复 + 既有 75）|
| Lint | `flutter analyze` 0 issue |
| Golden | `landscape_save_management.png` 生成并经用户对照 Figma 确认 |
| Visual | 用户对照确认：无裁切、渐变/布局/间距对齐；焦点框按反馈从「框整行」缩小到「只框箭头」|

## 已知缺口

| 项 | 状态 | 后续处理 |
|----|------|---------|
| load 图标（读取按钮）| Figma `imgUnion2` asset 持续 404、`use_figma` 也导不出（节点无可见图层），复用软盘图标（= save）| 待 Figma 源恢复或设计师补图标后替换 `ic_load.svg` |
| 竖版存档管理 | 不在本次范围（用户确认仅横版）| 后续 RC |

## 关键决策

- **续接 codex 模式**：完全复用 `LayoutSwitchOverlay` 的 overlay 范式（蒙层 0xCC121A29 + CallbackShortcuts ESC + FocusTraversalGroup + FocusableActionDetector + FocusRing），保证横版三个 overlay 风格一致。
- **模型降级合并**：analysis 的 FF001（纯数据模型无 UI）在 plan 阶段降为 FB001.1 子任务，避免给无 UI 的模型强加 visual-verify。
- **焦点框反馈迭代**：首版 FocusRing 框住返回按钮整行（含「存档管理」文字），用户反馈后改为只框箭头 24×24。

## 证据链接

- brainstorm：`.dev-flow/R005/analysis/brainstorm-2026-07-21--landscape-save-management.md`
- analysis：`.dev-flow/R005/analysis/2026-07-21--landscape-save-management.md`
- tasks：`.dev-flow/R005/landscape-save-management-tasks.md`
- golden：`flutter_logic/test/gamepad_app/landscape_save_management.png`
- 关键文件：`save_management_overlay.dart` / `save_slot_card.dart` / `landscape_page.dart`
