---
type: design
status: designed
requirement_cycle: R001
topic: contract-alignment
date: 2026-06-26
tags: [contract, api, frontend-backend-alignment]
source_analysis: 2026-06-16--client-bug-fix-agent-backend.md
architecture_md_updates: false
---

# R001 API 契约对齐文档（design 补遗）

> 关联分析：[client-bug-fix-agent backend](2026-06-16--client-bug-fix-agent-backend.md) | [frontend](2026-06-16--client-bug-fix-agent-frontend.md)

## Context

R001 跳过了 design 阶段，原 analysis（backend line 734）声明"请求/响应 JSON 详细格式在 tasks 阶段按 DTO 定义"。这导致前后端没有共同的"契约合同"可对照，出现两类已知事故：
- `/gaps` 页面崩溃（前端 services 按数组解析，后端返回分页对象）
- `/reports/{id}/clarify-options` 页面崩溃（同模式：包装对象 vs 数组）

本文档作为 **design 补遗**，从 backend Pydantic `response_model` 反推所有 API 端点的真实请求/响应结构，作为后续修复前端 types/services/MSW handlers + 补真实集成测试的唯一依据。

## 契约源声明

**唯一契约源**：backend FastAPI/Pydantic 的 `response_model`（`agent/api/dtos/report_dtos.py` + `agent/api/routers/gap_router.py`）。

前端 `types/`、`services/*Api.ts`、`mocks/handlers.ts` 三者必须从此源派生。任何三者与 response_model 不一致，**以 response_model 为准**。

## 1. 端点契约总表（响应）

| # | 端点 | response_model | 响应结构 | 前端 services 当前状态 |
|---|------|----------------|----------|----------------------|
| 1 | `GET /reports` | `ReportListResponse` | `{items: ReportSummary[], total, page, page_size}` | ✓ reportApi.list 用 `Paginated<ReportSummary>`，一致 |
| 2 | `GET /reports/{id}` | `ReportDetail` | 裸对象（14 字段） | ✓ reportApi.detail 一致 |
| 3 | `GET /reports/{id}/trajectory` | `TrajectoryResponse` | `{nodes: TrajectoryNode[], edges: TrajectoryEdge[]}` | ✓ reportApi.trajectory 一致（边字段 `from/to` 与后端 alias 一致） |
| 4 | `GET /reports/{id}/clarify-options` | `ClarifyOptionsResponse` | **`{options: ClarifyOption[]}` 包装** | ⚠️ services 已修（解包 `.options`），但 MSW handlers 仍返回裸数组、types 层声明仍偏宽 |
| 5 | `POST /reports/{id}/clarify` | `ClarifyResponse` | `{accepted: bool}` | ✓ clarifyApi.submit 一致 |
| 6 | `POST /reports/{id}/regression-feedback` | `RegressionFeedbackResponse` | `{metric_point_id, status_before, status_after, reflow_scheduled}` | ✓ reportApi.submitRegressionFeedback 一致 |
| 7 | `POST /webhook/{platform}` | `WebhookResponse` (202) | `{bug_report_id, accepted}` | N/A 前端不调用（webhook 是外部系统入口） |
| 8 | `GET /gaps` | `GapListResponse` | **`{items: GapSummary[], total, page, page_size}` 分页** | ⚠️ services 已修（解包 `.items`），但 MSW handlers 仍返回裸数组、types `CapabilityGap` 字段名错 |
| 9 | `POST /gaps/{id}/unblock` | `UnblockResponse` | **`{gap_id, status_before, status_after, reflow_scheduled}`** | ✗ **gapApi.unblock 类型声明为 `CapabilityGap`，与后端字段完全不同** |

## 2. 请求体契约（POST 端点）

| # | 端点 | backend Request 模型 | 前端 Request 类型 | 状态 |
|---|------|---------------------|------------------|------|
| 5 | `POST /reports/{id}/clarify` | `ClarifyRequest{answers: [{option_id, value}]}` | 同 | ✓ |
| 6 | `POST /reports/{id}/regression-feedback` | `{outcome: regression\|safe, evidence, bucket_dim?, bucket_value?}` | 同 | ✓ |
| 9 | `POST /gaps/{id}/unblock` | **`{evidence: str, action_taken: str}`**（均必填 min_length=1） | **`{unlock_action, evidence, git_commit_anchor?}`** | ✗ **字段名不匹配，后端会 422** |

## 3. 字段级差异（前端 types vs 后端 DTO）

### 3.1 `CapabilityGap`（前端 types/gap.ts）vs `GapSummary`（后端）

| 前端字段 | 后端字段 | 一致性 |
|----------|----------|--------|
| id | id | ✓ |
| gap_type | gap_type | ✓ |
| **unlock_action** | **waiting_reason** | ✗ 字段名不同 |
| estimated_unlock_value | estimated_unlock_value | ✓ |
| status | status | ✓ |
| linked_bug_ids | linked_bug_ids | ✓ |
| **git_commit_anchor** | **（不存在）** | ✗ 后端不返回 |

### 3.2 `ClarifyOption`（前端 types/report.ts）vs 后端

| 前端字段 | 后端字段 | 一致性 |
|----------|----------|--------|
| id, question, context | id, question, context | ✓ |
| field_key? | （无） | 前端多余 optional，运行时永远是 undefined |
| options? | （无） | 同上 |
| source? | （无） | 同上 |

> ClarifyOption 多余字段不导致崩溃（都是 optional），但会让组件代码 `option.source === 'kb'` 这类判断永远 falsy，导致 UI 行为与设计意图偏离。

## 4. 完整 JSON 契约示例（修复 & 测试依据）

### 4.1 GET /reports
```json
{
  "items": [{"id":"rpt-1","title":"crash","status":"received","tier":null,"created_at":null,"updated_at":null}],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 4.2 GET /reports/{id}/clarify-options（包装对象，非数组）
```json
{
  "options": [
    {"id":"opt-1","question":"复现路径是什么？","context":"crash 堆栈缺 frame"}
  ]
}
```
空场景：`{"options": []}`（不是 `[]`）

### 4.3 POST /reports/{id}/clarify
请求：
```json
{"answers": [{"option_id":"opt-1","value":"com.example.MainActivity"}]}
```
响应：`{"accepted": true}`

### 4.4 GET /gaps（分页对象，非数组）
```json
{
  "items": [{
    "id":"gap-1",
    "gap_type":"repro",
    "waiting_reason":"缺少复现该 crash 的设备型号信息",
    "estimated_unlock_value": 1.0,
    "status":"waiting",
    "linked_bug_ids": []
  }],
  "total": 1,
  "page": 1,
  "page_size": 20
}
```

### 4.5 POST /gaps/{id}/unblock
请求（**注意字段名 action_taken，不是 unlock_action**）：
```json
{"evidence":"device added","action_taken":"added Pixel 8 to farm"}
```
响应：
```json
{
  "gap_id":"gap-1",
  "status_before":"waiting",
  "status_after":"unblocked",
  "reflow_scheduled": true
}
```

### 4.6 POST /reports/{id}/regression-feedback
请求：`{"outcome":"regression","evidence":"still crashes on v1.2.3"}`
响应：`{"metric_point_id":"mp-1","status_before":"concluded","status_after":"reflowed","reflow_scheduled":true}`

## 5. 待修复项清单（按优先级）

### P0 阻塞功能（必须修）
| # | 文件 | 当前 | 应改为 | 依据 |
|---|------|------|--------|------|
| 1 | `frontend/src/services/gapApi.ts:19` | `unblock(): Promise<CapabilityGap>` | `Promise<UnblockResponse>` | §4.5 |
| 2 | `frontend/src/types/gap.ts:28-32` | `UnblockRequest{unlock_action, evidence, git_commit_anchor?}` | `{evidence, action_taken}` | §4.5 请求 |
| 3 | `frontend/src/types/gap.ts:21` | `unlock_action: string` | `waiting_reason: string \| null` | §3.1 |
| 4 | `frontend/src/types/gap.ts:25` | `git_commit_anchor: string \| null` | 删除（后端不返回） | §3.1 |
| 5 | `frontend/src/components/gap/GapUnblockAction.tsx` | 表单字段名 `unlock_action` | `action_taken` | §4.5 |

### P1 契约一致性（应修）
| # | 文件 | 当前 | 应改为 |
|---|------|------|--------|
| 6 | `frontend/src/mocks/handlers.ts` `GET /gaps` | 返回 `CapabilityGap[]` | 返回 `GapListResponse{items,total,page,page_size}` |
| 7 | `frontend/src/mocks/handlers.ts` `GET /reports/:id/clarify-options` | 返回 `ClarifyOption[]` | 返回 `{options: ClarifyOption[]}` |
| 8 | `frontend/src/mocks/handlers.ts` `POST /gaps/:id/unblock` | 返回 `CapabilityGap` | 返回 `UnblockResponse{gap_id,...}` |
| 9 | `frontend/src/types/report.ts:128-135` `ClarifyOption` 多余字段 | field_key/options/source | 删除（与后端 DTO 对齐） |

### P2 测试补齐（新增）
| # | 文件 | 待加 |
|---|------|------|
| 10 | `tests/integration/test_real_api_db.py` | `TestRealTrajectoryClarify`：trajectory / clarify-options / clarify POST 三个端点真实集成测试 |
| 11 | `tests/integration/test_real_api_db.py` | regression-feedback 的 regression+reflow 路径、webhook 成功路径、gap unblock 409 冲突路径 |
| 12 | `frontend/src/services/__tests__/*Api.test.ts`（新建目录） | services 层契约测试：验证解包逻辑对真实后端响应结构正确 |

## 6. 不变式（后续守卫）

1. **分页端点必返回分页对象**（`/reports`、`/gaps`），不允许裸数组
2. **包装端点必返回包装对象**（`/clarify-options` 返回 `{options:[...]}`），不允许裸数组
3. **`POST /gaps/{id}/unblock` 请求体字段名是 `action_taken`**，不是 `unlock_action`
4. **MSW handlers 必须与 backend response_model 一致**——handlers.spec.ts 的"契约守护"才有意义
5. **types/ 必须是 response_model 的前端投影**——多余字段（后端不返回的）要么删除要么标 `@deprecated`

## 7. 暂不处理

- webhook 请求体（`WebhookRequest` 用 `extra=allow`，是外部平台入口，前端不消费）
- ReportDetail 的 `raw_report` 字段（后端是 `dict[str, Any]`，前端类型 `Record<string, unknown>`，契约一致，不深究内部结构）
