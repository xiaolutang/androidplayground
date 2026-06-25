---
type: feature-map
last_updated: 2026-06-26
---

# 功能地图（Feature Map）

> 全局功能节点登记表。每个功能节点的编号 `BF/BB/FF/FB + 三位数字` 与 plan 任务 ID 同体系（`R{NNN}-{编号}`）。

## 层级索引

- [后端基础 BF](#后端基础-bf) — 基础设施、数据模型、通用服务
- [后端业务 BB](#后端业务-bb) — 业务逻辑、领域服务
- [前端基础 FF](#前端基础-ff) — 组件库、API、路由框架
- [前端业务 FB](#前端业务-fb) — 页面、交互流程

---

## 后端基础 BF

| 编号 | 功能节点 | 引入 RC | 状态 | 简介 |
|------|---------|--------|------|------|
| BF001 | Bug 上报接入适配器 | R001 | released | 适配多平台 webhook，归一化 `BugReport` |
| BF002 | 复现执行引擎 | R001 | released | 启停模拟器、装 APK、ADB 动作、截图采集 |
| BF003 | 视觉决策引擎 | R001 | released | 多模态模型看截图 → 决策下一步动作 |
| BF004 | 信号监听器 | R001 | released | logcat / Flutter error / 进程 / 视觉四类信号 |
| BF005 | Knowledge Base 存储 | R001 | released | trajectory / 负向知识 / 根因模式的存储检索 |
| BF006 | Playbook 注册中心 | R001 | released | Playbook Schema + 按症状检索 |
| BF007 | 锚点库 | R001 | released | 关键页面正常截图 + 文字预期 |
| BF008 | Capability Gap Tracker 存储 | R001 | released | 缺口条目存储、解锁价值评分、回流事件订阅 |

## 后端业务 BB

| 编号 | 功能节点 | 引入 RC | 状态 | 简介 |
|------|---------|--------|------|------|
| BB001 | 信息完备度评估器（ISM） | R001 | released | 关键字段识别、缺口分类、打分 |
| BB002 | 症状分类器 | R001 | released | bug → 症状类型 |
| BB003 | Playbook 执行器 | R001 | released | 编排复现 + 探测 + 诱发 |
| BB004 | 假设树引擎 | R001 | released | 假设提出/验证/回溯/确认状态机 |
| BB005 | 根因定位器 | R001 | released | 命中信号反向追溯代码位置 |
| BB006 | 修复置信度评估器 | R001 | released | 三维标准打分，决定 Tier |
| BB007 | 自动修复器 | R001 | released | 模板 → LLM patch → KB 历史校准 |
| BB008 | 回归验证器 | R001 | released | 复现序列 + 既有测试 + 静态检查三关 |
| BB009 | PR 提交器 | R001 | released | Tier 1 直接 PR / Tier 2 draft PR |
| BB010 | 缺口诊断器 | R001 | released | Tier 3/4 时识别四类缺口 |
| BB011 | 缺口补齐回流器 | R001 | released | 检测补齐事件、触发同类 bug 回流 |
| BB012 | 诊断报告生成器 | R001 | released | 结构化 JSON + markdown 双输出 |
| BB013 | 反思 agent | R001 | released | 提取负向知识与命中线索 |
| BB014 | 知识聚合器 | R001 | deferred | 周期性聚合 trajectory（MVP 外） |
| BB015 | 人工修复录入器 | R001 | released | 人修一次 → 结构化录入 → KB 模式条目 |

## 前端基础 FF

| 编号 | 功能节点 | 引入 RC | 状态 | 简介 |
|------|---------|--------|------|------|
| FF001 | 报告与工单 API | R001 | released | 报告/工单/trajectory/PR 查询接口 |
| FF002 | 缺口视图 API | R001 | released | 缺口列表、解锁价值排序、补齐动作提交 |

## 前端业务 FB

| 编号 | 功能节点 | 引入 RC | 状态 | 简介 |
|------|---------|--------|------|------|
| FB001 | 诊断报告详情页 | R001 | released | 报告 + 假设树可视化（MVP 含）；相似 issue 视图 MVP 不含，待后续 RC 基于 pgvector 补 |
| FB002 | PR 审核界面 | R001 | released | 复用 GitHub/GitLab PR 界面 |
| FB003 | 缺口视图 | R001 | released | 按解锁价值排序的缺口列表 + 补齐操作 |
| FB004 | 信息追问表单 | R001 | released | 结构化选项追问 |

---

## 状态图例

- **planned**：已规划，未实现
- **in_progress**：开发中
- **released**：已发布
- **deferred**：暂缓（MVP 外）
- **deprecated**：已废弃

## 跨节点依赖关系（关键链路）

```
BF001 → BB001 → BB002 → BF006 → BB003 → BB004 → BB005 → BB006
                                                        ↓
                                              ┌─────────┼─────────┐
                                              ↓         ↓         ↓
                                            BB007     BB009     BB010
                                              ↓         ↓         ↓
                                            BB008     (PR)     BB011 → 回流
                                              ↓
                                            BB009 → PR
```

反思与沉淀横切所有完成态：BB013 → BF005；BB015 → BF005（模式层）
