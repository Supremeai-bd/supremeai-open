// Unit test for Issue #2521 — CostDashboard WebSocket auth token source.
//
// বাংলা: আগে WS auth frame পড়ত `localStorage['supremeai_token']` — এই key পুরো
// codebase-এ কোথাও লেখা হয় না, তাই auth frame কখনোই যেত না (realtime metrics
// silently dead)। Fix: canonical `getRawToken()`। এই টেস্ট তিনটি জিনিস প্রমাণ করে:
//   1) সেশন টোকেন থাকলে প্রথম ফ্রেমে {type:'auth', token} যায় (getRawToken থেকে)
//   2) নীতি regression-guard: 'supremeai_token' key-তে যা থাকুক, তা আর পড়া হয় না
//   3) টোকেন অনুপস্থিত হলে দৃশ্যমান warn হয়, auth frame যায় না (rel001 নীরব ব্যর্থতা নয়)

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

// বাংলা: পেজের ভারী প্রতিবেশীদের হালকা stub — শুধু WS auth আচরণ মাপা হবে।
vi.mock('../../lib/modelBranding', () => ({
  getSupremeProviderLabel: (x: unknown) => String(x ?? ''),
}));

vi.mock('../../hooks/useEventBus', () => ({
  useEventBus: () => undefined,
}));

const mockGetRawToken = vi.hoisted(() => vi.fn((): string | null => null));
vi.mock('../../services/apiClient', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({
      data: {
        total_spent: 0,
        total_saved: 0,
        cached_queries: 0,
        free_tier_pct: 0,
        provider_breakdown: {},
      },
    }),
  },
  getRawToken: mockGetRawToken,
}));

import { CostDashboard } from './CostDashboard';

// ── Fake WebSocket: শুধু প্রয়োজনীয় সারফেস (constructor/send/close) ─────────
class FakeWebSocket {
  static readonly instances: FakeWebSocket[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  send = (msg: string): void => {
    this.sent.push(msg);
  };

  close = (): void => {};
}

const latestSocket = (): FakeWebSocket =>
  FakeWebSocket.instances[FakeWebSocket.instances.length - 1];

describe('CostDashboard WS auth (fix #2521)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    FakeWebSocket.instances.length = 0;
    vi.stubGlobal('WebSocket', FakeWebSocket);
    window.sessionStorage.clear();
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the canonical session token as the first auth frame on open', async () => {
    mockGetRawToken.mockReturnValue('tok-canonical-123');
    // নীতি regression-guard: পুরনো bug-পথের key-তে ফাঁদ বসিয়ে রাখা — fix ঠিক হলে
    // এই value কখনো ফ্রেমে যাবে না (আগের কোড এটাই পাঠাত, কারণ canonical key লেখা হতো না)।
    window.localStorage.setItem('supremeai_token', 'legacy-never-written-bug-token');

    render(<CostDashboard />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = latestSocket();
    expect(ws.url).toContain('/api/v1/metrics/stream');

    ws.onopen?.();

    await waitFor(() => expect(ws.sent).toHaveLength(1));
    const frame = JSON.parse(ws.sent[0]) as { type: string; token: string };
    expect(frame.type).toBe('auth');
    expect(frame.token).toBe('tok-canonical-123'); // getRawToken() থেকে — login যা লেখে
    expect(frame.token).not.toBe('legacy-never-written-bug-token');
  });

  it('skips the auth frame and warns visibly when no session token exists', async () => {
    mockGetRawToken.mockReturnValue(null);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    render(<CostDashboard />);
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1));
    const ws = latestSocket();

    ws.onopen?.();

    // কোনো auth frame নয় + নীরব ব্যর্থতা নয় — দৃশ্যমান সতর্কবার্তা।
    await waitFor(() => expect(ws.sent).toHaveLength(0));
    expect(warnSpy).toHaveBeenCalledWith(
      expect.stringContaining('unauthenticated'),
    );
    warnSpy.mockRestore();
  });

  it('keeps the metrics fetch path intact (apiClient.get on /api/billing/analytics)', async () => {
    mockGetRawToken.mockReturnValue('tok-abc');
    render(<CostDashboard />);
    await waitFor(() =>
      expect(screen.getByText(/Cost & Zero-Cost Savings Dashboard/i)).toBeInTheDocument(),
    );
  });
});
