/**
 * ReportListPage — 报告列表页
 *
 * URL search params 驱动分页 + status/tier 过滤（可分享/刷新保持）。
 * 数据通过 useReportList hook 获取，不直接调 apiClient。
 */

import { useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Table, Select, Space, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { useReportList } from '@/hooks/useReport';
import { PageContainer } from '@/components/common/PageContainer';
import { StatusBadge } from '@/components/common/StatusBadge';
import { BUG_STATUS_LABEL } from '@/utils/format';
import { formatTimestamp } from '@/utils/format';
import type { ReportSummary } from '@/types/report';
import type { BugReportStatus, Tier } from '@/types/report';

const { Title } = Typography;

const STATUS_OPTIONS = Object.entries(BUG_STATUS_LABEL).map(
  ([value, label]) => ({ value, label }),
);

const TIER_OPTIONS: { value: number; label: string }[] = [
  { value: 1, label: 'Tier 1' },
  { value: 2, label: 'Tier 2' },
  { value: 3, label: 'Tier 3' },
  { value: 4, label: 'Tier 4' },
];

export function ReportListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const page = Number(searchParams.get('page') ?? '1') || 1;
  const pageSize = Number(searchParams.get('page_size') ?? '10') || 10;
  const status = (searchParams.get('status') as BugReportStatus | null) ?? undefined;
  const tierParam = searchParams.get('tier');
  const tier = tierParam ? (Number(tierParam) as Tier) : undefined;

  const { data, isLoading, error, refetch } = useReportList({
    page,
    page_size: pageSize,
    status,
    tier,
  });

  const updateParams = useCallback(
    (updates: Record<string, string | undefined>) => {
      const next = new URLSearchParams(searchParams);
      for (const [key, value] of Object.entries(updates)) {
        if (value === undefined || value === '') {
          next.delete(key);
        } else {
          next.set(key, value);
        }
      }
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const columns: ColumnsType<ReportSummary> = [
    {
      title: '报告 ID',
      dataIndex: 'id',
      key: 'id',
      render: (text: string, record: ReportSummary) => (
        <a onClick={() => navigate(`/reports/${record.id}`)}>{text}</a>
      ),
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (text: string | null) => text ?? '-',
    },
    {
      title: '状态 / 层级',
      key: 'status',
      render: (_, record) => (
        <StatusBadge status={record.status} tier={record.tier} />
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string | null) => formatTimestamp(v),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      key: 'updated_at',
      render: (v: string | null) => formatTimestamp(v),
    },
  ];

  return (
    <div>
      <Title level={3}>报告列表</Title>
      <Space style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="状态筛选"
          style={{ width: 160 }}
          value={status}
          options={STATUS_OPTIONS}
          onChange={(val: BugReportStatus | undefined) =>
            updateParams({ status: val, page: undefined })
          }
        />
        <Select
          allowClear
          placeholder="层级筛选"
          style={{ width: 120 }}
          value={tier}
          options={TIER_OPTIONS}
          onChange={(val: Tier | undefined) =>
            updateParams({ tier: val ? String(val) : undefined, page: undefined })
          }
        />
      </Space>
      <PageContainer
        loading={isLoading}
        error={error}
        data={data}
        onRetry={() => refetch()}
        empty={(d) => d.items.length === 0}
      >
        {(paged) => (
          <Table<ReportSummary>
            rowKey="id"
            columns={columns}
            dataSource={paged.items}
            pagination={{
              current: page,
              pageSize: pageSize,
              total: paged.total,
              showSizeChanger: true,
              onChange: (p, ps) => {
                updateParams({
                  page: p > 1 ? String(p) : undefined,
                  page_size: ps !== 10 ? String(ps) : undefined,
                });
              },
            }}
          />
        )}
      </PageContainer>
    </div>
  );
}
