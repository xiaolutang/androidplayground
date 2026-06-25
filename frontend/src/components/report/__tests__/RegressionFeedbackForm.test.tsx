/**
 * RegressionFeedbackForm 单测 — 5 allowed 态显示 / 9 态隐藏
 */

import { describe, it, expect } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegressionFeedbackForm } from '@/components/report/RegressionFeedbackForm';
import type { BugReportStatus } from '@/types/report';

const ALL_14_STATUSES: BugReportStatus[] = [
  'received', 'assessing', 'degraded', 'reproducing',
  'located', 'fixing', 'verified', 'pr_open',
  'draft_pr', 'gap_pending', 'wont_reflow', 'concluded',
  'reflowed', 'reflected',
];

const ALLOWED_5: BugReportStatus[] = [
  'pr_open', 'draft_pr', 'concluded', 'reflected', 'reflowed',
];

function wrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function renderForm(status: BugReportStatus) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <RegressionFeedbackForm reportId="test-report" status={status} />,
    { wrapper: wrapper(client) },
  );
}

describe('RegressionFeedbackForm', () => {
  it('shows form for 5 allowed statuses', () => {
    for (const status of ALLOWED_5) {
      renderForm(status);
      expect(screen.getByText('回归反馈')).toBeInTheDocument();
      cleanup();
    }
  });

  it('hides form for 9 denied statuses (returns null)', () => {
    const denied9 = ALL_14_STATUSES.filter((s) => !ALLOWED_5.includes(s));
    for (const status of denied9) {
      const { container } = renderForm(status);
      // form should not render
      expect(screen.queryByText('回归反馈')).not.toBeInTheDocument();
      // container should be empty (null render)
      expect(container.innerHTML).toBe('');
      cleanup();
    }
  });
});
