---
version: "1.0"
type: tasks
topic: client-bug-fix-agent
requirement_cycle: R001
workflow:
  evaluate_provider: codex
  mode: auto
status: archived
---

# 客户端 Bug 修复 Agent — 前端任务清单

基于 [frontend design](analysis/2026-06-16--client-bug-fix-agent-frontend.md) 拆解。后端见 [backend-tasks](client-bug-fix-agent-tasks.md)。测试场景引用 [test design](analysis/2026-06-16--client-bug-fix-agent-test.md) 第 2 节前端测试场景矩阵。

## 全局约束

- **技术栈**：React 19.2 + TypeScript 6（严格模式）+ Vite 8 + TanStack Query 5.101 + React Router 7.18（库模式）+ Ant Design 6.4 + MSW 2.14 + vitest 4.1（D1-D7）
- **分层调用**：`routes/Page → hooks → services/*Api → apiClient → 后端`，严格单向，禁止反向
- **UI 组件**：纯展示 + 用户交互，不直接 fetch；数据全部经 Hook 注入；核心展示组件（HypothesisTree 等）只接收 props，可独立单测
- **命名**：字段保持 snake_case 与 backend Schema 一一对应（避免双向转换）；DTO 层不改名，仅 UI 展示层在 `utils/format.ts` 做文案别名映射
- **状态管理**：server state 全走 TanStack Query（缓存/loading/error/refetch/invalidate）；本地 UI 态用 useState + URL search params；不引入 Redux/Zustand
- **apiClient 是唯一 fetch 出口**：统一错误码映射（400/404/409/5xx → 友好提示），reportApi/gapApi/clarifyApi 按领域分组
- **契约源**：以 backend FastAPI/Pydantic `response_model` 自动生成的 `contracts/openapi.json` 为唯一契约源；types/ 与 MSW handlers 必须从该 artifact 派生（可用 openapi-typescript 生成 types）
- **FB002 边界**：PR 审核一律外链 GitHub/GitLab（BugReport.pr_url），前端不内嵌审核 UI
- **暂不实现**：相似 issue 视图 / 实时推送 / 暗黑模式 / i18n / 复杂图表 / 报告列表高级筛选 / 假设树交互编辑 / 移动端适配（见 frontend design 第 8 节）

## 执行顺序

> 按层依赖排序。骨架 → 类型 → 服务层 → 工具 → Hooks → 通用组件 → 领域组件 → 路由入口 → Mock 层 → 测试。

1. ✅ FE01 项目骨架与依赖
2. ✅ FE02 types/ 类型定义（report/gap/api）
3. ✅ FE03 services/apiClient.ts（统一 fetch + 错误码映射）
4. ✅ FE04 services/ 领域 API（reportApi/gapApi/clarifyApi）
5. ✅ FE05 utils/（format + treeBuilder）
6. ✅ FE06 hooks/（useReport/useGaps/useClarify/useRegressionFeedback）
7. ✅ FE07 components/common/（PageContainer + StatusBadge）
8. ✅ FE08 components/report/（ReportHeader/HypothesisTree/FixPatchCard/TrajectoryTimeline/RegressionFeedbackForm）
9. ✅ FE09 components/gap/（GapList + GapUnblockAction）
10. ✅ FE10 components/clarify/（ClarifyForm）
11. ✅ FE11 main.tsx + App.tsx（Provider + 路由表 + 侧边导航）
12. ✅ FE12 routes/（ReportListPage/ReportDetailPage/GapViewPage/ClarifyPage）
13. ✅ FE13 mocks/（handlers + server + browser）
14. ✅ FE14 handlers.spec.ts 契约守护测试
15. ✅ FE15 组件 + utils 单测
16. ✅ 最后 — 编译验证 + 全测试路径

---

## R001-FE01：项目骨架与依赖 `✅ 已完成`

- 文件：`frontend/package.json`、`frontend/vite.config.ts`、`frontend/tsconfig.json`、`frontend/index.html`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: []
- priority: 5
- risk_tags: [first_use]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - `cd frontend && npm install` 成功
  - `npm run dev` 启动 dev server，浏览器访问空白页无报错
  - `npm run build` 产出 dist/ 无错误
  - `tsc --noEmit` 无类型错误
- decision_refs: [D1, D2, D3, D4, D7]
- test_tasks:
  - type: integration
    description: dev server 启动 + 构建产物校验
    scenarios: [FE01 骨架可构建]
- contract_refs: []
- blocked_files: []

### FE01.1 package.json `✅`

依赖与脚本。版本号见 frontend design 第 6 节第三方依赖清单（均经 `npm view <pkg> version` 确认）。

```jsonc
{
  "name": "client-bug-fix-agent-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:coverage": "vitest run --coverage"
  },
  "dependencies": {
    "react": "19.2.7",
    "react-dom": "19.2.7",
    "react-router-dom": "7.18.0",
    "@tanstack/react-query": "5.101.0",
    "antd": "6.4.4"
  },
  "devDependencies": {
    "typescript": "6.0.3",
    "vite": "8.0.16",
    "@vitejs/plugin-react": "6.0.2",
    "msw": "2.14.6",
    "vitest": "4.1.9",
    "@vitest/coverage-v8": "4.1.9",
    "jsdom": "*",
    "@testing-library/react": "*",
    "@testing-library/jest-dom": "*",
    "openapi-typescript": "*"
  }
}
```

### FE01.2 vite.config.ts `✅`

```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // dev 阶段切真实后端：VITE_USE_MOCK=false 时走 proxy
      '/reports': 'http://localhost:8000',
      '/gaps': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
});
```

### FE01.3 tsconfig.json `✅`

严格模式。`strict: true`，`noUncheckedIndexedAccess: true`，paths 别名 `@/* → src/*`。

### FE01.4 index.html + 空 main.tsx 占位 `✅`

Vite 入口 HTML 挂载 `#root`；main.tsx 暂留 `<h1>boot ok</h1>` 占位（FE11 替换为真实 Provider 树）。

---

## R001-FE02：types/ 类型定义 `✅ 已完成`

- 文件：`frontend/src/types/report.ts`、`frontend/src/types/gap.ts`、`frontend/src/types/api.ts`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [FE01]
- priority: 5
- risk_tags: [contract_drift]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 所有类型字段名与 backend Schema 一一对应（snake_case）
  - Hypothesis.status 枚举为 `proposed/verifying/confirmed/refuted` 四态
  - BugReport.status 覆盖 backend 4.1 全部 14 态
  - CapabilityGap.status 覆盖 7 态（identified/waiting/unblocked/resolved/invalid_unblock/wont_reflow/wont_fix）
  - `tsc --noEmit` 通过
- decision_refs: []
- test_tasks:
  - type: unit
    description: 枚举值与 backend Schema 对齐校验
    scenarios: [契约测试表：Hypothesis.status 枚举 / ConfidenceScore 三维字段名 / CapabilityGap.unlock 价值字段名]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE02.1 report.ts `✅`

```ts
// 与 backend 4.1 Schema 一一对应，snake_case 保留
export type BugReportStatus =
  | 'received' | 'assessing' | 'degraded' | 'reproducing'
  | 'located' | 'fixing' | 'verified' | 'pr_open'
  | 'draft_pr' | 'gap_pending' | 'wont_reflow' | 'concluded'
  | 'reflowed' | 'reflected';

export type Tier = 1 | 2 | 3 | 4;

export interface ConfidenceScore {
  dim_info_completeness: number;
  dim_verification_feasibility: number;
  dim_patternability: number;
  kb_pattern_hit: boolean;
  tier: Tier;
  score: number;
}

export interface BugReport {
  id: string;
  status: BugReportStatus;
  tier: Tier | null;
  symptom_type: string;
  root_cause: string | null;
  confidence_score: ConfidenceScore | null;
  fix_patch_id: string | null;
  pr_url: string | null;
  clarify_requested: boolean;
  // ... 其余字段对齐 backend Schema
}

export type HypothesisStatus = 'proposed' | 'verifying' | 'confirmed' | 'refuted';

export interface Hypothesis {
  id: string;
  parent_id: string | null;
  hypothesis_text: string;
  expected_signal: string;
  status: HypothesisStatus;
  falsifying_signal: string | null;
  overturning_signal: string | null;
  is_rootcause: boolean;
  step_budget: number;
  step_used: number;
}

export interface TrajectoryEvent {
  id: string;
  // 字段对齐 backend TrajectoryEvent Schema
}

export interface Trajectory {
  id: string;
  root_hypothesis_id: string;
  hypotheses: Hypothesis[];
  total_step_budget: number;
  events: TrajectoryEvent[];
}

export type FixStrategy = 'template' | 'llm' | 'history_calibration';

export interface FixPatch {
  id: string;
  strategy: FixStrategy;
  is_draft: boolean;
  patch_diff: string;
  target_file: string;
  verification_report: unknown | null;
}

// 回归反馈请求 DTO（FF001）
export interface RegressionFeedbackRequest {
  outcome: 'regression' | 'safe';
  evidence: string;
  bucket_dim?: string;
  bucket_value?: string;
}

// 回归反馈响应 DTO
export interface RegressionFeedbackResponse {
  metric_point_id: string;
  status_before: BugReportStatus;
  status_after: BugReportStatus;
  reflow_scheduled: boolean;
}

// 追问候选 DTO
export interface ClarifyOption {
  field_key: string;
  question: string;
  options: string[];
  source: 'kb' | 'manual';
}
```

### FE02.2 gap.ts `✅`

```ts
export type CapabilityGapStatus =
  | 'identified' | 'waiting' | 'unblocked'
  | 'resolved' | 'invalid_unblock' | 'wont_reflow' | 'wont_fix';

export type GapType = 'information' | 'facility' | 'pattern' | 'model';

export interface CapabilityGap {
  id: string;
  gap_type: GapType;
  unlock_action: string;
  estimated_unlock_value: number;
  status: CapabilityGapStatus;
  linked_bug_ids: string[];
  git_commit_anchor: string | null;
}

export interface UnblockRequest {
  unlock_action: string;
  evidence: string;
  git_commit_anchor?: string;
}
```

### FE02.3 api.ts `✅`

通用分页 DTO、错误响应 DTO。

```ts
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiError {
  status: number;
  code: string;
  message: string;
  field_errors?: Record<string, string>;
}
```

---

## R001-FE03：services/apiClient.ts `✅ 已完成`

- 文件：`frontend/src/services/apiClient.ts`
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: [FE02]
- priority: 5
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 是全应用唯一 fetch 出口
  - 400/404/409/5xx 错误码统一映射为 ApiError
  - 409 状态非法映射为友好提示（当前状态不允许此操作）
  - 5xx 触发 antd message 全局错误通知
- decision_refs: []
- test_tasks:
  - type: unit
    description: apiClient 错误码映射
    scenarios: [前端测试场景表 apiClient 行：400/404/409/5xx 错误码映射 + 网络断开]
- contract_refs: []
- blocked_files: []

### FE03.1 apiClient 实现 `✅`

```ts
import { ApiError } from '@/types/api';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export async function apiClient<T>(
  path: string,
  options?: RequestInit & { params?: Record<string, string | number | undefined> },
): Promise<T> {
  // 1. 拼 URL（含 query params，跳过 undefined）
  // 2. fetch + Accept/Content-Type JSON
  // 3. !res.ok → 按 status 分组抛 ApiError
  //    - 400 → field_errors 解析
  //    - 404 → 「报告/缺口不存在」
  //    - 409 → 「当前状态不允许此操作」（状态非法）
  //    - 5xx → antd message.error 全局通知
  // 4. res.ok → res.json() as T
  // 5. 网络异常（fetch reject）→ ApiError(status=0, message='网络断开')
}
```

---

## R001-FE04：services/ 领域 API `✅ 已完成`

- 文件：`frontend/src/services/reportApi.ts`、`frontend/src/services/gapApi.ts`、`frontend/src/services/clarifyApi.ts`
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: [FE03]
- priority: 5
- risk_tags: [contract_drift]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 8 个端点全部封装（对应 backend FF001/FF002 第 4.3 节）
  - 路径/方法/响应类型与契约一致
  - DTO 类型从 types/ 引用，不重复定义
- decision_refs: []
- test_tasks:
  - type: integration
    description: 8 端点 MSW 拦截 + 类型对齐
    scenarios: [契约测试表 8 行]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE04.1 reportApi.ts `✅`

```ts
export const reportApi = {
  list(params: { page?: number; page_size?: number; status?: BugReportStatus; tier?: Tier }) {
    return apiClient<Paginated<BugReport>>('/reports', { params });
  },
  detail(id: string) {
    return apiClient<BugReport>(`/reports/${id}`);
  },
  trajectory(id: string) {
    return apiClient<Trajectory>(`/reports/${id}/trajectory`);
  },
  submitRegressionFeedback(id: string, body: RegressionFeedbackRequest) {
    return apiClient<RegressionFeedbackResponse>(`/reports/${id}/regression-feedback`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
```

### FE04.2 gapApi.ts `✅`

```ts
export const gapApi = {
  list() {
    return apiClient<CapabilityGap[]>('/gaps');  // 后端默认按 estimated_unlock_value 降序
  },
  unblock(id: string, body: UnblockRequest) {
    return apiClient<CapabilityGap>(`/gaps/${id}/unblock`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
```

### FE04.3 clarifyApi.ts `✅`

```ts
export const clarifyApi = {
  options(reportId: string) {
    return apiClient<ClarifyOption[]>(`/reports/${reportId}/clarify-options`);
  },
  submit(reportId: string, body: { answers: Array<{ field_key: string; value: string }> }) {
    return apiClient<BugReport>(`/reports/${reportId}/clarify`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
```

---

## R001-FE05：utils/ `✅ 已完成`

- 文件：`frontend/src/utils/format.ts`、`frontend/src/utils/treeBuilder.ts`
- 改动类型：新建
- domain: ui
- task_layer: foundation
- depends_on: [FE02]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - Hypothesis 四态 → UI 三色映射逻辑集中在 format.ts
  - ConfidenceScore 三维 → UI 短标签「信息/验证/模式」映射
  - CapabilityGap.estimated_unlock_value → UI「解锁价值」标签
  - treeBuilder 把扁平 Hypothesis[]（parent_id）转为 antd treeData
  - 纯函数，无副作用，可独立单测
- decision_refs: [D5]
- test_tasks:
  - type: unit
    description: format 映射 + treeBuilder 构建单测
    scenarios: [深层嵌套 10 层 / 大量节点 100+ / 空树]
- contract_refs: []
- blocked_files: []

### FE05.1 format.ts `✅`

```ts
// DTO 层不改名，仅 UI 展示层在此做文案别名
export const HYPOTHESIS_STATUS_LABEL: Record<HypothesisStatus, string> = {
  proposed: '进行中',
  verifying: '进行中',
  confirmed: '确认',
  refuted: '证伪',
};

export const HYPOTHESIS_STATUS_COLOR: Record<HypothesisStatus, string> = {
  proposed: 'default',     // 灰
  verifying: 'default',
  confirmed: 'success',    // 绿
  refuted: 'error',        // 红（保留展示，INV-2 负向知识可见）
};

export const CONFIDENCE_DIM_LABEL = {
  dim_info_completeness: '信息',
  dim_verification_feasibility: '验证',
  dim_patternability: '模式',
} as const;

export function formatGapValue(v: number): string {
  return `解锁价值 ${v.toFixed(2)}`;
}

// 其余：时间格式化、tier 文案、status 文案...
```

### FE05.2 treeBuilder.ts `✅`

```ts
import type { TreeDataNode } from 'antd';
import type { Hypothesis } from '@/types/report';

// 把扁平 hypotheses[] 按 parent_id 构建嵌套 antd treeData
export function buildHypothesisTree(hypotheses: Hypothesis[]): TreeDataNode[] {
  // 1. 建 id → children[] 索引
  // 2. 找 root（parent_id == null）
  // 3. 递归挂 children
  // 4. 每节点 title 渲染含 status color + hypothesis_text + step_used/step_budget
  // 返回 []；空输入返回 []
}
```

---

## R001-FE06：hooks/ `✅ 已完成`

- 文件：`frontend/src/hooks/useReport.ts`、`frontend/src/hooks/useGaps.ts`、`frontend/src/hooks/useClarify.ts`、`frontend/src/hooks/useRegressionFeedback.ts`
- 改动类型：新建
- domain: ui
- task_layer: business
- depends_on: [FE04]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 所有 server state 经 TanStack Query（useQuery/useMutation）
  - mutation 成功后正确 invalidate 相关 query key
  - 暴露 loading/error/data 三态
- decision_refs: [D2]
- test_tasks:
  - type: unit
    description: hooks loading/error/data + invalidate
    scenarios: [前端测试场景表各 hook 行]
- contract_refs: []
- blocked_files: []

### FE06.1 useReport.ts `✅`

```ts
export const reportKeys = {
  all: ['reports'] as const,
  list: (params: ...) => ['reports', 'list', params] as const,
  detail: (id: string) => ['reports', 'detail', id] as const,
  trajectory: (id: string) => ['reports', id, 'trajectory'] as const,
};

export function useReportList(params: ...) {
  return useQuery({ queryKey: reportKeys.list(params), queryFn: () => reportApi.list(params) });
}

export function useReport(id: string) {
  return useQuery({ queryKey: reportKeys.detail(id), queryFn: () => reportApi.detail(id) });
}

export function useTrajectory(id: string) {
  return useQuery({ queryKey: reportKeys.trajectory(id), queryFn: () => reportApi.trajectory(id) });
}
```

### FE06.2 useGaps.ts `✅`

```ts
export function useGaps() {
  return useQuery({ queryKey: ['gaps'], queryFn: () => gapApi.list() });
}

export function useUnblockGap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UnblockRequest }) => gapApi.unblock(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['gaps'] }),
  });
}
```

### FE06.3 useClarify.ts `✅`

```ts
export function useClarifyOptions(reportId: string) {
  return useQuery({
    queryKey: ['reports', reportId, 'clarify-options'],
    queryFn: () => clarifyApi.options(reportId),
  });
}

export function useSubmitClarify(reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ...) => clarifyApi.submit(reportId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: reportKeys.detail(reportId) }),
  });
}
```

### FE06.4 useRegressionFeedback.ts `✅`

```ts
export function useRegressionFeedback(reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RegressionFeedbackRequest) => reportApi.submitRegressionFeedback(reportId, body),
    onSuccess: (data) => {
      // 关键：读响应 reflow_scheduled
      // outcome=regression 且 reflow_scheduled=true（原态 concluded/reflected）
      //   → invalidate reportKeys.detail(reportId) 让状态翻为 reflowed
      // outcome=safe 或 reflow_scheduled=false
      //   → 仅刷新 MetricPoint 视图，不 refetch 报告主体
      if (data.reflow_scheduled) {
        qc.invalidateQueries({ queryKey: reportKeys.detail(reportId) });
      }
    },
  });
}
```

---

## R001-FE07：components/common/ `✅ 已完成`

- 文件：`frontend/src/components/common/PageContainer.tsx`、`frontend/src/components/common/StatusBadge.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE05]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - PageContainer 支持 loading/error/empty 三态
  - StatusBadge 支持 BugReport 14 态 + Tier 1-4 渲染
  - 纯展示组件，可独立单测
- decision_refs: []
- test_tasks:
  - type: unit
    description: PageContainer 三态 + StatusBadge 枚举渲染
    scenarios: [前端测试场景表 PageContainer + StatusBadge 行]
- contract_refs: []
- blocked_files: []

### FE07.1 PageContainer.tsx `✅`

```tsx
interface Props<T> {
  loading: boolean;
  error: unknown;
  data: T | undefined;
  empty?: (data: T) => boolean;
  onRetry?: () => void;
  children: (data: T) => ReactNode;
}
// loading → antd Skeleton 骨架
// error → 错误态 + 重试按钮（onRetry）
// empty → 空态（antd Empty）
// 正常 → children(data)
```

### FE07.2 StatusBadge.tsx `✅`

```tsx
// BugReport 14 态 + Tier 1-4 渲染
export function StatusBadge({ status, tier }: { status?: BugReportStatus; tier?: Tier }) {
  // status → antd Tag color + 文案
  // tier → antd Tag color（Tier1 绿 / Tier2 蓝 / Tier3 橙 / Tier4 红）
}
```

---

## R001-FE08：components/report/ `✅ 已完成`

- 文件：`frontend/src/components/report/ReportHeader.tsx`、`HypothesisTree.tsx`、`FixPatchCard.tsx`、`TrajectoryTimeline.tsx`、`RegressionFeedbackForm.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE06, FE07]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - HypothesisTree 四态节点 → 三色映射正确，refuted 保留可见（INV-2 精神）
  - FixPatchCard 渲染 diff + is_draft 标识
  - RegressionFeedbackForm 仅在 PR 已提交后阶段显示（allowed 5 态：pr_open/draft_pr/concluded/reflected/reflowed），其余 9 态隐藏入口
  - 提交回归反馈成功后按 reflow_scheduled 决定是否刷新报告主体
  - 所有组件只接收 props，不直接 fetch
- decision_refs: [D5]
- test_tasks:
  - type: unit
    description: 各组件渲染 + 交互
    scenarios: [前端测试场景表 ReportDetailPage/HypothesisTree/FixPatchCard/RegressionFeedbackForm 行；回归反馈 allowed 5 态显示、其余 9 态隐藏]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE08.1 ReportHeader.tsx `✅`

渲染 BugReport 状态/tier/置信度/版本。复用 StatusBadge。ConfidenceScore 三维 → 「信息/验证/模式」短标签（format.ts）。

### FE08.2 HypothesisTree.tsx `✅`

```tsx
interface Props { hypotheses: Hypothesis[]; }
// 用 utils/treeBuilder.ts 把扁平列表转 treeData
// antd <Tree> 渲染，title 自定义：status color + text + step_used/step_budget
// 四态→三色（proposed/verifying 灰、confirmed 绿、refuted 红保留）
```

### FE08.3 FixPatchCard.tsx `✅`

```tsx
interface Props { patch: FixPatch; }
// antd <Card>：is_draft 显眼标识（Tag 橙色「Draft」）
// patch_diff 用 <pre> 展示（MVP 不引入 react-diff-viewer，design 第 8 节暂不实现复杂图表）
// target_file 标题
```

### FE08.4 TrajectoryTimeline.tsx `✅`

```tsx
interface Props { events: TrajectoryEvent[]; }
// antd <Timeline> 渲染事件序列
```

### FE08.5 RegressionFeedbackForm.tsx `✅`

```tsx
interface Props {
  reportId: string;
  status: BugReportStatus;
  onDone?: () => void;
}
// 1. 计算 allowed = ['pr_open','draft_pr','concluded','reflected','reflowed'].includes(status)
// 2. !allowed → return null（隐藏入口）
// 3. allowed → antd <Form>：
//    - outcome: Select('regression' | 'safe')
//    - evidence: TextArea
//    - bucket_dim/bucket_value: 可选
// 4. 提交 → useRegressionFeedback(reportId).mutate(body)
// 5. 成功 → message.success + 关闭表单
// 6. 409 → message.warning('当前状态不允许此操作')
// 7. 读响应 reflow_scheduled（hook 内已处理 invalidate）
```

---

## R001-FE09：components/gap/ `✅ 已完成`

- 文件：`frontend/src/components/gap/GapList.tsx`、`GapUnblockAction.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE06, FE07]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - GapList 按 estimated_unlock_value 降序
  - GapUnblockAction 仅在 status=waiting 时显示
  - 补齐成功后列表自动刷新（hook invalidate）
- decision_refs: []
- test_tasks:
  - type: unit
    description: GapList 排序 + GapUnblockAction 显示/隐藏 + invalidate
    scenarios: [前端测试场景表 GapList + GapUnblockAction 行]
- contract_refs: []
- blocked_files: []

### FE09.1 GapList.tsx `✅`

```tsx
interface Props { gaps: CapabilityGap[]; }
// 渲染 antd <List>，每项：gap_type / formatGapValue(estimated_unlock_value) / status Tag
// status=waiting → 挂载 <GapUnblockAction>
// status≠waiting → 隐藏补齐入口
// 注：排序由后端保证（gapApi.list 默认降序）；前端不做二次排序，仅展示
```

### FE09.2 GapUnblockAction.tsx `✅`

```tsx
interface Props { gap: CapabilityGap; }
// status≠waiting → return null
// status=waiting → antd <Button> 触发 Drawer/Form：
//   - unlock_action
//   - evidence（必填）
//   - git_commit_anchor（可选）
// 提交 → useUnblockGap().mutate({ id, body })
// 成功 → message.success（hook 已 invalidate gaps 列表，自动刷新）
// error → message.error 保留输入
```

---

## R001-FE10：components/clarify/ClarifyForm.tsx `✅ 已完成`

- 文件：`frontend/src/components/clarify/ClarifyForm.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE06, FE07]
- priority: 4
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 候选 ClarifyOption[] 渲染为结构化表单（field_key → question + options 或自由输入）
  - 空候选场景显示「暂无可追问项」+ 返回按钮（不自动轮询）
  - 提交成功后调用方跳回报告页
- decision_refs: []
- test_tasks:
  - type: unit
    description: ClarifyForm 渲染候选 + 空候选 + 提交
    scenarios: [前端测试场景表 ClarifyForm 行]
- contract_refs: []
- blocked_files: []

### FE10.1 ClarifyForm.tsx `✅`

```tsx
interface Props {
  reportId: string;
  options: ClarifyOption[];
  onSubmitted?: () => void;
}
// 空 options → antd <Empty>「暂无可追问项」+ <Button onClick={onSubmitted}>返回报告</Button>
// 非空 → antd <Form>：
//   每个 ClarifyOption 渲染 question 标签 + options Radio（source=kb）或 Input（source=manual）
// 提交 → useSubmitClarify(reportId).mutate
// 成功 → onSubmitted()
// error → 保留选择 + message.error
```

---

## R001-FE11：main.tsx + App.tsx `✅ 已完成`

- 文件：`frontend/src/main.tsx`、`frontend/src/App.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE07, FE08, FE09, FE10, FE13]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - main.tsx 挂载 QueryClientProvider + RouterProvider + AntdApp + ConfigProvider（中文）
  - App.tsx 含侧边导航（报告/缺口）+ 路由表（4 条路由）
  - dev 模式按 VITE_USE_MOCK 启用 MSW（mock 层 FE13 就绪后生效）
- decision_refs: [D2, D3, D4, D7]
- test_tasks:
  - type: integration
    description: 路由可达 + Provider 挂载
    scenarios: [三页面可访问 /reports/:id、/gaps、/reports/:id/clarify]
- contract_refs: []
- blocked_files: []

### FE11.1 main.tsx `✅`

```tsx
// 1. dev 模式 + VITE_USE_MOCK !== 'false' → 动态 import('../mocks/browser') 启用 MSW
// 2. 挂载：
//    <QueryClientProvider client={queryClient}>
//      <AntdApp>  // antd v6 App（message/notification/context 统一入口）
//        <ConfigProvider locale={zhCN}>
//          <RouterProvider router={router} />
//        </ConfigProvider>
//      </AntdApp>
//    </QueryClientProvider>
```

### FE11.2 App.tsx + 路由表 `✅`

```tsx
// 用 React Router 7.18 库模式 createBrowserRouter
const router = createBrowserRouter([
  { path: '/', element: <AppLayout />, children: [
    { index: true, element: <Navigate to="/reports" /> },
    { path: 'reports', element: <ReportListPage /> },
    { path: 'reports/:id', element: <ReportDetailPage /> },
    { path: 'reports/:id/clarify', element: <ClarifyPage /> },
    { path: 'gaps', element: <GapViewPage /> },
  ]},
]);

// AppLayout：antd Layout + Sider（报告/缺口导航）+ Content（<Outlet/>）
```

---

## R001-FE12：routes/ `✅ 已完成`

- 文件：`frontend/src/routes/ReportListPage.tsx`、`ReportDetailPage.tsx`、`GapViewPage.tsx`、`ClarifyPage.tsx`
- 改动类型：新建
- domain: ui
- task_layer: ui
- depends_on: [FE08, FE09, FE10, FE11]
- priority: 4
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - ReportListPage 支持分页 + status/tier 过滤（URL params）
  - ReportDetailPage 组合 ReportHeader + HypothesisTree + FixPatchCard + TrajectoryTimeline + RegressionFeedbackForm
  - GapViewPage 渲染 GapList
  - ClarifyPage 渲染 ClarifyForm，提交后跳回 /reports/:id
  - 所有页面用 PageContainer 包裹 loading/error/empty 三态
- decision_refs: [D6]
- test_tasks:
  - type: integration
    description: 各页面流程
    scenarios: [前端测试场景表 ReportListPage/ReportDetailPage 行；FB001 报告详情+反馈 5.1 / FB003 缺口+补齐 5.2 / FB004 追问闭环 5.3]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE12.1 ReportListPage.tsx `✅`

```tsx
// URL search params: page/page_size/status/tier（可分享/刷新保持）
// useReportList(params)
// PageContainer 包裹 → antd <Table> 分页 + status/tier 过滤器
// 行点击 → navigate(`/reports/${id}`)
```

### FE12.2 ReportDetailPage.tsx `✅`

```tsx
// useParams<{ id }>()
// useReport(id) → PageContainer → ReportHeader
// useTrajectory(id) → HypothesisTree + TrajectoryTimeline
// report.fix_patch_id 存在 → 渲染 FixPatchCard（需补 query 取 patch；MVP 简化：report 内联 fix_patch 或单独 query）
// report.status ∈ allowed 5 态 → 渲染 RegressionFeedbackForm
// report.pr_url 存在 → 外链按钮（FB002 边界）
// report.clarify_requested → 显示追问入口（跳 /reports/:id/clarify）
```

### FE12.3 GapViewPage.tsx `✅`

```tsx
// useGaps() → PageContainer → <GapList gaps={data} />
```

### FE12.4 ClarifyPage.tsx `✅`

```tsx
// useParams<{ id }>()
// useClarifyOptions(id) → PageContainer → <ClarifyForm reportId options onSubmitted={() => navigate(`/reports/${id}`)} />
```

---

## R001-FE13：mocks/ MSW mock 层 `✅ 已完成`

- 文件：`frontend/src/mocks/handlers.ts`、`frontend/src/mocks/server.ts`、`frontend/src/mocks/browser.ts`
- 改动类型：新建
- domain: infra
- task_layer: foundation
- depends_on: [FE04]
- priority: 4
- risk_tags: [contract_drift]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 8 个端点全部在 handlers.ts 覆盖（对应 frontend design「MSW 覆盖清单」）
  - 响应模板关键内容与契约一致（含 14 态 status / 四态 hypothesis / pr_url / clarify_requested）
  - server.ts 供 vitest（node 环境）；browser.ts 供 dev 先行
  - 响应模板含异常场景（409 状态非法、空候选、404 不存在）
- decision_refs: [D7]
- test_tasks:
  - type: integration
    description: handlers.spec.ts 校验响应 Schema 自洽
    scenarios: [契约测试表 8 行 + 异常场景]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE13.1 handlers.ts `✅`

```ts
import { http, HttpResponse } from 'msw';

// 8 个端点全量模板，对应 frontend design MSW 覆盖清单
export const handlers = [
  http.get('/reports', ({ request }) => {
    // 解析 URL params → 按 status/tier 过滤 → 返回分页 BugReport[]
  }),
  http.get('/reports/:id', ({ params }) => {
    // 返回完整 BugReport（含 confidence_score/tier/fix_patch_id/pr_url）
    // 或 404
  }),
  http.get('/reports/:id/trajectory', ({ params }) => {
    // 返回 Trajectory（hypotheses 四态扁平数组 + events）
  }),
  http.get('/reports/:id/clarify-options', ({ params }) => {
    // 返回 ClarifyOption[]，含空候选场景
  }),
  http.post('/reports/:id/clarify', async ({ request }) => {
    // 200 + BugReport(clarify_requested=false)
  }),
  http.post('/reports/:id/regression-feedback', async ({ request }) => {
    // 按 outcome 返回 200 + {metric_point_id, status_before, status_after, reflow_scheduled}
    // 或 409（denied 9 态）
  }),
  http.get('/gaps', () => {
    // 返回 CapabilityGap[]，按 estimated_unlock_value 降序
  }),
  http.post('/gaps/:id/unblock', async ({ request }) => {
    // 200 + CapabilityGap(status=unblocked)
  }),
];
```

### FE13.2 server.ts `✅`

```ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
// 供 vitest setupFiles 启动：server.listen({ onUnhandledRequest: 'error' })
// afterEach: server.resetHandlers()
// afterAll: server.close()
```

### FE13.3 browser.ts `✅`

```ts
import { setupWorker } from 'msw/browser';
import { handlers } from './handlers';

export const worker = setupWorker(...handlers);
// main.tsx dev 模式动态启用：worker.start({ onUnhandledRequest: 'bypass' })
```

---

## R001-FE14：handlers.spec.ts 契约守护测试 `✅ 已完成`

- 文件：`frontend/src/mocks/handlers.spec.ts`、`frontend/src/test/setup.ts`
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [FE13]
- priority: 4
- risk_tags: [contract_drift]
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 每个 handler 响应 Schema 自洽（必填字段、枚举值与 backend Schema 一致）
  - regression-feedback handler 覆盖 allowed 5 态 × {regression, safe} + denied 9 态全量 28 case
  - 类型层面与 types/ 对齐（用 tsd 或类型断言）
- decision_refs: [D7]
- test_tasks:
  - type: integration
    description: 契约守护
    scenarios: [契约测试表全行 + regression-feedback 28 case]
- contract_refs: [contracts/openapi.json]
- blocked_files: []

### FE14.1 test/setup.ts `✅`

```ts
import '@testing-library/jest-dom';
import { server } from '../mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

### FE14.2 handlers.spec.ts `✅`

对每个 handler 发起请求 + 断言响应 Schema。关键断言：

- GET /reports：返回 Paginated<BugReport>，items[].status ∈ 14 态枚举
- GET /reports/:id/trajectory：hypotheses[].status ∈ 4 态枚举
- POST /reports/:id/regression-feedback：参数化 14 态 × 2 outcome = 28 case，断言 allowed 5 态返回 200、denied 9 态返回 409、reflow_scheduled 在 concluded/reflected + regression 时为 true
- POST /gaps/:id/unblock：返回 CapabilityGap.status='unblocked'

---

## R001-FE15：组件 + utils 单测 `✅ 已完成`

- 文件：`frontend/src/components/**/*.spec.tsx`、`frontend/src/utils/*.spec.ts`、`frontend/src/hooks/*.spec.tsx`
- 改动类型：新建
- domain: integration
- task_layer: business
- depends_on: [FE05, FE06, FE07, FE08, FE09, FE10, FE14]
- priority: 3
- risk_tags: []
- smoke_required: false
- mode: direct
- status: pending
- acceptance_criteria:
  - 组件 + hooks + utils 覆盖率 ≥80%
  - HypothesisTree 四态三色映射正确，refuted 保留可见
  - RegressionFeedbackForm allowed 5 态显示入口、其余 9 态隐藏
  - treeBuilder 支持深层嵌套（10 层）+ 大量节点（100+）+ 空树
  - apiClient 错误码映射全场景
- decision_refs: []
- test_tasks:
  - type: unit
    description: 全前端测试场景表
    scenarios: [前端测试场景表全行]
- contract_refs: []
- blocked_files: []

### FE15.1 utils 单测 `✅`

format.ts 映射断言 + treeBuilder.ts 构建（含 10 层嵌套 / 100+ 节点 / 空树）。

### FE15.2 组件单测 `✅`

用 @testing-library/react 渲染：

- HypothesisTree：mock 四态节点 → 断言三色映射 + refuted 保留
- RegressionFeedbackForm：参数化 14 态 → 断言 5 态渲染、9 态 return null
- FixPatchCard：is_draft 标识渲染
- GapList：排序展示（由后端保证，前端断言展示）
- ClarifyForm：空候选 → Empty + 返回按钮；非空 → 表单
- PageContainer：三态
- StatusBadge：14 态 + tier 1-4

### FE15.3 hooks 单测 `✅`

用 @testing-library/react-hooks + QueryClientProvider wrapper：

- useReport/useGaps/useClarify：loading/error/data 三态
- useRegressionFeedback：reflow_scheduled=true 时 invalidate report detail
- useUnblockGap：成功后 invalidate gaps 列表

---

## R001-FE16：最后 — 编译验证 + 测试路径 `✅ 已完成`

- 文件：无（验证步骤）
- 改动类型：配置
- domain: integration
- task_layer: business
- depends_on: [FE01, FE02, FE03, FE04, FE05, FE06, FE07, FE08, FE09, FE10, FE11, FE12, FE13, FE14, FE15]
- priority: 5
- risk_tags: []
- smoke_required: true
- mode: direct
- status: pending
- acceptance_criteria:
  - `cd frontend && npm run typecheck` 无错误
  - `cd frontend && npm run build` 产出 dist/ 无错误
  - `cd frontend && npm run test` 全部通过
  - `cd frontend && npm run test:coverage` 组件+hooks+utils 覆盖率 ≥80%
  - 手动冒烟：`npm run dev`（MSW 启用）→ 访问 /reports/:id、/gaps、/reports/:id/clarify 三页面可达 + 三态完备
  - 手动冒烟：假设树 mock 四态节点三色正确，refuted 保留可见
  - 手动冒烟：回归反馈入口仅 allowed 5 态显示
- decision_refs: []
- test_tasks:
  - type: integration
    description: 全前端验证路径
    scenarios: [frontend design 第 7 节验收标准全表]
- contract_refs: []
- blocked_files: []

### FE16.1 验证命令序列 `✅`

```bash
cd frontend
npm run typecheck    # tsc --noEmit 无错误
npm run build        # 产出 dist/
npm run test         # 全部通过
npm run test:coverage # 覆盖率 ≥80%
npm run dev          # 手动冒烟三页面 + 三态 + 四色映射 + allowed 5 态
```

### FE16.2 联调切换 `✅`

```bash
# 切真实后端（联调阶段）
VITE_USE_MOCK=false npm run dev
# 对齐 backend FF001/FF002 真实端点，发现 drift 即同步 handlers.ts
```
