# WebSocket Spec — Live Agent Execution Event Stream

Wire specification for streaming live agent execution (thoughts, tool calls,
outputs) over WebSocket. The frame format is SSOT'd in
[`api-schemas/websocket-events.schema.json`](../api-schemas/websocket-events.schema.json).

> **Contract-first note:** the MCP Tower currently serves the transports
> documented in [`docs/MCP_CONNECT.md`](MCP_CONNECT.md) (Streamable HTTP + SSE).
> This document pins the **live event stream wire format** so Tower servers and
> clients can adopt WebSocket without renegotiating the contract.

---

## 1. Frame envelope

One JSON object per WebSocket message. Every frame carries:

| Field | Type | Always | Description |
|---|---|---|---|
| `frame_type` | `"event"` \| `"heartbeat"` | ✅ | Frame discriminator |
| `seq` | integer ≥ 0 | ✅ | **Monotonically increasing** per connection |
| `timestamp` | RFC 3339 UTC | ✅ | Server emission instant — the ordering authority |
| `event` | 6-value enum | event only | Which execution event this is |
| `task_id` | `task-<id>` | event only | Task whose execution is streaming |
| `agent_id` | `agent-<id>` | event only | Emitting agent |
| `payload` | object | event only | Shape pinned to the event tag (see §2) |
| `heartbeat` | object | heartbeat only | ping/pong body (see §3) |

**Ordering guarantee:** `seq` increases by 1 per frame on a connection.
A receiver seeing a gap (`seq` jumps) MUST trigger a resync (reconnect or
snapshot request) rather than replaying stale state. `timestamp` breaks ties
across connections; within one connection `seq` is authoritative.

**Payload pinning (poka-yoke):** each `event` tag admits exactly one payload
shape — e.g. a `tool:invoking` frame carrying an error payload is
structurally invalid and rejected by the schema.

---

## 2. Event catalog

| Event | Meaning | Payload (required fields) |
|---|---|---|
| `agent:started` | Agent begins working the task | `goal`; optional `mode`, `attempt` |
| `agent:thought` | Streaming thought narration | `content` (≤8192 chars, truncatable, `truncated` flag); optional `step` |
| `tool:invoking` | Tool call about to dispatch | `tool`; optional `arguments_digest`, `invocation_id` |
| `tool:result` | Tool call completed | `tool`, `status` (`ok`/`error`); optional `invocation_id`, `duration_ms`, `summary` |
| `agent:done` | Terminal success — stream ends | optional `summary`, `artifacts` |
| `agent:error` | Terminal failure — stream ends | `error_code`, `message`, `retryable` |

Correlation: pair `tool:invoking` ↔ `tool:result` via `invocation_id`.
Terminal frames (`agent:done` / `agent:error`) are final: servers close or
drain the stream after emitting one; clients MUST NOT expect further events
for the same `task_id` on the stream.

### 2.1 Example event frame

```json
{
  "frame_type": "event",
  "event": "tool:result",
  "seq": 42,
  "timestamp": "2026-02-14T09:30:12Z",
  "task_id": "task-40",
  "agent_id": "agent-1",
  "payload": {
    "tool": "repo_read",
    "status": "ok",
    "invocation_id": "inv-771f2c",
    "duration_ms": 340,
    "summary": "read 2 files"
  }
}
```

---

## 3. Heartbeat protocol (ping/pong)

Keepalives share the envelope under `frame_type: "heartbeat"`:

```json
{ "frame_type": "heartbeat", "seq": 7, "timestamp": "2026-02-14T09:30:30Z",
  "heartbeat": { "kind": "ping", "interval_seconds": 30, "timeout_seconds": 60 } }
```

Rules:

1. The **client sends `kind: "ping"`** on the negotiated cadence
   (`interval_seconds`, 5–300 s).
2. The **server answers `kind: "pong"`** echoing the ping's `seq`.
3. If no pong arrives within `timeout_seconds` (5–600 s), the connection is
   dead → close it and follow §4 (reconnect with backoff).
4. Heartbeats occupy the same `seq` space as events — gaps mean lost frames
   regardless of kind.
5. Note for operators: WebSocket protocol-level ping/pong (RFC 6455 control
   frames) may run in parallel; the JSON heartbeat exists so that proxies and
   thin clients that surface only data frames stay observable.

---

## 4. Connection and reconnection rules

1. **Connect** to the Tower's WebSocket endpoint with `?client=<your-unique-name>`
   (identity rules identical to [`docs/MCP_CONNECT.md` §1](MCP_CONNECT.md):
   anonymous → viewer; role adopts only with a live-verified credential).
2. **Subscribe** by task: send
   `{"action":"subscribe","task_id":"task-<id>"}`; the server then streams
   that task's frames on this connection.
3. **Resync on gap:** on `seq` discontinuity, close and reconnect; after
   reconnect, re-subscribe and reconcile state from terminal frames or the
   task API.
4. **Backoff:** reconnect with exponential backoff + jitter (start 1 s, cap
   60 s). Honor `429`/`Retry-After` from HTTP upgrade failures — the Tower's
   rate limiter is per-IP and hot-looping hurts every agent behind your
   egress IP.
5. **Cleanup:** unsubscribe/close cleanly on shutdown; do not leak ghost
   subscriptions.

### 4.1 Minimal browser client (JS)

```js
const ws = new WebSocket("wss://supremeai-mcp-tower.onrender.com/ws?client=demo-web");
ws.onopen = () => ws.send(JSON.stringify({ action: "subscribe", task_id: "task-40" }));
ws.onmessage = (ev) => {
  const frame = JSON.parse(ev.data);
  if (frame.frame_type === "heartbeat" && frame.heartbeat.kind === "ping") {
    ws.send(JSON.stringify({ ...frame, heartbeat: { ...frame.heartbeat, kind: "pong" } }));
    return;
  }
  if (frame.seq !== (lastSeq ?? frame.seq) && lastSeq !== undefined && frame.seq !== lastSeq + 1) {
    // gap → resync per §4.3
  }
  lastSeq = frame.seq;
  if (frame.frame_type === "event") console.log(frame.event, frame.payload);
};
```

### 4.2 Minimal stdlib-oriented Python sketch

```python
# zero-extra-deps sketch: any RFC 6455 client works; the wire contract is
# plain JSON text messages validated against websocket-events.schema.json.
import json, websocket  # pip install websocket-client — transport only

ws = websocket.create_connection(
    "wss://supremeai-mcp-tower.onrender.com/ws?client=demo-py"
)
ws.send(json.dumps({"action": "subscribe", "task_id": "task-40"}))
for raw in ws:
    frame = json.loads(raw)
    ...  # handle heartbeat pong echo + seq-gap resync per §3/§4
```

---

## 5. Validation

Frames are JSON Schema (Draft 2020-12) instances of
`api-schemas/websocket-events.schema.json`. Emitting servers SHOULD validate
before send; clients MUST fail-closed on frames that do not validate
(log, drop, resync — never guess).
