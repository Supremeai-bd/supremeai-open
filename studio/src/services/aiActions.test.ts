import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';

const fakeService = {
  sendChatMessage: vi.fn().mockResolvedValue({ response: 'resp-text' }),
  getSessionId: vi.fn().mockReturnValue('sid'),
};
const fakeSecurity = {
  scanCode: vi.fn().mockResolvedValue([{ severity: 'high', type: 'x', description: 'd', recommendation: 'r' }]),
};
const fakePerformance = {
  analyzePerformance: vi.fn().mockResolvedValue({
    complexity_score: 10,
    estimated_impact: 'low',
    bottlenecks: [],
    recommendations: [],
  }),
};
const fakeHealing = {
  healError: vi.fn().mockResolvedValue({ fixedCode: 'fixed', explanation: 'expl' }),
};
const shared = {
  service: fakeService,
  security: fakeSecurity,
  performance: fakePerformance,
  healing: fakeHealing,
  scope: {},
};

const apiCall = vi.fn().mockResolvedValue({ status: 200, ok: true, data: {} });
const getSharedServices = vi.fn().mockReturnValue(shared);
const promptForOtp = vi.fn();

vi.mock('./supremeShared', () => ({ getSharedServices, apiCall }));
vi.mock('@supremeai/shared-services', () => ({ promptForOtp }));

const { useAiActions } = await import('./aiActions');

const ctx = { code: 'const a = 1;', language: 'ts', path: 'p.ts' };

describe('useAiActions', () => {
  it('returns actions with idle busy state', () => {
    const { result } = renderHook(() => useAiActions());
    expect(result.current.busy).toBeNull();
    expect(typeof result.current.explain).toBe('function');
    expect(typeof result.current.runWithContext).toBe('function');
  });

  it('runWithContext warns when no active file', () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const _onLoading = vi.fn();
    act(() => {
      result.current.runWithContext(null, onOutput, async () => {});
    });
    expect(getSharedServices).not.toHaveBeenCalled();
    expect(onOutput).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'SupremeAI', kind: 'plain' })
    );
  });

  it('runWithContext invokes handler with file context', () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const handler = vi.fn();
    const file = { content: 'x', language: 'ts', path: 'p.ts' } as never;
    act(() => {
      result.current.runWithContext(file, onOutput, handler);
    });
    expect(handler).toHaveBeenCalledWith({ code: 'x', language: 'ts', path: 'p.ts' });
  });

  it('explain sends a chat message and reports output', async () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.explain(ctx, onOutput, onLoading);
    });
    expect(getSharedServices).toHaveBeenCalled();
    expect(fakeService.sendChatMessage).toHaveBeenCalled();
    expect(onOutput).toHaveBeenCalledWith(expect.objectContaining({ content: 'resp-text' }));
    expect(onLoading).toHaveBeenNthCalledWith(1, true);
    expect(onLoading).toHaveBeenLastCalledWith(false);
  });

  it('review sends a chat message', async () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.review(ctx, onOutput, onLoading);
    });
    expect(fakeService.sendChatMessage).toHaveBeenCalled();
    expect(onOutput).toHaveBeenCalledWith(expect.objectContaining({ title: '🛡️ AI Code Review' }));
  });

  it('securityScan formats issues', async () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.securityScan(ctx, onOutput, onLoading);
    });
    expect(fakeSecurity.scanCode).toHaveBeenCalled();
    const call = onOutput.mock.calls[0][0];
    expect(call.content).toContain('[HIGH]');
    expect(call.meta).toBe('1 issue(s)');
  });

  it('analyzePerformance reports complexity', async () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.analyzePerformance(ctx, onOutput, onLoading);
    });
    expect(fakePerformance.analyzePerformance).toHaveBeenCalled();
    expect(onOutput.mock.calls[0][0].content).toContain('Complexity Score: 10/100');
  });

  it('autoHeal reports fixed code', async () => {
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.autoHeal(ctx, onOutput, onLoading);
    });
    expect(fakeHealing.healError).toHaveBeenCalled();
    expect(onOutput.mock.calls[0][0].content).toContain('fixed');
  });

  it('autoHeal handles no fix', async () => {
    fakeHealing.healError.mockResolvedValueOnce({ explanation: 'e' });
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.autoHeal(ctx, onOutput, onLoading);
    });
    expect(onOutput.mock.calls[0][0].content).toContain('কোনো automatic fix');
  });

  it('jitAction reports cancellation', async () => {
    promptForOtp.mockResolvedValueOnce({ cancelled: true });
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.jitAction(onOutput, onLoading);
    });
    expect(apiCall).not.toHaveBeenCalled();
    expect(onOutput.mock.calls[0][0].content).toContain('বাতিল');
  });

  it('jitAction binds target on success', async () => {
    promptForOtp.mockResolvedValueOnce({ cancelled: false, otpCode: '111', reason: 'r' });
    apiCall.mockResolvedValueOnce({ status: 200, ok: true, data: { bound: true } });
    const { result } = renderHook(() => useAiActions());
    const onOutput = vi.fn();
    const onLoading = vi.fn();
    await act(async () => {
      await result.current.jitAction(onOutput, onLoading);
    });
    expect(apiCall).toHaveBeenCalledWith(
      expect.objectContaining({ endpoint: '/admin-api/workspaces/bind-target', method: 'POST' })
    );
    expect(onOutput.mock.calls[0][0].content).toContain('OTP যাচাই সফল');
  });
});
