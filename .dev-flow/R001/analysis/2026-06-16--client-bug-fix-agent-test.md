---
module: client-bug-fix-agent
version: 1.0.0
date: 2026-06-17
tags: [agent, test, pytest, vitest, msw, testcontainers]
type: design_test
status: designed
requirement_cycle: R001
source_analysis: 2026-06-16--client-bug-fix-agent.md
architecture_md_updates: true
architecture_md_updates_note: 回写 architecture INV-2「回归必过」按 Tier 分级（Tier1 三关 / Tier2 draft 轻量验证），与 backend 5.1 已确认口径对齐
---

# 客户端 Bug 修复 Agent — 测试设计

> 关联设计：[客户端 Bug 修复 Agent 1.0.0 backend](2026-06-16--client-bug-fix-agent-backend.md) | [客户端 Bug 修复 Agent 1.0.0 frontend](2026-06-16--client-bug-fix-agent-frontend.md)

## 1. 测试策略

> R001 是 agent 系统 MVP：链路长（上报→排查→修复→验证→提 PR→反思）、外部依赖重（LLM/模拟器/Git/上报平台）、成本敏感（LLM token + 模拟器启动）。测试策略以"外部依赖全 mock + 关键状态机/算法单测兜底 + API 契约集成测试"为主，**MVP 不做全链路真实 E2E**（模拟器+LLM 端到端单次成本与稳定性不适合 CI）。

| 层级 | 范围 | 工具 | 目标覆盖率 | CI 必跑 |
|------|------|------|-----------|---------|
| 单元测试 | 函数/方法级（状态机、打分、检索排序、treeBuilder、format） | pytest（backend）/ vitest（frontend） | 核心业务逻辑 ≥80% | ✅ |
| 集成测试 | API 端点 + 关键业务链路（FastAPI route → service → DB） | pytest + httpx + Testcontainers（PostgreSQL+pgvector） | FF001/FF002 关键链路 100% | ✅ |
| 契约测试 | 前后端 DTO 一致性、MSW handler 与 backend OpenAPI 对齐 | vitest + MSW handlers.spec.ts + OpenAPI schema diff | 全部 FF001/FF002 端点 | ✅ |
| 状态机测试 | BugReport 14 态 / Hypothesis 4 态 / CapabilityGap 7 态合法迁移 | pytest parametrize（状态迁移矩阵） | 合法迁移 100%、非法迁移全判定 | ✅ |
| E2E | 全链路（webhook → 修复 → PR） | 手动 + docker-compose 全栈（不含模拟器/LLM 真实调用） | 主成功路径 1 条（冒烟） | ❌（手动） |

**不做全链路 E2E 的理由**：模拟器启动 + ADB 动作 + 多模态 LLM 视觉决策单次跑通成本高、不稳定，CI 不可承受。改为：(1) BF002 复现引擎用真实模拟器做独立集成测试（不进主链路）；(2) BF003 视觉决策用 LLM mock（固定响应）验证编排；(3) 全链路冒烟手动跑，发布前 1 次。

**覆盖率盲区说明**：LLM 真实输出质量、视觉决策准确率、模拟器 UI 探测成功率——这三维不纳入自动化覆盖率，靠 MetricPoint（backend 4.1 MetricPoint）上线后观测，属"线上验收"非"CI 验收"。

## 2. 测试场景矩阵

### 后端测试场景（FF001 / FF002 + 关键服务）

#### API 端点测试（集成层，httpx + Testcontainers）

| API 端点 | 正常 | 异常(4xx) | 边界 | 安全/状态机 |
|----------|------|-----------|------|------------|
| `POST /webhook/{platform}` | BF001 归一化成功 → BugReport(received) | 400 schema 错 / 404 未知 platform / 409 重复 event_id | 空 raw_report / 超长堆栈 / 缺 versionCode | 签名校验（适配器参数化） |
| `GET /reports` | 分页 + status/tier 过滤 | 400 参数错 | page=0 / page超大 / 过滤无结果 | 越权（MVP 无鉴权，标 TODO） |
| `GET /reports/{id}` | 返回完整 BugReport | 404 不存在 | 刚收到未评估 / 已 concluded | — |
| `GET /reports/{id}/trajectory` | 返回 Hypothesis 树 + events | 404 | 空 trajectory（BB003 未启动） | — |
| `GET /reports/{id}/clarify-options` | 返回 KB 派生候选 | 404 / 409 非临界态 | 空候选（KB 冷启动）/ 候选数=1 | 非 assessing+clarify_requested → 409 |
| `POST /reports/{id}/clarify` | 提交 → clarify_requested=false 重跑 BB001 | 400 字段错 / 404 | 空答案 / 超长 | 非临界态提交 → 409 |
| `POST /reports/{id}/regression-feedback` | 写 MetricPoint；outcome=regression 且 concluded/reflected → reflowed+回流（见下方双维度矩阵） | 400 / 404 | evidence 超长 | 非允许状态（received/assessing/located/fixing）→ 409（见 backend 4.3 允许状态） |
| `GET /gaps` | 按 estimated_unlock_value 降序 | 400 | 空列表 / 单条 | — |
| `POST /gaps/{id}/unblock` | status: waiting→unblocked + 触发 BB011 回流 | 400 / 404 | evidence 空 | 非 waiting→409；已 resolved→409 |

**`POST /reports/{id}/regression-feedback` 状态矩阵（全量参数化）**：

基于 backend 4.1 BugReport.status 唯一 14 态枚举（`received/assessing/degraded/reproducing/located/fixing/verified/pr_open/draft_pr/gap_pending/wont_reflow/concluded/reflowed/reflected`）。allowed = `pr_open/draft_pr/concluded/reflected/reflowed`（5 态，PR 已提交后任一阶段，含反思沉淀后发现回归），denied = 其余 9 态：

| BugReport.status | 允许? | HTTP | 说明 |
|-----------------|-------|------|------|
| received | ❌ | 409 | 未开始排查 |
| assessing | ❌ | 409 | 评估中（含 clarify_requested 子回路） |
| degraded | ❌ | 409 | 信息不足降级 |
| reproducing | ❌ | 409 | 排查中 |
| located | ❌ | 409 | 已定位未修复 |
| fixing | ❌ | 409 | 修复中 |
| verified | ❌ | 409 | 已验证未提 PR |
| gap_pending | ❌ | 409 | 缺口诊断中 |
| wont_reflow | ❌ | 409 | 已转人工 |
| pr_open | ✅ | 200 | PR 审核期反馈 |
| draft_pr | ✅ | 200 | draft PR 反馈 |
| concluded | ✅ | 200 | 合并后回归观测 |
| reflected | ✅ | 200 | 已反思沉淀后发现线上回归（触发路径 B `reflected→reflowed`） |
| reflowed | ✅ | 200 | 回流中/回流后反馈 |

> **参数化测试（态 × outcome 双维度）**：14 态 × {regression, safe}，共 28 case。
> - **denied 9 态**：两 outcome 均返回 409 + 不写 MetricPoint + 状态不变。
> - **allowed 5 态 × outcome=safe**：返回 200 + 写 MetricPoint（metric_type=safety）+ 状态不变（`status_after == status_before`）+ `reflow_scheduled=false`。
> - **allowed × outcome=regression**：
>   - `concluded`/`reflected`：200 + 写 MetricPoint + `status_after=reflowed` + `reflow_scheduled=true` + 断言 ORB 回流入队（`reflowed → received` 迁移可观测）。
>   - `pr_open`/`draft_pr`/`reflowed`：200 + 写 MetricPoint + 状态不变 + `reflow_scheduled=false`（PR 未合并或已在回流，不重复触发）。
> **响应体断言**：`{metric_point_id, status_before, status_after, reflow_scheduled}` 四字段齐全且语义正确。状态枚举以 backend 4.1 唯一定义为准。

#### 关键业务逻辑测试（单元层）

| 模块 | 场景 | 预期 |
|------|------|------|
| BB001 ISM | 完备/临界/不足三档打分 | 阈值边界稳定 |
| BB002 症状分类 | crash/ANR/UI-hang/state-mismatch 四类 | 分类与 raw_report 字段映射正确 |
| BB004 HypothesisEngine | proposed→verifying→confirmed/refuted；refuted 永久保留（INV-2）；步数耗尽转缺口 | 状态迁移合法；refuted 不被删除 |
| BB004 换方向 | 回溯父节点切兄弟分支；rootcause 回退（overturning）| 树结构正确更新；overturning_signal/overturning_stage 填充 |
| BB006 ConfidenceScore | 三维组合 → Tier 1-4 | tier 分流阈值稳定 |
| BB007 AutoFixer | template→llm→history_calibration 优先级；Tier2 产出 is_draft=true | strategy_chain 记录完整 |
| BB008 RegressionVerifier | 三关：复现序列/既有测试/静态检查；fail 区分根因错 vs 补丁错 | fail-根因错→BB004 回退；fail-补丁错→BB007 重试 |
| BB008 Tier1 vs Tier2 验证口径（INV-2 分级） | Tier1：三关全过才提普通 PR；Tier2：轻量验证（静态检查 + 可验证子集）+ is_draft=true + rationale 含未验证项 | Tier1 三关任一 fail→不提 PR；Tier2 轻量 fail→不提 draft；Tier2 通过但完整回归未跑→提 draft + 标 unverified；人工审核阶段补回归（见 backend 5.1） |
| KBRetriever | symptom_type 预过滤 + pgvector 排序；stale 降权（×0.5）；conflicting 成组返回；冷启动 top_k<0.5 → degraded=true | 两阶段检索正确；降级路径触发 |
| 负向知识反查 | 相似度 >0.85 剪枝 / 0.6-0.85 降权 / <0.6 不影响 | 阈值分支正确 |
| BB010 GapDiagnoser | 四类缺口（信息/设施/模式/模型）识别 | 类型判定准确 |
| BB011 ReflowManager | 补齐事件检测 + 同类 bug 回流 + reflow_count 上限保护 | 超上限转 wont_reflow，不再自动回流（AP-1） |
| BB015 ManualFixRecorder | 人修 patch → KB pattern；仅此路径写 pattern 层（INV-3/AP-3） | 其他模块写 pattern 层应被权限校验拒绝 |
| BF001 归一化 | Bugly/Sentry/Crashlytics 三平台 raw → 统一 BugReport | 字段映射无丢失；versionCode 必携带（INV-1） |

#### 状态机迁移矩阵（参数化测试）

| 实体 | 场景 | 覆盖 |
|------|------|------|
| BugReport (14 态) | 全部合法迁移 + 关键非法迁移（如 concluded → assessing 应拒绝；concluded 仅可 → reflowed 显式触发，INV-3） | 14 态枚举以 backend 4.1 唯一定义为准：`received/assessing/degraded/reproducing/located/fixing/verified/pr_open/draft_pr/gap_pending/wont_reflow/concluded/reflowed/reflected`。合法迁移测试基准分两路径：**路径 A**（缺口补齐回流）按 analysis 状态流转表 `gap_pending → received`；**路径 B**（已合并后回归）按 backend 4.1 `reflowed` 定义 `concluded/reflected → reflowed → received`。两条路径合法迁移 100% 覆盖 |
| Hypothesis (4 态) | proposed→verifying→{confirmed\|refuted}；confirmed→refuted（overturning） | 全部迁移 |
| CapabilityGap (7 态) | identified→waiting→unblocked→{resolved\|invalid_unblock\|wont_reflow\|wont_fix} | 全部迁移；状态只能改不能删（INV-2） |

### 功能节点覆盖矩阵（feature-map 全量 planned 节点）

> 每个 planned 节点必须有测试落点（BB014 deferred 豁免）。下表把 feature-map 所有节点映射到测试类型与核心断言，避免 plan 阶段漏任务。

| 节点 | 名称 | 测试类型 | 核心断言 | 覆盖位置 |
|------|------|---------|---------|---------|
| BF001 | Bug 上报接入适配器 | 单元 + 集成 | Bugly/Sentry/Crashlytics 三平台归一化；versionCode 必携带（INV-1）；webhook 幂等 | 关键业务逻辑表 + API 表 |
| BF002 | 复现执行引擎 | 独立集成（手动）+ 单元（mock） | 模拟器启停/ADB 动作/截图采集；超时重试；启动失败转设施缺口 | 故障注入表 + 暂不测试 |
| BF003 | 视觉决策引擎 | 单元（LLM mock） | prompt_type 分发；降级路径（LLM 失败不崩）；响应解析失败重试 | 故障注入表 |
| BF004 | 信号监听器 | 单元 + 集成 | logcat/Flutter error/进程/视觉四类信号解析；信号路由 | 关键业务逻辑表（BB004 消费侧） |
| BF005 | KB 存储 | 集成（真实 PG+pgvector） | 三层检索；stale/conflicting 过滤；冷启动降级 | 关键业务逻辑表 KBRetriever |
| BF006 | Playbook 注册中心 | 单元 + 集成 | Schema 校验；按症状检索 | 关键业务逻辑表 BB003 依赖 |
| BF007 | 锚点库 | 单元 | 锚点匹配；视觉特征向量比对 | BB003 探测侧 |
| BF008 | Capability Gap 存储 | 集成 | 缺口条目 CRUD；状态迁移；linked_bug_ids 关联 | 状态机矩阵 + API 表 |
| BB001 | ISM | 单元 | 完备/临界/不足三档；阈值边界 | 关键业务逻辑表 |
| BB002 | 症状分类器 | 单元 | crash/ANR/UI-hang/state-mismatch 四类 | 关键业务逻辑表 |
| BB003 | Playbook 执行器 | 单元（mock BF002/BF003）+ 集成 | 复现+探测+诱发编排；步数预算耗尽转缺口 | 关键业务逻辑表 BB004 + 故障注入 |
| BB004 | 假设树引擎 | 单元 + 状态机 | 4 态迁移；换方向/回溯/根因回退；refuted 永久保留（INV-2）；负向知识反查 | 关键业务逻辑表 + 状态机矩阵 |
| BB005 | 根因定位器 | 单元 | 命中信号反向追溯代码位置；trace 准确性 | 本表新增行（下） |
| BB006 | 修复置信度评估器 | 单元 | 三维组合→Tier 1-4；阈值稳定 | 关键业务逻辑表 |
| BB007 | 自动修复器 | 单元 | template→llm→history_calibration 优先级；Tier2 is_draft=true | 关键业务逻辑表 |
| BB008 | 回归验证器 | 单元 + 集成 | 三关；Tier1/Tier2 分级（INV-2 细化）；fail 分流 | 关键业务逻辑表 + Tier1/Tier2 行 |
| BB009 | PR 提交器 | 单元（mock git_client） | Tier1 普通 PR / Tier2 draft PR 分流；push 失败不破坏状态 | 关键业务逻辑表 + 故障注入 |
| BB010 | 缺口诊断器 | 单元 | 四类缺口（信息/设施/模式/模型）识别 | 关键业务逻辑表 |
| BB011 | 缺口补齐回流器 | 单元 + 集成 | 补齐事件检测；同类 bug 回流；reflow_count 超限转 wont_reflow（AP-1） | 关键业务逻辑表 |
| BB012 | 诊断报告生成器 | 单元 | 结构化 JSON + markdown 双输出；字段完整 | 本表新增行（下） |
| BB013 | 反思 agent | 单元（LLM mock） | 负向知识提取；命中线索；写入 raw_trajectory/negative_knowledge 层 | 本表新增行（下） |
| BB014 | 知识聚合器 | deferred | MVP 外，豁免 | 暂不测试 |
| BB015 | 人工修复录入器 | 单元 + 权限测试 | 人修→KB pattern；**仅此路径写 pattern 层**（INV-3/AP-3）；其他模块写 pattern 应被拒绝 | 关键业务逻辑表 |
| FF001 | 报告与工单 API | 集成 | 全部 /reports/* 端点 | API 端点表 |
| FF002 | 缺口视图 API | 集成 | /gaps + /unblock | API 端点表 |
| FB001 | 诊断报告详情页 | 前端单测 + 契约 | 渲染 + 假设树 + 补丁 + 反馈 | 前端测试场景表 |
| FB002 | PR 审核界面 | 外链（不测） | 复用 GitHub/GitLab | 暂不测试 |
| FB003 | 缺口视图 | 前端单测 + 契约 | 列表排序 + 补齐 | 前端测试场景表 |
| FB004 | 信息追问表单 | 前端单测 + 契约 | 候选渲染 + 提交 + 空候选 | 前端测试场景表 |

**BB005 / BB012 / BB013 补充断言**（上表引用）：

| 节点 | 核心断言 |
|------|---------|
| BB005 根因定位器 | 命中信号（堆栈帧/日志关键词/视觉锚点）→ 代码文件:行 映射准确；多信号冲突时优先级；无匹配→返回 located 状态但 root_cause_hypothesis_space 为空（转缺口） |
| BB012 诊断报告生成器 | 输出 JSON 含 bug_report_id/tier/trajectory_id/root_cause/confidence/gaps；markdown 可读；字段缺失时不崩（降级输出） |
| BB013 反思 agent | 输入 trajectory（含 refuted）→ 提取 negative_knowledge 条目；区分「被证伪假设」vs「命中线索」；仅写 raw_trajectory/negative_knowledge 层，不写 pattern 层（权限校验） |

### 前端测试场景

| 组件/页面 | 正常交互 | 异常状态 | 边界 |
|----------|---------|---------|------|
| ReportListPage | 分页/过滤/跳详情 | loading/error/empty | 无数据/超大页 |
| ReportDetailPage | 渲染报告头+假设树+补丁+反馈 | loading/error | 无 FixPatch / 无 trajectory |
| HypothesisTree | 四态→三色映射；refuted 保留可见 | 空树 | 深层嵌套（10 层）/ 大量节点（100+） |
| FixPatchCard | diff 渲染；is_draft 标识 | 无 patch | 超大 diff |
| RegressionFeedbackForm | 提交成功 → message | 409 状态非法 | 非允许状态隐藏入口（与 backend allowed states 对齐） |
| GapList | 按 estimated_unlock_value 降序 | empty | 单条 |
| GapUnblockAction | 提交 → invalidate 刷新 | error 保留输入 | 非 waiting 隐藏 |
| ClarifyForm | 渲染候选 → 提交回跳 | 空候选（提示+返回按钮） | 候选=1 |
| PageContainer | loading 骨架 / error 重试 / empty | — | — |
| StatusBadge | 14 态 + tier 1-4 渲染 | — | — |
| apiClient | 400/404/409/5xx 错误码映射 | — | 网络断开 |

### 契约测试

| 契约 | 前端期望（MSW handlers.ts） | 后端实际（OpenAPI） | 验证方式 |
|------|---------------------------|-------------------|---------|
| GET /reports | 分页 DTO | FastAPI response_model | vitest spec + OpenAPI diff CI |
| GET /reports/{id} | BugReport Schema | 同上 | 同上 |
| GET /reports/{id}/trajectory | Trajectory + Hypothesis[] | 同上 | 同上 |
| GET /reports/{id}/clarify-options | ClarifyOption[] | 同上 | 同上 |
| POST /reports/{id}/clarify | BugReport(clarify_requested=false) | 同上 | 同上 |
| POST /reports/{id}/regression-feedback | 200 `{metric_point_id,status_before,status_after,reflow_scheduled}` / 409 | 同上 | 同上 |
| GET /gaps | CapabilityGap[] | 同上 | 同上 |
| POST /gaps/{id}/unblock | CapabilityGap(status=unblocked) | 同上 | 同上 |
| Hypothesis.status 枚举 | proposed/verifying/confirmed/refuted | 同上 | 类型对齐 + 枚举值校验 |
| ConfidenceScore 三维字段 | dim_info_completeness/dim_verification_feasibility/dim_patternability | 同上 | 字段名 + 类型 |
| CapabilityGap.unlock 价值字段 | estimated_unlock_value | 同上 | 字段名（非 unlock_value） |

> **drift 守护**：handlers.spec.ts 校验响应 Schema 自洽；联调阶段切真实后端跑冒烟；backend OpenAPI 变更触发 CI 比对 handlers.ts，drift 失败阻塞合并。
>
> **唯一契约源**：以 backend FastAPI/Pydantic `response_model` 自动生成的 OpenAPI artifact（`/openapi.json`）为前后端唯一契约源。生成时机：backend CI 构建 step 导出 `openapi.json` → 提交到 `contracts/openapi.json`（或发布到内部 schema registry）。frontend MSW handlers.ts + types/ 必须从该 artifact 派生（可用 openapi-typescript 生成 types）。backend design 4.3 注「DTO 详细格式到 tasks 阶段定义」指 Pydantic model 的具体字段——一旦 tasks 阶段定义，即固化为 OpenAPI artifact，成为不可变契约，变更走 PR review。

## 3. 验收标准

> 与 backend/frontend design 第 7 节对齐，聚焦可测试性。

| 验收条件 | 验证方式 | 关联测试场景 |
|----------|---------|-------------|
| backend 单测全过 | `pytest tests/unit/ -v` | 后端关键业务逻辑表 |
| backend 集成测试全过 | `pytest tests/integration/ -v`（Testcontainers 起 PG+pgvector） | API 端点测试表 |
| backend 覆盖率 ≥80%（核心业务） | `pytest --cov=app --cov-report=term-missing` | 单元+集成 |
| frontend 单测全过 | `vitest run` | 前端组件表 |
| frontend 覆盖率 ≥80%（组件+hooks+utils） | `vitest run --coverage` | 同上 |
| 契约测试全过 | `vitest run handlers.spec.ts` + OpenAPI diff | 契约测试表 |
| 状态机迁移矩阵全过 | `pytest tests/state_machine/ -v`（参数化） | 状态机迁移矩阵 |
| 三图一致（前端） | 类图/模块依赖图/项目结构节点对应关系单测 | 第 1 轮 review 已校验 |
| 假设树四态三色映射正确 | vitest：mock 四态节点 → 断言渲染颜色 | HypothesisTree |
| 回归反馈 allowed states 对齐 | 单测：allowed 5 态（pr_open/draft_pr/concluded/reflected/reflowed）显示入口，其余 9 态隐藏入口 | RegressionFeedbackForm |
| 缺口按 estimated_unlock_value 排序 | 单测 + 集成（真实 PG 排序） | GapList |
| BF001 三平台归一化 | 单测：Bugly/Sentry/Crashlytics fixture → 同一 BugReport | BF001 |
| KB 三层检索权限 | 单测：非 BB013/BB015 模块写 pattern 层 → 拒绝 | INV-3 / AP-3 |
| 全链路冒烟（手动） | docker-compose 全栈 + LLM/模拟器 mock，跑 1 条 Tier1 主链 | 手动跑通 + 截图归档 |

## 4. 集成测试方案

### 环境拓扑

| 组件 | 方式 | 说明 |
|------|------|------|
| backend FastAPI | 本地 uvicorn 启动（pytest fixture） | httpx.AsyncClient 直连 |
| PostgreSQL + pgvector | Testcontainers（真实容器） | 必须真实：验证向量检索 SQL + 向量索引行为；每测试隔离 schema |
| LangGraph 编排 | 真实（Python 进程内） | 状态机流转必须真实验证 |
| LLM API（LLMGateway） | Mock（fakeresponses） | 成本+稳定性；固定响应验证编排逻辑 |
| Android 模拟器 + ADB | Mock（BF002 接口层打桩） | 集成测试不启模拟器；BF002 独立集成测试单独跑（见下） |
| Git 平台 API | Mock（git_client 打桩） | 不真实提 PR；验证 BB009 分流逻辑 |
| Bug 上报平台 webhook | fixture（本地 POST） | 用 BF001 各平台 fixture 文件 |
| frontend（vitest） | jsdom | MSW 拦截 fetch，不需要真实 backend |
| frontend（联调冒烟） | 本地 vite dev + 真实 backend | 切 VITE_USE_MOCK=false |

### 启动与清理

```bash
# backend 集成测试（Testcontainers 自动起 PG）
pytest tests/integration/ -v
# Testcontainers 每 test 自动 create/drop schema，无需手动清理

# backend BF002 模拟器独立集成（手动触发，不进主 CI）
pytest tests/integration_bf002/ -v --run-emulator

# frontend 测试
cd frontend && vitest run
# 契约 + 单测一并跑

# 全栈冒烟（手动，发布前）
docker compose -f docker-compose.test.yml up -d
# 切 VITE_USE_MOCK=false 跑前端冒烟
```

### 真实 vs Mock 边界

| 依赖 | 真实 / Mock | 理由 |
|------|------------|------|
| PostgreSQL + pgvector | 真实（Testcontainers） | 验证向量索引、SQL、事务、连接池；H2/SQLite 无 pgvector |
| LangGraph 编排 | 真实 | 状态机是核心逻辑，不能 mock |
| LLM API | Mock | 成本（视觉决策 token 高）+ 不稳定 + 输出不确定 |
| Android 模拟器 + ADB | Mock（主链）/ 真实（BF002 独立集成） | 启动慢、不稳定；BF002 单独覆盖 |
| Git 平台 API | Mock | 不应自动化真实提 PR；分流逻辑可 mock 验证 |
| 上报平台 webhook | fixture | 离线可控 |
| 前端 fetch（MSW） | Mock | 前端独立可测；联调切真实 |

### 故障注入方式

| 场景 | 注入手段 | 预期行为 |
|------|---------|---------|
| LLM API 超时/500 | LLMGateway mock 延迟/异常 | BB003/BB007 降级（KB 走冷启动降级路径） |
| LLM 返回不合法 JSON | mock 返回乱码 | 解析失败 → 重试 N 次 → 写 trajectory 事件 → 不崩 |
| PG 连接断开 | Testcontainers stop | apiClient 5xx → 全局错误通知；重连后恢复 |
| pgvector 索引失效 | EXPLAIN 验证走顺序扫描 | 测试断言走 ivfflat 索引（性能护栏） |
| 模拟器启动失败 | BF002 mock 抛异常 | BB003 → Tier3 缺口诊断（设施缺口） |
| ADB 动作超时 | mock 延迟 | BF002 重试 → 失败转 trajectory 事件 |
| KB 检索全 <0.5 | 植入远向量 | degraded=true → BB006 模式维度低分 / BB007 直生成 |
| Git push 拒绝（权限） | mock 403 | BB009 错误事件 + 不破坏 BugReport 状态 |
| Webhook 重复 event_id | 重复 POST | 409 幂等拒绝 |
| 步数预算耗尽 | 植入大 step_used | BB004 不再换方向 → BB010 缺口诊断 |
| PR 合并后回归 | POST regression-feedback outcome=regression（concluded 态） | MetricPoint 写入 + `status→reflowed` + `reflow_scheduled=true` + CapabilityGap 反馈链路 |

## 5. 测试数据与 Mock 实现策略

### 测试数据准备

| 数据类型 | 准备方式 | 位置 |
|---------|---------|------|
| BF001 三平台 raw_report | fixture 文件（Bugly/Sentry/Crashlytics 真实样本脱敏） | `tests/fixtures/webhook/` |
| BugReport 14 态种子 | factory（bug_report_factory）覆盖每个 status 值 | `tests/factories/` |
| Hypothesis 4 态树 | factory 构造 proposed/verifying/confirmed/refuted + overturning 树 | 同上 |
| CapabilityGap 7 态 | factory 每态各 1 条 + 不同 estimated_unlock_value | 同上 |
| KB 三层条目 | seeder（raw_trajectory / negative_knowledge / pattern）+ 向量预生成 | `tests/seeders/kb.py` |
| ClarifyOption 候选 | factory（KB 派生 / 空候选） | 同上 |
| 前端 MSW 响应模板 | handlers.ts 内联 fixture（与 backend DTO 对齐） | `frontend/src/mocks/handlers.ts` |
| LLM 响应模板 | fakeresponses（视觉决策/修复/反思各场景） | `tests/fixtures/llm/` |

### Mock 实现细节

**backend LLMGateway mock**：
```python
# tests/conftest.py
class FakeLLMGateway:
    def __init__(self, response_map): self.responses = response_map
    async def complete(self, prompt_type, **kw): return self.responses[prompt_type]
```
按 `prompt_type`（vision_decision / symptom_classify / fix_patch / reflection）分发固定响应，覆盖正常+异常+降级路径。真实网关映射（golden-set 跑真实 LLM 时用）：`vision_decision → GLM-5V-Turbo`，`symptom_classify/fix_patch/reflection → glm-5.1`，均经 New API（D2）。

**BF002 模拟器 mock（双模式，见 backend 5.1 BB003 双执行模式）**：
```python
class FakeReproduceEngine:        # 复现模式：确定性跑脚本
    async def reproduce(self, bug_report_id):
        return ReproduceResult(success=True, signals=FIXED_SIGNALS[bug_report_id])

class FakeADBTools:              # 探测/诱发模式：agent tool-calling loop
    async def screenshot(self): return FIXTURE_SCREENSHOTS.next()  # 按脚本返回预设截图序列
    async def tap(self, x, y): return {"ok": True}
    async def swipe(self, *a): return {"ok": True}
```
复现模式注入预设信号，验证 BB003/BB004 对信号的消费逻辑；探测/诱发模式用 `FakeADBTools` 返回预设截图序列，验证 BF003（GLM-5V-Turbo）的 tool_call 决策链与步数预算（D7）约束。

**frontend MSW handlers**：见 frontend design「MSW 覆盖清单」8 个端点全量模板；handlers.spec.ts 校验响应 Schema 自洽。

### 测试隔离策略

| 层 | 隔离方式 |
|----|---------|
| backend 集成 | 每 test 创建独立 PG schema（Testcontainers），test 结束 drop；无共享状态 |
| backend 单测 | 全 mock，无 DB 依赖 |
| 状态机测试 | 每 case 新建实体实例，不依赖前 case |
| frontend vitest | jsdom 每 test 重置；MSW server.listen/resetHandlers |
| 契约测试 | 纯 schema 比对，无副作用 |

**禁止共享 DB 状态**：R001 trajectory 永久保留（INV-2），但测试环境必须隔离——测试产生的 trajectory 不能污染；用独立 schema + test 结束 drop 解决。

## 6. 暂不测试

| 功能 | 理由 | 风险评估 |
|------|------|---------|
| 全链路真实 E2E（含模拟器+真实 LLM） | CI 成本与稳定性不可承受；LLM 输出不确定 | 中（靠 MetricPoint 线上观测 + 发布前手动冒烟） |
| BF002 真实模拟器集成进主 CI | 启动慢、不稳定、跨平台 | 中（独立可选集成 `tests/integration_bf002/`，手动触发 `--run-emulator`） |
| LLM 真实输出质量 | 非确定性，无法断言 | 高（替代验收见下） |
| 视觉决策准确率 | 依赖具体 LLM provider 选型 | 高（替代验收见下） |
| Git 平台真实 API（提真实 PR） | 不应自动化；破坏外部仓库 | 低（mock 验证分流逻辑足够） |

### 高风险项替代验收方案

> 两个「高风险」项必须有可执行替代验收，不能仅靠线上观测被动发现问题。

**LLM 真实输出质量**（影响 BB002 症状分类 / BB004 假设生成 / BB007 修复 patch / BB013 反思）：

| 替代验收 | 方式 | 阈值/责任人 |
|---------|------|-----------|
| 离线 golden set 回归 | 维护 `tests/golden/llm_quality/`：每类 prompt_type 预埋 20+ 标注样本（输入 prompt + 期望输出 Schema + 关键字段），用真实 LLM provider 跑（可手动/夜间 job），断言 Schema 合规率 + 关键字段命中率 | Schema 合规率 ≥95%；关键字段命中率 ≥80% |
| 发布前人工抽检 | 每次发布前，维护者从近期 trajectory 随机抽 5 条，人工评估 LLM 输出合理性 | 5 条中严重问题 ≤1 条方可发布 |
| 线上 MetricPoint effectiveness | 自动化观测：自动修复成功率、根因定位准确率（合并后人工标 ground truth） | 冷启动期 effectiveness ≥30%（baseline，逐版本提升） |

**视觉决策准确率**（BF003 多模态模型看截图决策下一步）：

| 替代验收 | 方式 | 阈值/责任人 |
|---------|------|-----------|
| 视觉决策 golden set | D11 冷启动期锚点库为空，改用**人工造截图样本**（正常页面截图 + 文字预期）作 ground truth；BF003 对同一截图决策，断言识别准确率 | 冷启动 ≥50%（无锚点对照降级）；到公司录入锚点后 ≥70% |
| 诱发动作可执行性 | 视觉决策输出的 ADB 动作（tap/swipe/text）在模拟器上可执行率（不报错） | 可执行率 ≥85% |
| 线上 trajectory 回放抽检 | 发布前抽 3 条 trajectory，人工评估视觉决策步骤合理性 | 3 条中无明显错误决策 |
| 性能/压测 | MVP 阶段流量小 | 低 |
| 暗黑模式渲染 | frontend 第 8 节暂不实现 | 低 |
| i18n | 同上 | 低 |
| 鉴权/越权（MVP 无鉴权） | architecture.md CON-2 未锁鉴权；FF001/FF002 默认内网 | 中（TODO：MVP 后补，目前 GET /reports 标 TODO） |
| 跨 bug 聚合（BB014） | backend 第 8 节 deferred | 低 |

### 开放参数验收口径（冷启动期）

> analysis 待确认 #5/#6/#11 的**数值**需运行后才有，但**验收方法必须在开始前定死**，否则集成验收时无据可依。冷启动期（KB pattern 层条目 < config.N）验收口径 = 「方法可执行 + 出基线报告」即通过，不设达标线；达标线待 KB 累积期校准。

| 开放参数 | 验收方法（开始前定死） | 冷启动期通过判据 | 达标线（KB 累积期目标） |
|---------|----------------------|----------------|----------------------|
| LLM patch 命中率（待确认 #5） | 人工造 N=20 标注样本（崩溃型 bug + 已知正确 patch），跑 BB007 真实 LLM，断言 patch 可编译 + 通过该 bug 复现序列 | 出「命中率基线报告」（命中率 X% 记录在案、可复跑） | 逐版本对比提升，无硬线 |
| 修复置信度校准（待确认 #6） | 收集「置信度分桶 vs 实际成功率」配对数据，画 reliability diagram + 算 Brier score / ECE | 出「校准基线报告」（diagram 可生成，Brier score 记录在案） | ECE < 0.2 |
| 五维验收埋点（待确认 #11） | backend 5.5 MetricPoint 五维计算口径可执行，能从 DB 查出五个维度数值 | 「可观测」即通过：查询 MetricPoint 返回五维非空 | 阈值参数化待校准 |
| 视觉决策准确率（D11 降级） | 见上表「视觉决策 golden set」：人工造截图样本（锚点库冷启动空） | 冷启动 ≥50% | ≥70%（锚点录入后） |

**关键区分**：数值（命中率 X%、Brier score Y）运行后才产生，design 阶段不定死；验收方法（用什么样本、测什么、出什么报告）design 阶段必须定死。MVP 验收 = 「方法可执行 + 基线报告产出」，**不等于**「数值达标」。

> **风险评估说明**：「高」风险项必须有替代验收手段（MetricPoint 线上观测 / 手动冒烟 / 独立可选集成测试），不能完全无覆盖。
