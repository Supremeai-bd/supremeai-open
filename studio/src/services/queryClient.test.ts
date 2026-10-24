import { describe, it, expect, vi, beforeEach } from 'vitest';

const { classifyError, smartRetryDecision } = await import('./queryClient');

describe('classifyError', () => {
  it('classifies network errors as retryable', () => {
    expect(classifyError(new Error('fetch failed'))).toEqual({ retryable: true, category: 'network' });
    expect(classifyError(new Error('network unreachable'))).toEqual({ retryable: true, category: 'network' });
  });

  it('classifies auth errors as non-retryable', () => {
    expect(classifyError(new Error('401 unauthorized'))).toEqual({ retryable: false, category: 'auth' });
    expect(classifyError(new Error('forbidden 403'))).toEqual({ retryable: false, category: 'auth' });
  });

  it('classifies rate limit errors as retryable', () => {
    expect(classifyError(new Error('429 too many requests'))).toEqual({ retryable: true, category: 'rate_limit' });
  });

  it('classifies server errors as retryable', () => {
    expect(classifyError(new Error('500 internal'))).toEqual({ retryable: true, category: 'server' });
    expect(classifyError(new Error('502 bad gateway'))).toEqual({ retryable: true, category: 'server' });
    expect(classifyError(new Error('503 unavailable'))).toEqual({ retryable: true, category: 'server' });
  });

  it('classifies client errors as non-retryable', () => {
    expect(classifyError(new Error('400 bad request'))).toEqual({ retryable: false, category: 'client' });
    expect(classifyError(new Error('404 not found'))).toEqual({ retryable: false, category: 'client' });
    expect(classifyError(new Error('422 unprocessable'))).toEqual({ retryable: false, category: 'client' });
  });

  it('reads retryable status from a status field on the error object', () => {
    expect(classifyError({ status: 504 })).toEqual({ retryable: true, category: 'server' });
    expect(classifyError({ status: 422 })).toEqual({ retryable: false, category: 'client' });
  });

  it('defaults unknown errors to retryable/unknown', () => {
    expect(classifyError(new Error('weird'))).toEqual({ retryable: true, category: 'unknown' });
    expect(classifyError('not an error')).toEqual({ retryable: true, category: 'unknown' });
  });
});

describe('smartRetryDecision', () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
    delete (window as unknown as { __VITE_MAX_RETRIES?: string }).__VITE_MAX_RETRIES;
  });

  it('does not retry non-retryable errors', () => {
    expect(smartRetryDecision(0, new Error('401 unauthorized'))).toBe(false);
  });

  it('retries retryable errors below the max', () => {
    expect(smartRetryDecision(2, new Error('fetch failed'))).toBe(true);
  });

  it('stops retrying once the max is reached', () => {
    expect(smartRetryDecision(3, new Error('fetch failed'))).toBe(false);
  });

  it('honors a custom max retries override', () => {
    vi.stubGlobal('window', { ...window, __VITE_MAX_RETRIES: '1' });
    expect(smartRetryDecision(1, new Error('fetch failed'))).toBe(false);
    expect(smartRetryDecision(0, new Error('fetch failed'))).toBe(true);
  });
});
