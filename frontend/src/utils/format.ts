/**
 * UI 展示层文案映射 — 纯函数，无副作用
 *
 * DTO 层不改名，仅在此做文案别名映射。
 */

import type {
  BugReportStatus,
  Tier,
  HypothesisStatus,
} from '@/types/report';
import type {
  CapabilityGapStatus,
  GapType,
} from '@/types/gap';

// ---------------------------------------------------------------------------
// BugReport 14 态 → 文案 + antd Tag color
// ---------------------------------------------------------------------------
export const BUG_STATUS_LABEL: Record<BugReportStatus, string> = {
  received: '已接收',
  assessing: '评估中',
  degraded: '服务降级',
  reproducing: '复现中',
  located: '已定位',
  fixing: '修复中',
  verified: '已验证',
  pr_open: 'PR 已开',
  draft_pr: 'Draft PR',
  gap_pending: '等待补齐',
  wont_reflow: '不回流',
  concluded: '已结案',
  reflowed: '回流中',
  reflected: '已反思',
};

export const BUG_STATUS_COLOR: Record<BugReportStatus, string> = {
  received: 'default',
  assessing: 'processing',
  degraded: 'warning',
  reproducing: 'processing',
  located: 'blue',
  fixing: 'processing',
  verified: 'success',
  pr_open: 'success',
  draft_pr: 'warning',
  gap_pending: 'orange',
  wont_reflow: 'default',
  concluded: 'default',
  reflowed: 'processing',
  reflected: 'purple',
};

// ---------------------------------------------------------------------------
// Tier 1-4 → 文案 + color
// ---------------------------------------------------------------------------
export const TIER_LABEL: Record<Tier, string> = {
  1: 'Tier 1',
  2: 'Tier 2',
  3: 'Tier 3',
  4: 'Tier 4',
};

export const TIER_COLOR: Record<Tier, string> = {
  1: 'green',
  2: 'blue',
  3: 'orange',
  4: 'red',
};

// ---------------------------------------------------------------------------
// Hypothesis 4 态 → 文案 + color
// ---------------------------------------------------------------------------
export const HYPOTHESIS_STATUS_LABEL: Record<HypothesisStatus, string> = {
  proposed: '待验证',
  verifying: '验证中',
  confirmed: '已确认',
  refuted: '已证伪',
};

export const HYPOTHESIS_STATUS_COLOR: Record<HypothesisStatus, string> = {
  proposed: 'default',
  verifying: 'processing',
  confirmed: 'success',
  refuted: 'error',
};

// ---------------------------------------------------------------------------
// ConfidenceScore 三维 → 短标签
// ---------------------------------------------------------------------------
export const CONFIDENCE_DIM_LABEL = {
  dim_info_completeness: '信息',
  dim_verification_feasibility: '验证',
  dim_patternability: '模式',
} as const;

// ---------------------------------------------------------------------------
// CapabilityGap 状态 → 文案 + color
// ---------------------------------------------------------------------------
export const GAP_STATUS_LABEL: Record<CapabilityGapStatus, string> = {
  identified: '已识别',
  waiting: '等待补齐',
  unblocked: '已补齐',
  resolved: '已解决',
  invalid_unblock: '补齐无效',
  wont_reflow: '不回流',
  wont_fix: '不修复',
};

export const GAP_STATUS_COLOR: Record<CapabilityGapStatus, string> = {
  identified: 'blue',
  waiting: 'orange',
  unblocked: 'success',
  resolved: 'green',
  invalid_unblock: 'red',
  wont_reflow: 'default',
  wont_fix: 'default',
};

// ---------------------------------------------------------------------------
// GapType → 文案
// ---------------------------------------------------------------------------
export const GAP_TYPE_LABEL: Record<GapType, string> = {
  information: '信息缺失',
  facility: '设施缺失',
  pattern: '模式缺失',
  model: '模型缺失',
};

// ---------------------------------------------------------------------------
// 工具函数
// ---------------------------------------------------------------------------

/** estimated_unlock_value → UI 解锁价值标签 */
export function formatGapValue(v: number | null): string {
  if (v === null) return '解锁价值 -';
  return `解锁价值 ${v.toFixed(2)}`;
}

/** ISO timestamp → 本地时间短格式 */
export function formatTimestamp(iso: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/** 回归反馈允许显示的状态（5 态） */
export const REGRESSION_FEEDBACK_ALLOWED: BugReportStatus[] = [
  'pr_open',
  'draft_pr',
  'concluded',
  'reflected',
  'reflowed',
];

export function canShowRegressionFeedback(status: BugReportStatus): boolean {
  return REGRESSION_FEEDBACK_ALLOWED.includes(status);
}
