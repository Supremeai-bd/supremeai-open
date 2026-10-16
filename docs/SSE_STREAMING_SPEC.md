---
id: sse-streaming-spec
title: "Server-Sent Events & HTTP Streaming — Client Specification (MCP Tower + Gateway)"
document_role: specification
status: active
canonical: true
owner: auditor
last_verified: 2026-10-16
governing_issue: 336
related_docs:
  - AGENT_RULES.md
  - docs/CONSUMERS.md
  - docs/FAQ.md
  - docs/MCP_CONNECT.md
  - docs/WEBSOCKET_SPEC.md
---

# Server-Sent Events & HTTP Streaming — Client Specification

> **What this document is:** the streaming specification for SupremeAI's two public HTTP surfaces — **Part A** codifies the *shipped, live-verified* MCP-over-SSE transport of the Control Tower; **Part B** specifies the *missing* Gateway chat-streaming response contract (`stream: true` is already declared in the OpenAPI; the response side is not) as a normative, additive proposal. BN: SupremeAI-র দুইটি স্ট্রিমিং সারফেসের চুক্তি — MCP ট্রান্সপোর্ট (লাইভ যাচাইকৃত) ও গেটওয়ে চ্যাট-স্ট্রিম (ঘোষিত কিন্তু অনির্দিষ্ট — এই দলিলই সেই শূন্যতা পূরণের প্রস্তাব)।
>
> **Live evidence:** all Part A framing was captured from the production Tower (`https://supremeai-mcp-tower.onrender.com`) on 2026-10-16 with a zero-credential probe. Part B is a proposal — nothing in it is implemented yet, and it is marked as such at every rule.
>
> **Compliance role:** this file is cited by issue #336 (live SSE/HTTP streaming endpoint handlers, P1) as a compliance input — the implementation MUST conform to Part B's framing rules, and Part A remains the transport truth for the Tower's `/sse` entry. Originally authored for #31 (transport scope landed via PR #312's `docs/MCP_CONNECT.md`); this document carries the parts #336 cites that `MCP_CONNECT.md` does not cover: the Gateway `stream: true` response contract.

---

## 1. Scope — the two streaming surfaces

| Surface | Endpoint | Status |
|---|---|---|
| **A. MCP transport (SSE)** | `GET https://supremeai-mcp-tower.onrender.com/sse` (+ `POST /messages?sessionId=…`) | **Shipped.** Advertised in `mcp.json` (`supremeai-control-tower-sse`, `transport: sse`) beside the streamable-HTTP entry (`/mcp`). Codified here from live capture. |
| **B. Gateway chat streaming** | `POST /v1/chat/completions` with `stream: true` | **Declared but unspecified.** `api-schemas/gateway.openapi.yaml` declares the request field (`stream: { type: boolean, default: false }`) while the documented response is only the non-streaming `ChatCompletionResponse` object. Part B closes this as an additive proposal. |

A client that only ever uses surface A needs nothing else. A client that wants token-by-token completions needs Part B.

## 2. Part A — MCP-over-SSE transport contract (shipped, live-verified)

### 2.1 The handshake, exactly as observed

```text
GET /sse HTTP/2
Accept: text/event-stream

── response ──────────────────────────────────────────────
HTTP/2 200
content-type: text/event-stream
cache-control: no-cache, no-transform

event: endpoint
data: /messages?sessionId=ae6149ea-f9a8-4dbf-bc9d-52759d8ad1c4
```

Live round-trip (2026-10-16, guest, zero credentials):

```text
1. GET  /sse                                    → 200 text/event-stream
2. ←   event: endpoint  data: /messages?sessionId=<uuid>
3. POST /messages?sessionId=<uuid>  (initialize JSON-RPC)
        → HTTP 202  body: 'Accepted'
4. ←   event: message  data: {"result":{"protocolVersion":"2025-03-26",
        "capabilities":{"tools":{"listChanged":true}, …}}}
```

### 2.2 Normative rules (Part A)

1. **One session per stream.** The server's first SSE event is always `event: endpoint` carrying a **relative** `/messages?sessionId=<uuid>` URL. That session is bound to that stream; it dies with it.
2. **The POST channel returns receipts, not results.** Every JSON-RPC message goes to the `endpoint` URL as `Content-Type: application/json`; the HTTP response is **202 Accepted** with a trivial body. Never parse the POST response for results.
3. **All JSON-RPC responses and server-initiated requests arrive asynchronously on the SSE stream** as `event: message` frames with JSON-RPC payloads in `data:`. Match responses to requests by JSON-RPC `id`, never by ordering assumptions.
4. **Relative endpoint resolution.** The `endpoint` data is relative to the SSE origin — resolve it against the origin, never against the current page/working path. Never absolutize it from client config.
5. **Required headers:** `Accept: text/event-stream` on the GET; `Content-Type: application/json` on POSTs. Server side sets `cache-control: no-cache, no-transform` — clients must not add their own transform-compatible caching on this stream.
6. **Reconnection = new session.** On stream drop, reconnect with a fresh `GET /sse`, receive a **new** sessionId, and re-run `initialize`. Old sessionIds are not resumable; do not reuse a stale `endpoint` URL.
7. **Capabilities are advertised in the initialize result** — observed live: `"tools":{"listChanged":true}`, meaning the client should expect and honor `notifications/tools/list_changed` and re-run `tools/list` instead of caching tool inventory forever.
8. **Transport selection:** `mcp.json` deliberately exposes both entries — prefer the streamable-HTTP entry (`/mcp`) in clients that support it (single connection, simpler lifecycle); use the SSE entry (`/sse`) for compatibility. Both speak the same tool surface; no tool is exclusive to either.
9. **Authentication posture:** the observed guest handshake is zero-credential — visibility scoping happens per-session (guest sees 9 tools; tenant-scoped tools like `memory.*` are never advertised). Clients must not assume a fixed tool list across sessions or credentials.

### 2.3 Degradation & failure behavior (Part A)

- If the first `endpoint` event does not arrive, treat the transport as failed and fall back (or retry with backoff) — **never** POST to a guessed `/messages` URL.
- If the SSE stream closes mid-conversation, pending JSON-RPC calls are unresolved: re-resolve per rule 6 and retry idempotent calls; treat non-idempotent in-flight work as failed and re-derive from server state.
- The tower renders behind proxies (Render/Cloudflare observed); clients must tolerate proxy-added headers and must not require HTTP/2.

## 3. Part B — Gateway chat streaming response contract (PROPOSAL, additive)

> **Status: proposal.** Main's OpenAPI declares `stream` but documents no streaming response. The rules below are the contract a client may code against **once implemented**, and the shape the implementation must take. Additive only: no existing non-streaming behavior changes.

### 3.1 Response envelope

When `stream: true`, the Gateway responds with:

1. `Content-Type: text/event-stream` (+ `Cache-Control: no-cache, no-transform`), status **200** — stream setup errors (auth, validation, rate limit) remain **ordinary JSON error responses with their normal status codes**, emitted *before* the stream starts. Never start a 200 stream and then fail semantically.
2. Each token step is one SSE frame:

```text
data: {"id":"…","object":"chat.completion.chunk","created":1700000000,"model":"<served-model>","choices":[{"index":0,"delta":{"content":"<token>"},"finish_reason":null}]}

```

3. The final frames: one chunk carrying `"finish_reason": "<stop|length|…>"`, then the terminator line `data: [DONE]`, then the server closes the stream.
4. **Usage honesty (mirrors the non-streaming doctrine in the OpenAPI — "না পেলে বানানো নয়, ক্ষেত্রটি বাদ"):** if the provider reports usage, a final chunk carries the `usage` object; if it does not, the field is simply absent. Fabricated usage is a contract violation.

### 3.2 Mid-stream errors

- If the upstream fails after the stream has started, emit exactly one terminal error frame and close:

```text
data: {"error":{"message":"…","type":"…","code":"…"}}

```

- Clients treat a received `error` frame as terminal: stop parsing, do not retry mid-stream (the request already consumed provider work), and surface the error object verbatim.
- Retry doctrine otherwise inherits the shipped client baseline (`examples/gateway_client.py`): retry **only** on 502/503, with backoff — a 502/503 means the stream never started.

### 3.3 Client parsing rules (Part B)

1. Split the body on `\n\n`; every complete block must start with `data: `.
2. `[DONE]` is the only sentinel; a stream that closes without it is an incomplete response — surface a truncation error, never silently accept.
3. Accumulate `choices[*].delta.content` in arrival order; `delta.role` appears only on the first chunk.
4. Ignore unknown JSON fields and unknown SSE event names (forward compatibility); never fail on extra fields.
5. Enforce a client-side idle timeout: a stream that sends no bytes for a configured window (recommend 60 s) is treated as dead (see 3.2's error semantics for surfacing).

### 3.4 Versioning

- Specifying Part B in `api-schemas/gateway.openapi.yaml` is an **additive MINOR** change: a new response variant (`text/event-stream`) for the existing 200 response, plus a `ChatCompletionChunk` schema. The `stream` request field already exists — no breaking change, no MAJOR.
- The non-streaming response remains byte-identical for `stream: false`/absent.

## 4. Client implementation checklist (both surfaces)

1. **A:** parse `event: endpoint` → resolve relative → POST JSON-RPC → expect 202 → read `event: message` → match by id.
2. **A:** reconnect = new session + re-`initialize`; honor `tools.listChanged`.
3. **B:** 200 + `text/event-stream` only after pre-flight validation passed; ordinary errors keep ordinary status codes.
4. **B:** `data: ` block parser, `[DONE]` sentinel, terminal `error` frame handling, no mid-stream retries, 60 s idle timeout.
5. **Both:** `cache-control: no-cache, no-transform` respected; proxy tolerance; no hardcoded absolute message URLs.
6. **Both:** every observable failure mode surfaces an actionable message (the FAQ's validation-error doctrine) — silent swallowing is a defect.

## 5. Related Documents

- [docs/MCP_CONNECT.md](./MCP_CONNECT.md) — connection guide for both MCP transports incl. identity model, session lifecycle, and real limits table (PR #312)
- [docs/WEBSOCKET_SPEC.md](./WEBSOCKET_SPEC.md) — WebSocket live event stream wire contract (issue #40, PR #313) — the push-event sibling of this document's request-stream contract
- [docs/CONSUMERS.md](./CONSUMERS.md) — consumer contract, key lifecycle, error semantics (the non-streaming baseline Part B extends)
- [docs/FAQ.md](./FAQ.md) — symptom→cause→fix for known validation-error classes (client-facing failure doctrine)
- [AGENT_RULES.md](../AGENT_RULES.md) — agent policy constitution (document circle, boundary guards, §8 navigation policy)
