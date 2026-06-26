/**
 * handlers.spec.ts — 契约守护测试
 *
 * 验证每个 MSW handler 的响应结构与 types/ 定义一致（字段名、类型、枚举值）。
 * 确保 mock 数据不与 backend Schema 漂移。
 */

import { describe, it, expect } from 'vitest';
import type {
  Paginated,
} from '@/types/api';
import type {
  ReportSummary,
  ReportDetail,
  TrajectoryResponse,
  ClarifyOption,
  ClarifyResponse,
  RegressionFeedbackResponse,
  BugReportStatus,
  RegressionFeedbackRequest,
} from '@/types/report';
import type {
  CapabilityGap,
  UnblockResponse,
} from '@/types/gap';

// ---------------------------------------------------------------------------
// 14 态 + 4 态枚举常量（与 types/ 定义对齐）
// ---------------------------------------------------------------------------
const VALID_BUG_STATUSES: BugReportStatus[] = [
  'received', 'assessing', 'degraded', 'reproducing',
  'located', 'fixing', 'verified', 'pr_open',
  'draft_pr', 'gap_pending', 'wont_reflow', 'concluded',
  'reflowed', 'reflected',
];

const VALID_HYPOTHESIS_STATUSES = ['proposed', 'verifying', 'confirmed', 'refuted'];

const VALID_GAP_STATUSES = [
  'identified', 'waiting', 'unblocked',
  'resolved', 'invalid_unblock', 'wont_reflow', 'wont_fix',
];

const REGRESSION_ALLOWED: BugReportStatus[] = [
  'pr_open', 'draft_pr', 'concluded', 'reflected', 'reflowed',
];

const BASE = 'http://localhost';

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MSW handlers contract', () => {
  describe('GET /reports', () => {
    it('returns Paginated<ReportSummary> with valid status enum', async () => {
      const res = await fetch(`${BASE}/reports?page=1&page_size=10`);
      expect(res.ok).toBe(true);
      const data = (await res.json()) as Paginated<ReportSummary>;

      expect(data).toHaveProperty('items');
      expect(data).toHaveProperty('total');
      expect(data).toHaveProperty('page');
      expect(data).toHaveProperty('page_size');
      expect(Array.isArray(data.items)).toBe(true);
      expect(data.page).toBe(1);
      expect(data.page_size).toBe(10);

      for (const item of data.items) {
        expect(typeof item.id).toBe('string');
        expect(VALID_BUG_STATUSES).toContain(item.status);
        if (item.tier !== null) {
          expect([1, 2, 3, 4]).toContain(item.tier);
        }
      }
    });

    it('filters by status', async () => {
      const res = await fetch(`${BASE}/reports?status=verified`);
      const data = (await res.json()) as Paginated<ReportSummary>;
      for (const item of data.items) {
        expect(item.status).toBe('verified');
      }
    });

    it('filters by tier', async () => {
      const res = await fetch(`${BASE}/reports?tier=2`);
      const data = (await res.json()) as Paginated<ReportSummary>;
      for (const item of data.items) {
        expect(item.tier).toBe(2);
      }
    });
  });

  describe('GET /reports/:id', () => {
    it('returns ReportDetail with correct field types', async () => {
      const res = await fetch(`${BASE}/reports/rpt-001`);
      expect(res.ok).toBe(true);
      const data = (await res.json()) as ReportDetail;

      expect(typeof data.id).toBe('string');
      expect(VALID_BUG_STATUSES).toContain(data.status);
      expect(typeof data.reflow_count).toBe('number');
      // pr_url 是 string | null
      expect(data.pr_url === null || typeof data.pr_url === 'string').toBe(true);
    });

    it('returns 404 for not-found id', async () => {
      const res = await fetch(`${BASE}/reports/not-found`);
      expect(res.status).toBe(404);
    });
  });

  describe('GET /reports/:id/trajectory', () => {
    it('returns TrajectoryResponse with nodes and edges', async () => {
      const res = await fetch(`${BASE}/reports/rpt-001/trajectory`);
      expect(res.ok).toBe(true);
      const data = (await res.json()) as TrajectoryResponse;

      expect(Array.isArray(data.nodes)).toBe(true);
      expect(Array.isArray(data.edges)).toBe(true);

      for (const node of data.nodes) {
        expect(typeof node.id).toBe('string');
        if (node.status !== null) {
          expect(VALID_HYPOTHESIS_STATUSES).toContain(node.status);
        }
      }

      for (const edge of data.edges) {
        expect(typeof edge.from).toBe('string');
        expect(typeof edge.to).toBe('string');
      }
    });

    it('includes all four hypothesis statuses', async () => {
      const res = await fetch(`${BASE}/reports/rpt-001/trajectory`);
      const data = (await res.json()) as TrajectoryResponse;
      const statuses = data.nodes.map((n) => n.status).filter(Boolean);
      expect(statuses).toContain('confirmed');
      expect(statuses).toContain('refuted');
      expect(statuses).toContain('proposed');
      expect(statuses).toContain('verifying');
    });
  });

  describe('GET /reports/:id/clarify-options', () => {
    it('returns {options: ClarifyOption[]} with correct fields', async () => {
      const res = await fetch(`${BASE}/reports/rpt-001/clarify-options`);
      expect(res.ok).toBe(true);
      const data = (await res.json()) as { options: ClarifyOption[] };

      expect(Array.isArray(data.options)).toBe(true);
      expect(data.options.length).toBeGreaterThan(0);

      for (const opt of data.options) {
        expect(typeof opt.id).toBe('string');
        expect(typeof opt.question).toBe('string');
      }
    });

    it('returns empty options for empty-clarify id', async () => {
      const res = await fetch(`${BASE}/reports/empty-clarify/clarify-options`);
      const data = (await res.json()) as { options: ClarifyOption[] };
      expect(data.options).toEqual([]);
    });
  });

  describe('POST /reports/:id/clarify', () => {
    it('returns ClarifyResponse with accepted field', async () => {
      const res = await fetch(`${BASE}/reports/rpt-001/clarify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          answers: [{ option_id: 'opt-1', value: 'v1.0' }],
        }),
      });
      expect(res.ok).toBe(true);
      const data = (await res.json()) as ClarifyResponse;
      expect(typeof data.accepted).toBe('boolean');
    });
  });

  describe('POST /reports/:id/regression-feedback', () => {
    // 参数化 14 态 x 2 outcome = 28 case
    const outcomes: Array<'regression' | 'safe'> = ['regression', 'safe'];

    for (const status of VALID_BUG_STATUSES) {
      for (const outcome of outcomes) {
        const isAllowed = REGRESSION_ALLOWED.includes(status);
        const shouldReflow =
          outcome === 'regression' &&
          (status === 'concluded' || status === 'reflected');

        it(`${isAllowed ? '200' : '409'} for status=${status} outcome=${outcome}`, async () => {
          const body: RegressionFeedbackRequest = {
            outcome,
            evidence: 'test evidence',
          };
          const res = await fetch(
            `${BASE}/reports/rpt--${status}/regression-feedback`,
            {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(body),
            },
          );

          if (isAllowed) {
            expect(res.status).toBe(200);
            const data = (await res.json()) as RegressionFeedbackResponse;
            expect(typeof data.metric_point_id).toBe('string');
            expect(VALID_BUG_STATUSES).toContain(data.status_before);
            expect(VALID_BUG_STATUSES).toContain(data.status_after);
            expect(typeof data.reflow_scheduled).toBe('boolean');

            if (shouldReflow) {
              expect(data.reflow_scheduled).toBe(true);
              expect(data.status_after).toBe('reflowed');
            } else {
              expect(data.reflow_scheduled).toBe(false);
            }
          } else {
            expect(res.status).toBe(409);
          }
        });
      }
    }
  });

  describe('GET /gaps', () => {
    it('returns Paginated<CapabilityGap> with valid fields', async () => {
      const res = await fetch(`${BASE}/gaps`);
      expect(res.ok).toBe(true);
      const data = (await res.json()) as Paginated<CapabilityGap>;

      expect(data).toHaveProperty('items');
      expect(data).toHaveProperty('total');
      expect(Array.isArray(data.items)).toBe(true);
      expect(data.items.length).toBeGreaterThan(0);

      for (const gap of data.items) {
        expect(typeof gap.id).toBe('string');
        expect(['information', 'facility', 'pattern', 'model']).toContain(gap.gap_type);
        if (gap.waiting_reason !== null) {
          expect(typeof gap.waiting_reason).toBe('string');
        }
        if (gap.estimated_unlock_value !== null) {
          expect(typeof gap.estimated_unlock_value).toBe('number');
        }
        expect(VALID_GAP_STATUSES).toContain(gap.status);
        expect(Array.isArray(gap.linked_bug_ids)).toBe(true);
      }
    });

    it('returns gaps sorted by estimated_unlock_value descending', async () => {
      const res = await fetch(`${BASE}/gaps`);
      const data = (await res.json()) as Paginated<CapabilityGap>;
      for (let i = 1; i < data.items.length; i++) {
        const cur = data.items[i]!.estimated_unlock_value;
        const prev = data.items[i - 1]!.estimated_unlock_value;
        if (cur !== null && prev !== null) {
          expect(cur).toBeLessThanOrEqual(prev);
        }
      }
    });
  });

  describe('POST /gaps/:id/unblock', () => {
    it('returns UnblockResponse with status_after=unblocked', async () => {
      const res = await fetch(`${BASE}/gaps/gap-1/unblock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_taken: '已补充文档',
          evidence: 'docs/link',
        }),
      });
      expect(res.ok).toBe(true);
      const data = (await res.json()) as UnblockResponse;
      expect(data.gap_id).toBe('gap-1');
      expect(data.status_after).toBe('unblocked');
      expect(typeof data.reflow_scheduled).toBe('boolean');
    });

    it('returns 404 for unknown gap', async () => {
      const res = await fetch(`${BASE}/gaps/unknown/unblock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_taken: 'test',
          evidence: 'test',
        }),
      });
      expect(res.status).toBe(404);
    });

    it('returns 409 for conflict gap', async () => {
      const res = await fetch(`${BASE}/gaps/conflict-gap/unblock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_taken: 'test',
          evidence: 'test',
        }),
      });
      expect(res.status).toBe(409);
    });
  });
});
