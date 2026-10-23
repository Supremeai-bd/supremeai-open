import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import React from 'react';
import { ServiceHealthBar } from './ServiceHealthBar';

vi.mock('../../utils/api', () => ({
  getApiBaseUrl: vi.fn(() => 'https://supremeai-api-ulw0.onrender.com'),
}));

describe('ServiceHealthBar component', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.clearAllMocks();
  });

  const renderComponent = (customClient?: QueryClient) =>
    render(
      <QueryClientProvider client={customClient || queryClient}>
        <ServiceHealthBar />
      </QueryClientProvider>
    );

  it('renders loading state initially', () => {
    global.fetch = vi.fn(() => new Promise(() => {})) as any;
    renderComponent();
    expect(screen.getByText('Connecting to Node...')).toBeInTheDocument();
  });

  it('renders healthy state when 5-node API succeeds', async () => {
    const mockData = {
      status: 'healthy',
      timestamp: Date.now(),
      total_response_time_ms: 120,
      checks: {
        api: { name: 'API Gateway', status: 'healthy', message: 'Online', response_time_ms: 5 },
        scraper: { name: 'Scraper Relay', status: 'healthy', message: 'Online', response_time_ms: 45 },
        tower: { name: 'MCP Control Tower', status: 'healthy', message: 'Online', response_time_ms: 30 },
        primary: { name: 'Primary Core Node', status: 'healthy', message: 'Online', response_time_ms: 20 },
        worker: { name: 'Worker Node', status: 'healthy', message: 'Online', response_time_ms: 20 },
      },
      summary: {
        total_checks: 5,
        healthy: 5,
        degraded: 0,
        unhealthy: 0,
        unknown: 0,
      },
    };

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        headers: { get: () => 'application/json' },
        text: async () => JSON.stringify(mockData),
      })
    ) as any;

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Network Optimal')).toBeInTheDocument();
    });

    expect(screen.getByText('5/5')).toBeInTheDocument();

    // Click to toggle diagnostics modal
    const button = screen.getByTitle('Diagnostic Matrix (Click to toggle)');
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('System Telemetry')).toBeInTheDocument();
      expect(screen.getByText('API Gateway')).toBeInTheDocument();
      expect(screen.getByText('Scraper Relay')).toBeInTheDocument();
    });
  });

  it('renders fallback label on error', async () => {
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        url: 'https://supremeai-api-ulw0.onrender.com/api/health-aggregation',
        headers: { get: () => 'application/json' },
        text: async () => 'Internal Error',
      })
    ) as any;

    const errorClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: 0,
        },
      },
    });

    renderComponent(errorClient);

    await waitFor(() => {
      expect(screen.getByText('Sync Pending')).toBeInTheDocument();
    });
  });
});
