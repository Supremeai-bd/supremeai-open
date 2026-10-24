import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { startAntiSleepHeartbeat } from './heartbeat';

// Issue #2522: heartbeat now probes via apiClient.get — module mocked here.
const { mockGet } = vi.hoisted(() => ({ mockGet: vi.fn() }));
vi.mock('./apiClient', () => ({
  apiClient: { get: (...args: unknown[]) => mockGet(...args) },
}));

describe('heartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns timeout and interval ids', () => {
    const result = startAntiSleepHeartbeat();
    expect(result.timeoutId).toBeDefined();
    expect(result.intervalId).toBeDefined();
  });

  it('pings the health endpoint on schedule', async () => {
    mockGet.mockResolvedValue({ status: 'ok' });

    startAntiSleepHeartbeat();
    expect(mockGet).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(10_000);
    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/live',
      expect.objectContaining({ headers: expect.any(Object) })
    );
  });

  it('logs a warning when the health endpoint returns non-ok', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockGet.mockRejectedValue(Object.assign(new Error('HTTP 500'), { status: 500 }));

    startAntiSleepHeartbeat();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('500')
    );
    consoleSpy.mockRestore();
  });

  it('logs a warning when the probe throws', async () => {
    const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    mockGet.mockRejectedValue(new Error('network down'));

    startAntiSleepHeartbeat();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(consoleSpy).toHaveBeenCalledWith(
      expect.stringContaining('Could not reach')
    );
    consoleSpy.mockRestore();
  });
});
