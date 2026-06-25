/**
 * FixPatchCard — 渲染 diff + is_draft 标识
 *
 * is_draft 显眼标识（Tag 橙色「Draft」）
 * patch_diff 用 <pre> 展示
 *
 * 纯展示组件，只接收 props。
 */

import { Card, Tag, Space, Typography } from 'antd';
import type { FixPatch } from '@/types/report';

const { Text } = Typography;

interface FixPatchCardProps {
  patch: FixPatch;
}

const STRATEGY_LABEL: Record<string, string> = {
  template: '模板',
  llm: 'LLM',
  history_calibration: '历史校准',
};

export function FixPatchCard({ patch }: FixPatchCardProps) {
  return (
    <Card
      size="small"
      title={
        <Space>
          <Text strong>{patch.target_file}</Text>
          {patch.is_draft && <Tag color="orange">Draft</Tag>}
          <Tag>{STRATEGY_LABEL[patch.strategy] ?? patch.strategy}</Tag>
        </Space>
      }
    >
      <pre
        style={{
          background: '#f5f5f5',
          padding: 12,
          borderRadius: 4,
          overflow: 'auto',
          fontSize: 13,
          margin: 0,
        }}
      >
        {patch.patch_diff}
      </pre>
    </Card>
  );
}
