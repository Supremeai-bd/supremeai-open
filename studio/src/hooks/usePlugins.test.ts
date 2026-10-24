import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { usePlugins } from './usePlugins';

vi.mock('../utils/api', () => ({
  getApiBaseUrl: vi.fn(() => 'http://localhost:8080'),
}));

// Issue #2522: hook now uses apiClient (get/post/delete) — module mocked here.
const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
  },
}));

describe('usePlugins hook', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches marketplace and installed plugins on mount', async () => {
    const mockMarketplace = [{ id: 'p1', name: 'Plugin 1', description: 'Desc 1', category: 'tools' }];
    const mockInstalled = [{ id: 'i1', plugin_id: 'p1', status: 'active', is_enabled: true }];

    mockGet.mockImplementation((path: string) => {
      if (String(path).includes('/marketplace')) {
        return Promise.resolve({ plugins: mockMarketplace });
      }
      if (String(path).includes('/installed')) {
        return Promise.resolve({ installations: mockInstalled });
      }
      return Promise.reject(new Error('Unknown url'));
    });

    const { result } = renderHook(() => usePlugins());

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.marketplacePlugins).toEqual(mockMarketplace);
    expect(result.current.installedPlugins).toEqual(mockInstalled);
    expect(result.current.error).toBeNull();
  });

  it('handles fetch errors gracefully', async () => {
    mockGet.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => usePlugins());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network error');
  });

  it('installs a plugin successfully and refreshes list', async () => {
    mockPost.mockResolvedValue({ success: true });
    mockGet.mockResolvedValue({ plugins: [], installations: [] });

    const { result } = renderHook(() => usePlugins());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.installPlugin('p1', ['read']);
    });

    expect(mockPost).toHaveBeenCalledWith(
      '/api/v1/plugins/install',
      { plugin_id: 'p1', granted_capabilities: ['read'] }
    );
  });

  it('uninstalls a plugin and refreshes the list', async () => {
    mockDelete.mockResolvedValue(undefined);
    mockGet.mockResolvedValue({ plugins: [], installations: [] });

    const { result } = renderHook(() => usePlugins());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    await act(async () => {
      await result.current.uninstallPlugin('p1');
    });

    expect(mockDelete).toHaveBeenCalledWith('/api/v1/plugins/uninstall/p1');
  });
});
