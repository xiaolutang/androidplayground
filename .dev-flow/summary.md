---
type: summary
last_updated: 2026-06-27
---

# 变更记录（Summary）

> 全局变更历史。按 RC 归档时间倒序追加。每条记录含：交付摘要 + 模块清单 + 能力清单 + 证据链接。

---

## R005 横版手柄「存档管理」二级页面（2026-07-22 归档）

### 交付摘要

续接 codex 横版手柄框架，实现横版菜单「存档管理」(`MenuAction.saveManagement`) 的二级页 overlay。点击弹出浅色 picker-panel（443×282@(201,26) 圆角24 径向渐变），含返回按钮、快速存档区（1 槽）、手动存档区（2 槽 save/load/delete），有状态 demo（删除真移除、保存刷新时间）。严格对齐 Figma 3448:30090，复用 `LayoutSwitchOverlay` 范式。

**核心能力**：
- 存档管理二级 overlay（蒙层 + 径向渐变面板 + 两区 + 滚动条）
- 有状态增删保存读取（StatefulWidget 维护 quick/manual 列表）
- 槽位操作按钮焦点 + FocusRing（Enter/Space 激活）
- 横版三态互斥（menu / layout / saveMgmt）

### 模块清单

| 模块 | 任务 ID | 关键产物 |
|------|---------|---------|
| 领域模型 | FB001.1 | `SaveSlot` + `SaveSlotKind` |
| 存档槽卡片 | FB002 | `SaveSlotCard` + `_SlotIconButton` |
| 存档管理 overlay | FB001 | `SaveManagementOverlay` + `_BackTitle` + `_SectionHeader` |
| 横版挂载 + 测试 | FF002 | landscape_page `saveManagementOpen` 状态 + 5 测试 + 1 回归修复 |

### 验收基线

| 维度 | 数据 |
|------|------|
| 全量测试 | 81 passed |
| Lint | `flutter analyze` 0 issue |
| Golden | `landscape_save_management.png` 用户对照 Figma 确认 |

### 已知缺口

- load 图标（读取按钮）：Figma `imgUnion2` asset 404、`use_figma` 导不出，复用软盘（= save）
- 竖版存档管理：不在本次范围

### 证据链接

- 验收：`.dev-flow/R005/evidence/r005-evaluation.md`
- 任务清单：`.dev-flow/R005/landscape-save-management-tasks.md`
- analysis：`.dev-flow/R005/analysis/2026-07-21--landscape-save-management.md`

---

## R004 焦点边界受阻抖动反馈（2026-06-27 归档）

### 交付摘要

R002 焦点策略的体验增强补丁。当方向键在焦点边界无候选（到头/到边）时，让当前焦点按钮沿受阻轴向做 ±4px / 250ms / 3 周期 sin 波抖动，给用户"此路不通"的体感反馈。

**核心能力**：
- **边界受阻信号通道（FF005）**：`SmartFocusTraversalPolicy.blockedDirectionNotifier`（`ValueNotifier<TraversalDirection?>`），在 `inDirection` 垂直 return-false 路径 + 水平 `super.inDirection` 返回 false 后写入受阻方向
- **方向感知抖动（FB008）**：`FocusableButton` 订阅 notifier，当自身是 primaryFocus 时启动抖动 — 垂直受阻（up/down）→ dy 振荡 dx=0；水平受阻（left/right）→ dx 振荡 dy=0
- **防抖幂等**：动画中再次收到信号 `forward(from:0)` 重启，不堆叠
- **失焦即停**：抖动中失焦立即 `stop()`，让位给正常焦点切换
- **三个 Flutter 坑位规避**：(1) `Curve.transform` 端点短路导致 sin(6π)≠0 → 改用裸 `math.sin`；(2) `CurveTween` 要求输出 ∈[0,1] 违反 sin → 不用 tween；(3) `forward(from:0)` 首帧 Ticker 未启动 → 双 pump 模式

### 模块清单

| 模块 | 任务 ID | 关键产物 |
|------|---------|---------|
| 焦点策略 FF | FF005 | `blockedDirectionNotifier` 字段 + 2 个写入点（垂直/水平 return-false 路径） |
| 抖动按钮 FB | FB008 | `FocusableButton.blockedNotifier` 入参 + `AnimationController` + `AnimatedBuilder` + `Transform.translate` 方向感知抖动 |
| 集成测试 FF | FF009 | 真实 `PersonalCenterDemoPage` + `sendKeyEvent` 端到端验证（垂直/水平/连续防抖/失焦取消 4 场景） |

### 能力清单

| 能力 | 来源 | 当前状态 |
|------|------|---------|
| 焦点边界受阻信号通道 | FF005 | released（policy → widget 单向 notifier） |
| 方向感知抖动反馈 | FB008 | released（垂直/水平轴向分离，±4px/250ms/3 周期 sin） |
| 抖动防抖 + 失焦即停 | FB008 | released（forward(from:0) 重启 + focus listener stop） |

### 验收基线

| 维度 | 数据 |
|------|------|
| 单元测试 | FF005×4 + FB008×5 = 9 passed |
| 集成测试 | FF009×4 passed（真实页面 + 真实按键） |
| 全量回归 | 56 tests passed（R002 既有 35 + R004 新增 13 + 其他 8） |
| Lint | `flutter analyze` 无 error |
| simplify | routing=none（测试 helper 重复已收敛到 focus_test_helpers.dart） |

### visual-verify 接入范围

- **页面**：PersonalCenterDemoPage（已在 R002 接入范围）
- **技术栈**：Flutter（flutter_logic 模块）
- **采集方式**：widget test 对 Transform.translate dx/dy 的断言作为视觉门控代理（抖动位移量程可量化验证）
- **稳定标识**：`personal_center.button.shake_transform`、`personal_center.policy.blocked_notifier`（见 R004 acceptance-spec.yaml）

### 证据链接

- 任务清单：`.dev-flow/R004/focus-boundary-shake-feedback-tasks.md`
- 分析文档：`.dev-flow/R004/analysis/`（需求分析 + frontend 设计 + acceptance-spec.yaml）
- 关键 commit：`a32e85cb`（FF005+FB008+FF009 完整实现）

---

## R002 Flutter 焦点进阶 Demo（2026-06-27 归档）

### 交付摘要

纯 Flutter 前端 demo，验证自定义焦点策略在 TV/掌机类设备（方向键导航）下的工程实践。位于 `flutter_logic/` 模块，遵循 R001 Add-to-App 模式。

**核心能力**：
- **三层焦点降级策略**：`记忆（focusedChild）→ 优先级（NumericFocusOrder）→ 物理兜底（DFS）`，命中即返回
- **跨 FocusScope 智能导航**：方向键跨区域（左导航↔右内容区）时自动走三层降级进入目标区域，同区域走几何就近
- **垂直方向键列聚类隔离**：up/down 方向只在 X 轴区间相交的候选中排序，防止跨列跳转
- **requestFocusCallback 接入 SDK ensureVisible 链路**：跨 scope 路径用 hook 而非裸 `.requestFocus()`，免费拿到 `Scrollable.ensureVisible` 滚动；alignment:0.5 适配 home indicator 安全区
- **M3 scrolledUnder 全局关闭**：appBarTheme 三属性（scrolledUnderElevation:0 + surfaceTintColor:transparent + backgroundColor 固定），消除 body 滚动时 AppBar 变色导致的 iOS 状态栏闪烁

**五个修复（FIX001-FIX005）**：
- FIX001：垂直方向 X 重叠过滤（列聚类）
- FIX002：移除 AnimatedScale 修复焦点框左右裁剪
- FIX003：appBarTheme 全局关闭 M3 scrolledUnder（状态栏闪烁修复）
- FIX004：StackFit.expand + Row stretch 修复右内容区高度塌陷
- FIX005：SmartFocusTraversalPolicy 跨 scope 改用 requestFocusCallback，恢复 SDK ensureVisible 链路（系统性修复，删除 widget 层 `_handleFocusChange` 补丁）

### 模块清单

| 模块 | 任务 ID | 关键产物 |
|------|---------|---------|
| 焦点策略 FF | FF003-FF004 | SmartFocusTraversalPolicy（三层降级 + 列聚类）/ FocusableButton（统一封装 + 边框高亮） |
| 焦点页面 FB | FB005-FB006 | PersonalCenterDemoPage（左导航 + 右内容区）/ FocusDebugOverlay（调试浮层） |
| 入口页 | — | HomePage（Playground 入口 + 跳转 demo） |
| 测试 | — | 43 widget test（含 ensureVisible 回归捕获） + iPhone 16 横屏模拟器集成诊断 |

### 能力清单

| 能力 | 来源 | 当前状态 |
|------|------|---------|
| 自定义焦点遍历策略（三层降级） | FF003 | released（记忆 > 优先级 > 兜底） |
| 跨 FocusScope 方向键导航 | FF003 | released（左导航 ↔ 右内容区） |
| 垂直方向列聚类隔离 | FF003 FIX001 | released（X 重叠过滤） |
| requestFocusCallback ensureVisible 链路 | FF003 FIX005 | released（alignment:0.5 绕开 safe area） |
| M3 scrolledUnder 全局关闭 | Theme | released（消除状态栏闪烁） |
| 焦点调试浮层 | FB006 | released（primaryFocus 显示 + 节点删除/重置记忆/打印 Rect） |

### 验收基线

| 维度 | 数据 |
|------|------|
| Widget 测试 | 43 passed（含 layout/focus/home_page 三组） |
| 回归捕获 | 记忆层 ensureVisible 测试（重置 scrollOffset 后断言 >0） — 对照实验验证有效 |
| 视觉验收 | GLM-5V-Turbo 分析 iPhone 16 模拟器横屏截图 — 焦点框无裁剪 / 列隔离生效 / 状态栏不闪烁 |
| Lint | `flutter analyze` 无 error |

### visual-verify 接入范围

- **页面**：HomePage、PersonalCenterDemoPage
- **技术栈**：Flutter（flutter_logic 模块）
- **采集方式**：手动截图 + GLM-5V-Turbo 视觉分析（无自动化采集层；后续若引入自动化采集器再回写此节）

### 证据链接

- 任务清单：`.dev-flow/R002/flutter-focus-demo-tasks.md` + `flutter-focus-vertical-fix-tasks.md`（FIX001-FIX005 全部 archived）
- 分析文档：`.dev-flow/R002/analysis/`（3 份：需求分析 + frontend 投影 + FIX005 根因分析）
- 执行证据：`.dev-flow/R002/evidence/r002-evaluation.md`
- 关键 commit：`cd265e12`（FIX003/004/005 系统性修复）+ `ce475376`（FIX005 根因分析与 tasks 登记）

---

## R001 客户端 Bug 自动修复 Agent（2026-06-26 归档）

### 交付摘要

首个需求周期。建立客户端 bug 自动修复 agent 的完整骨架（MVP C 值守诊断路径 + B 自动修复预留接口）。

**核心能力**：
- **三组件架构落地**：Playbook（BF006）+ Knowledge Base（BF005）+ Information Sufficiency Model（BB001）
- **LangGraph 14 态状态机编排**（ORB01，D1 决策）：`received → classifying → analyzing → reproducing → hypothesizing → diagnosing → fixing → verifying → reporting` 全路径 + 异常回退
- **双路径修复策略**（INV-2 按 Tier 分级）：Tier1 高置信走三关 + 普通 PR；Tier2 中置信走轻量验证 + draft PR
- **Capability Gap 闭环**：未补齐缺口永久可查（BF008），补齐后触发同类 bug 回流（BB011）
- **Docker 全栈一键启**（DEP01，D10）：postgres(pgvector) + agent + frontend + Android 模拟器宿主原生 + `host.docker.internal:5037` ADB 桥

### 模块清单

| 模块 | 任务 ID | 关键产物 |
|------|---------|---------|
| 基础设施 INF | INF01-INF06 | DB 迁移 / 配置 / 日志 / 错误码 / 测试 fixture |
| 数据模型 SCH | SCH01-SCH02 | 12 SQLAlchemy ORM 表 + Pydantic Schema |
| 后端基础 BF | BF001-BF008 | BugReportAdapter / 复现引擎 / 视觉决策 / 信号监听 / KB / Playbook / 锚点库 / Gap Tracker |
| 后端业务 BB | BB001-BB015 | ISM / 症状分类 / Playbook 执行 / 假设树 / 根因定位 / 置信度 / 自动修复 / 回归验证 / PR 提交 / 缺口诊断 / 回流 / 报告生成 / 反思 / 人工录入（BB014 知识聚合 deferred） |
| API 层 FF | FF001-FF002 | report_router（7 端点+webhook） / gap_router（2 端点） |
| 编排器 ORB | ORB01 | LangGraph StateGraph 14 态 + 节点路由 |
| 入口 ENT | ENT01 | FastAPI main.py + lifespan DB 初始化 |
| 部署 DEP | DEP01 | docker-compose + Dockerfile + Makefile（11 目标） |
| 集成测试 INT | INT01-INT04 | API+Testcontainers 49 case / 状态机迁移矩阵 351 case / 模拟器手动 14 case / golden set 7 case |
| 前端 FE | FE01-FE16 | React 19 + TS 6 + Vite 8 + antd 6.4 + TanStack Query 5.101 + MSW 2.14 + vitest 4.1（81 单测） |

### 能力清单

| 能力 | 来源 | 当前状态 |
|------|------|---------|
| Bug 上报归一化（Sentry 适配器） | BF001 | released（参数化可扩展） |
| Android 模拟器复现/探测双模式 | BF002 | released（subprocess ADB） |
| 多模态视觉决策 | BF003 | released（默认 GLM-5V-Turbo） |
| 四类信号监听（logcat/Flutter error/进程/视觉） | BF004 | released |
| KB 存储 + 向量检索 | BF005 | released（pgvector） |
| Playbook 注册 + 按症状检索 | BF006 | released |
| 锚点库（Schema + 检索） | BF007 | released（数据冷启动为空） |
| Capability Gap 存储 + 解锁价值评分 | BF008 | released |
| LangGraph 状态机编排 | ORB01 | released（14 态） |
| Tier 分级修复路径 | BB006+BB007+BB008+BB009 | released（Tier1 普通 PR / Tier2 draft PR） |
| 缺口诊断 + 回流闭环 | BB010+BB011 | released |
| 诊断报告双输出（JSON + MD） | BB012 | released |
| 反思沉淀负向知识 | BB013 | released |
| 人工修复录入 KB 模式层 | BB015 | released（INV-3 强制） |
| 前端报告/缺口/追问三大视图 | FE01-FE16 | released（MSW mock 全契约覆盖） |

### 验收基线

| 维度 | 数据 |
|------|------|
| 后端单元测试 | 1420 passed（含 INT02 351 case 状态机矩阵） |
| 后端集成测试 | 49 passed + 3 skipped（Testcontainers PG+pgvector） |
| Golden set | 7 passed（LLM schema 100% / vision 75% cold start） |
| 模拟器手动 | 14 case（`@pytest.mark.emulator`，默认 skip） |
| 前端单测 | 92 passed（vitest，含 11 services 契约测试） |
| Lint | ruff All checks passed |
| Sprint Contract | 18/18 agreed（8 条协商验收） |

### 已知缺口（deferred / open）

| 项 | 状态 | 后续处理 |
|----|------|---------|
| BB014 知识聚合器 | deferred（MVP 外） | 待后续 RC 周期性 trajectory 聚合 |
| KB 锚点库数据 | 能力已建，数据为空 | 待公司录入激活 |
| Flutter 状态管理框架 | 未锁定 | 留客户端 design（影响 Playbook 探测方式） |
| 步数/token 预算具体数值 | design 给默认值 | 待实验阶段校准 |

### 证据链接

- 任务清单：`.dev-flow/R001/client-bug-fix-agent-tasks.md`（56 任务 archived）
- 前端任务清单：`.dev-flow/R001/client-bug-fix-agent-frontend-tasks.md`（16 任务 archived）
- 分析文档：`.dev-flow/R001/analysis/`（5 份：主文档+backend+frontend+test+brainstorm）
- Sprint Contract：`.dev-flow/R001/contracts/`（18 条 agreed）
- 执行证据：`.dev-flow/R001/evidence/`（按 task_id 命名）

### 归档后契约对齐修复（2026-06-26）

> R001 归档后首次真实联调发现前后端契约漂移，根因是 design 阶段跳过导致接口结构未固化。以下为补齐修复。

| Commit | 修复内容 |
|--------|---------|
| `f77319f8` | P0：gap types/services 对齐 UnblockResponse + waiting_reason；P1：ClarifyOption 移除多余字段 + MSW 3 handler 结构修正 + ClarifyForm 简化；P2：新增 services 契约测试 11 case |
| `0ea56c27` | Codex 审查发现 gap_type 后端 Optional[str] vs 前端严格枚举 → 改为 nullable + 未知值回退 |
| `b1a1a674` | Playwright 前端冒烟测试（/gaps + /clarify + /reports/:id 三页面） |

**新增测试资产**：
- `frontend/src/services/__tests__/serviceContract.test.ts`（11 case，验证响应解包 + 错误传播）
- `tests/integration/test_frontend_pages.py`（Playwright 浏览器冒烟，验证页面不崩溃）

---
