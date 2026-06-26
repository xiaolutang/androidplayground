/**
 * 缺口领域 API
 *
 * 端点对应 backend FF001/FF002:
 * - GET  /gaps
 * - POST /gaps/:id/unblock
 */

import { apiClient } from './apiClient';
import type { CapabilityGap, UnblockRequest, UnblockResponse } from '@/types/gap';

export const gapApi = {
  async list(): Promise<CapabilityGap[]> {
    // 后端 /gaps 返回 {items, total, page, page_size} 分页结构，此处解包
    const res = await apiClient<{ items: CapabilityGap[] }>('/gaps');
    return res.items;
  },

  unblock(id: string, body: UnblockRequest): Promise<UnblockResponse> {
    return apiClient<UnblockResponse>(`/gaps/${id}/unblock`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },
};
