---
type: architecture
last_updated: 2026-06-17
maintained_by: R001 起建立
---

# 架构基线（Architecture Baseline）

> 本文档记录项目的不变量、约束与禁止模式。任何 RC 涉及架构变更必须先更新本文档。

## 一、系统拓扑

### 1.1 客户端代码仓库（agent 操作对象）

- **混合栈**：Android 原生主工程（Kotlin，`app/`）+ Flutter 模块（Dart，`flutter_logic/`）
- **演进策略**：新业务用 Flutter 写；只有动到老业务才用原生（来自 R001 brainstorm 共识）
- **构建**：Android 用 Gradle Kotlin DSL（`build.gradle.kts` / `settings.gradle.kts`）；Flutter 用标准 `pubspec.yaml`
- **Flutter 集成方式**：Add-to-App 模式（`flutter_logic/` 作为模块被主工程引用）

### 1.2 Agent 系统（R001 design 已定技术栈）

- **部署形态**：独立后端服务（不嵌入客户端 App）；**agent + 前端 + PostgreSQL+pgvector 全走 docker**（同一 `docker-compose.yml`，仅 Android 模拟器宿主机原生——需 GUI/KVM）；agent 容器经 `host.docker.internal:5037` adb 网络桥操控原生模拟器（`make up` 一键启动，R001 design D10）
- **运行环境**：可启 Android 模拟器 + ADB 的 Linux/macOS 主机（mac Docker Desktop 原生支持 `host.docker.internal`）
- **代码仓库**：当前仓库 `agent/` 子目录（R001 design 确定）
- **技术栈**（R001 design 确定）：Python 3.11+ / LangGraph 编排 / FastAPI（API+BFF）/ SQLAlchemy + PostgreSQL（trajectory 永久保留）/ pgvector（KB 向量检索，同库）/ React + Vite（最小化前端）
- **LLM 接入**：LLMGateway 抽象，走 OpenAI 兼容协议对接 **New API 网关**；**文本类（BB002/BB004/BB007/BB013）默认 `model=glm-5.1`，视觉类（BF003 截图决策）默认 `model=GLM-5V-Turbo`**，均经同一 New API `base_url`；config 切 `model` 即换（R001 design D2）
- **上报平台接入**：BugReportAdapter 参数化；**MVP 第一适配器 = Sentry**，其他平台（Bugly/Crashlytics/自建）按 adapter 扩展（R001 design D8）
- **模拟器操控**：Android Emulator + ADB（subprocess）；BF002 封装为 ADB 工具层，**复现走确定性 Playbook 脚本 / 探测诱发走 LangGraph agent tool-calling loop**（R001 design D3，双模式共用同一 ADB 底层）
- **KB 锚点库（BF007）**：MVP 建「存储+检索+Schema」能力，数据冷启动为空；BF003 降级纯 LLM 判断，待公司后录入激活（R001 design D11）
- **解锁价值公式**：`estimated_unlock_value = 同类 bug 历史频率 × 补齐后可修复比例`，用于 Capability Gap 排序（R001 design D12）
- **成本控制**：步数预算 / token 预算参数化（config，design 给默认值；步数预算对 agent tool-calling loop 同样硬约束）

## 二、不变量（Invariants）

### INV-1 客户端层不变量
- Flutter 与 Android 原生通过 **MethodChannel / EventChannel** 通信，不允许直接共享内存
- Flutter 层状态管理：依赖项目现有方案（待 R001 design 阶段确认具体框架：Provider / Bloc / Riverpod？）
- 客户端版本通过 `versionCode` / `versionName` 标识，所有 bug 上报必须携带

### INV-2 Agent 系统不变量
- **人在合并闸门**：MVP 阶段所有 PR 必须人工审核合并，agent 不允许自主合并（来自 R001 关键决策）
- **回归必过（按 Tier 分级）**：
  - **Tier1（高置信）PR**：提交前必须通过三关（复现序列回归 + 既有测试 + 静态检查），全过后提普通 PR
  - **Tier2（中置信/部分可验证）draft PR**：提交前走轻量验证（至少静态检查 + 可验证子集），`is_draft=true` 标注未验证项 rationale；完整回归三关留待人工审核阶段按需触发
  - 理由：Tier2 本就表示自动验证能力不足，强制三关会卡死；draft PR 语义是「待人工审核」，与「人在合并闸门」一致——最终合并权仍在人工
  - 例外口径（R001 design-review 第 X 轮回写）：原 INV-2 写「任何 PR 必须三关」与 Tier2 draft PR 路径冲突，本条按 Tier 分级细化
- **Trajectory 永久保留**：所有排查轨迹（含被证伪的假设）永不删除，作为负向知识沉淀
- **Capability Gap 不消失**：未补齐的缺口永久可查，补齐后状态变化但不删除历史

### INV-3 数据不变量
- `BugReport` 一旦 `concluded` 不可回退（除 `reflowed` 显式触发）
- KB 模式条目录入需经过 `BB015 人工修复录入器`，不允许 agent 直接写入 KB 模式层

## 三、约束（Constraints）

### CON-1 模拟器与真机
- **MVP 只用模拟器**：不接真机农场（Capability Gap Tracker 触发后再投入）
- **模拟器覆盖范围**：Flutter 层崩溃/逻辑/UI bug；不覆盖性能、ROM、硬件类
- **ADB 操作边界**：视觉决策主路径，ADB 辅助输入文本/滑动/返回

### CON-2 外部依赖
- **多模态 LLM API**：必接（视觉决策、症状分类、反思、修复器共用）；**已选默认：经 New API 网关的 OpenAI 兼容协议**，文本 `glm-5.1` / 视觉 `GLM-5V-Turbo`（保持参数化，config 可切）
- **Bug 上报平台**：必接一个（Bugly / Crashlytics / Sentry / 自建）；**已选默认：Sentry**（适配器参数化，可扩展）
- **Git 平台 API**：必接（GitHub / GitLab），用于 PR 提交

### CON-3 成本约束
- 单 bug 处理成本上限：待 R001 design 通过"步数上限 / 超时阈值"参数化
- LLM token 成本：视觉决策是主要开销，需要 token 预算控制

## 四、禁止模式（Anti-patterns）

### AP-1 agent 行为禁止
- **禁止** agent 在回归验证失败时降级到 draft PR 误导开发者（R001 自审修正：必须走缺口诊断）
- **禁止** agent 直接合并 PR（人在闸门）
- **禁止** agent 删除 trajectory 中被证伪的假设（负向知识必须保留）
- **禁止** agent 在 `bug.reflowed` 次数超上限后继续自动回流（必须转人工）

### AP-2 架构禁止
- **禁止** 把 agent 系统嵌入客户端 App（部署形态约束）
- **禁止** 跨过 `BugReport` Schema 直接对接上报平台原始格式（必须经 BF001 归一化）
- **禁止** 跨过 `ConfidenceScore` 直接做 Tier 分流决策（必须经 BB006 评估）

### AP-3 数据禁止
- **禁止** KB 模式层直接由 agent 写入（必须经 BB015 人工录入）
- **禁止** 删除已沉淀的 Capability Gap 条目（只能改状态）

## 五、外部接口契约

| 契约 | 对端 | 方向 | 备注 |
|------|------|------|------|
| Bug 上报 webhook | 上报平台（Bugly/Sentry/Crashlytics） | 入 | 经 BF001 归一化 |
| Git 平台 API | GitHub/GitLab | 出 | 用于提 PR |
| LLM API | 多模态模型提供商 | 出 | 视觉/分类/修复/反思共用 |
| 客户端代码仓库 | git | 双向 | blame/检索/提交 |

## 六、R001 design 已定 / 仍未锁定项

### design 已定（已回写 1.2 / CON-2 节）
- agent 部署形态：`agent/` 子目录、Python 实现
- 技术栈：LangGraph / FastAPI / PostgreSQL+pgvector / React+Vite
- 部署形态（D10）：agent + 前端 + PG 全 docker，仅 Android 模拟器宿主原生（adb 网络桥）
- 模拟器操控（D3）：subprocess ADB 底层 + BF002 工具层，复现/探测诱发双模式
- LLM provider（D2）：New API 网关 + glm-5.1（文本）/ GLM-5V-Turbo（视觉），保持参数化可切
- 上报平台（D8）：Sentry 为第一适配器，BugReportAdapter 参数化可扩展
- KB 锚点库（D11）：能力先建，数据冷启动为空，BF003 降级纯 LLM
- 解锁价值公式（D12）：频率 × 可修复性
- KB 冲突处理（D9）：conflicting 成组返回 + 旧条目标 stale 不删
- 成本上限：步数/token 预算参数化

### 仍未锁定（后续实验/校准定）
- Flutter 状态管理框架（客户端侧，agent 不直接涉及；但影响 Playbook 对客户端状态的探测方式，留客户端 design）
- LLM/上报平台的备选 provider（默认已定，config 可切；待实验阶段按效果决定是否替换）
- 步数/token 预算具体数值（design 给默认值，待校准）
- KB 锚点库数据内容（D11，待公司录入）
