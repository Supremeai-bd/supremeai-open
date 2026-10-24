import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import { Skills } from './Skills';
import { Providers } from './Providers';
import { MemoryKnowledge } from './MemoryKnowledge';
import * as hooks from '../../data/hooks';

vi.mock('../../data/hooks', () => ({
  useSkills: vi.fn(),
  useProviders: vi.fn(),
  useMemoryStats: vi.fn(),
  useKnowledgeStats: vi.fn(),
  useRouterConfig: vi.fn(),
  useUpdateRules: vi.fn(),
}));

describe('Build Modules Unit Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Skills', () => {
    it('renders loading state when fetching skills', () => {
      vi.mocked(hooks.useSkills).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);

      render(<Skills />);
      expect(screen.getByText('স্কিল লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders skill items properly', () => {
      vi.mocked(hooks.useSkills).mockReturnValue({
        data: [
          { id: '1', name: 'Web Scraper', enabled: true, version: '1.2.0', source: 'registry', installed: true },
          { id: '2', name: 'Code Generator', enabled: false, version: '2.0.0', source: 'local', installed: false },
        ],
        isLoading: false,
      } as any);

      render(<Skills />);
      expect(screen.getByText('Skills Marketplace')).toBeInTheDocument();
      expect(screen.getByText('Web Scraper')).toBeInTheDocument();
      expect(screen.getByText('ENABLED')).toBeInTheDocument();
      expect(screen.getByText('Code Generator')).toBeInTheDocument();
      expect(screen.getByText('DISABLED')).toBeInTheDocument();
      expect(screen.getByText('NOT INSTALLED')).toBeInTheDocument();
    });
  });

  describe('Providers', () => {
    it('renders loading state when fetching providers', () => {
      vi.mocked(hooks.useProviders).mockReturnValue({
        data: undefined,
        isLoading: true,
      } as any);

      render(<Providers />);
      expect(screen.getByText('প্রোভাইডার লোড হচ্ছে...')).toBeInTheDocument();
    });

    it('renders providers list with latency and models', () => {
      vi.mocked(hooks.useProviders).mockReturnValue({
        data: [
          {
            id: 'openai',
            name: 'OpenAI Direct',
            status: 'healthy',
            mode: 'production',
            latency_ms: 120,
            rate_limit_remaining: 950,
            rate_limit_max: 1000,
            models: ['gpt-4o', 'o3-mini'],
            latency_history: [110, 115, 120],
          },
        ],
        isLoading: false,
      } as any);

      render(<Providers />);
      expect(screen.getByText('Providers')).toBeInTheDocument();
      expect(screen.getByText('OpenAI Direct')).toBeInTheDocument();
      expect(screen.getByText('120ms')).toBeInTheDocument();
      expect(screen.getByText('950/1000')).toBeInTheDocument();
      expect(screen.getByText('gpt-4o')).toBeInTheDocument();
    });
  });

  describe('MemoryKnowledge', () => {
    it('renders memory and knowledge stats properly', () => {
      vi.mocked(hooks.useMemoryStats).mockReturnValue({
        data: {
          banks: [
            { name: 'session-store', entry_count: 42, recent_writes: 5 },
          ],
          semantic_cache_hit_rate: 0.88,
          tokens_saved: 125000,
        },
        isLoading: false,
      } as any);
      vi.mocked(hooks.useKnowledgeStats).mockReturnValue({
        data: {
          docs_count: 50,
          rag_index_status: 'indexed',
        },
        isLoading: false,
      } as any);

      render(<MemoryKnowledge />);
      expect(screen.getByText('Memory & Knowledge')).toBeInTheDocument();
      expect(screen.getByText('session-store')).toBeInTheDocument();
      expect(screen.getByText('42 entries')).toBeInTheDocument();
      expect(screen.getByText('88')).toBeInTheDocument();
      expect(screen.getByText('50 docs indexed')).toBeInTheDocument();
    });
  });
});
