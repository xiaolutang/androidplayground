/**
 * HypothesisTree 单测 — 四态三色映射 + refuted 保留可见
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HypothesisTree } from '@/components/report/HypothesisTree';
import { HYPOTHESIS_STATUS_LABEL } from '@/utils/format';
import type { Hypothesis } from '@/types/report';

function makeHypothesis(
  id: string,
  status: Hypothesis['status'],
  text: string = `假设-${id}`,
  parentId: string | null = null,
): Hypothesis {
  return {
    id,
    parent_id: parentId,
    hypothesis_text: text,
    expected_signal: '',
    status,
    falsifying_signal: null,
    overturning_signal: null,
    is_rootcause: parentId === null,
    step_budget: 10,
    step_used: 3,
  };
}

describe('HypothesisTree', () => {
  it('renders empty message for empty hypotheses', () => {
    render(<HypothesisTree hypotheses={[]} />);
    expect(screen.getByText('暂无假设数据')).toBeInTheDocument();
  });

  it('renders all four statuses', () => {
    const hypotheses: Hypothesis[] = [
      makeHypothesis('h1', 'proposed', '假设A'),
      makeHypothesis('h2', 'verifying', '假设B'),
      makeHypothesis('h3', 'confirmed', '假设C'),
      makeHypothesis('h4', 'refuted', '假设D'),
    ];

    render(<HypothesisTree hypotheses={hypotheses} />);

    // 所有四态标签都可见
    expect(screen.getByText(HYPOTHESIS_STATUS_LABEL.proposed)).toBeInTheDocument();
    expect(screen.getByText(HYPOTHESIS_STATUS_LABEL.verifying)).toBeInTheDocument();
    expect(screen.getByText(HYPOTHESIS_STATUS_LABEL.confirmed)).toBeInTheDocument();
    expect(screen.getByText(HYPOTHESIS_STATUS_LABEL.refuted)).toBeInTheDocument();
  });

  it('keeps refuted nodes visible (INV-2 negative knowledge)', () => {
    const hypotheses: Hypothesis[] = [
      makeHypothesis('h1', 'confirmed', '确认假设'),
      makeHypothesis('h2', 'refuted', '证伪假设'),
    ];

    render(<HypothesisTree hypotheses={hypotheses} />);

    // refuted 节点文本可见
    expect(screen.getByText('证伪假设')).toBeInTheDocument();
    expect(screen.getByText(HYPOTHESIS_STATUS_LABEL.refuted)).toBeInTheDocument();
  });

  it('shows rootcause tag for is_rootcause', () => {
    const hypotheses: Hypothesis[] = [
      makeHypothesis('h1', 'confirmed', '根因假设'),
    ];
    hypotheses[0]!.is_rootcause = true;

    render(<HypothesisTree hypotheses={hypotheses} />);
    expect(screen.getByText('根因')).toBeInTheDocument();
  });

  it('shows step usage', () => {
    const hypotheses: Hypothesis[] = [
      makeHypothesis('h1', 'proposed', '步骤假设'),
    ];

    render(<HypothesisTree hypotheses={hypotheses} />);
    expect(screen.getByText('3/10 步')).toBeInTheDocument();
  });
});
