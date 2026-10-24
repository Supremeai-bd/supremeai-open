import { describe, it, expect, vi, afterEach } from 'vitest';
import { setDesktopPrompt, apiCall, platform } from './supremeShared';

describe('supremeShared', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('exposes the electron platform object', () => {
    expect(platform).toBeDefined();
  });

  it('setDesktopPrompt does not throw', () => {
    expect(() => setDesktopPrompt({ title: 'Bind', fields: [] } as unknown as Parameters<typeof setDesktopPrompt>[0])).not.toThrow();
  });

  it('apiCall falls back to fetch when no desktop API', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetchMock);

    const res = await apiCall({ endpoint: '/api/v1/x', method: 'POST', body: { a: 1 } });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/x'),
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ a: 1 }) })
    );
    expect(res.ok).toBe(true);
    expect(res.data).toEqual({ ok: true });
  });
});
