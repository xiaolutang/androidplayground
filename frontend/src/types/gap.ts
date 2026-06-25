/**
 * CapabilityGap 类型定义
 *
 * 字段名 snake_case，与 backend Schema 一一对应。
 */

export type CapabilityGapStatus =
  | 'identified'
  | 'waiting'
  | 'unblocked'
  | 'resolved'
  | 'invalid_unblock'
  | 'wont_reflow'
  | 'wont_fix';

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
