---
type: rc_queue
last_updated: 2026-06-17
---

# RC 队列（Requirement Cycle Queue）

> 跟踪所有需求周期的状态。新增 RC 从 R002 起编号（R001 已 active）。

## 队列状态

| RC 编号 | 主题 | 状态 | 当前阶段 | 启动日期 | 备注 |
|---------|------|------|---------|---------|------|
| R001 | 客户端 Bug 自动修复 Agent | active | design-review 全部通过（backend 5 轮 / frontend 2 轮 / test 6 轮 Codex PASS），待进入 plan | 2026-06-16 | 首个 RC；design 期间回写 architecture INV-2（Tier 分级）|

## 状态图例

- **active**：当前活跃，正在推进
- **paused**：暂停（阻塞等待外部输入）
- **archived**：已归档（完成或放弃）
- **queued**：排队等待启动

## 阶段图例

- brainstorm → analysis → analysis-review → design → design-review → plan → plan-review → execute → evaluate → archive

## 历史归档

（暂无）
