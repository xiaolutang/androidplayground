/**
 * treeBuilder.ts 单测 — buildHypothesisTree
 *
 * 覆盖：空数组、扁平→树、parent_id 链、孤立节点、深层嵌套、大量节点
 */

import { describe, it, expect } from 'vitest';
import { buildHypothesisTree } from '@/utils/treeBuilder';
import type { Hypothesis } from '@/types/report';

function makeHypothesis(
  id: string,
  parentId: string | null,
  text: string = `H-${id}`,
): Hypothesis {
  return {
    id,
    parent_id: parentId,
    hypothesis_text: text,
    expected_signal: '',
    status: 'proposed',
    falsifying_signal: null,
    overturning_signal: null,
    is_rootcause: parentId === null,
    step_budget: 10,
    step_used: 0,
  };
}

describe('buildHypothesisTree', () => {
  it('returns empty array for empty input', () => {
    expect(buildHypothesisTree([])).toEqual([]);
  });

  it('returns empty array for null input', () => {
    expect(buildHypothesisTree(null as unknown as Hypothesis[])).toEqual([]);
  });

  it('builds single root node', () => {
    const h = makeHypothesis('h1', null);
    const tree = buildHypothesisTree([h]);
    expect(tree).toHaveLength(1);
    expect(tree[0]!.key).toBe('h1');
    expect(tree[0]!.children).toEqual([]);
  });

  it('builds parent-child chain', () => {
    const hypotheses = [
      makeHypothesis('h1', null),
      makeHypothesis('h2', 'h1'),
      makeHypothesis('h3', 'h2'),
    ];
    const tree = buildHypothesisTree(hypotheses);
    expect(tree).toHaveLength(1);
    expect(tree[0]!.key).toBe('h1');
    expect(tree[0]!.children).toHaveLength(1);
    expect(tree[0]!.children[0]!.key).toBe('h2');
    expect(tree[0]!.children[0]!.children).toHaveLength(1);
    expect(tree[0]!.children[0]!.children[0]!.key).toBe('h3');
  });

  it('builds multiple roots', () => {
    const hypotheses = [
      makeHypothesis('h1', null),
      makeHypothesis('h2', null),
      makeHypothesis('h3', 'h1'),
    ];
    const tree = buildHypothesisTree(hypotheses);
    expect(tree).toHaveLength(2);
    expect(tree[0]!.key).toBe('h1');
    expect(tree[0]!.children).toHaveLength(1);
    expect(tree[1]!.key).toBe('h2');
    expect(tree[1]!.children).toEqual([]);
  });

  it('handles orphan nodes (parent not found)', () => {
    // h2's parent_id points to non-existent 'hX'
    // h2 should not appear in any root tree
    const hypotheses = [
      makeHypothesis('h1', null),
      makeHypothesis('h2', 'hX'),
    ];
    const tree = buildHypothesisTree(hypotheses);
    // Only h1 is a root (parent_id=null)
    expect(tree).toHaveLength(1);
    expect(tree[0]!.key).toBe('h1');
    expect(tree[0]!.children).toEqual([]);
    // h2 is an orphan — only appears under childrenMap['hX'], not reachable from root
  });

  it('preserves hypothesis data in node', () => {
    const h: Hypothesis = {
      id: 'h1',
      parent_id: null,
      hypothesis_text: '内存泄漏',
      expected_signal: 'heap grows',
      status: 'confirmed',
      falsifying_signal: null,
      overturning_signal: null,
      is_rootcause: true,
      step_budget: 20,
      step_used: 5,
    };
    const tree = buildHypothesisTree([h]);
    expect(tree[0]!.hypothesis).toEqual(h);
    expect(tree[0]!.title).toBe('内存泄漏');
  });

  it('supports 10-level deep nesting', () => {
    const hypotheses: Hypothesis[] = [];
    hypotheses.push(makeHypothesis('h0', null));
    for (let i = 1; i <= 10; i++) {
      hypotheses.push(makeHypothesis(`h${i}`, `h${i - 1}`));
    }
    const tree = buildHypothesisTree(hypotheses);

    // Walk the tree to depth 10
    let node = tree[0]!;
    expect(node.key).toBe('h0');
    for (let depth = 1; depth <= 10; depth++) {
      expect(node.children).toHaveLength(1);
      node = node.children[0]!;
      expect(node.key).toBe(`h${depth}`);
    }
    expect(node.children).toEqual([]);
  });

  it('supports 100+ nodes', () => {
    const hypotheses: Hypothesis[] = [];
    // 1 root with 99 children
    hypotheses.push(makeHypothesis('root', null));
    for (let i = 1; i <= 99; i++) {
      hypotheses.push(makeHypothesis(`child-${i}`, 'root'));
    }
    const tree = buildHypothesisTree(hypotheses);
    expect(tree).toHaveLength(1);
    expect(tree[0]!.key).toBe('root');
    expect(tree[0]!.children).toHaveLength(99);
  });

  it('handles sibling groups', () => {
    const hypotheses = [
      makeHypothesis('root', null),
      makeHypothesis('a', 'root'),
      makeHypothesis('b', 'root'),
      makeHypothesis('c', 'root'),
      makeHypothesis('a1', 'a'),
      makeHypothesis('a2', 'a'),
    ];
    const tree = buildHypothesisTree(hypotheses);
    expect(tree).toHaveLength(1);
    const root = tree[0]!;
    expect(root.children).toHaveLength(3);
    const aNode = root.children.find((c) => c.key === 'a');
    expect(aNode).toBeDefined();
    expect(aNode!.children).toHaveLength(2);
  });
});
