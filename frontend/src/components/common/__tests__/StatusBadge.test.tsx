/**
 * StatusBadge 单测 — 14 态渲染 + Tier 1-4
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge } from '@/components/common/StatusBadge';
import { BUG_STATUS_LABEL, TIER_LABEL } from '@/utils/format';
import type { BugReportStatus, Tier } from '@/types/report';

const ALL_14_STATUSES: BugReportStatus[] = [
  'received', 'assessing', 'degraded', 'reproducing',
  'located', 'fixing', 'verified', 'pr_open',
  'draft_pr', 'gap_pending', 'wont_reflow', 'concluded',
  'reflowed', 'reflected',
];

describe('StatusBadge', () => {
  it('renders all 14 statuses', () => {
    for (const status of ALL_14_STATUSES) {
      const { unmount } = render(<StatusBadge status={status} />);
      expect(screen.getByText(BUG_STATUS_LABEL[status])).toBeInTheDocument();
      unmount();
    }
  });

  it('renders all 4 tiers', () => {
    const tiers: Tier[] = [1, 2, 3, 4];
    for (const tier of tiers) {
      const { unmount } = render(<StatusBadge tier={tier} />);
      expect(screen.getByText(TIER_LABEL[tier])).toBeInTheDocument();
      unmount();
    }
  });

  it('renders status + tier together', () => {
    render(<StatusBadge status="verified" tier={1} />);
    expect(screen.getByText(BUG_STATUS_LABEL.verified)).toBeInTheDocument();
    expect(screen.getByText(TIER_LABEL[1])).toBeInTheDocument();
  });

  it('renders nothing when neither status nor tier', () => {
    const { container } = render(<StatusBadge />);
    // Space renders a wrapper div
    expect(container.firstChild).toBeTruthy();
  });

  it('renders null tier as no tag', () => {
    const { container } = render(<StatusBadge status="received" tier={null} />);
    expect(screen.getByText(BUG_STATUS_LABEL.received)).toBeInTheDocument();
    // Should not contain any Tier label
    const tierLabels = container.querySelectorAll('.ant-tag');
    // Only status tag, no tier tag
    expect(tierLabels).toHaveLength(1);
  });
});
