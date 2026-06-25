/**
 * format.ts 单测 — 文案映射 + 工具函数
 */

import { describe, it, expect } from 'vitest';
import {
  BUG_STATUS_LABEL,
  BUG_STATUS_COLOR,
  TIER_LABEL,
  TIER_COLOR,
  HYPOTHESIS_STATUS_LABEL,
  HYPOTHESIS_STATUS_COLOR,
  CONFIDENCE_DIM_LABEL,
  GAP_STATUS_LABEL,
  GAP_STATUS_COLOR,
  GAP_TYPE_LABEL,
  REGRESSION_FEEDBACK_ALLOWED,
  canShowRegressionFeedback,
  formatGapValue,
  formatTimestamp,
} from '@/utils/format';
import type { BugReportStatus } from '@/types/report';

const ALL_14_STATUSES: BugReportStatus[] = [
  'received', 'assessing', 'degraded', 'reproducing',
  'located', 'fixing', 'verified', 'pr_open',
  'draft_pr', 'gap_pending', 'wont_reflow', 'concluded',
  'reflowed', 'reflected',
];

describe('format utils', () => {
  describe('BUG_STATUS_LABEL', () => {
    it('covers all 14 statuses', () => {
      for (const s of ALL_14_STATUSES) {
        expect(BUG_STATUS_LABEL[s]).toBeDefined();
        expect(typeof BUG_STATUS_LABEL[s]).toBe('string');
      }
      expect(Object.keys(BUG_STATUS_LABEL)).toHaveLength(14);
    });
  });

  describe('BUG_STATUS_COLOR', () => {
    it('covers all 14 statuses with valid antd color', () => {
      for (const s of ALL_14_STATUSES) {
        expect(BUG_STATUS_COLOR[s]).toBeDefined();
        expect(typeof BUG_STATUS_COLOR[s]).toBe('string');
      }
    });
  });

  describe('TIER_LABEL / TIER_COLOR', () => {
    it('covers Tier 1-4', () => {
      expect(TIER_LABEL[1]).toBe('Tier 1');
      expect(TIER_LABEL[2]).toBe('Tier 2');
      expect(TIER_LABEL[3]).toBe('Tier 3');
      expect(TIER_LABEL[4]).toBe('Tier 4');

      expect(TIER_COLOR[1]).toBe('green');
      expect(TIER_COLOR[2]).toBe('blue');
      expect(TIER_COLOR[3]).toBe('orange');
      expect(TIER_COLOR[4]).toBe('red');
    });
  });

  describe('HYPOTHESIS_STATUS_LABEL / COLOR', () => {
    it('covers all 4 hypothesis statuses', () => {
      const statuses = ['proposed', 'verifying', 'confirmed', 'refuted'] as const;
      for (const s of statuses) {
        expect(HYPOTHESIS_STATUS_LABEL[s]).toBeDefined();
        expect(HYPOTHESIS_STATUS_COLOR[s]).toBeDefined();
      }
    });

    it('maps confirmed to success (green)', () => {
      expect(HYPOTHESIS_STATUS_COLOR.confirmed).toBe('success');
    });

    it('maps refuted to error (red) - preserved visible (INV-2)', () => {
      expect(HYPOTHESIS_STATUS_COLOR.refuted).toBe('error');
    });
  });

  describe('CONFIDENCE_DIM_LABEL', () => {
    it('has 3 dimensions', () => {
      expect(CONFIDENCE_DIM_LABEL.dim_info_completeness).toBe('信息');
      expect(CONFIDENCE_DIM_LABEL.dim_verification_feasibility).toBe('验证');
      expect(CONFIDENCE_DIM_LABEL.dim_patternability).toBe('模式');
    });
  });

  describe('GAP labels', () => {
    it('covers all 7 gap statuses', () => {
      const statuses = [
        'identified', 'waiting', 'unblocked',
        'resolved', 'invalid_unblock', 'wont_reflow', 'wont_fix',
      ] as const;
      for (const s of statuses) {
        expect(GAP_STATUS_LABEL[s]).toBeDefined();
        expect(GAP_STATUS_COLOR[s]).toBeDefined();
      }
    });

    it('covers all 4 gap types', () => {
      const types = ['information', 'facility', 'pattern', 'model'] as const;
      for (const t of types) {
        expect(GAP_TYPE_LABEL[t]).toBeDefined();
      }
    });
  });

  describe('canShowRegressionFeedback', () => {
    const allowed5: BugReportStatus[] = [
      'pr_open', 'draft_pr', 'concluded', 'reflected', 'reflowed',
    ];
    const denied9: BugReportStatus[] = ALL_14_STATUSES.filter(
      (s) => !allowed5.includes(s),
    );

    it('returns true for 5 allowed statuses', () => {
      for (const s of allowed5) {
        expect(canShowRegressionFeedback(s)).toBe(true);
      }
    });

    it('returns false for 9 denied statuses', () => {
      for (const s of denied9) {
        expect(canShowRegressionFeedback(s)).toBe(false);
      }
    });

    it('REGRESSION_FEEDBACK_ALLOWED has exactly 5 entries', () => {
      expect(REGRESSION_FEEDBACK_ALLOWED).toHaveLength(5);
    });
  });

  describe('formatGapValue', () => {
    it('formats number with 2 decimals', () => {
      expect(formatGapValue(8.5)).toBe('解锁价值 8.50');
      expect(formatGapValue(3.14159)).toBe('解锁价值 3.14');
      expect(formatGapValue(0)).toBe('解锁价值 0.00');
    });
  });

  describe('formatTimestamp', () => {
    it('returns "-" for null', () => {
      expect(formatTimestamp(null)).toBe('-');
    });

    it('returns formatted string for valid ISO', () => {
      const result = formatTimestamp('2026-06-20T10:00:00Z');
      expect(result).not.toBe('-');
      expect(result).not.toBe('2026-06-20T10:00:00Z');
      expect(typeof result).toBe('string');
    });

    it('returns original string for invalid date', () => {
      expect(formatTimestamp('not-a-date')).toBe('not-a-date');
    });
  });
});
