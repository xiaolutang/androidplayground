/**
 * Gaps hooks — TanStack Query 封装
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { gapApi } from '@/services/gapApi';
import type { UnblockRequest } from '@/types/gap';

export const gapKeys = {
  all: ['gaps'] as const,
};

export function useGaps() {
  return useQuery({
    queryKey: gapKeys.all,
    queryFn: () => gapApi.list(),
  });
}

export function useUnblockGap() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: UnblockRequest }) =>
      gapApi.unblock(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: gapKeys.all });
    },
  });
}
