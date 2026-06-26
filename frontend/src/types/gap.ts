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
  /** 缺口描述（后端 GapSummary.waiting_reason，作为等待原因展示） */
  waiting_reason: string | null;
  estimated_unlock_value: number | null;
  status: CapabilityGapStatus;
  linked_bug_ids: string[];
}

export interface UnblockRequest {
  evidence: string;
  action_taken: string;
}

/** POST /gaps/{id}/unblock 响应（对应 backend UnblockResponse） */
export interface UnblockResponse {
  gap_id: string;
  status_before: string;
  status_after: string;
  reflow_scheduled: boolean;
}
