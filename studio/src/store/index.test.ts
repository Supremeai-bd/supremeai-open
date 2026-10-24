import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { isUnifiedStoreEnabled, tryEnableUnifiedStore, disableUnifiedStore } from './index';

vi.mock('./unifiedStore', () => ({
  useUnifiedStore: {
    getState: () => ({ auth: {}, chat: {}, workspace: {}, theme: {}, admin: {} }),
  },
}));

describe('store/index — unified store flag', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('is disabled by default', () => {
    expect(isUnifiedStoreEnabled()).toBe(false);
  });

  it('is enabled when localStorage flag is set', () => {
    window.localStorage.setItem('UNIFIED_STORE', 'true');
    expect(isUnifiedStoreEnabled()).toBe(true);
  });

  it('tryEnableUnifiedStore flips the flag and returns true when slices present', async () => {
    const result = await tryEnableUnifiedStore();
    expect(result).toBe(true);
    expect(window.localStorage.getItem('UNIFIED_STORE')).toBe('true');
  });

  it('disableUnifiedStore removes the flag', () => {
    window.localStorage.setItem('UNIFIED_STORE', 'true');
    disableUnifiedStore();
    expect(window.localStorage.getItem('UNIFIED_STORE')).toBeNull();
  });
});
