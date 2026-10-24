import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getDeviceFingerprint } from './deviceFingerprint';

describe('getDeviceFingerprint', () => {
  beforeEach(() => {
    // Reset any internal state if possible, though since cachedFingerprint is local we might just test idempotency
  });

  it('computes a stable fingerprint string', async () => {
    // Mock crypto.subtle.digest if not present in vitest/jsdom environment
    if (!window.crypto) {
      Object.defineProperty(window, 'crypto', { value: { subtle: {} } });
    }
    const cryptoObject = window.crypto as Crypto & { subtle: SubtleCrypto };
    Object.defineProperty(cryptoObject, 'subtle', { configurable: true, value: { digest: vi.fn().mockResolvedValue(new ArrayBuffer(32)) } });

    const fp1 = await getDeviceFingerprint();
    expect(fp1).toBeTypeOf('string');
    expect(fp1.length).toBeGreaterThan(0);

    // It should cache the result and return the same fingerprint
    const fp2 = await getDeviceFingerprint();
    expect(fp1).toBe(fp2);
  });
});
