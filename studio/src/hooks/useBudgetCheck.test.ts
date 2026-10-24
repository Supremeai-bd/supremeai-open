/**
 * Tests for useBudgetCheck hook — budget/quota checking.
 */
import { describe, it, expect } from 'vitest';

describe('useBudgetCheck', () => {
  it('should be importable', async () => {
    const mod = await import('./useBudgetCheck');
    expect(mod).toBeDefined();
  });

  it('should export a hook function', async () => {
    const mod = await import('./useBudgetCheck');
    const fn = mod.useBudgetCheck;
    expect(typeof fn).toBe('function');
  });
});
