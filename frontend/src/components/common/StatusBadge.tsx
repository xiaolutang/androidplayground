/**
 * StatusBadge — BugReport 14 态 + Tier 1-4 渲染
 *
 * 纯展示组件。
 */

import { Tag, Space } from 'antd';
import type { BugReportStatus, Tier } from '@/types/report';
import {
  BUG_STATUS_LABEL,
  BUG_STATUS_COLOR,
  TIER_LABEL,
  TIER_COLOR,
} from '@/utils/format';

interface StatusBadgeProps {
  status?: BugReportStatus;
  tier?: Tier | null;
}

export function StatusBadge({ status, tier }: StatusBadgeProps) {
  return (
    <Space size="small">
      {status && (
        <Tag color={BUG_STATUS_COLOR[status]}>
          {BUG_STATUS_LABEL[status]}
        </Tag>
      )}
      {tier != null && (
        <Tag color={TIER_COLOR[tier]}>
          {TIER_LABEL[tier]}
        </Tag>
      )}
    </Space>
  );
}
