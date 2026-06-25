/**
 * HypothesisTree — 树形展示假设
 *
 * 四态三色映射：
 * - proposed/verifying → 灰（default）
 * - confirmed → 绿（success）
 * - refuted → 红（error），保留可见（INV-2 负向知识）
 *
 * 纯展示组件，只接收 props。
 */

import { Tree, Tag, Space } from 'antd';
import type { TreeDataNode } from 'antd';
import type { Hypothesis } from '@/types/report';
import {
  HYPOTHESIS_STATUS_LABEL,
  HYPOTHESIS_STATUS_COLOR,
} from '@/utils/format';
import { buildHypothesisTree } from '@/utils/treeBuilder';

interface HypothesisTreeProps {
  hypotheses: Hypothesis[];
}

function toAntdTreeData(
  nodes: ReturnType<typeof buildHypothesisTree>,
): TreeDataNode[] {
  return nodes.map((node) => {
    const h = node.hypothesis;
    return {
      key: node.key,
      title: (
        <Space size="small">
          <Tag color={HYPOTHESIS_STATUS_COLOR[h.status]}>
            {HYPOTHESIS_STATUS_LABEL[h.status]}
          </Tag>
          <span>{h.hypothesis_text}</span>
          {h.is_rootcause && <Tag color="purple">根因</Tag>}
          <span style={{ color: '#999', fontSize: 12 }}>
            {h.step_used}/{h.step_budget} 步
          </span>
        </Space>
      ),
      children:
        node.children.length > 0 ? toAntdTreeData(node.children) : undefined,
    };
  });
}

export function HypothesisTree({ hypotheses }: HypothesisTreeProps) {
  if (!hypotheses || hypotheses.length === 0) {
    return <div style={{ color: '#999' }}>暂无假设数据</div>;
  }

  const tree = buildHypothesisTree(hypotheses);
  const treeData = toAntdTreeData(tree);

  return (
    <Tree
      treeData={treeData}
      defaultExpandAll
      showLine
    />
  );
}
