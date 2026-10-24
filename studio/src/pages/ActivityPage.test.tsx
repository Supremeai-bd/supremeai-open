import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/activityService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/activityService')>();
  return { ...actual, activityService: { listActivity: vi.fn() } };
});

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { ActivityPage } from './ActivityPage';
import { activityService } from '../services/activityService';

const mockedService = activityService as unknown as {
  listActivity: ReturnType<typeof vi.fn>;
};

const sampleMission = {
  id: 'm1',
  title: 'Ship pricing page',
  goal_text: 'Launch the new pricing page.',
  state: 'running' as const,
  priority: 5,
  current_phase: 1,
  phases: [
    { name: 'Draft', status: 'done', note: '' },
    { name: 'Review', status: 'pending', note: '' },
  ],
  agent_id: null,
  failure_reason: null,
  repair_count: 0,
  created_at: '2026-09-16T08:00:00Z',
  updated_at: '2026-09-16T09:30:00Z',
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <ActivityPage />
    </MemoryRouter>,
  );

describe('ActivityPage (ERR-B03)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.listActivity.mockResolvedValue({
      items: [],
      count: 0,
      skip: 0,
      limit: 50,
    });
  });

  it('renders empty state when no missions exist', async () => {
    renderPage();
    expect(await screen.findByTestId('activity-empty')).toBeInTheDocument();
    expect(mockedService.listActivity).toHaveBeenCalledWith({ state: undefined, limit: 50 });
  });

  it('renders the real mission timeline with state badge and phase progress', async () => {
    mockedService.listActivity.mockResolvedValue({
      items: [sampleMission],
      count: 1,
      skip: 0,
      limit: 50,
    });
    renderPage();
    expect(await screen.findByTestId('activity-event')).toBeInTheDocument();
    expect(screen.getByText('Ship pricing page')).toBeInTheDocument();
    expect(screen.getByTestId('activity-state-m1')).toHaveTextContent('Running');
    expect(screen.getByText('Phases: 1/2 (1 done)')).toBeInTheDocument();
  });

  it('filters by state via chips and refetches', async () => {
    renderPage();
    await screen.findByTestId('activity-empty');
    await userEvent.click(screen.getByTestId('activity-filter-failed'));
    await waitFor(() => {
      expect(mockedService.listActivity).toHaveBeenLastCalledWith({
        state: 'failed',
        limit: 50,
      });
    });
  });

  it('shows failure reason and repair count when present', async () => {
    mockedService.listActivity.mockResolvedValue({
      items: [
        {
          ...sampleMission,
          id: 'm2',
          state: 'failed' as const,
          failure_reason: 'Phase 2 assertion timeout',
          repair_count: 2,
        },
      ],
      count: 1,
      skip: 0,
      limit: 50,
    });
    renderPage();
    expect(await screen.findByTestId('activity-event')).toBeInTheDocument();
    expect(screen.getByText(/Failure reason: Phase 2 assertion timeout/)).toBeInTheDocument();
    expect(screen.getByText(/2 repairs/)).toBeInTheDocument();
  });

  it('shows an honest error state when loading fails', async () => {
    mockedService.listActivity.mockRejectedValue(new Error('event bus unreachable'));
    renderPage();
    expect(await screen.findByTestId('activity-error')).toBeInTheDocument();
    expect(screen.getByText('event bus unreachable')).toBeInTheDocument();
  });

  it('refresh button refetches current filter', async () => {
    renderPage();
    await screen.findByTestId('activity-empty');
    await userEvent.click(screen.getByTestId('activity-refresh-btn'));
    await waitFor(() => {
      expect(mockedService.listActivity.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });
});
