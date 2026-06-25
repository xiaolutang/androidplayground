/**
 * 缺口领域 API
 *
 * 端点对应 backend FF001/FF002:
 * - GET  /gaps
 * - POST /gaps/:id/unblock
 */

import { apiClient } from './apiClient';
import type { CapabilityGap, UnblockRequest } from '@/types/gap';

export const gapApi = {
  list(): Promise<CapabilityGap[]> {
    return apiClient<CapabilityGap[]>('/gaps');
  },

  unblock(id: string, body: UnblockRequest): Promise<CapabilityGap> {
    return apiClient<CapabilityGap>(`/gaps/${id}/unblock`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
