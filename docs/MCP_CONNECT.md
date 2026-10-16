# MCP Connect — Connecting AI Clients to the SupremeAI MCP Tower

Complete client implementation specification for connecting to the SupremeAI
MCP Tower over the two supported transports:

| Transport | URL | Protocol | Best for |
|---|---|---|---|
| **Streamable HTTP** | `https://supremeai-mcp-tower.onrender.com/mcp` | MCP over Streamable HTTP (GET/POST/DELETE) | Full MCP clients (Claude Desktop, IDE agents, custom harnesses) |
| **SSE** | `https://supremeai-mcp-tower.onrender.com/sse` | Server-Sent Events (GET) | Web AI clients, legacy MCP SSE clients, dashboards |

Reference implementations (zero dependencies, mirroring this guide 1:1):

- Python: [`examples/mcp-client-py/client.py`](../examples/mcp-client-py/client.py)
- TypeScript: [`examples/mcp-client-ts/client.ts`](../examples/mcp-client-ts/client.ts)

---

## 1. Identity model (read this first)

The Tower is **default-deny RBAC**. What you can do depends on the role your
connection resolves to:

1. **Anonymous** — no `?client=` parameter and no credential: you connect as
   `public_viewer` (safe read-only capability). Your calls are still visible on
   the ops dashboard (an observability record is created).
2. **Named client** — append `?client=<your-unique-name>` to the URL:

   ```
   https://supremeai-mcp-tower.onrender.com/mcp?client=<your-unique-name>
   ```

   The `?client=` parameter gives you a **stable identity across sessions**.
   The URL alone is NEVER authentication (#48 Verified Slot Architecture): a
   presented identity adopts its stored role **only** when the request also
   presents a credential that verifies live against the operational registry.
   Otherwise the strict `viewer` fallback applies.
3. **Credentialed roles** — role-gated tools (`action_*`, `tenant_*`,
   `autonomy_kill_switch`, approvals) require an **agent** or **admin** role
   resolved from a verified credential. Anonymous callers receive:

   ```
   Forbidden: tool 'x' requires agent role or higher
   ```

Role ladder (operational SSOT: `policy/auth.context.ts` #110):
`viewer → restricted_viewer → repo_viewer → agent → admin → supremeadmin`.
The Layer-1 contract view of this ladder lives in
[`api-schemas/permissions.schema.json`](../api-schemas/permissions.schema.json).

---

## 2. Streamable HTTP transport (`/mcp`)

The canonical MCP transport. Methods: `GET`, `POST`, `DELETE`.

### 2.1 Session lifecycle (stateful, per-session)

The Tower routes every request by the `Mcp-Session-Id` header:

1. **Initialize** — `POST /mcp` a JSON-RPC `initialize` request **without** a
   session header. The server mints a NEW per-session transport and returns a
   `Mcp-Session-Id` response header.
2. **Continue** — send every subsequent request with
   `Mcp-Session-Id: <id>`. Requests without the header are treated as new
   sessions (a second `initialize`), not as a continuation.
3. **Terminate** — `DELETE /mcp` with the session header.

> Historical note: the old single-shared-transport design caused
> `404 -32001 Session not found` for everyone once one client closed its
> session. Per-session routing (#2588) removed that failure class — if you
> still see `-32001`, your client is reusing a stale/expired session id:
> re-run `initialize`.

### 2.2 Initialize request (copy-paste)

```bash
curl -sS -D /tmp/h.txt -X POST \
  "https://supremeai-mcp-tower.onrender.com/mcp?client=demo-curl" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-curl","version":"1.0.0"}}}'

# Extract the session id from the response headers:
grep -i "mcp-session-id" /tmp/h.txt
```

### 2.3 Listing and calling tools

```bash
SID="<paste mcp-session-id here>"

# List tools:
curl -sS -X POST "https://supremeai-mcp-tower.onrender.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'

# Call a tool:
curl -sS -X POST "https://supremeai-mcp-tower.onrender.com/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SID" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"<tool_name>","arguments":{}}}'
```

Compatibility: the Tower forgives generic web fetchers that omit the
`Accept` header (it defaults to `application/json, text/event-stream`), but
spec-conformant clients SHOULD always send it.

### 2.4 Transport-level limits and errors

| Status | Meaning | Client action |
|---|---|---|
| `429` + `Retry-After` | Per-IP rate limit exceeded (sliding window) | Wait `Retry-After` seconds; retry with backoff. Never hot-loop. |
| `413` | Request body exceeds `MAX_REQUEST_BYTES` | Shrink the payload (batch smaller). |
| `403` `protected_capability` | Default-deny RBAC: role insufficient | Register / present verified credentials; see §1. |
| `404` `-32001` | Session not found (stale `Mcp-Session-Id`) | Re-`initialize` and use the fresh session id. |
| `503` | Server-side resource cap hit | Back off; retry later. |

---

## 3. SSE transport (`/sse`)

`GET /sse` — Server-Sent Events, intended for Web AI clients (e.g. Claude Web)
and legacy MCP SSE clients. The response is an `text/event-stream`:

- The first events carry your session/endpoint information; subsequent events
  are JSON-RPC messages pushed by the Tower.
- Each SSE session pins a transport + socket. **Session table is bounded**
  (#109): when the cap is hit you receive `503 {"error": "Too many concurrent
  SSE sessions", "activeSessions": N}` — reconnect with exponential backoff,
  do not hammer.
- Connecting records **auto-presence** for the dashboard (`protocol: "sse"`).
- Identity rules are identical to §1 (`?client=` + verified credential ⇒
  stored role; otherwise strict `viewer` fallback).

### 3.1 Minimal SSE read (curl)

```bash
curl -N -sS "https://supremeai-mcp-tower.onrender.com/sse?client=demo-curl"
```

(`-N` disables buffering so you see events as they arrive.)

### 3.2 Reading SSE in Python (stdlib)

See `sse_read()` in [`examples/mcp-client-py/client.py`](../examples/mcp-client-py/client.py):
it opens a `GET` with `Accept: text/event-stream` and yields parsed
`event:`/`data:` frames. Reconnect on `ConnectionError` with backoff.

### 3.3 Reading SSE in TypeScript (fetch)

See `sseRead()` in [`examples/mcp-client-ts/client.ts`](../examples/mcp-client-ts/client.ts):
it consumes `response.body` as a stream, splits on the `\n\n` frame delimiter
and parses `event:`/`data:` lines. Same reconnect discipline.

---

## 4. Health checks (no credentials needed)

```bash
curl -sS "https://supremeai-mcp-tower.onrender.com/health"
```

`/health` (and `/`) are public and cheap — use them for smoke tests and
uptime probes before opening MCP sessions. Richer (role-gated) views:
`/health/summary`, `/health/dashboard`.

---

## 5. Operational etiquette (federation contract)

1. **One session per client process.** Do not share `Mcp-Session-Id` across
   processes; it pins server-side state.
2. **Always `DELETE /mcp` on shutdown** — frees the session transport.
3. **Respect `Retry-After`** — the rate limiter is per-IP; hot-looping hurts
   every agent behind your egress IP (see `docs/CONTRIBUTING.md` §troubleshooting).
4. **Never put credentials in URLs** — query strings leak into proxy/CDN logs
   and Referer headers. The Tower rejects token query parameters by design;
   browser approval links use per-request expiring HMAC signatures instead.
5. **Idle? Emit heartbeats.** Long-running agents should adopt the heartbeat
   protocol (`docs/HEARTBEAT_PROTOCOL.md`) so orphaned claims get released.

---

## 6. Client checklist (are you a good citizen?)

- [ ] Sends `?client=` with a unique stable name
- [ ] Sends `Accept: application/json, text/event-stream` on `/mcp` POSTs
- [ ] Persists and replays `Mcp-Session-Id` for the session's lifetime
- [ ] Re-`initialize`s on `404 -32001` instead of crashing
- [ ] Honors `Retry-After` on `429`
- [ ] `DELETE`s the session on exit
- [ ] Never logs or commits credentials
