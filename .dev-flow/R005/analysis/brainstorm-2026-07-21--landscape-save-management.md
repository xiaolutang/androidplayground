---
date: 2026-07-21
type: brainstorm
status: concluded
requirement_cycle: R005
topic: landscape-save-management
source: user_direct
---

# 横版手柄「存档管理」二级页面

## 背景

用户下午 token 耗尽，改用 codex 完成了横版手柄框架（`landscape_page.dart`）：
- 横版菜单 overlay（`MenuOverlay`，8 项菜单，含「存档管理」）
- 横版「切换布局」二级页（`LayoutSwitchOverlay`，d8b690cf）

但横版菜单点击「存档管理」(`MenuAction.saveManagement`) 当前在 `_selectMenuItem` 中**无处理**，没有对应二级页。本 RC 续做该二级页。

## 结论

- **要做什么**：实现横版「存档管理」二级页 overlay（`SaveManagementOverlay`），挂在横版菜单 `MenuAction.saveManagement` 上。点击菜单项打开面板，面板内可浏览/操作存档槽，返回按钮回菜单。
- **不做什么**：
  - 竖版存档管理（本次范围外，竖版菜单点该项仍无反应，留后续）
  - 真实存档文件持久化（demo 用内存 mock 数据）
  - 真实缩略图抓取（用占位图/纯色块）
- **关键约束**：
  - 复用现有横版手柄框架（`landscape_page.dart` 底层手柄不变）
  - 严格对齐 `LayoutSwitchOverlay` 的 overlay 模式（蒙层 + 二级面板 + 返回 + FocusRing）
  - Figma node 3448:30090 为唯一视觉基线（844×390 横屏）
- **核心场景**：
  1. 横版菜单焦点移到「存档管理」→ 确认 → 打开 `SaveManagementOverlay`
  2. 面板内方向键在「返回 / 快存删除 / 手动槽 save·load·delete」间导航，FocusRing 高亮
  3. **有状态 demo**：删除按钮真移除对应槽位（列表收缩）；保存/读取有反馈（操作后刷新时间或日志）
  4. 返回按钮 / ESC → 回菜单（菜单焦点回到「存档管理」）
  5. 底部 logo 按钮 → dismiss 全部 overlay 回底层手柄（沿用现有 `_dismissOverlays`）
- **待确认（已定）**：
  - 范围 = 仅横版 ✅（用户确认）
  - 交互 = 可交互 demo 有状态 ✅（用户确认：删除真移除、保存/读取有反馈）

## 关键讨论

- **朝向范围**：用户原话「完成横版的存档管理页面」。发散到「是否含竖版」，确认**仅横版**——竖版需另查 Figma 适配，工作量翻倍，留后续。
- **交互性取舍**：
  - 纯展示：聚焦 UI 还原，按钮只记录日志，无状态 ← 被否
  - **有状态 demo**：`StatefulWidget` 维护存档列表，删除真移除、保存/读取有反馈 ← **采纳**
  - 理由：存档管理的核心价值就在「增删读写」的可感知反馈，纯展示会丢掉一半交互语义。
- **返回交互**：对齐 `LayoutSwitchOverlay`——返回按钮回**菜单**（不是 dismiss 全部），蒙层点击走 `onDismiss`（dismiss 全部回底层）。两条路径区分明确。
- **焦点起点**：打开 overlay 后首个焦点落在「返回按钮」（autofocus），与 LayoutSwitchOverlay 的返回区首个焦点一致。
- **数据模型**：新增 `SaveSlot` 领域模型（title / time / thumbnail / kind: quick|manual），quick 槽只有删除，manual 槽有 save/load/delete。mock：1 quick + 2~3 manual。
