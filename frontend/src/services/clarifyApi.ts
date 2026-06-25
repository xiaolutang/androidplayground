/**
 * 追问领域 API
 *
 * 端点对应 backend FF001 AC-4/AC-5:
 * - GET  /reports/:id/clarify-options
 * - POST /reports/:id/clarify
 */

import { apiClient } from './apiClient';
import type {
  ClarifyOption,
  ClarifyRequest,
  ClarifyResponse,
} from '@/types/report';

export const clarifyApi = {
  options(reportId: string): Promise<ClarifyOption[]> {
    return apiClient<ClarifyOption[]>(`/reports/${reportId}/clarify-options`);
  },

  submit(reportId: string, body: ClarifyRequest): Promise<ClarifyResponse> {
    return apiClient<ClarifyResponse>(`/reports/${reportId}/clarify`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
