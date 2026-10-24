import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { HealthMap } from './HealthMap';
import { EventsExplorer } from './EventsExplorer';
import * as hooks from '../../data/hooks';

vi.mock('../../data/hooks', () => ({
  useHealthMap: vi.fn(),
  useDashboardEvents: vi.fn(),
  useMetrics: vi.fn(),
  useTraffic: vi.fn(),
}));

describe('Observe Modules Unit Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('HealthMap', () => {
    it('renders loading state when fetching health map', () => {
      vi.mocked(hooks.useHealthMap).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);

      render(<HealthMap />);
      expect(screen.getByText('হেল্থ ম্যাপ লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders nodes with health status and latencies', () => {
      vi.mocked(hooks.useHealthMap).mockReturnValue({
        data: {
          overall_health_percent: 98,
          gcp: { status: 'healthy', latency: 45 },
          railway: { status: 'healthy', latency: 50 },
          render: { status: 'healthy', latency: 60 },
          core_services: {
            auth: { status: 'healthy', latency: 20 },
            database: { status: 'healthy', latency: 15 },
          },
        },
        isLoading: false,
      } as any);

      render(<HealthMap />);
      expect(screen.getByText('Health Map')).toBeInTheDocument();
      expect(screen.getByText('GCP')).toBeInTheDocument();
      expect(screen.getByText('RAILWAY')).toBeInTheDocument();
      expect(screen.getByText('RENDER')).toBeInTheDocument();
      expect(screen.getByText('AUTH')).toBeInTheDocument();
      expect(screen.getByText('DATABASE')).toBeInTheDocument();
    });
  });

  describe('EventsExplorer', () => {
    it('renders loading state when fetching events', () => {
      vi.mocked(hooks.useDashboardEvents).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);

      render(<EventsExplorer />);
      expect(screen.getByText('ইভেন্ট লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders events timeline', () => {
      vi.mocked(hooks.useDashboardEvents).mockReturnValue({
        data: [
          {
            timestamp: '2026-09-11T12:00:00Z',
            source: 'auth',
            type: 'login',
            title: 'User logged in',
            message: 'User admin logged in successfully',
            level: 'info',
          },
        ],
        isLoading: false,
      } as any);

      render(<EventsExplorer />);
      expect(screen.getByText('Events Explorer')).toBeInTheDocument();
      expect(screen.getByText('User admin logged in successfully')).toBeInTheDocument();
    });
  });
});
