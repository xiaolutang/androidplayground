/**
 * ReportHeader — 渲染 BugReport 状态/tier/root_cause/pr_url
 *
 * 复用 StatusBadge。纯展示组件，只接收 props。
 */

import { Descriptions, Button, Space, Tag } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import type { ReportDetail } from '@/types/report';
import { StatusBadge } from '@/components/common/StatusBadge';
import { formatTimestamp } from '@/utils/format';

interface ReportHeaderProps {
  report: ReportDetail;
}

export function ReportHeader({ report }: ReportHeaderProps) {
  return (
    <Descriptions
      title={report.title ?? report.id}
      bordered
      column={2}
      extra={
        report.pr_url ? (
          <Button
            type="link"
            href={report.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            icon={<LinkOutlined />}
          >
            查看 PR
          </Button>
        ) : undefined
      }
    >
      <Descriptions.Item label="报告 ID">
        {report.id}
      </Descriptions.Item>
      <Descriptions.Item label="状态">
        <StatusBadge status={report.status} tier={report.tier} />
      </Descriptions.Item>
      <Descriptions.Item label="症状类型">
        {report.symptom_type ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label="根因">
        {report.root_cause ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label="根因位置">
        {report.root_cause_location ?? '-'}
      </Descriptions.Item>
      <Descriptions.Item label="回流次数">
        {report.reflow_count}
      </Descriptions.Item>
      <Descriptions.Item label="创建时间">
        {formatTimestamp(report.created_at)}
      </Descriptions.Item>
      <Descriptions.Item label="更新时间">
        {formatTimestamp(report.updated_at)}
      </Descriptions.Item>
    </Descriptions>
  );
}
