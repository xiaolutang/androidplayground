/**
 * RegressionFeedback hook — TanStack Query useMutation 封装
 *
 * 关键逻辑：按 reflow_scheduled 决定是否刷新报告主体
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { reportApi } from '@/services/reportApi';
import type { RegressionFeedbackRequest } from '@/types/report';
import { reportKeys } from './useReport';

export function useRegressionFeedback(reportId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RegressionFeedbackRequest) =>
      reportApi.submitRegressionFeedback(reportId, body),
    onSuccess: (data) => {
      // outcome=regression 且 reflow_scheduled=true → invalidate report detail
      // 让状态翻为 reflowed
      if (data.reflow_scheduled) {
        qc.invalidateQueries({ queryKey: reportKeys.detail(reportId) });
      }
    },
  });
}
