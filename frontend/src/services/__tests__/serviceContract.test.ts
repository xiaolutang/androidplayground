/**
 * Service 层契约测试
 *
 * 验证 service 函数正确解包后端响应结构：
 * - reportApi.list() → Paginated<ReportSummary>（不解包，直传分页结构）
 * - clarifyApi.options() → ClarifyOption[]（从 {options:[...]} 解包）
 * - gapApi.list() → CapabilityGap[]（从 {items,...} 解包 .items）
 * - gapApi.unblock() → UnblockResponse（非 CapabilityGap）
 *
 * 这正是 R001 契约漂移导致 /gaps 和 /clarify 页面崩溃的根因层。
 * 用 MSW default handlers 拦截，验证 service 转换逻辑。
 */

import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@/mocks/server';
import { reportApi } from '@/services/reportApi';
import { clarifyApi } from '@/services/clarifyApi';
import { gapApi } from '@/services/gapApi';
import type { ApiError } from '@/types/api';

describe('Service contract — response unpacking', () => {
  describe('reportApi.list()', () => {
    it('returns Paginated<ReportSummary> with pagination fields', async () => {
      const data = await reportApi.list({ page: 1, page_size: 5 });
      expect(data).toHaveProperty('items');
      expect(data).toHaveProperty('total');
      expect(data).toHaveProperty('page', 1);
      expect(data).toHaveProperty('page_size', 5);
      expect(Array.isArray(data.items)).toBe(true);
    });

    it('returns items with valid ReportSummary shape', async () => {
      const data = await reportApi.list();
      for (const item of data.items) {
        expect(typeof item.id).toBe('string');
        expect(typeof item.status).toBe('string');
      }
    });
  });

  describe('clarifyApi.options()', () => {
    it('unpacks {options: [...]} → ClarifyOption[]', async () => {
      const options = await clarifyApi.options('rpt-001');
      expect(Array.isArray(options)).toBe(true);
      expect(options.length).toBeGreaterThan(0);
      for (const opt of options) {
        expect(typeof opt.id).toBe('string');
        expect(typeof opt.question).toBe('string');
      }
    });

    it('returns empty array when backend returns {options: []}', async () => {
      server.use(
        http.get('*/reports/:id/clarify-options', () => {
          return HttpResponse.json({ options: [] });
        }),
      );
      const options = await clarifyApi.options('rpt-empty');
      expect(options).toEqual([]);
    });
  });

  describe('gapApi.list()', () => {
    it('unpacks {items, total, page, page_size} → CapabilityGap[]', async () => {
      const gaps = await gapApi.list();
      expect(Array.isArray(gaps)).toBe(true);
      expect(gaps.length).toBeGreaterThan(0);
      for (const gap of gaps) {
        expect(typeof gap.id).toBe('string');
        expect(Array.isArray(gap.linked_bug_ids)).toBe(true);
      }
    });

    it('does NOT return raw paginated wrapper', async () => {
      const gaps = await gapApi.list();
      // If service forgot to unpack, gaps would be {items, total, ...} object
      expect(gaps).not.toHaveProperty('items');
      expect(gaps).not.toHaveProperty('total');
    });

    it('handles null gap_type without crash (backend Optional[str])', async () => {
      server.use(
        http.get('*/gaps', () => {
          return HttpResponse.json({
            items: [
              {
                id: 'gap-null',
                gap_type: null,
                waiting_reason: '测试空类型',
                estimated_unlock_value: 1.0,
                status: 'waiting',
                linked_bug_ids: [],
              },
            ],
            total: 1,
            page: 1,
            page_size: 20,
          });
        }),
      );
      const gaps = await gapApi.list();
      expect(gaps[0]!.gap_type).toBeNull();
    });
  });

  describe('gapApi.unblock()', () => {
    it('returns UnblockResponse (not CapabilityGap)', async () => {
      const res = await gapApi.unblock('gap-1', {
        action_taken: '已补充文档',
        evidence: 'docs/link',
      });
      expect(res).toHaveProperty('gap_id');
      expect(res).toHaveProperty('status_before');
      expect(res).toHaveProperty('status_after');
      expect(res).toHaveProperty('reflow_scheduled');
      expect(typeof res.reflow_scheduled).toBe('boolean');
      // Should NOT have CapabilityGap fields
      expect(res).not.toHaveProperty('gap_type');
      expect(res).not.toHaveProperty('linked_bug_ids');
    });
  });
});

describe('Service contract — error propagation', () => {
  it('reportApi.detail() throws ApiError with code=NOT_FOUND on 404', async () => {
    try {
      await reportApi.detail('not-found');
      expect.unreachable('should have thrown');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.code).toBe('NOT_FOUND');
    }
  });

  it('gapApi.unblock() throws ApiError with code=STATE_CONFLICT on 409', async () => {
    try {
      await gapApi.unblock('conflict-gap', {
        action_taken: 'test',
        evidence: 'test',
      });
      expect.unreachable('should have thrown');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(409);
      expect(apiErr.code).toBe('STATE_CONFLICT');
    }
  });

  it('gapApi.unblock() throws ApiError with code=NOT_FOUND on 404', async () => {
    try {
      await gapApi.unblock('nonexistent-gap', {
        action_taken: 'test',
        evidence: 'test',
      });
      expect.unreachable('should have thrown');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.code).toBe('NOT_FOUND');
    }
  });
});
