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

  it('renders healthy state when the health-aggregation payload succeeds', async () => {
    // Contract aligned with the canonical-endpoint rewrite (ServiceHealthBar
    // fetchPublicHealth + SERVICE_LABEL_MAP): display names come from the
    // check-key label map, not from a per-node `name` field. The old
    // 5-node mock (api/tower/primary/worker + 'API Gateway' labels) asserted
    // a contract the component no longer implements.
    const healthyCheck = { status: 'healthy', message: 'Online', response_time_ms: 5 };
    const mockData = {
      status: 'healthy',
      timestamp: Date.now(),
      total_response_time_ms: 120,
      checks: {
        application: { ...healthyCheck },
        database: { ...healthyCheck, response_time_ms: 12 },
        redis: { ...healthyCheck, response_time_ms: 3 },
        scraper: { ...healthyCheck, response_time_ms: 45 },
        ollama: { ...healthyCheck, response_time_ms: 30 },
        memory: { ...healthyCheck },
        disk: { ...healthyCheck },
        external_services: { ...healthyCheck, response_time_ms: 20 },
        integrations: { ...healthyCheck, response_time_ms: 20 },
      },
      summary: {
        total_checks: 9,
        healthy: 9,
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

    expect(screen.getByText('9/9')).toBeInTheDocument();

    // Click to toggle diagnostics modal — node rows render the
    // SERVICE_LABEL_MAP labels for the aggregation keys.
    const button = screen.getByTitle('Diagnostic Matrix (Click to toggle)');
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText('System Telemetry')).toBeInTheDocument();
      expect(screen.getByText('Backend Core')).toBeInTheDocument();
      expect(screen.getByText('Scraper Service')).toBeInTheDocument();
      expect(screen.getByText('Data Store (Postgres)')).toBeInTheDocument();
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
