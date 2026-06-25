/**
 * MSW handlers — 全部 8 个 API 端点的 mock
 *
 * 端点对应 backend FF001/FF002 第 4.3 节：
 * - GET    /reports                          报告列表（分页 + status/tier 过滤）
 * - GET    /reports/:id                      报告详情
 * - GET    /reports/:id/trajectory           假设树/轨迹
 * - GET    /reports/:id/clarify-options      追问候选
 * - POST   /reports/:id/clarify              提交追问
 * - POST   /reports/:id/regression-feedback  回归反馈
 * - GET    /gaps                             缺口列表
 * - POST   /gaps/:id/unblock                 补齐缺口
 *
 * 响应模板关键内容与 types/ 定义一致（含 14 态 status / 四态 hypothesis 等）。
 */

import { http, HttpResponse } from 'msw';
import type {
  ReportSummary,
  ReportDetail,
  TrajectoryResponse,
  TrajectoryNode,
  TrajectoryEdge,
  ClarifyOption,
  ClarifyResponse,
  RegressionFeedbackRequest,
  RegressionFeedbackResponse,
  BugReportStatus,
} from '@/types/report';
import type {
  CapabilityGap,
  UnblockRequest,
} from '@/types/gap';
import type { Paginated } from '@/types/api';

// ---------------------------------------------------------------------------
// Mock 数据工厂
// ---------------------------------------------------------------------------

const ALL_STATUSES: BugReportStatus[] = [
  'received', 'assessing', 'degraded', 'reproducing',
  'located', 'fixing', 'verified', 'pr_open',
  'draft_pr', 'gap_pending', 'wont_reflow', 'concluded',
  'reflowed', 'reflected',
];

const REGRESSION_ALLOWED: BugReportStatus[] = [
  'pr_open', 'draft_pr', 'concluded', 'reflected', 'reflowed',
];

function makeReportSummary(
  id: string,
  status: BugReportStatus = 'received',
  tier: 1 | 2 | 3 | 4 | null = null,
): ReportSummary {
  return {
    id,
    title: `Bug 报告 ${id}`,
    status,
    tier,
    created_at: '2026-06-20T10:00:00Z',
    updated_at: '2026-06-20T12:00:00Z',
  };
}

function makeReportDetail(
  id: string,
  status: BugReportStatus = 'received',
): ReportDetail {
  return {
    id,
    title: `Bug 报告 ${id}`,
    status,
    tier: 2,
    symptom_type: 'crash',
    root_cause: '空指针异常',
    root_cause_location: 'src/main.py:42',
    confidence_score_id: 'cs-001',
    fix_patch_id: 'fp-001',
    pr_url: 'https://github.com/example/repo/pull/1',
    reflow_count: 0,
    created_at: '2026-06-20T10:00:00Z',
    updated_at: '2026-06-20T12:00:00Z',
    raw_report: null,
  };
}

function makeTrajectory(reportId: string): TrajectoryResponse {
  const nodes: TrajectoryNode[] = [
    { id: 'h1', label: '假设 A：内存泄漏', status: 'confirmed', confidence: 0.9 },
    { id: 'h2', label: '假设 B：线程竞争', status: 'refuted', confidence: 0.3 },
    { id: 'h3', label: '假设 C：配置错误', status: 'proposed', confidence: 0.5 },
    { id: 'h4', label: '假设 D：版本不兼容', status: 'verifying', confidence: 0.6 },
  ];
  const edges: TrajectoryEdge[] = [
    { from: 'h1', to: 'h2', label: null },
    { from: 'h1', to: 'h3', label: null },
    { from: 'h3', to: 'h4', label: null },
  ];
  return { nodes, edges };
}

function makeClarifyOptions(): ClarifyOption[] {
  return [
    {
      id: 'opt-1',
      question: '是否在特定版本下复现？',
      context: '需要确认复现环境',
      field_key: 'version',
      options: ['v1.0', 'v1.1', 'v2.0'],
      source: 'kb',
    },
    {
      id: 'opt-2',
      question: '是否有错误日志？',
      context: '日志文件',
      field_key: 'log',
      source: 'manual',
    },
  ];
}

function makeGaps(): CapabilityGap[] {
  return [
    {
      id: 'gap-1',
      gap_type: 'information',
      unlock_action: '补充版本兼容矩阵',
      estimated_unlock_value: 8.5,
      status: 'waiting',
      linked_bug_ids: ['rpt-001'],
      git_commit_anchor: null,
    },
    {
      id: 'gap-2',
      gap_type: 'facility',
      unlock_action: '部署 CI 重跑环境',
      estimated_unlock_value: 6.2,
      status: 'identified',
      linked_bug_ids: ['rpt-002'],
      git_commit_anchor: 'abc1234',
    },
    {
      id: 'gap-3',
      gap_type: 'pattern',
      unlock_action: '补全 KB 模式条目',
      estimated_unlock_value: 3.1,
      status: 'unblocked',
      linked_bug_ids: [],
      git_commit_anchor: null,
    },
  ];
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const handlers = [
  // 1. GET /reports — 列表
  http.get('*/reports', ({ request }) => {
    const url = new URL(request.url);
    const params = url.searchParams;

    const page = Number(params.get('page') ?? '1') || 1;
    const pageSize = Number(params.get('page_size') ?? '10') || 10;
    const statusFilter = params.get('status') ?? undefined;
    const tierFilter = params.get('tier') ?? undefined;

    // 生成全部 mock 报告
    const allReports: ReportSummary[] = [];
    for (let i = 0; i < ALL_STATUSES.length; i++) {
      const tier = ((i % 4) + 1) as 1 | 2 | 3 | 4;
      allReports.push(makeReportSummary(`rpt-${String(i + 1).padStart(3, '0')}`, ALL_STATUSES[i]!, tier));
    }

    // 过滤
    let filtered = allReports;
    if (statusFilter) {
      filtered = filtered.filter((r) => r.status === statusFilter);
    }
    if (tierFilter) {
      filtered = filtered.filter((r) => r.tier === Number(tierFilter));
    }

    // 分页
    const start = (page - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);
    const result: Paginated<ReportSummary> = {
      items,
      total: filtered.length,
      page,
      page_size: pageSize,
    };
    return HttpResponse.json(result);
  }),

  // 2. GET /reports/:id — 详情
  http.get('*/reports/:id', ({ params }) => {
    const id = params.id as string;

    // 特殊 id 触发 404
    if (id === 'not-found') {
      return new HttpResponse(
        JSON.stringify({ detail: 'Report not found' }),
        { status: 404 },
      );
    }

    const statusParam = new URLSearchParams(id).get('status');
    const status = (statusParam as BugReportStatus) || 'verified';
    return HttpResponse.json(makeReportDetail(id, status));
  }),

  // 3. GET /reports/:id/trajectory — 轨迹
  http.get('*/reports/:id/trajectory', ({ params }) => {
    const id = params.id as string;
    return HttpResponse.json(makeTrajectory(id));
  }),

  // 4. GET /reports/:id/clarify-options — 追问候选
  http.get('*/reports/:id/clarify-options', ({ params }) => {
    const id = params.id as string;

    // 特殊 id 返回空候选
    if (id === 'empty-clarify') {
      return HttpResponse.json([]);
    }

    return HttpResponse.json(makeClarifyOptions());
  }),

  // 5. POST /reports/:id/clarify — 提交追问
  http.post('*/reports/:id/clarify', async ({ request, params }) => {
    const _id = params.id as string;
    const body = (await request.json()) as { answers: unknown[] };
    const response: ClarifyResponse = { accepted: true };
    return HttpResponse.json(response);
  }),

  // 6. POST /reports/:id/regression-feedback — 回归反馈
  http.post('*/reports/:id/regression-feedback', async ({ request, params }) => {
    const reportId = params.id as string;
    const body = (await request.json()) as RegressionFeedbackRequest;

    // 从 reportId 中提取 status（mock 约定：reportId 可编码 status）
    // 默认用 'concluded' 触发 reflow 逻辑
    const encodedStatus = reportId.split('--')[1] as BugReportStatus | undefined;
    const currentStatus: BugReportStatus = encodedStatus ?? 'concluded';

    // 检查是否在 allowed 5 态
    if (!REGRESSION_ALLOWED.includes(currentStatus)) {
      return new HttpResponse(
        JSON.stringify({ detail: 'State conflict: regression feedback not allowed' }),
        { status: 409 },
      );
    }

    // outcome=regression 且 status ∈ {concluded, reflected} → reflow_scheduled=true
    const reflowScheduled =
      body.outcome === 'regression' &&
      (currentStatus === 'concluded' || currentStatus === 'reflected');

    const statusAfter: BugReportStatus = reflowScheduled
      ? 'reflowed'
      : currentStatus;

    const response: RegressionFeedbackResponse = {
      metric_point_id: `mp-${Date.now()}`,
      status_before: currentStatus,
      status_after: statusAfter,
      reflow_scheduled: reflowScheduled,
    };
    return HttpResponse.json(response);
  }),

  // 7. GET /gaps — 缺口列表
  http.get('*/gaps', () => {
    return HttpResponse.json(makeGaps());
  }),

  // 8. POST /gaps/:id/unblock — 补齐缺口
  http.post('*/gaps/:id/unblock', async ({ request, params }) => {
    const gapId = params.id as string;
    const body = (await request.json()) as UnblockRequest;

    // 特殊 id 触发 409
    if (gapId === 'conflict-gap') {
      return new HttpResponse(
        JSON.stringify({ detail: 'State conflict' }),
        { status: 409 },
      );
    }

    const gaps = makeGaps();
    const gap = gaps.find((g) => g.id === gapId);
    if (!gap) {
      return new HttpResponse(
        JSON.stringify({ detail: 'Gap not found' }),
        { status: 404 },
      );
    }

    const updated: CapabilityGap = {
      ...gap,
      status: 'unblocked',
      unlock_action: body.unlock_action,
      git_commit_anchor: body.git_commit_anchor ?? gap.git_commit_anchor,
    };
    return HttpResponse.json(updated);
  }),
];
