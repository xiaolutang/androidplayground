/**
 * GapViewPage — 缺口管理页
 *
 * 数据通过 useGaps hook 获取，不直接调 apiClient。
 */

import { useGaps } from '@/hooks/useGaps';
import { PageContainer } from '@/components/common/PageContainer';
import { GapList } from '@/components/gap/GapList';

export function GapViewPage() {
  const { data, isLoading, error, refetch } = useGaps();

  return (
    <PageContainer
      title="缺口管理"
      loading={isLoading}
      error={error}
      data={data}
      onRetry={() => refetch()}
      empty={(d) => d.length === 0}
    >
      {(gaps) => <GapList gaps={gaps} />}
    </PageContainer>
  );
}
