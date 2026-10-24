import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { CostAuditor } from './CostAuditor';
import { ROISavings } from './ROISavings';
import * as hooks from '../../data/hooks';

vi.mock('../../data/hooks', () => ({
  useCostReport: vi.fn(),
  useBudgetCaps: vi.fn(),
  useROI: vi.fn(),
  useUsage: vi.fn(),
  useUpdateBudgetCap: vi.fn(),
}));

describe('Money Modules Unit Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('CostAuditor', () => {
    it('renders loading state when fetching cost data', () => {
      vi.mocked(hooks.useCostReport).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);
      vi.mocked(hooks.useBudgetCaps).mockReturnValue({
        data: undefined,
        isLoading: false,
      } as any);

      render(<CostAuditor />);
      expect(screen.getByText('কস্ট লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders cost report and budget caps correctly', () => {
      vi.mocked(hooks.useCostReport).mockReturnValue({
        data: {
          report: 'Total spend: $120.50 for all tenants',
          generated_at: '2026-09-11 12:00:00',
        },
        isLoading: false,
      } as any);
      vi.mocked(hooks.useBudgetCaps).mockReturnValue({
        data: {
          default_cap: 500,
          per_tenant: { 'tenant-1': 1000 },
        },
        isLoading: false,
      } as any);

      render(<CostAuditor />);
      expect(screen.getByText('Cost Auditor')).toBeInTheDocument();
      expect(screen.getByText('Total spend: $120.50 for all tenants')).toBeInTheDocument();
      expect(screen.getByText('Generated: 2026-09-11 12:00:00')).toBeInTheDocument();
      expect(screen.getByText('Default cap: $500')).toBeInTheDocument();
      expect(screen.getByText('Per-tenant caps: 1 configured')).toBeInTheDocument();
    });
  });

  describe('ROISavings', () => {
    it('renders loading state when fetching ROI data', () => {
      vi.mocked(hooks.useROI).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);

      render(<ROISavings />);
      expect(screen.getByText('ROI লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders ROI tiles with formatted data', () => {
      vi.mocked(hooks.useROI).mockReturnValue({
        data: {
          semantic_cache_hits: 15420,
          estimated_usd_saved: 420.75,
          duplicate_executions_prevented: 1200,
          api_cost_reduction_ratio: 0.35,
        },
        isLoading: false,
      } as any);

      render(<ROISavings />);
      expect(screen.getByText('ROI Savings')).toBeInTheDocument();
      expect(screen.getByText('CACHE HITS')).toBeInTheDocument();
      expect(screen.getByText('15420')).toBeInTheDocument();
      expect(screen.getByText('USD SAVED')).toBeInTheDocument();
      expect(screen.getByText('PREVENTED')).toBeInTheDocument();
      expect(screen.getByText('COST REDUCTION')).toBeInTheDocument();
      expect(screen.getByText('35')).toBeInTheDocument();
    });
  });
});
