---
version: "1.0"
type: tasks
topic: client-bug-fix-agent
requirement_cycle: R001
workflow:
  evaluate_provider: codex
  mode: auto
status: planned
---

# 客户端 Bug 修复 Agent — 后端任务清单

基于 [backend design](analysis/2026-06-16--client-bug-fix-agent-backend.md) 拆解。前端见 [frontend-tasks](client-bug-fix-agent-frontend-tasks.md)。

## 全局约束

- **语言/框架**：Python 3.11+ / LangGraph（编排 D1）/ FastAPI（API+BFF）/ SQLAlchemy + PostgreSQL+pgvector（同库 D4）
- **LLM**：LLMGateway 走 OpenAI 兼容协议对接 New API 网关；文本 `model=glm-5.1`，视觉 `model=GLM-5V-Turbo`，按 `prompt_type` 路由（D2）。用 `openai` SDK，`base_url` 指 New API
- **部署**：agent + 前端 + PG 全 docker；Android 模拟器宿主原生；agent 容器经 `host.docker.internal:5037` adb 桥连模拟器（D10）
- **不变量**：人在合并闸门（INV-2）；trajectory/refuted 假设/concluded 工单永不删（INV-2）；KB pattern 层仅 BB015 写（INV-3/AP-3）；concluded 不可回退除 reflowed（INV-3）
- **禁止**：agent 自主合并 PR；跨层调用（API→BF 必须经 Orchestrator/BB）
- **命名**：BugReport.status 14 态唯一定义在 backend 4.1，test/frontend 引用此
- **版本号**：各依赖最新稳定版经 `pip index versions` 确认后写入 pyproject.toml
- **暂不实现**：BB014 跨 bug 聚合（KBEntry.layer=aggregated 预留）；相似 issue 查询 API；真实全链路 E2E（仅手动冒烟）

## 执行顺序

> 按层依赖排序。数据结构 → 基础设施服务 → M5存储 → M2复现探测 → M1评估 → M3诊断 → M4修复 → M5成长 → 入口/编排/API → 部署 → 集成测试。

1. ✅ INF01 项目骨架与依赖
2. ✅ INF02 config.py（预算/阈值/LLM 参数）
3. ✅ INF03 db.py（SQLAlchemy + pgvector）
4. ✅ SCH01 核心 Schema（8 + MetricPoint）
5. ✅ SCH02 边界协议 Schema（ReproStep/Signal/Anchor/DiagnosisReport/ManualFixEntry）
6. ✅ INF04 LLMGateway（D2）
7. ✅ INF05 adb_client.py（subprocess + 网络桥）
8. ✅ INF06 git_client.py
9. ✅ BF005 KB 存储（stores + retriever + staleness）
10. ✅ BF008 Gap 存储 + 解锁价值评分
11. ✅ BF002 复现执行 + ADB 工具层
12. ✅ BF003 视觉决策引擎
13. ✅ BF004 信号监听器
14. ✅ BF006 Playbook 注册中心 + 崩溃型 Playbook
15. ✅ BF007 锚点库（D11 能力先建，数据冷启动空）
16. ✅ BF001 Bug 上报接入适配器（D8 Sentry 第一适配器）
17. ⬜ BB001 信息完备度评估（ISM）
18. ⬜ BB002 症状分类
19. ⬜ BB006 修复置信度评估
20. ⬜ BB003 Playbook 执行器（双模式）
21. ⬜ BB004 假设树引擎（换方向/回溯/步数预算）
22. ⬜ BB005 根因定位
23. ⬜ BB012 诊断报告生成器
24. ⬜ BB007 自动修复器
25. ⬜ BB008 回归验证器（三关 + Tier 分级）
26. ⬜ BB009 PR 提交器
27. ⬜ BB010 缺口诊断器
28. ⬜ BB011 回流管理
29. ⬜ BB013 反思 agent
30. ⬜ BB015 人工修复录入器
31. ⬜ ORB01 Orchestrator（LangGraph 状态机）
32. ⬜ FF001 report_router
33. ⬜ FF002 gap_router
34. ⬜ ENT01 main.py（FastAPI 入口）
35. ⬜ DEP01 docker-compose + Dockerfile + Makefile
36. ⬜ INT01 backend 集成测试（API + Testcontainers）
37. ⬜ INT02 状态机迁移矩阵测试
38. ⬜ INT03 BF002 模拟器独立集成（手动触发）
39. ⬜ INT04 golden set + 开放参数验收基线
40. ⬜ 最后 — 编译验证 + 全测试路径

---

## R001-INF01：项目骨架与依赖 `✅ 已完成`

- 文件：`agent/pyproject.toml`、`agent/__init__.py` 及 3.1 目录树空骨架
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `pip install -e agent/` 成功
  - 目录树与 design 3.1 一致（intake/reproduce/vision/signal/kb/playbook/anchor/gap/assessment/diagnosis/fix/gap_mgmt/report/reflection/api/schemas/infra + orchestrator.py + main.py）
- decision_refs: [D1, D4]
- test_tasks:
  - type: integration
    description: 安装可导入 + 目录树与 design 3.1 一致性校验
    scenarios: [INF01 骨架可构建]
- blocked_files: []

### INF01.1 pyproject.toml `✅`
依赖：langgraph, fastapi, uvicorn, sqlalchemy, pgvector(both python pkg + PG ext), openai, adbutils 或 subprocess 封装, pydantic, httpx, pytest, testcontainers。版本号经 `pip index versions <pkg>` 确认最新稳定版写入。

### INF01.2 目录空骨架 `✅`
按 design 3.1 建 agent/ 全部子目录 + `__init__.py`，tests/{unit,integration,state_machine,integration_bf002,golden,fixtures}。

---

## R001-INF02：config.py `✅ 已完成`

- 文件：`agent/infra/config.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [INF01]
- priority: 5
- mode: direct
- status: pending
- acceptance_criteria:
  - 步数/token 预算、LLM base_url/model、KB 阈值均可从环境变量/config 读取
- decision_refs: [D2, D7, D9]
- test_tasks:
  - type: unit
    description: 各参数默认值与 D7 一致；环境变量覆盖优先级；LLM model 按 prompt_type 路由映射
    scenarios: [D7 预算默认值校验, D2 model 路由映射]

### INF02.1 参数定义 `✅`
```python
# 步数预算（D7 默认值，待校准）
SINGLE_HYPOTHESIS_STEP_BUDGET = 5
GLOBAL_STEP_BUDGET = 30
TOKEN_BUDGET_PER_BUG = 50000
FIX_RETRY_MAX = 3
# LLM（D2）
LLM_BASE_URL = env("NEW_API_BASE_URL")  # New API 网关
LLM_TEXT_MODEL = "glm-5.1"      # BB002/BB004/BB007/BB013
LLM_VISION_MODEL = "GLM-5V-Turbo"  # BF003
# KB 阈值（D6/D9，待校准）
KB_SIMILARITY_FLOOR = 0.5
KB_NEGATIVE_PRUNE = 0.85
KB_NEGATIVE_DEMOTE = 0.6
KB_STALE_DEMOTE = 0.5
KB_COLD_START_N = 10  # pattern 层条目 < N → cold_start
# ADB 网络桥（D10）
ADB_HOST = "host.docker.internal"; ADB_PORT = 5037
```

---

## R001-INF03：db.py `✅ 已完成`

- 文件：`agent/infra/db.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [INF01]
- priority: 5
- mode: direct
- status: pending
- acceptance_criteria:
  - SQLAlchemy session + pgvector 扩展可用
  - Testcontainers 能起 PG+pgvector
- decision_refs: [D4]
- test_tasks:
  - type: integration
    description: Testcontainers 起 PG+pgvector；CREATE EXTENSION vector 成功；Vector 类型可读写
    scenarios: [D4 存储层基础设施]

### INF03.1 引擎与 session `⬜`
- `create_engine`（同步）/ `async_sessionmaker`；启动时 `CREATE EXTENSION IF NOT EXISTS vector`
- pgvector Python 侧：`from pgvector.sqlalchemy import Vector`

---

## R001-SCH01：核心 Schema（8 + MetricPoint） `✅ 已完成`

- 文件：`agent/schemas/{bug_report,playbook,trajectory,confidence,fix_patch,capability_gap,kb_entry,metric_point}.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF03]
- priority: 5
- mode: direct
- status: pending
- acceptance_criteria:
  - 字段与 backend 4.1 一一对应；14 态枚举唯一定义于此；Hypothesis 自引用树可建
- contract_refs: [analysis/2026-06-16--client-bug-fix-agent-backend.md]
- decision_refs: [D4]
- test_tasks:
  - type: unit
    description: BugReport.status 14 态枚举完整 + 唯一；Hypothesis 4 态 + parent_id 自引用可建树；CapabilityGap.status 7 态；ConfidenceScore 三维字段名；KBEntry.root_cause_signals 为 Vector 类型
    scenarios: [INT02 状态机矩阵依赖, 契约测试表枚举值校验]

### SCH01.1 BugReport + 状态枚举 `✅`
字段见 backend 4.1（含 14 态 status 唯一枚举、clarify_requested、reflow_count）。`STATUS_ALLOWED_REGRESSION_FEEDBACK = {pr_open,draft_pr,concluded,reflected,reflowed}`（regression-feedback 5 态）。

### SCH01.2 Playbook / Trajectory / Hypothesis `✅`
Playbook（symptom_type/detection_actions/hypothesis_space/passive）；Trajectory（root_hypothesis_id/total_step_budget/kb_reads）；Hypothesis 自引用树（parent_id/status: proposed/verifying/confirmed/refuted/overturning_*）。refuted 永久保留（INV-2）。

### SCH01.3 ConfidenceScore / FixPatch / CapabilityGap / KBEntry / MetricPoint `✅`
按 backend 4.1 完整字段。KBEntry.root_cause_signals = Vector(dim)；validity_status=valid/stale/conflicting（D9）。MetricPoint 五维 metric_type + bucket_dim（5.5）。

---

## R001-SCH02：边界协议 Schema `✅ 已完成`

- 文件：`agent/schemas/{repro_step,signal,anchor,diagnosis_report,manual_fix_entry}.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF03]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria:
  - ReproStep 含 step_no/action/target_coords/screenshot_ref/actual_signal 字段
  - Signal.signal_type ∈ {logcat, flutter_error, process, visual}；含 pattern/severity/source_config
  - Anchor 含 page_id/screenshot_ref/text_expectation；visual_features 为 Vector 类型
  - DiagnosisReport 含 format ∈ {json, markdown}；capability_gaps 为 list[str] FK
  - ManualFixEntry 含 patch_diff/trajectory_id/root_cause_text/trigger_conditions/json/kb_pattern_id（BB015→KB pattern 写入契约）
- test_tasks:
  - type: unit
    description: 五个边界 Schema 字段完整性 + 类型断言；Anchor.visual_features 向量类型；ManualFixEntry.trigger_conditions 结构（pattern 检索用）
    scenarios: [契约测试表边界 Schema, BB015 写 pattern 契约依赖]

### SCH02.1 五个边界 Schema `✅`
ReproStep（BF002 产出/BB008 回归复用）；Signal（四类 signal_type）；Anchor（visual_features Vector）；DiagnosisReport（JSON+markdown）；ManualFixEntry（BB015→KB pattern）。

---

## R001-INF04：LLMGateway `✅ 已完成`

- 文件：`agent/infra/llm_gateway.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [INF02]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - 按 prompt_type 路由到 text/vision model；OpenAI 兼容协议；超时/非法 JSON 重试 N 次不崩
- decision_refs: [D2]
- test_tasks:
  - type: unit
    description: FakeLLMGateway 按 prompt_type 分发；非法 JSON 重试；超时降级
    scenarios: [vision_decision, symptom_classify, fix_patch, reflection]

### INF04.1 接口与实现 `✅`
```python
class LLMGateway(Protocol):
    async def complete(self, prompt_type: Literal["vision_decision","symptom_classify","fix_patch","reflection"], **kw) -> LLMResponse: ...
# 实现：openai.AsyncOpenAI(base_url=LLM_BASE_URL)；prompt_type→model 映射（INF02）
```
逻辑：1) 按 prompt_type 选 model 2) 调 chat.completions（vision 带 image_url）3) 解析失败重试 FIX_RETRY_MAX 4) 超限/异常抛 LLMError 供调用方降级。

**实现摘要**：8 AC 全 pass（Sprint Contract agreed）。NewAPILLMGateway + FakeLLMGateway + LLMResponse + LLMError + _PROMPT_TYPE_TO_CHANNEL 路由层。17 单测 + 文本链路真实调用（glm-5.1 返回 "收到"）+ 视觉 skip。全量 117 passed, 1 skipped。evidence: `.dev-flow/R001/evidence/R001-INF04.md`

---

## R001-INF05：adb_client.py `✅ 已完成`

- 文件：`agent/infra/adb_client.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [INF02]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - 经 `adb -H host.docker.internal -P 5037` 连宿主 adb server；tap/swipe/screenshot/install 可执行
- decision_refs: [D3, D10]
- test_tasks:
  - type: integration
    description: 宿主起 adb server + 模拟器后，adb_client 六个动作（tap/swipe/input_text/screenshot/install_apk/press_key）可执行；动作超时触发重试；连不上 adb server 抛错不崩
    scenarios: [D10 adb 网络桥验证, BF002 独立集成依赖, 故障注入表 ADB 动作超时]

### INF05.1 subprocess adb 封装 `✅`
封装 `subprocess` 调 adb（网络桥参数）；暴露 `tap/swipe/input_text/screenshot/install_apk/press_key`，超时重试。BF002 工具层（BF002）复用此底座。

**实现摘要**：8 AC 全 pass（Sprint Contract agreed）。ADBClient + 三段式二进制解析 + 本地/网络桥自适应 + 6 动作 + 4 异常子类 + 连接错不重试。33 单测 + 3 集成 skip（无设备）。全量 150 passed, 4 skipped。evidence: `.dev-flow/R001/evidence/R001-INF05.md`

---

## R001-INF06：git_client.py `✅ 已完成`

- 文件：`agent/infra/git_client.py`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [INF01]
- priority: 4
- smoke_required: true
- mode: direct
- status: completed
- acceptance_criteria: blame/检索/建分支/commit/push 可执行；push 拒绝不破坏状态
- decision_refs: []
- test_tasks:
  - type: unit
    description: 本地临时 git 仓库 fixture；blame/grep 返回正确；建分支+commit 成功；push 403（权限拒绝）抛错事件且不破坏仓库状态
    scenarios: [关键业务逻辑表 BB009 push 拒绝, 故障注入表 Git push 拒绝]

### INF06.1 git 操作封装 `✅`
blame、grep 代码、create_branch、commit、push（BB009 用）。push 403 → 抛错事件，不破坏 BugReport。

**实现摘要**：acceptance_criteria 全 pass。GitClient + BlameLine/GrepMatch + GitPushRejectedError（BB009 契约）。纯 subprocess（不引 GitPython）。24 单测（blame/grep/branch/commit/push + 异常分类 + push 拒绝不破坏状态）。全量 174 passed, 4 skipped。evidence: `.dev-flow/R001/evidence/R001-INF06.md`

---

## R001-BF005：KB 存储（三层 + 检索 + 陈旧） `✅ 已完成`

- 文件：`agent/kb/stores/{trajectory_store,negative_knowledge_store,pattern_store}.py`、`agent/kb/retriever.py`、`agent/kb/staleness_checker.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [SCH01, INF03]
- priority: 5
- mode: negotiated
- status: completed
- acceptance_criteria:
  - 三层检索（symptom_type 预过滤 + pgvector 排序）；stale 降权×0.5 不删；conflicting 成组返回；冷启动 top_k<0.5 → degraded=true
  - **权限**：pattern 层仅允许 BB015 写入，其他模块写应被拒绝（INV-3/AP-3）
- contract_refs: [backend 5.3]
- decision_refs: [D5, D6, D9]
- test_tasks:
  - type: integration
    description: 真实 PG+pgvector 三层检索；stale/conflicting 过滤；冷启动降级；非 BB015 写 pattern 拒绝
    scenarios: [test 关键业务逻辑表 KBRetriever, 负向知识反查]

### BF005.1 stores 三层 `✅`
各层 CRUD；pattern_store 写入做调用方校验（仅 ManualFixRecorder）。

### BF005.2 KBRetriever（5.3 算法） `✅`
两阶段：预过滤（symptom_type+layer）→ pgvector 排序。stale×0.5；conflicting 成组（附 conflicting_entry_ids）；git_anchor 差异大 → 标 stale。输出 `List<{entry,similarity,validity_status,conflicting_with?}>` + `degraded:bool`。

### BF005.3 StalenessChecker `✅`
git_commit_anchor vs HEAD 差异 → revalidate → 失败标 stale（不删）。

### BF005.4 负向知识反查（BB004 用） `✅`
输入候选假设 → 检索 negative_knowledge → 相似度 >0.85 剪枝 / 0.6-0.85 降权×0.3 / <0.6 不影响。

**实现摘要**：9 AC 全 pass（Sprint Contract agreed）。三层 store + KBRetriever 两阶段 + StalenessChecker 注入式 + negate_hypotheses 三档。权限校验（KBPermissionError 不继承 PermissionError）。32 单测 + 31 集成（真实 pgvector）。全量 237 passed, 4 skipped, ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF005.md`

---

## R001-BF008：Gap 存储 + 解锁价值评分 `✅ 已完成`

- 文件：`agent/gap/gap_store.py`、`agent/gap/unlock_value_scorer.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [SCH01, INF03]
- priority: 4
- mode: direct
- status: completed
- acceptance_criteria: 缺口 CRUD；7 态迁移；linked_bug_ids 关联；状态只能改不能删（INV-2）
- decision_refs: [D12]
- test_tasks:
  - type: unit
    description: 7 态迁移矩阵；unlock_value = 频率×可修复比例
    scenarios: [状态机矩阵 CapabilityGap]

### BF008.1 unlock_value_scorer `✅`
`estimated_unlock_value = 同类 bug 历史频率 × 补齐后可修复比例`（两因子从 MetricPoint/trajectory 统计）。

**实现摘要**：acceptance_criteria 5/5 通过。GapStore + 7 态迁移矩阵 + INV-2 守护（GapDeleteError）+ linked_bug_ids JSON 关联。UnlockValueScorer 从 MetricPoint 统计 frequency + fix_ratio。10 单测 + 22 集成。全量 269 passed, 4 skipped, ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF008.md`

---

## R001-BF002：复现执行 + ADB 工具层 `✅ 已完成`

- 文件：`agent/reproduce/{emulator_pool,apk_installer,adb_tools,reproduce_runner,screenshot_collector}.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF05]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - ADB 工具层（tap/swipe/screenshot/install/press）可执行；复现模式确定性跑脚本；启动失败转设施缺口
- contract_refs: [backend 5.1 BB003 双模式]
- decision_refs: [D3]
- test_tasks:
  - type: integration
    description: BF002 独立模拟器集成（手动 --run-emulator）；超时重试；启动失败→设施缺口
    scenarios: [故障注入表]

### BF002.1 adb_tools（工具层，双模式共用） `✅`
封装 INF05 为统一工具接口：`tap/swipe/input_text/screenshot/install_apk/press_key`。复现脚本与 agent tool-calling 共用。

### BF002.2 reproduce_runner（复现模式） `✅`
确定性顺序调 adb_tools 跑 Playbook 复现脚本，采集 ReproStep + 信号。BF003 不参与（或仅关键节点校验截图）。

### BF002.3 emulator_pool / apk_installer / screenshot_collector `✅`
模拟器启停/分配；APK 安装；截图采集（喂 BF003）。

**实现摘要**：8 AC 全 pass（Sprint Contract agreed，conditional_pass）。adb_tools 7 函数 thin wrapper；emulator_pool 单模拟器 MVP + best-effort GapStore 降级；apk_installer install/launch/uninstall/version；screenshot_collector data_url+file_url 双模式；reproduce_runner 表驱动 dispatch + 默认 abort + logcat fallback。47 单测 + 2 集成（skipif）。全量 316 passed, 6 skipped, ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF002.md`

---

## R001-BF003：视觉决策引擎 `✅ 已完成`

- 文件：`agent/vision/vision_decision_engine.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF04, BF007]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: completed
- acceptance_criteria:
  - 看截图→决策下一个 ADB tool_call；LLM 失败降级不崩；D11 锚点空时纯 LLM 判断
- contract_refs: [backend 5.1 双模式②探测/诱发]
- decision_refs: [D2, D11]
- test_tasks:
  - type: unit
    description: LLM mock；prompt_type=vision_decision 分发；降级；响应解析失败重试
    scenarios: [故障注入表, 视觉决策 golden set]

### BF003.1 决策接口 `✅`
输入截图（+ 可选锚点对照）→ 输出下一个 tool_call（tap/swipe/...）+ 置信度。调 LLMGateway(vision_decision→GLM-5V-Turbo)。锚点库（BF007）为空时纯 LLM（D11 降级）。

**实现摘要**：8 AC 全 pass（Sprint Contract agreed）。VisionDecision dataclass + VisionDecisionEngine（decide async + 锚点对照双模式 + LLM 失败 fallback + 7 action 白名单 + 置信度加权融合）。23 单测 + 2 集成（skipif）。全量 356 passed, 8 skipped, ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF003.md`

---

## R001-BF004：信号监听器 `✅ 已完成`

- 文件：`agent/signals/{logcat_listener,flutter_error_listener,process_listener,visual_signal_detector,router}.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF05, SCH02]
- priority: 4
- mode: direct
- status: done
- acceptance_criteria: 四类信号（logcat/flutter_error/process/visual）解析 + 路由给 BB003/BB004
- test_tasks:
  - type: unit
    description: 四类信号 fixture 解析；路由正确
    scenarios: [关键业务逻辑表 BB004 消费侧]
- **实现摘要**：6 AC 全 pass（Mode 2 direct 验收）。四类信号监听器（logcat/flutter_error/process/visual）+ SignalRouter 路由。19 单测全 pass，全量 375 passed / 8 skipped，ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF004.md`

### BF004.1 四类 listener `⬜`
logcat/Flutter error（channel）/进程（崩溃/ANR）/视觉（白屏/Loading，配合 BF003+BF007）。产 Signal 喂 BB003。

---

## R001-BF006：Playbook 注册中心 + 崩溃型 Playbook `⬜ 待处理`

- 文件：`agent/playbook/{registry,schema}.py`、`agent/playbook/definitions/crash_playbook.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [SCH01]
- priority: 5
- mode: direct
- status: pending
- acceptance_criteria: Schema 校验；按 symptom_type 检索；崩溃型 Playbook（passive=true）可加载
- decision_refs: []
- test_tasks:
  - type: unit
    description: Schema 校验；按症状检索
    scenarios: [BB003 依赖]

### BF006.1 registry/schema `⬜`
Playbook Schema（SCH01）；registry 按 symptom_type 检索。

### BF006.2 crash_playbook `⬜`
MVP 第一个 Playbook：崩溃型（passive=true，被动等信号；hypothesis_space 含崩溃假设种子）。其余 4 类（blank/loading/no_response/data_error）建空定义占位，MVP 后补。

---

## R001-BF007：锚点库（D11 能力先建） `✅ 已完成`

- 文件：`agent/anchor/anchor_library.py`
- 改动类型：新建
- domain: backend
- task_layer: foundation
- depends_on: [INF03, SCH02]
- priority: 3
- mode: direct
- status: completed
- acceptance_criteria: 存储+检索+Schema 能力可用；数据冷启动为空；BF003 降级纯 LLM
- decision_refs: [D11]
- test_tasks:
  - type: unit
    description: 锚点匹配；视觉特征向量比对；空库降级
    scenarios: [BB003 探测侧]

### BF007.1 anchor_library `✅`
Anchor CRUD + 按 page_id 检索 + visual_features 向量比对。数据空，到公司录入激活（不改代码）。

**实现摘要**：6 AC 全 pass（Mode 2 direct）。AnchorLibrary CRUD + match_by_visual_features（pgvector 余弦）+ is_empty。空库返回 [] + BF003 降级契约。12 单测 + 5 集成（真实 pgvector）。全量 333 passed, 6 skipped, ruff All checks passed。evidence: `.dev-flow/R001/evidence/R001-BF007.md`

---

## R001-BF001：Bug 上报接入适配器 `⬜ 待处理`

- 文件：`agent/intake/bug_report_adapter.py`、`agent/intake/adapters/sentry_adapter.py`、`agent/intake/adapters/bugly_adapter.py`（占位）
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [SCH01]
- priority: 5
- mode: negotiated
- status: pending
- acceptance_criteria:
  - Sentry raw → 归一化 BugReport(received)；versionCode 必携（INV-1）；webhook event_id 幂等（重复 409）
- contract_refs: [backend 4.3 POST /webhook/{platform}]
- decision_refs: [D8]
- test_tasks:
  - type: unit
    description: Sentry/Bugly/Crashlytics fixture 归一化；versionCode 必携；幂等
    scenarios: [关键业务逻辑表 BF001, API 表 POST /webhook]

### BF001.1 抽象基类 + Sentry 适配器 `⬜`
`BugReportAdapter.normalize(raw) -> BugReport`；Sentry 第一适配器完整实现；bugly_adapter 占位。event_id 幂等表。

---

## R001-BB001：信息完备度评估（ISM） `⬜ 待处理`

- 文件：`agent/assessment/info_sufficiency_evaluator.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF04, BF005]
- priority: 4
- mode: negotiated
- status: pending
- acceptance_criteria: 完备/临界/不足三档打分；临界→clarify_requested=true（assessing 子回路）；不足→degraded
- contract_refs: [backend 5.1 追问 loop]
- decision_refs: []
- test_tasks:
  - type: unit
    description: 三档打分；阈值边界；临界追问
    scenarios: [关键业务逻辑表 BB001]

### BB001.1 ISM `⬜`
输入 BugReport → 打分（completeness_score）+ gaps（A/B/C/D）。完备→进 BB002；临界→clarify_requested=true；不足→degraded。追问候选从 KB 派生（BF005）。

---

## R001-BB002：症状分类 `⬜ 待处理`

- 文件：`agent/assessment/symptom_classifier.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF04]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: crash/blank/loading/no_response/data_error 分类正确
- test_tasks:
  - type: unit
    description: 五类分类；raw_report 字段映射
    scenarios: [关键业务逻辑表 BB002]

### BB002.1 分类器 `⬜`
调 LLMGateway(symptom_classify→glm-5.1)。输出 symptom_type（5 类）。

---

## R001-BB006：修复置信度评估 `⬜ 待处理`

- 文件：`agent/assessment/confidence_evaluator.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF005]
- priority: 4
- mode: negotiated
- status: pending
- acceptance_criteria: 三维（info/verify/pattern）组合→Tier 1-4；KB 模式命中影响 pattern 维
- contract_refs: [backend 5.5]
- decision_refs: [D6]
- test_tasks:
  - type: unit
    description: 三维→Tier 阈值稳定；KB 模式命中影响
    scenarios: [关键业务逻辑表 BB006]

### BB006.1 ConfidenceEvaluator `⬜`
三维打分（dim_info_completeness/dim_verification_feasibility/dim_patternability）+ kb_pattern_hit → tier（1-4）。产出 ConfidenceScore。

---

## R001-BB003：Playbook 执行器（双模式） `⬜ 待处理`

- 文件：`agent/diagnosis/playbook_executor.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF002, BF003, BF004, BF006]
- priority: 5
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - ①复现模式：确定性跑 reproduce_runner；②探测/诱发模式：LangGraph agent loop，BF003 把 ADB 工具当 agent tools 调；步数预算（D7）对 loop 硬约束；步数耗尽→缺口
- contract_refs: [backend 5.1 BB003 双执行模式]
- decision_refs: [D3, D7]
- test_tasks:
  - type: unit
    description: 复现模式 mock（FakeReproduceEngine）；探测模式 mock（FakeADBTools 预设截图序列）；步数耗尽→缺口
    scenarios: [关键业务逻辑表 BB003/BB004, 故障注入]

### BB003.1 双模式编排 `⬜`
- 复现模式：Playbook 有脚本 → reproduce_runner 确定性跑，BF003 不参与
- 探测/诱发模式：Playbook 无明确脚本 → 起 LangGraph loop，BF003 看截图→决策 tool_call→BF002 执行→BF004 采信号→循环，命中信号或步数耗尽止
- 输出复现证据（ReproStep 序列 + 信号）喂 BB004

---

## R001-BB004：假设树引擎 `⬜ 待处理`

- 文件：`agent/diagnosis/hypothesis_engine.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF005, SCH01]
- priority: 5
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 4 态迁移（proposed/verifying/confirmed/refuted）；换方向（回溯父切兄弟）；根因回退（rootcause.overturned）；步数预算耗尽→不再换方向转缺口；refuted 永久保留（INV-2）；负向知识反查剪枝
- contract_refs: [backend 5.2 假设树机制]
- decision_refs: [D7]
- test_tasks:
  - type: unit
    description: 4 态迁移；换方向/回溯/overturning；refuted 不删；步数耗尽转缺口；负向反查
    scenarios: [关键业务逻辑表 BB004 换方向, 状态机矩阵 Hypothesis]

### BB004.1 假设树状态机 `⬜`
封装回溯/根因回退/步数预算（内部闭环，不外泄 Orchestrator）。confirmed 被 fixing/regression 信号推翻 → rootcause.overturned（fixing→located）。全局步数耗尽 → 转缺口诊断。

---

## R001-BB005：根因定位 `⬜ 待处理`

- 文件：`agent/diagnosis/root_cause_locator.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF06]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: 命中信号→代码 file:line 反溯；多信号优先级；无匹配→located 但根因空（转缺口）
- test_tasks:
  - type: unit
    description: 堆栈/日志/视觉锚点→代码位置；无匹配转缺口
    scenarios: [BB005 补充断言]

### BB005.1 定位器 `⬜`
命中信号（堆栈帧/日志关键词/视觉锚点）→ git blame/检索 → root_cause_location(file:line)。

---

## R001-BB012：诊断报告生成器 `⬜ 待处理`

- 文件：`agent/report/diagnosis_report_generator.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [SCH02]
- priority: 3
- mode: direct
- status: pending
- acceptance_criteria: JSON + markdown 双输出；字段缺失降级输出不崩
- test_tasks:
  - type: unit
    description: 双格式输出；字段缺失降级
    scenarios: [BB012 补充断言]

### BB012.1 报告生成 `⬜`
聚合 BugReport + Trajectory + ConfidenceScore + Gaps → DiagnosisReport（json/markdown）。Tier3/4 主产出。

---

## R001-BB007：自动修复器 `⬜ 待处理`

- 文件：`agent/fix/auto_fixer.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF04, BF005, INF06]
- priority: 4
- risk_tags: [network]
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - strategy 优先级 template→llm→history_calibration；Tier2 产出 is_draft=true+rationale；strategy_chain 记录完整；KB 校准走历史 patch
- contract_refs: [backend 5.1 Tier1/Tier2]
- decision_refs: [D6]
- test_tasks:
  - type: unit
    description: 三策略优先级；Tier2 is_draft；strategy_chain
    scenarios: [关键业务逻辑表 BB007]

### BB007.1 AutoFixer `⬜`
按可解决性优先级：template（KB pattern 套用）→ llm（LLMGateway fix_patch→glm-5.1 直生成）→ history_calibration（KB 历史校准）。产出 FixPatch（is_draft 由 tier 决定）。

---

## R001-BB008：回归验证器（三关 + Tier 分级） `⬜ 待处理`

- 文件：`agent/fix/regression_verifier.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF002]
- priority: 4
- mode: negotiated
- status: pending
- acceptance_criteria:
  - Tier1：三关（复现序列回归+既有测试+静态检查）全过才提普通 PR；Tier2：轻量（静态+可验证子集）+is_draft；fail 区分根因错（→BB004 回退）vs 补丁错（→BB007 重试）
- contract_refs: [backend 5.1, INV-2]
- decision_refs: []
- test_tasks:
  - type: unit
    description: Tier1 三关；Tier2 轻量；fail 分流（根因错/补丁错）
    scenarios: [关键业务逻辑表 BB008, Tier1/Tier2 行]

### BB008.1 三关验证 + Tier 分级 `⬜`
复现序列回归（复用 BF002 reproduce_runner + ReproStep）、既有测试、静态检查。fail 分类：根因错 → BB004 根因回退；补丁错 → BB007 换策略重试（F4a，最多 FIX_RETRY_MAX）。

---

## R001-BB009：PR 提交器 `⬜ 待处理`

- 文件：`agent/fix/pr_submitter.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF06]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: Tier1 普通 PR（is_draft=false）；Tier2 draft PR；push 失败不破坏状态
- test_tasks:
  - type: unit
    description: Tier1/Tier2 分流；push 拒绝不破坏状态
    scenarios: [关键业务逻辑表 BB009, 故障注入]

### BB009.1 PRSubmitter `⬜`
建分支 + commit + push（git_client）→ 提 PR。**禁止自主合并**（INV-2，人在闸门）。

---

## R001-BB010：缺口诊断器 `⬜ 待处理`

- 文件：`agent/gap_mgmt/gap_diagnoser.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF008]
- priority: 3
- mode: direct
- status: pending
- acceptance_criteria: 四类缺口（信息/设施/模式/模型）识别；写 CapabilityGap(waiting)
- test_tasks:
  - type: unit
    description: 四类缺口识别
    scenarios: [关键业务逻辑表 BB010]

### BB010.1 GapDiagnoser `⬜`
步数耗尽/降级 → 识别四类 gap_type → 写 CapabilityGap。

---

## R001-BB011：回流管理 `⬜ 待处理`

- 文件：`agent/gap_mgmt/reflow_manager.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF008]
- priority: 3
- mode: negotiated
- status: pending
- acceptance_criteria: 补齐检测→发 `bug.reflowed` 事件（由 ORB01 监听重跑主链，事件驱动解耦，BB011 不直接调 ORB01）；reflow_count 超限→wont_reflow 转人工（AP-1）；regression-feedback outcome=regression+concluded/reflected→reflowed+回流
- contract_refs: [backend 4.3 regression-feedback, 5.4]
- decision_refs: []
- test_tasks:
  - type: unit
    description: 补齐回流（断言发出 bug.reflowed 事件 + 事件载荷含 bug_report_id/reflow_count）；超限 wont_reflow（不发事件）；regression 回流（路径 B 发事件）
    scenarios: [关键业务逻辑表 BB011, 状态矩阵 regression-feedback]

### BB011.1 ReflowManager `⬜`
两条回流路径：A（gap_pending 补齐→发 `bug.reflowed` 事件，ORB01 监听后 `gap_pending→received` 重跑）；B（concluded/reflected + regression → 发 `bug.reflowed` 事件 → ORB01 监听后 `→reflowed→received`）。reflow_count 上限保护，超限不发事件转 wont_reflow。**解耦方式**：BB011 只产事件，不调 ORB01；ORB01 依赖 BB011（订阅其事件），无反向依赖，消除循环。

---

## R001-BB013：反思 agent `⬜ 待处理`

- 文件：`agent/reflection/reflection_agent.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [INF04, BF005]
- priority: 3
- mode: negotiated
- status: pending
- acceptance_criteria: 读 trajectory（含 refuted）→ 提取 negative_knowledge + 命中线索；**仅写 raw_trajectory/negative_knowledge 层，禁写 pattern（INV-3）**
- test_tasks:
  - type: unit
    description: 负向知识提取；命中线索；权限校验（不写 pattern）
    scenarios: [BB013 补充断言]

### BB013.1 ReflectionAgent `⬜`
独立读 trajectory → LLMGateway(reflection→glm-5.1) → 写 KBRetriever（negative_knowledge 层）。

---

## R001-BB015：人工修复录入器 `⬜ 待处理`

- 文件：`agent/gap_mgmt/manual_fix_recorder.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BF005]
- priority: 3
- mode: negotiated
- status: pending
- acceptance_criteria: 人修 patch→KB pattern；**唯一允许写 pattern 层的入口**（INV-3/AP-3）；其他模块写 pattern 被拒
- test_tasks:
  - type: unit
    description: 人修→pattern；非 BB015 写 pattern 拒绝
    scenarios: [关键业务逻辑表 BB015, INV-3]

### BB015.1 ManualFixRecorder `⬜`
抓取人修 commit patch → 引导填 root_cause/trigger_conditions → 写 KBEntry(pattern)。

---

## R001-ORB01：Orchestrator（LangGraph 状态机） `⬜ 待处理`

- 文件：`agent/orchestrator.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [BB001, BB002, BB003, BB004, BB005, BB006, BB007, BB008, BB009, BB010, BB011, BB013, BF001]
- priority: 5
- smoke_required: true
- mode: negotiated
- status: pending
- acceptance_criteria:
  - 驱动 BugReport 走完 14 态（合法迁移 100%）；步数/token 预算硬约束；人工闸门（不自主合并）
- contract_refs: [backend 5.1 主链]
- decision_refs: [D1, D7]
- test_tasks:
  - type: integration
    description: 真实 LangGraph 编排主链（LLM/模拟器 mock）；14 态迁移
    scenarios: [状态机矩阵 BugReport, 集成测试]

### ORB01.1 LangGraph 状态机 `⬜`
节点：归一化→ISM→分类→Playbook 选择→BB003→BB004→BB005→BB006 分流→（Tier1: BB007→BB008→BB009 普通 PR | Tier2: BB007 draft→BB009 draft | Tier3/4: BB010 缺口）。终态反思 BB013。步数预算耗尽→BB010。

---

## R001-FF001：report_router `⬜ 待处理`

- 文件：`agent/api/routers/report_router.py`、`agent/api/dtos/`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [ORB01, BB011, BB015]
- priority: 4
- mode: negotiated
- status: pending
- acceptance_criteria: 9 端点路径/方法/状态码与 backend 4.3 一致；regression-feedback 写 MetricPoint + 状态副作用（5 态 allowed/9 态 409）；响应体四字段
- contract_refs: [backend 4.3, OpenAPI 唯一契约源]
- decision_refs: []
- test_tasks:
  - type: integration
    description: 9 端点集成；regression-feedback 28 case（14态×2 outcome）
    scenarios: [API 端点测试表, regression-feedback 状态矩阵]

### FF001.1 端点实现 `⬜`
GET /reports、/reports/{id}、/reports/{id}/trajectory、/reports/{id}/clarify-options；POST /reports/{id}/clarify、/reports/{id}/regression-feedback、/webhook/{platform}。regression-feedback 按 outcome + 状态分支（4.3 语义）。

---

## R001-FF002：gap_router `⬜ 待处理`

- 文件：`agent/api/routers/gap_router.py`
- 改动类型：新建
- domain: backend
- task_layer: business
- depends_on: [ORB01, BB011, BF008]
- priority: 3
- mode: direct
- status: pending
- acceptance_criteria: GET /gaps 按 estimated_unlock_value 降序；POST /gaps/{id}/unblock waiting→unblocked + 触发 BB011
- contract_refs: [backend 4.3]
- test_tasks:
  - type: integration
    description: /gaps 排序；/unblock 状态迁移
    scenarios: [API 端点测试表]

---

## R001-ENT01：main.py（FastAPI 入口） `⬜ 待处理`

- 文件：`agent/main.py`
- 改动类型：新建
- domain: infra
- task_layer: business
- depends_on: [FF001, FF002, ORB01]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: uvicorn 启动；路由挂载；DB 初始化（pgvector 扩展）；导出 /openapi.json（契约源）
- decision_refs: [D10]
- test_tasks:
  - type: integration
    description: uvicorn 启动 + 9 端点路由可达 + /openapi.json 导出含全部端点定义（契约源 artifact）
    scenarios: [契约源导出, INT01 API 集成依赖]

### ENT01.1 FastAPI 入口 `⬜`
挂载 FF001/FF002 + /webhook；启动建表 + pgvector；`app.openapi()` 导出 OpenAPI artifact（test 契约源）。

---

## R001-DEP01：docker-compose + Dockerfile + Makefile `⬜ 待处理`

- 文件：`docker-compose.yml`、`Dockerfile`、`Makefile`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [ENT01]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: `make up` 起宿主 adb server+模拟器→docker compose up 起 PG+agent+前端；agent 容器经 host.docker.internal:5037 连模拟器
- decision_refs: [D10]
- test_tasks:
  - type: integration
    description: make up 一键启动；三容器健康检查；agent 容器内 `adb -H host.docker.internal -P 5037 devices` 能列出宿主模拟器
    scenarios: [D10 部署验证, 全链路冒烟前置]

### DEP01.1 三容器 compose + adb 桥 `⬜`
compose：postgres(pgvector) + agent(含 adb client) + frontend。Dockerfile agent 镜像。Makefile `up`：adb server + 模拟器 → compose up。

---

## R001-INT01：backend 集成测试 `⬜ 待处理`

- 文件：`tests/integration/`、`tests/conftest.py`（FakeLLMGateway/FakeReproduceEngine/FakeADBTools）
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [FF001, FF002, ORB01]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: 9 端点集成全过；regression-feedback 28 case；Testcontainers PG+pgvector 隔离
- contract_refs: [test 4 集成测试方案]
- test_tasks:
  - type: integration
    description: API 端点测试表全量；regression-feedback 14态×2 outcome=28 case
    scenarios: [API 端点测试表, regression-feedback 状态矩阵]

### INT01.1 conftest mock + Testcontainers `⬜`
FakeLLMGateway（按 prompt_type 分发）、FakeReproduceEngine（复现模式）、FakeADBTools（探测模式预设截图序列）；Testcontainers 每 test 独立 schema。

---

## R001-INT02：状态机迁移矩阵测试 `⬜ 待处理`

- 文件：`tests/state_machine/`
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [SCH01]
- priority: 4
- mode: direct
- status: pending
- acceptance_criteria: BugReport 14 态（路径 A+B）合法迁移 100%、非法迁移全判；Hypothesis 4 态；CapabilityGap 7 态
- test_tasks:
  - type: integration
    description: 三实体状态机参数化矩阵
    scenarios: [状态机迁移矩阵]

---

## R001-INT03：BF002 模拟器独立集成（手动） `⬜ 待处理`

- 文件：`tests/integration_bf002/`
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [BF002]
- priority: 2
- mode: direct
- status: pending
- acceptance_criteria: `pytest tests/integration_bf002/ --run-emulator` 手动跑通；不进主 CI
- test_tasks:
  - type: integration
    description: 真实模拟器启停/ADB 动作/截图；超时重试
    scenarios: [故障注入表 BF002]

---

## R001-INT04：golden set + 开放参数验收基线 `⬜ 待处理`

- 文件：`tests/golden/llm_quality/`、`tests/golden/vision/`、验收基线报告脚本
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [BB007, BF003, BB006]
- priority: 3
- mode: negotiated
- status: pending
- acceptance_criteria: LLM patch 命中率（N=20 人工造样本）+ 置信度校准（reliability diagram+Brier）+ 视觉决策（人工造截图 ≥50% cold）方法可执行、出基线报告
- contract_refs: [test 开放参数验收口径]
- decision_refs: [D11]
- test_tasks:
  - type: integration
    description: 三类基线报告产出——LLM patch 命中率报告（N=20 样本，Schema 合规率≥95% + 关键字段命中率≥80%）；置信度校准报告（reliability diagram + Brier score 记录在案）；视觉决策 golden 报告（人工造截图，冷启动≥50%）
    scenarios: [开放参数验收口径表全行, 高风险项替代验收方案 LLM 质量+视觉准确率]

### INT04.1 golden set + 基线报告 `⬜`
每 prompt_type 20+ 标注样本（真实 LLM 跑，断言 Schema 合规率+关键字段命中率）；视觉 golden（人工造截图样本，锚点空）；置信度 reliability diagram + Brier。MVP 验收=方法可执行+基线报告产出（非数值达标）。

---

## 最后：编译验证 + 全测试路径 `⬜ 待处理`

- `pip install -e agent/ && pytest tests/unit tests/integration tests/state_machine -v`
- `cd frontend && npm run build && vitest run`（前端任务见 frontend-tasks）
- `make up` 冒烟（手动）
- 验收埋点：查询 MetricPoint 返回五维非空（冷启动基线）
