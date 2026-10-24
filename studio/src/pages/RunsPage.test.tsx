import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../services/runService', () => ({
  runService: {
    listRuns: vi.fn(),
    getTrace: vi.fn(),
    repairRun: vi.fn(),
    cancelRun: vi.fn(),
    startRun: vi.fn(),
  },
}));

// বাংলা: WorkspaceLayout (UnifiedAppShell) ভারী — পেজ লজিক টেস্টে হালকা stub।
vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import { RunsPage } from './RunsPage';
import { runService } from '../services/runService';

const mockedService = runService as unknown as {
  listRuns: ReturnType<typeof vi.fn>;
  getTrace: ReturnType<typeof vi.fn>;
  repairRun: ReturnType<typeof vi.fn>;
  cancelRun: ReturnType<typeof vi.fn>;
  startRun: ReturnType<typeof vi.fn>;
};

const failedRun = {
  id: 'r1',
  title: 'Deploy pricing API',
  goal_text: 'Ship it.',
  state: 'failed',
  priority: 5,
  current_phase: 2,
  phases: [
    { name: 'Build', status: 'done', note: '' },
    { name: 'Deploy', status: 'failed', note: '' },
  ],
  agent_id: null,
  failure_reason: 'Phase 2 assertion timeout',
  repair_count: 0,
  created_at: '2026-09-16T08:00:00Z',
  updated_at: '2026-09-16T09:30:00Z',
};

const renderPage = () =>
  render(
    <MemoryRouter>
      <RunsPage />
    </MemoryRouter>,
  );

describe('RunsPage (ERR-B04)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedService.listRuns.mockResolvedValue({
      items: [],
      count: 0,
      skip: 0,
      limit: 50,
    });
    mockedService.getTrace.mockResolvedValue({
      items: [
        {
          id: 't1',
          mission_id: 'r1',
          seq: 1,
          phase: 0,
          event: 'mission_created',
          detail: null,
          created_at: '2026-09-16T08:00:00Z',
        },
      ],
      count: 1,
      mission_id: 'r1',
    });
  });

  it('renders empty state when no runs exist', async () => {
    renderPage();
    expect(await screen.findByTestId('runs-empty')).toBeInTheDocument();
  });

  it('lists runs with state badge and retry action for failed runs', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [failedRun],
      count: 1,
      skip: 0,
      limit: 50,
    });
    renderPage();
    expect(await screen.findByTestId('run-card')).toBeInTheDocument();
    expect(screen.getByText('Deploy pricing API')).toBeInTheDocument();
    expect(screen.getByTestId('run-state-r1')).toHaveTextContent('failed');
    expect(screen.getByTestId('run-retry-btn-r1')).toBeInTheDocument();
    expect(screen.getByText(/Failure reason: Phase 2 assertion timeout/)).toBeInTheDocument();
  });

  it('expands the step observer and shows trace events', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [failedRun],
      count: 1,
      skip: 0,
      limit: 50,
    });
    renderPage();
    await screen.findByTestId('run-card');

    await userEvent.click(screen.getByTestId('run-expand-btn-r1'));
    expect(screen.getByTestId('run-trace-r1')).toBeInTheDocument();
    expect(mockedService.getTrace).toHaveBeenCalledWith('r1');
    expect(await screen.findByTestId('trace-event')).toBeInTheDocument();
    expect(screen.getByText('mission_created')).toBeInTheDocument();
  });

  it('retry calls repair and refetches the run list', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [failedRun],
      count: 1,
      skip: 0,
      limit: 50,
    });
    mockedService.repairRun.mockResolvedValue({ ...failedRun, state: 'repairing' });
    renderPage();
    await screen.findByTestId('run-card');

    await userEvent.click(screen.getByTestId('run-retry-btn-r1'));
    await waitFor(() => {
      expect(mockedService.repairRun).toHaveBeenCalledWith('r1');
    });
    await waitFor(() => {
      expect(mockedService.listRuns.mock.calls.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('surfaces backend transition errors verbatim', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [failedRun],
      count: 1,
      skip: 0,
      limit: 50,
    });
    mockedService.repairRun.mockRejectedValue(
      new Error('illegal transition: failed is terminal'),
    );
    renderPage();
    await screen.findByTestId('run-card');

    await userEvent.click(screen.getByTestId('run-retry-btn-r1'));
    expect(await screen.findByTestId('runs-action-error')).toBeInTheDocument();
    expect(screen.getByText(/illegal transition/)).toBeInTheDocument();
  });

  it('offers start for approved runs and cancel for running ones', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [
        { ...failedRun, id: 'r2', state: 'approved', failure_reason: null },
        { ...failedRun, id: 'r3', state: 'running', failure_reason: null },
      ],
      count: 2,
      skip: 0,
      limit: 50,
    });
    renderPage();
    expect(await screen.findByTestId('run-start-btn-r2')).toBeInTheDocument();
    expect(screen.getByTestId('run-cancel-btn-r3')).toBeInTheDocument();
    expect(screen.queryByTestId('run-retry-btn-r2')).not.toBeInTheDocument();
  });

  it('cancels a run only after the 2s hold-to-confirm gesture (Task-12)', async () => {
    mockedService.listRuns.mockResolvedValue({
      items: [{ ...failedRun, id: 'r3', state: 'running', failure_reason: null }],
      count: 1,
      skip: 0,
      limit: 50,
    });
    renderPage();
    const cancelBtn = await screen.findByTestId('run-cancel-btn-r3');

    // বাংলা: এক ক্লিকে (pointerdown+pointerup) hold বাতিল হয় — cancel হবে না।
    await userEvent.click(cancelBtn);
    expect(mockedService.cancelRun).not.toHaveBeenCalled();

    // বাংলা: pointerdown ধরে রাখা → ২ সেকেন্ডের fill transition শেষ (transitionEnd)
    // → তখনই একবার cancelRun কল হবে (hold-to-confirm contract)।
    fireEvent.pointerDown(cancelBtn);
    fireEvent.transitionEnd(screen.getByTestId('run-cancel-btn-r3-fill'));
    await waitFor(() => expect(mockedService.cancelRun).toHaveBeenCalledWith('r3'));
    expect(mockedService.cancelRun).toHaveBeenCalledTimes(1);
  });

  it('shows an honest error state when loading fails', async () => {
    mockedService.listRuns.mockRejectedValue(new Error('observer offline'));
    renderPage();
    expect(await screen.findByTestId('runs-error')).toBeInTheDocument();
    expect(screen.getByText('observer offline')).toBeInTheDocument();
  });
});
