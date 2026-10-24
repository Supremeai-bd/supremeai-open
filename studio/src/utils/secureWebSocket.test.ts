/**
 * Tests for secureWebSocket.ts
 *
 * Tests cover:
 * - URL construction (no token in URL query)
 * - First-message auth frame ({"type":"auth","token":"..."})
 * - Strip-guard for accidental ?token= in caller-supplied URLs
 * - Callback wiring (onMessage / onClose / onError)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// The token comes from apiClient.getRawToken() at open time — mock it so the
// auth frame is deterministic (createSecureWebSocket has no token parameter).
vi.mock('../services/apiClient', () => ({
  getRawToken: () => 'test-token-123',
}));

// Mock WebSocket
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  readyState = 0; // CONNECTING
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  sentMessages: string[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    // Simulate async open
    setTimeout(() => {
      this.readyState = 1; // OPEN
      this.onopen?.(new Event('open'));
    }, 0);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close(code?: number, reason?: string) {
    this.readyState = 3; // CLOSED
    this.onclose?.(new CloseEvent('close', { code: code ?? 1000, reason: reason ?? '' }));
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal('WebSocket', MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('secureWebSocket', () => {
  it('should be importable and export the documented API', async () => {
    const mod = await import('./secureWebSocket');
    expect(typeof mod.createSecureWebSocket).toBe('function');
    expect(typeof mod.getAuthToken).toBe('function');
  });

  it('should send auth frame as first message after open', async () => {
    // The first message after WebSocket opens should be {"type":"auth","token":"<bearer>"}
    // This is the "first-message auth" pattern (vs token-in-URL)
    const { createSecureWebSocket } = await import('./secureWebSocket');

    createSecureWebSocket('wss://test.example.com/ws', {});
    // Wait for the async open
    await new Promise(r => setTimeout(r, 10));

    const mockWs = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(mockWs).toBeDefined();
    expect(mockWs.sentMessages.length).toBeGreaterThan(0);
    const firstMsg = JSON.parse(mockWs.sentMessages[0]);
    expect(firstMsg.type).toBe('auth');
    expect(firstMsg.token).toBe('test-token-123');
    // Token should NOT be in the URL
    expect(mockWs.url).not.toContain('token=');
    expect(mockWs.url).not.toContain('?');
  });

  it('should strip an accidental ?token= from the caller-supplied URL', async () => {
    // Strip-guard: even a buggy caller must never leak the token via the URL
    const { createSecureWebSocket } = await import('./secureWebSocket');

    createSecureWebSocket('wss://test.example.com/ws?token=leaked-secret', {});
    await new Promise(r => setTimeout(r, 10));

    const mockWs = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    expect(mockWs.url).toBe('wss://test.example.com/ws');
    expect(mockWs.url).not.toContain('leaked-secret');
  });

  it('should wire message/close/error callbacks through', async () => {
    const { createSecureWebSocket } = await import('./secureWebSocket');
    const onMessage = vi.fn();
    const onClose = vi.fn();
    const onError = vi.fn();

    const ws = createSecureWebSocket('wss://test.example.com/ws', {
      onMessage,
      onClose,
      onError,
    });
    await new Promise(r => setTimeout(r, 10));

    ws.onmessage?.(new MessageEvent('message', { data: 'hello' }));
    expect(onMessage).toHaveBeenCalledTimes(1);

    ws.onerror?.(new Event('error'));
    expect(onError).toHaveBeenCalledTimes(1);

    ws.onclose?.(new CloseEvent('close', { code: 1000 }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
