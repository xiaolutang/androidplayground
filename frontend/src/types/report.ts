/**
 * BugReport / Trajectory / FixPatch / Clarify 类型定义
 *
 * 字段名 snake_case，与 backend Schema (agent/api/dtos/report_dtos.py) 一一对应。
 */

// ---------------------------------------------------------------------------
// BugReport 14 态
// ---------------------------------------------------------------------------
export type BugReportStatus =
  | 'received'
  | 'assessing'
  | 'degraded'
  | 'reproducing'
  | 'located'
  | 'fixing'
  | 'verified'
  | 'pr_open'
  | 'draft_pr'
  | 'gap_pending'
  | 'wont_reflow'
  | 'concluded'
  | 'reflowed'
  | 'reflected';

export type Tier = 1 | 2 | 3 | 4;

// ---------------------------------------------------------------------------
// ConfidenceScore（用于 report detail 展示）
// ---------------------------------------------------------------------------
export interface ConfidenceScore {
  dim_info_completeness: number;
  dim_verification_feasibility: number;
  dim_patternability: number;
  kb_pattern_hit: boolean;
  tier: Tier;
  score: number;
}

// ---------------------------------------------------------------------------
// ReportSummary（列表项，对应 backend ReportSummary）
// ---------------------------------------------------------------------------
export interface ReportSummary {
  id: string;
  title: string | null;
  status: BugReportStatus;
  tier: Tier | null;
  created_at: string | null;
  updated_at: string | null;
}

// ---------------------------------------------------------------------------
// ReportDetail（详情，对应 backend ReportDetail）
// ---------------------------------------------------------------------------
export interface ReportDetail {
  id: string;
  title: string | null;
  status: BugReportStatus;
  tier: Tier | null;
  symptom_type: string | null;
  root_cause: string | null;
  root_cause_location: string | null;
  confidence_score_id: string | null;
  fix_patch_id: string | null;
  pr_url: string | null;
  reflow_count: number;
  created_at: string | null;
  updated_at: string | null;
  raw_report: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// Trajectory（假设树，对应 backend TrajectoryResponse + node/edge 结构）
// ---------------------------------------------------------------------------
export interface TrajectoryNode {
  id: string;
  label: string | null;
  status: string | null;
  confidence: number | null;
}

export interface TrajectoryEdge {
  from: string;
  to: string;
  label: string | null;
}

export interface TrajectoryResponse {
  nodes: TrajectoryNode[];
  edges: TrajectoryEdge[];
}

// ---------------------------------------------------------------------------
// Hypothesis（前端假设树展示用扩展结构，与 tasks.md FE02 对齐）
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// FixPatch
// ---------------------------------------------------------------------------
export type FixStrategy = 'template' | 'llm' | 'history_calibration';

export interface FixPatch {
  id: string;
  strategy: FixStrategy;
  is_draft: boolean;
  patch_diff: string;
  target_file: string;
  verification_report: unknown | null;
}

// ---------------------------------------------------------------------------
// Clarify（对应 backend ClarifyOption / ClarifyRequest）
// ---------------------------------------------------------------------------
export interface ClarifyOption {
  id: string;
  question: string;
  context: string | null;
  field_key?: string;
  options?: string[];
  source?: 'kb' | 'manual';
}

export interface ClarifyAnswerItem {
  option_id: string;
  value: string;
}

export interface ClarifyRequest {
  answers: ClarifyAnswerItem[];
}

export interface ClarifyResponse {
  accepted: boolean;
}

// ---------------------------------------------------------------------------
// RegressionFeedback（对应 backend RegressionFeedbackRequest/Response）
// ---------------------------------------------------------------------------
export type RegressionOutcome = 'regression' | 'safe';

export interface RegressionFeedbackRequest {
  outcome: RegressionOutcome;
  evidence: string;
  bucket_dim?: string;
  bucket_value?: string;
}

export interface RegressionFeedbackResponse {
  metric_point_id: string;
  status_before: BugReportStatus;
  status_after: BugReportStatus;
  reflow_scheduled: boolean;
}
