/**
 * Clarify hooks — TanStack Query 封装
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { clarifyApi } from '@/services/clarifyApi';
import type { ClarifyRequest } from '@/types/report';
import { reportKeys } from './useReport';

export const clarifyKeys = {
  options: (reportId: string) => ['reports', reportId, 'clarify-options'] as const,
};

export function useClarifyOptions(reportId: string) {
  return useQuery({
    queryKey: clarifyKeys.options(reportId),
    queryFn: () => clarifyApi.options(reportId),
    enabled: !!reportId,
  });
}

export function useSubmitClarify(reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ClarifyRequest) => clarifyApi.submit(reportId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: reportKeys.detail(reportId) });
    },
  });
}
