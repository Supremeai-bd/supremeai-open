import { describe, it, expect, vi, beforeEach } from 'vitest';

const getMock = vi.fn();
const postMock = vi.fn();

vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
  },
}));

import { useStore } from './useStore';

describe('useStore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useStore.setState({
      systemConfig: useStore.getState().systemConfig,
      isConfigLoaded: false,
      isServerOnline: false,
      sessionId: null,
      currentIdempotencyKey: null,
      isOrchestrating: false,
      chatHistory: [],
      activeTaskType: 'general',
      executionError: null,
      streamLogs: [],
      deployGate: null,
      isGateLoading: false,
      isForging: false,
      forgeFeedback: null,
      forgeSuccessCode: null,
    });
  });

  it('merges config and marks it loaded', () => {
    useStore.getState().setConfig({ activeTaskType: 'general' } as never);
    expect(useStore.getState().isConfigLoaded).toBe(true);
    expect(useStore.getState().systemConfig).toBeTruthy();
  });

  it('sets server status and initializes a session', () => {
    useStore.getState().setServerStatus(true);
    expect(useStore.getState().isServerOnline).toBe(true);
    useStore.getState().initializeSession('sess-1');
    expect(useStore.getState().sessionId).toBe('sess-1');
  });

  it('generates and stores an idempotency key', () => {
    const key = useStore.getState().generateIdempotencyKey();
    expect(key).toBeTruthy();
    expect(useStore.getState().currentIdempotencyKey).toBe(key);
  });

  it('adds messages to the chat history', () => {
    useStore.getState().addMessage({ role: 'user', content: 'hi' });
    expect(useStore.getState().chatHistory).toHaveLength(1);
    expect(useStore.getState().chatHistory[0].content).toBe('hi');
  });

  it('clears the chat history', () => {
    useStore.getState().addMessage({ role: 'user', content: 'hi' });
    useStore.getState().clearHistory();
    expect(useStore.getState().chatHistory).toHaveLength(0);
  });

  it('toggles orchestration state', () => {
    useStore.getState().triggerOrchestration(true, 'boom');
    expect(useStore.getState().isOrchestrating).toBe(true);
    expect(useStore.getState().executionError).toBe('boom');
  });

  it('does not fetch gate status without an admin token', async () => {
    await useStore.getState().fetchGateStatus();
    expect(getMock).not.toHaveBeenCalled();
  });

  it('fetches gate status when an admin token is present', async () => {
    localStorage.setItem('supreme_admin_jwt', 'tok');
    getMock.mockResolvedValue({ status: 'HEALTHY', error: '' });
    await useStore.getState().fetchGateStatus();
    expect(useStore.getState().deployGate?.status).toBe('UNLOCKED');
    expect(useStore.getState().isGateLoading).toBe(false);
  });

  it('executes a successful gate override', async () => {
    postMock.mockResolvedValue({ success: true, message: 'ok', forced_status: 'UNLOCKED' });
    const res = await useStore.getState().executeGateOverride('UNLOCKED', 'reason', 'secret');
    expect(res.success).toBe(true);
    expect(useStore.getState().deployGate?.status).toBe('UNLOCKED');
    // বাংলা মন্তব্য: URL চুক্তি লক (#2475) — ব্যাকএন্ডে শুধু /admin-api/gate/override আছে;
    // /api/admin/gate/override পাথ 404 দেয়, তাই ভুল পাথ ফিরে এলে টেস্ট লাল হবে।
    expect(postMock).toHaveBeenCalledWith(
      '/admin-api/gate/override',
      expect.objectContaining({ target_status: 'UNLOCKED', admin_secret: 'secret' }),
    );
    const calledPath = postMock.mock.calls[0][0] as string;
    expect(calledPath).not.toBe('/api/admin/gate/override');
  });

  it('reports a rejected gate override', async () => {
    postMock.mockResolvedValue({ success: false, detail: 'nope' });
    const res = await useStore.getState().executeGateOverride('LOCKED', 'reason', 'secret');
    expect(res.success).toBe(false);
    expect(res.message).toContain('nope');
  });

  it('forges a new skill successfully', async () => {
    postMock.mockResolvedValue({ success: true, skill_name: 'x', generated_code: 'code' });
    await useStore.getState().forgeNewSkill('x', 'demand');
    expect(useStore.getState().isForging).toBe(false);
    expect(useStore.getState().forgeSuccessCode).toBe('code');
  });

  it('handles a forge failure response', async () => {
    postMock.mockResolvedValue({ success: false, detail: 'sandbox fail' });
    await useStore.getState().forgeNewSkill('x', 'demand');
    expect(useStore.getState().forgeFeedback).toContain('sandbox fail');
  });

  it('handles a forge network error', async () => {
    postMock.mockRejectedValue(new Error('net down'));
    await useStore.getState().forgeNewSkill('x', 'demand');
    expect(useStore.getState().forgeFeedback).toContain('net down');
  });
});
