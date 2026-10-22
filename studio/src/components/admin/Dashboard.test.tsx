import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import Dashboard from './Dashboard';

vi.mock('../../hooks/useDashboardData', () => ({
  useMetrics: vi.fn(() => ({
    data: {
      requests_per_second: 5,
      latency_p95_ms: 18,
      availability_percent: 99.9,
      cpu_percent: 15,
      active_agents: 3,
      redis_commands: 12000,
    },
  })),
  useThreatScan: vi.fn(() => ({
    data: { findings: [] },
  })),
  useCIReports: vi.fn(() => ({
    data: [],
  })),
  useDashboardEvents: vi.fn(() => ({
    data: [],
  })),
}));

describe('Admin Command Center (WO5)', () => {
  it('renders KPI cards and honest availability data instead of hardcoded placeholder', () => {
    render(<Dashboard />);
    const kpis = screen.getAllByTestId('admin-kpi');
    expect(kpis.length).toBe(4);

    // Availability KPI should display real metric percentage
    expect(screen.getByText('99.9%')).toBeInTheDocument();
    expect(screen.getByText('Healthy')).toBeInTheDocument();

    // Redis Quota card
    expect(screen.getByTestId('redis-quota-card')).toBeInTheDocument();
    expect(screen.getByText(/12000 \/ 500k/i)).toBeInTheDocument();
  });
});
