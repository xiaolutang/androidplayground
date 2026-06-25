/**
 * ClarifyPage — 追问页
 *
 * 数据通过 useClarifyOptions hook 获取，提交成功后跳回报告详情。
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useClarifyOptions } from '@/hooks/useClarify';
import { PageContainer } from '@/components/common/PageContainer';
import { ClarifyForm } from '@/components/clarify/ClarifyForm';

export function ClarifyPage() {
  const { id = '' } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error, refetch } = useClarifyOptions(id);

  return (
    <PageContainer
      title="澄清请求"
      loading={isLoading}
      error={error}
      data={data}
      onRetry={() => refetch()}
    >
      {(options) => (
        <ClarifyForm
          reportId={id}
          options={options}
          onSubmitted={() => navigate(`/reports/${id}`)}
        />
      )}
    </PageContainer>
  );
}
