// Guest-chat relay header contract (CORS allowlist guard).
//
// Live-probed 2026-10-31 (GLM Agent 28, human-eye cycle): the gateway
// (supremeai-api-ulw0.onrender.com) answers a CORS preflight for
// POST /v1/chat/completions with
//   Access-Control-Allow-Headers: Accept, Accept-Language, Authorization,
//     Content-Language, Content-Type, Origin, Referer, X-Correlation-ID,
//     X-Forwarded-For, X-Guest-Mode, X-SupremeAI-Key
// and returns HTTP 400 for a preflight that also requests
// X-Conversation-Id. UnifiedChatPanel used to send that header on every
// guest turn (conversation identity is generated per conversation), so the
// browser blocked the POST outright and the customer saw the relay reported
// offline even though both relays were healthy.
//
// This guard pins the relay request surface: every header the guest chat
// sends to the gateway must be inside the live allowlist, and the
// conversation identity must keep travelling in the request body (the
// non-redundant channel). If a future change reintroduces a non-allowlisted
// custom header, this test fails before any customer can hit the dead path.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { callLiveAI } from './UnifiedChatPanel';

// Live allowlist probed from the gateway preflight (2026-10-31, differential
// curl: x-conversation-id alone -> 400; every listed header -> 200).
const LIVE_ALLOWLIST = new Set([
  'accept',
  'accept-language',
  'authorization',
  'content-language',
  'content-type',
  'origin',
  'referer',
  'x-correlation-id',
  'x-forwarded-for',
  'x-guest-mode',
  'x-supremeai-key',
]);

describe('guest chat relay header contract', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends only CORS-allowlisted headers and carries conversation_id in the body', async () => {
    const captured: Array<{ url: string; init: RequestInit }> = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
        captured.push({ url: String(url), init: init ?? {} });
        return new Response(
          JSON.stringify({
            choices: [{ message: { content: 'OK' } }],
            conversation_id: 'conv-guard-28',
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        );
      }),
    );

    const result = await callLiveAI(
      'guard ping',
      'Supreme Auto',
      '',
      undefined,
      { conversationId: 'conv-guard-28' },
    );

    expect(result.text).toBe('OK');
    expect(captured.length).toBeGreaterThan(0);

    const post = captured.find((c) => c.url.includes('/v1/chat/completions'));
    expect(post).toBeDefined();

    const headerEntries = new Headers((post!.init.headers as HeadersInit) ?? {});
    const headerKeys = [...headerEntries.keys()].map((k) => k.toLowerCase());

    // The regression pin: no header outside the live allowlist. Any new
    // custom header must first be added to the gateway's CORS allow-headers
    // (owner lane) and then to LIVE_ALLOWLIST here.
    const outside = headerKeys.filter((k) => !LIVE_ALLOWLIST.has(k));
    expect(outside).toEqual([]);

    // The specific regression that shipped broken: conversation identity in
    // a header. It must never come back as a header (it lives in the body).
    expect(headerKeys).not.toContain('x-conversation-id');

    // The non-redundant channel: identity still travels in the body.
    const body = JSON.parse(String(post!.init.body ?? '{}')) as {
      conversation_id?: string;
      messages?: Array<{ role: string; content: string }>;
    };
    expect(body.conversation_id).toBe('conv-guard-28');
    // messages[0] is the system prompt; the user turn is the last entry.
    const userTurn = body.messages?.filter((m) => m.role === 'user').at(-1);
    expect(userTurn?.content).toBe('guard ping');

    // Guest key default is present and allowlisted.
    expect(headerKeys).toContain('x-supremeai-key');
    expect(headerEntries.get('X-SupremeAI-Key')).toBe('guest');
  });
});
