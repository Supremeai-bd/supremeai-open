import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../lib/cache.manager', () => ({
  getCacheStats: vi.fn(() => ({ hits: 10, misses: 5 })),
  resetCacheStats: vi.fn(),
}));

import { CostOptimizerService, getCostOptimizer } from './costOptimizer.service';

describe('CostOptimizerService', () => {
  let service: CostOptimizerService;

  beforeEach(() => {
    service = new CostOptimizerService();
    localStorage.clear();
  });

  it('allows requests and reports remaining under the rate limit', () => {
    const res = service.canMakeRequest('/api/test', 'user-1');
    expect(res.allowed).toBe(true);
    expect(res.remaining).toBeGreaterThanOrEqual(0);
    expect(res.retryAfter).toBeUndefined();
  });

  it('blocks requests after exceeding the rate limit', () => {
    const svc = new CostOptimizerService({ rateLimitRequests: 2, rateLimitWindowMs: 60000 });
    svc.canMakeRequest('/x', 'u');
    svc.canMakeRequest('/x', 'u');
    const blocked = svc.canMakeRequest('/x', 'u');
    expect(blocked.allowed).toBe(false);
    expect(blocked.retryAfter).toBeGreaterThan(0);
  });

  it('skips rate limiting when disabled', () => {
    const svc = new CostOptimizerService({ enableRateLimiting: false });
    expect(svc.canMakeRequest('/x', 'u').allowed).toBe(true);
  });

  it('deduplicates identical requests and skips dedup when disabled', async () => {
    const fetchFn = vi.fn(async () => 'data');
    const r1 = await service.deduplicateRequest('req1', fetchFn);
    expect(r1).toBe('data');
    const r2 = await service.deduplicateRequest('req1', fetchFn);
    expect(r2).toBe('data');
    expect(fetchFn).toHaveBeenCalledTimes(1);

    const svc2 = new CostOptimizerService({ enableDeduplication: false });
    const fetch2 = vi.fn(async () => 'd2');
    await svc2.deduplicateRequest('req2', fetch2);
    await svc2.deduplicateRequest('req2', fetch2);
    expect(fetch2).toHaveBeenCalledTimes(2);
  });

  it('validates payload size against the configured max', () => {
    expect(service.validatePayloadSize('small').valid).toBe(true);
    const big = service.validatePayloadSize('x'.repeat(2 * 1024 * 1024));
    expect(big.valid).toBe(false);
    expect(big.maxSize).toBe(1024 * 1024);
  });

  it('returns the correct cache TTL per path type', () => {
    expect(service.getCacheTTLForPath('/api/ai/generate')).toBe(60);
    expect(service.getCacheTTLForPath('/api/foo')).toBe(300);
    expect(service.getCacheTTLForPath('/static/app.js')).toBe(3600);
  });

  it('produces an optimization report derived from cache stats', () => {
    const report = service.getOptimizationReport();
    expect(report.config).toBeDefined();
    expect(report.cacheStats).toEqual({ hits: 10, misses: 5 });
    expect(report.savings).toHaveProperty('estimatedRequestsSaved');
    expect(report.savings).toHaveProperty('estimatedCostSaved');
  });

  it('resets all optimization state without throwing', () => {
    expect(() => service.resetAll()).not.toThrow();
  });

  it('getCostOptimizer returns a singleton instance', () => {
    expect(getCostOptimizer()).toBe(getCostOptimizer());
  });

  it('computes distinct hashes for distinct data', () => {
    const h1 = (service as unknown as { deduplicator: { getHash: (s: string) => string } }).deduplicator.getHash('a');
    const h2 = (service as unknown as { deduplicator: { getHash: (s: string) => string } }).deduplicator.getHash('b');
    expect(h1).not.toBe(h2);
  });
});
