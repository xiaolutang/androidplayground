/**
 * Report hooks — TanStack Query 封装
 *
 * 暴露 loading/error/data 三态。
 * mutation 成功后正确 invalidate 相关 query key。
 */

import { useQuery } from '@tanstack/react-query';
import { reportApi, type ReportListParams } from '@/services/reportApi';

export const reportKeys = {
  all: ['reports'] as const,
  list: (params: ReportListParams) => ['reports', 'list', params] as const,
  detail: (id: string) => ['reports', 'detail', id] as const,
  trajectory: (id: string) => ['reports', id, 'trajectory'] as const,
};

export function useReportList(params: ReportListParams) {
  return useQuery({
    queryKey: reportKeys.list(params),
    queryFn: () => reportApi.list(params),
  });
}

export function useReport(id: string) {
  return useQuery({
    queryKey: reportKeys.detail(id),
    queryFn: () => reportApi.detail(id),
    enabled: !!id,
  });
}

export function useTrajectory(id: string) {
  return useQuery({
    queryKey: reportKeys.trajectory(id),
    queryFn: () => reportApi.trajectory(id),
    enabled: !!id,
  });
}
