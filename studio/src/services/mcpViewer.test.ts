import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  normalizeMcpUrl,
  loadMcpViewerData,
  formatViewerValue,
} from './mcpViewer';

describe('mcpViewer service', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('normalizes MCP URLs correctly', () => {
    expect(normalizeMcpUrl('http://localhost:8000/')).toBe('http://localhost:8000');
    expect(normalizeMcpUrl('http://localhost:8000/mcp')).toBe('http://localhost:8000');
    expect(normalizeMcpUrl('  http://localhost:8000/mcp/  ')).toBe('http://localhost:8000');
  });

  it('formats viewer values appropriately', () => {
    expect(formatViewerValue('hello world')).toBe('hello world');
    expect(formatViewerValue({ a: 1 })).toBe(JSON.stringify({ a: 1 }, null, 2));
  });

  it('throws error if empty URL is passed', async () => {
    await expect(loadMcpViewerData('')).rejects.toThrow('Enter an MCP server URL.');
  });

  it('successfully loads and aggregates MCP viewer data', async () => {
    const mockHealth = { status: 'healthy', version: '1.0.0' };
    const mockDashboard = { uptime_seconds: 3600 };
    const mockManifest = {
      tools: [{ name: 'crawler', description: 'Web crawler' }],
      capabilities: ['streaming', 'tools'],
      resources: [{ uri: 'file://logs' }],
    };

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (url.includes('/health/summary')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockHealth),
        });
      }
      if (url.includes('/health/dashboard')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockDashboard),
        });
      }
      if (url.includes('/manifest')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockManifest),
        });
      }
      return Promise.resolve({
        ok: false,
        status: 404,
      });
    }) as unknown as typeof fetch;

    const data = await loadMcpViewerData('http://localhost:8000', 'test-token');
    expect(data.health).toEqual(mockHealth);
    expect(data.dashboard).toEqual(mockDashboard);
    expect(data.tools).toHaveLength(1);
    expect(data.resources).toHaveLength(1);
    expect(data.capabilities).toEqual(['streaming', 'tools']);
  });

  it('throws when URL exposes no readable endpoints', async () => {
    global.fetch = vi.fn().mockImplementation(() => {
      const err = new Error('Not found: 404');
      return Promise.reject(err);
    }) as unknown as typeof fetch;

    await expect(loadMcpViewerData('http://localhost:9999')).rejects.toThrow();
  });
});
