/**
 * Tests for useDashboardData hook — dashboard data fetching.
 */
import { describe, it, expect } from 'vitest';

describe('useDashboardData', () => {
  it('should be importable', async () => {
    const mod = await import('./useDashboardData');
    expect(mod).toBeDefined();
  });

  it('should export a hook function', async () => {
    const mod = await import('./useDashboardData');
    const fn = mod.useDashboardData;
    expect(typeof fn).toBe('function');
  });
});
