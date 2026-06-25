/**
 * 假设树构建器 — 把扁平 Hypothesis[] 按 parent_id 转为嵌套树结构
 *
 * 纯函数，无副作用，可独立单测。
 */

import type { Hypothesis } from '@/types/report';

export interface HypothesisTreeNode {
  key: string;
  title: string;
  hypothesis: Hypothesis;
  children: HypothesisTreeNode[];
}

/**
 * 将扁平假设列表构建为嵌套树。
 *
 * 算法：
 * 1. 建两层索引：parentId→children[] 和 id→node
 * 2. 找 root（parent_id == null）
 * 3. 递归挂 children
 *
 * 时间复杂度 O(n)，支持深层嵌套和大量节点。
 */
export function buildHypothesisTree(hypotheses: Hypothesis[]): HypothesisTreeNode[] {
  if (!hypotheses || hypotheses.length === 0) return [];

  const nodeMap = new Map<string, HypothesisTreeNode>();
  const childrenMap = new Map<string | null, HypothesisTreeNode[]>();

  // 第一遍：创建所有节点
  for (const h of hypotheses) {
    const node: HypothesisTreeNode = {
      key: h.id,
      title: h.hypothesis_text,
      hypothesis: h,
      children: [],
    };
    nodeMap.set(h.id, node);

    const siblings = childrenMap.get(h.parent_id) ?? [];
    siblings.push(node);
    childrenMap.set(h.parent_id, siblings);
  }

  // 第二遍：从 root 开始递归填充 children
  const roots = childrenMap.get(null) ?? [];

  function fillChildren(node: HypothesisTreeNode): void {
    const children = childrenMap.get(node.key) ?? [];
    node.children = children;
    for (const child of children) {
      fillChildren(child);
    }
  }

  for (const root of roots) {
    fillChildren(root);
  }

  return roots;
}

/**
 * 把 TrajectoryResponse（nodes + edges）转为 Hypothesis 树结构。
 *
 * 用于后端 trajectory API 返回的 node/edge 图结构，转成前端树展示。
 */
export function buildTreeFromTrajectory(
  nodes: { id: string; label: string | null; status: string | null }[],
  edges: { from: string; to: string; label: string | null }[],
): HypothesisTreeNode[] {
  if (!nodes || nodes.length === 0) return [];

  // 找出所有有父节点的 id（即 edge.to）
  const childIds = new Set(edges.map((e) => e.to));

  // root = 没有 edge 指向它的 node
  const rootNodes = nodes.filter((n) => !childIds.has(n.id));

  const edgesFromMap = new Map<string, string[]>();
  for (const edge of edges) {
    const children = edgesFromMap.get(edge.from) ?? [];
    children.push(edge.to);
    edgesFromMap.set(edge.from, children);
  }

  function buildNode(
    nodeId: string,
    visited: Set<string> = new Set(),
  ): HypothesisTreeNode {
    if (visited.has(nodeId)) {
      // 防止环
      return {
        key: nodeId,
        title: '(cycle)',
        hypothesis: {
          id: nodeId,
          parent_id: null,
          hypothesis_text: '(cycle)',
          expected_signal: '',
          status: 'refuted',
          falsifying_signal: null,
          overturning_signal: null,
          is_rootcause: false,
          step_budget: 0,
          step_used: 0,
        },
        children: [],
      };
    }
    visited.add(nodeId);

    const node = nodes.find((n) => n.id === nodeId);
    const childIds = edgesFromMap.get(nodeId) ?? [];

    const hypothesis: Hypothesis = {
      id: nodeId,
      parent_id: null,
      hypothesis_text: node?.label ?? nodeId,
      expected_signal: '',
      status: (node?.status as Hypothesis['status']) ?? 'proposed',
      falsifying_signal: null,
      overturning_signal: null,
      is_rootcause: rootNodes.some((rn) => rn.id === nodeId),
      step_budget: 0,
      step_used: 0,
    };

    return {
      key: nodeId,
      title: node?.label ?? nodeId,
      hypothesis,
      children: childIds.map((cid) => buildNode(cid, new Set(visited))),
    };
  }

  return rootNodes.map((rn) => buildNode(rn.id));
}
