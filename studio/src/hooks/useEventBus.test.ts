/**
 * Tests for useEventBus hook — event bus pub/sub pattern.
 */
import { describe, it, expect } from 'vitest';

describe('useEventBus', () => {
  it('should be importable', async () => {
    const mod = await import('./useEventBus');
    expect(mod).toBeDefined();
  });

  it('should export a hook function', async () => {
    const mod = await import('./useEventBus');
    const fn = mod.useEventBus || mod.default;
    expect(typeof fn).toBe('function');
  });
});
