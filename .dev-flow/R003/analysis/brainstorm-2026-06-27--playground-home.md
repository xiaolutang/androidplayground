---
type: brainstorm
topic: playground-home
requirement_cycle: R003
date: 2026-06-27
status: concluded
---

# Flutter Playground 入口页 — Brainstorm 结论

## 背景

`flutter_logic/` 是 playground 实验场，当前 `main.dart` 把 `home` 直接指向 `PersonalCenterDemoPage`，导致应用启动即进入焦点 demo，无法承载后续新增 demo。

## 用户决策（已确认）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 展示形式 | ListView 列表 | 简单直观，demo 数量不定时易扩展 |
| 路由方式 | Named routes 命名路由 | 在 MaterialApp 统一注册，新增 demo 加一条路由即可 |
| 返回入口 | 子页面 AppBar 自带 back | Flutter push 进栈时 AppBar 默认带返回箭头，无需改现有 demo 页 |

## 范围

- **改**：`lib/main.dart`（home 改 HomePage + 注册 routes）
- **新增**：`lib/home_page.dart`（ListView 入口列表）
- **不动**：`lib/pages/personal_center_page.dart`（AppBar 已存在，push 后自动有返回）

## 不在范围

- demo 分类/分组（demo 数量少，单层列表够用）
- demo 元信息（图标/描述）— 先只放标题，后续按需扩
- 持久化最近访问 — playground 不需要
