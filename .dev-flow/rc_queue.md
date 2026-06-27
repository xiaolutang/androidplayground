---
type: rc_queue
last_updated: 2026-06-27
---

# RC 队列（Requirement Cycle Queue）

> 跟踪所有需求周期的状态。新增 RC 从 R005 起编号（R001/R002 已归档）。

## 队列状态

| RC 编号 | 主题 | 状态 | 当前阶段 | 启动日期 | 备注 |
|---------|------|------|---------|---------|------|
| R001 | 客户端 Bug 自动修复 Agent | archived | 已归档 | 2026-06-16 | 首个 RC；72 任务全部完成（56 后端 + 16 前端，BB014 deferred）|
| R002 | Flutter 焦点进阶 Demo | archived | 已归档 | 2026-06-26 | 焦点策略 + 5 个修复全部完成；43 widget test 全绿 |
| R003 | Flutter Playground 入口页 | planned | plan | 2026-06-27 | 基于 R002 焦点 demo 加 Playground 总入口；待 execute |
| R004 | 焦点边界受阻抖动反馈 | archived | 已归档 | 2026-06-27 | 2 节点（FF005 + FB008）+ FF009 集成测试；56 测试全绿 |

## 待规划

（暂无 queued RC。新 RC 从 R005 起编号，需先完成 brainstorm → analysis → design → plan。）

## 状态图例

- **active**：当前活跃，正在推进
- **paused**：暂停（阻塞等待外部输入）
- **archived**：已归档（完成或放弃）
- **queued**：排队等待启动
- **planned**：已规划（analysis+plan 就绪），等待 execute

## 阶段图例

- brainstorm → analysis → analysis-review → design → design-review → plan → plan-review → execute → evaluate → archive

## 历史归档

- **R004**（2026-06-27）：焦点边界受阻抖动反馈。policy→widget notifier 信号通道 + 方向感知 sin 波抖动。详见 `.dev-flow/summary.md`。
- **R002**（2026-06-27）：Flutter 焦点进阶 Demo。三层焦点降级 + 跨 scope 导航 + 5 个修复。详见 `.dev-flow/summary.md`。
- **R001**（2026-06-26）：客户端 Bug 自动修复 Agent。详见 `.dev-flow/summary.md`。
