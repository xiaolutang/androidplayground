/**
 * GapList — 缺口列表
 *
 * 按 estimated_unlock_value 降序展示（后端保证排序）。
 * status=waiting → 挂载 GapUnblockAction。
 * status != waiting → 隐藏补齐入口。
 *
 * 纯展示组件，只接收 props。
 */

import { List, Tag, Typography, Space } from 'antd';
import type { CapabilityGap } from '@/types/gap';
import {
  GAP_STATUS_LABEL,
  GAP_STATUS_COLOR,
  GAP_TYPE_LABEL,
  formatGapValue,
} from '@/utils/format';
import { GapUnblockAction } from './GapUnblockAction';

const { Text } = Typography;

interface GapListProps {
  gaps: CapabilityGap[];
}

export function GapList({ gaps }: GapListProps) {
  return (
    <List
      dataSource={gaps}
      renderItem={(gap) => (
        <List.Item
          actions={
            gap.status === 'waiting'
              ? [<GapUnblockAction key="unblock" gap={gap} />]
              : undefined
          }
        >
          <List.Item.Meta
            title={
              <Space size="small">
                <Tag color={GAP_STATUS_COLOR[gap.status]}>
                  {GAP_STATUS_LABEL[gap.status]}
                </Tag>
                <Tag>{GAP_TYPE_LABEL[gap.gap_type]}</Tag>
                <Text strong>{formatGapValue(gap.estimated_unlock_value)}</Text>
              </Space>
            }
            description={
              <div>
                {gap.waiting_reason && <Text>{gap.waiting_reason}</Text>}
                {gap.linked_bug_ids.length > 0 && (
                  <Text type="secondary" style={{ marginLeft: 8 }}>
                    关联: {gap.linked_bug_ids.join(', ')}
                  </Text>
                )}
              </div>
            }
          />
        </List.Item>
      )}
    />
  );
}
