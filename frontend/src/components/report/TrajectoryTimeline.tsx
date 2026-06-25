/**
 * TrajectoryTimeline — 时间线展示事件
 *
 * 从 TrajectoryResponse（nodes + edges）提取事件序列展示。
 * 纯展示组件，只接收 props。
 */

import { Timeline, Typography } from 'antd';
import type { TrajectoryNode, TrajectoryEdge } from '@/types/report';

const { Text } = Typography;

interface TrajectoryTimelineProps {
  nodes: TrajectoryNode[];
  edges: TrajectoryEdge[];
}

export function TrajectoryTimeline({ nodes, edges }: TrajectoryTimelineProps) {
  if (!nodes || nodes.length === 0) {
    return <Text type="secondary">暂无轨迹事件</Text>;
  }

  // 按 edges 顺序排列节点
  const orderedNodes: TrajectoryNode[] = [];

  // 建立子节点索引
  const childMap = new Map<string, string[]>();
  const childIds = new Set<string>();
  for (const edge of edges) {
    const list = childMap.get(edge.from) ?? [];
    list.push(edge.to);
    childMap.set(edge.from, list);
    childIds.add(edge.to);
  }

  // root = 没有被 edge 指向的 node
  const roots = nodes.filter((n) => !childIds.has(n.id));
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  // 深度优先遍历出有序序列
  const visited = new Set<string>();
  function visit(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const node = nodeMap.get(id);
    if (node) orderedNodes.push(node);
    const children = childMap.get(id) ?? [];
    for (const childId of children) {
      visit(childId);
    }
  }
  for (const root of roots) {
    visit(root.id);
  }
  // 补上可能因为孤岛没被遍历的
  for (const node of nodes) {
    if (!visited.has(node.id)) {
      orderedNodes.push(node);
    }
  }

  const items = orderedNodes.map((node) => ({
    color: node.status === 'confirmed' ? 'green' : node.status === 'refuted' ? 'red' : 'blue',
    children: (
      <div>
        <Text strong>{node.label ?? node.id}</Text>
        {node.status && (
          <Text type="secondary" style={{ marginLeft: 8 }}>
            ({node.status})
          </Text>
        )}
        {node.confidence != null && (
          <Text type="secondary" style={{ marginLeft: 8 }}>
            置信度: {node.confidence.toFixed(2)}
          </Text>
        )}
      </div>
    ),
  }));

  return <Timeline items={items} />;
}
