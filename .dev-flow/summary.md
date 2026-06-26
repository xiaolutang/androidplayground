---
type: summary
last_updated: 2026-06-26
---

# 变更记录（Summary）

> 全局变更历史。按 RC 归档时间倒序追加。每条记录含：交付摘要 + 模块清单 + 能力清单 + 证据链接。

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
