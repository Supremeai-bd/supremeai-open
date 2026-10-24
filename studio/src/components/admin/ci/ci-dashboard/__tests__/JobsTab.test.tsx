// FINAL-TEST: tests for the ci-dashboard JobsTab status filter (the select
// used to be decorative — no state, no filtering).
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { JobsTab } from '../tabs/JobsTab';
import type { CISummaryData } from '../types';

function makeJob(name: string, status: CISummaryData['jobs'][number]['status']) {
  return {
    name,
    status,
    duration: 42,
    error_count: 0,
    warning_count: 0,
  };
}

const data: CISummaryData = {
  version: '2.0',
  timestamp: new Date().toISOString(),
  repository: 'owner/repo',
  run: {
    id: 1,
    number: 1,
    event: 'push',
    branch: 'main',
    commit: { sha: 'abcdef1234567890', message: 'test' },
    triggered_by: 'tester',
    duration_seconds: 120,
  },
  metrics: {
    total_jobs: 3,
    passed: 1,
    failed: 1,
    cancelled: 0,
    skipped: 0,
    success_rate: 33.3,
    score: 50,
    grade: 'F',
    badges: [],
  },
  jobs: [
    makeJob('job-a', 'success'),
    makeJob('job-b', 'failure'),
    makeJob('job-c', 'in_progress'),
  ],
  errors: { total: 0, by_severity: {}, by_category: {}, items: [] },
  warnings: { total: 0, sample: [] },
  insights: [],
  recommendations: [],
};

describe('JobsTab status filter', () => {
  it('renders all jobs by default', () => {
    render(<JobsTab data={data} onJobClick={vi.fn()} />);
    expect(screen.getByText('job-a')).toBeInTheDocument();
    expect(screen.getByText('job-b')).toBeInTheDocument();
    expect(screen.getByText('job-c')).toBeInTheDocument();
  });

  it('filters to failed jobs only', () => {
    render(<JobsTab data={data} onJobClick={vi.fn()} />);
    const select = screen.getByLabelText('Filter jobs by status') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'failed' } });
    expect(select.value).toBe('failed');
    expect(screen.getByText('job-b')).toBeInTheDocument();
    expect(screen.queryByText('job-a')).not.toBeInTheDocument();
    expect(screen.queryByText('job-c')).not.toBeInTheDocument();
  });

  it('filters to passed jobs only', () => {
    render(<JobsTab data={data} onJobClick={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Filter jobs by status'), {
      target: { value: 'passed' },
    });
    expect(screen.getByText('job-a')).toBeInTheDocument();
    expect(screen.queryByText('job-b')).not.toBeInTheDocument();
  });

  it('shows an empty state with reset when nothing matches', () => {
    const emptyData = { ...data, jobs: [makeJob('job-a', 'success')] };
    render(<JobsTab data={emptyData} onJobClick={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Filter jobs by status'), {
      target: { value: 'failed' },
    });
    expect(screen.getByText(/No jobs match/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /reset filter/i }));
    expect(screen.getByText('job-a')).toBeInTheDocument();
  });

  it('shows "in progress" jobs for the in-progress filter', () => {
    render(<JobsTab data={data} onJobClick={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('Filter jobs by status'), {
      target: { value: 'in_progress' },
    });
    expect(screen.getByText('job-c')).toBeInTheDocument();
    expect(screen.queryByText('job-a')).not.toBeInTheDocument();
  });

  it('shows filter counts in the options', () => {
    render(<JobsTab data={data} onJobClick={vi.fn()} />);
    const select = screen.getByLabelText('Filter jobs by status') as HTMLSelectElement;
    const options = within(select).getAllByRole('option') as HTMLOptionElement[];
    expect(options.map((o) => o.textContent)).toContain('Passed Only (1)');
    expect(options.map((o) => o.textContent)).toContain('Failed Only (1)');
  });
});
