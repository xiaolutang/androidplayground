/**
 * 报告领域 API
 *
 * 端点对应 backend FF001 AC-1~AC-3, AC-6:
 * - GET  /reports
 * - GET  /reports/:id
 * - GET  /reports/:id/trajectory
 * - POST /reports/:id/regression-feedback
 */

import { apiClient } from './apiClient';
import type { Paginated } from '@/types/api';
import type {
  ReportSummary,
  ReportDetail,
  TrajectoryResponse,
  RegressionFeedbackRequest,
  RegressionFeedbackResponse,
} from '@/types/report';

export interface ReportListParams {
  page?: number;
  page_size?: number;
  status?: string;
  tier?: number;
}

export const reportApi = {
  list(params: ReportListParams = {}): Promise<Paginated<ReportSummary>> {
    const query: Record<string, string | number | undefined> = {
      page: params.page,
      page_size: params.page_size,
      status: params.status,
      tier: params.tier,
    };
    return apiClient<Paginated<ReportSummary>>('/reports', { params: query });
  },

  detail(id: string): Promise<ReportDetail> {
    return apiClient<ReportDetail>(`/reports/${id}`);
  },

  trajectory(id: string): Promise<TrajectoryResponse> {
    return apiClient<TrajectoryResponse>(`/reports/${id}/trajectory`);
  },

  submitRegressionFeedback(
    id: string,
    body: RegressionFeedbackRequest,
  ): Promise<RegressionFeedbackResponse> {
    return apiClient<RegressionFeedbackResponse>(
      `/reports/${id}/regression-feedback`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      },
    );
  },
};
