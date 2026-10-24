import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { CommandDeck } from './CommandDeck';
import * as hooks from '../../data/hooks';

vi.mock('../../data/hooks', () => ({
  useMetrics: vi.fn(),
  useHealthMap: vi.fn(),
  useCIReports: vi.fn(),
  useDashboardEvents: vi.fn(),
  useProviders: vi.fn(),
  useTraffic: vi.fn(),
  useDeployGate: vi.fn(),
  useDeploy: vi.fn(() => ({ mutate: vi.fn() })),
  useCreateBackup: vi.fn(() => ({ mutate: vi.fn() })),
  useSecurityRescan: vi.fn(() => ({ mutate: vi.fn() })),
  useToggleDeployGate: vi.fn(() => ({ mutate: vi.fn() })),
  useAcknowledgeAlert: vi.fn(() => ({ mutate: vi.fn() })),
}));

vi.mock('./InfraTopology', () => ({
  InfraTopology: () => <div data-testid="infra-topology">Infra Topology Map</div>,
}));

describe('CommandDeck Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state when metrics are loading', () => {
    vi.mocked(hooks.useMetrics).mockReturnValue({
      data: undefined,
      isLoading: true,
    } as any);
    vi.mocked(hooks.useHealthMap).mockReturnValue({ data: undefined } as any);
    vi.mocked(hooks.useCIReports).mockReturnValue({ data: undefined } as any);
    vi.mocked(hooks.useDashboardEvents).mockReturnValue({ data: undefined } as any);
    vi.mocked(hooks.useProviders).mockReturnValue({ data: undefined } as any);
    vi.mocked(hooks.useTraffic).mockReturnValue({ data: undefined } as any);
    vi.mocked(hooks.useDeployGate).mockReturnValue({ data: undefined } as any);

    render(<CommandDeck />);
    expect(screen.getByText('কমান্ড ডেক লোড হচ্ছে...')).toBeInTheDocument();
  });

  it('renders main dashboard sections when data is available', () => {
    vi.mocked(hooks.useMetrics).mockReturnValue({
      data: {
        cpu_usage_percent: 24,
        memory_usage_percent: 45,
        requests_per_second: 150,
        total_requests_24h: 35000,
        error_rate: 0.1,
        model_call_distribution: { 'gpt-4o': 80, 'gemini-2.0': 20 },
      },
      isLoading: false,
    } as any);
    vi.mocked(hooks.useHealthMap).mockReturnValue({
      data: { overall_health_percent: 99 },
    } as any);
    vi.mocked(hooks.useCIReports).mockReturnValue({
      data: [],
    } as any);
    vi.mocked(hooks.useDashboardEvents).mockReturnValue({
      data: [
        { level: 'critical', message: 'Database connection pool spike' },
      ],
    } as any);
    vi.mocked(hooks.useProviders).mockReturnValue({ data: [] } as any);
    vi.mocked(hooks.useTraffic).mockReturnValue({ data: { hourly: [] } } as any);
    vi.mocked(hooks.useDeployGate).mockReturnValue({ data: { status: 'OPEN' } } as any);

    render(<CommandDeck />);
    expect(screen.getAllByText('Database connection pool spike').length).toBeGreaterThan(0);
    expect(screen.getByText('ডিপ্লয়')).toBeInTheDocument();
    expect(screen.getByText('ব্যাকআপ')).toBeInTheDocument();
    expect(screen.getByText('সিকিউরিটি স্ক্যান')).toBeInTheDocument();
    expect(screen.getByText('গেট লক')).toBeInTheDocument();
    expect(screen.getByTestId('infra-topology')).toBeInTheDocument();
  });
});
