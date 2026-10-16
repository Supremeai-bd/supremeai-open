// monitor.test.mjs — offline harness for the vscode agent monitor (issue #333).
//
// node:test against the COMPILED pure modules (dist/): status transitions,
// fail-closed frame validation, seq-gap resync, reconnect backoff, bounded
// buffer, and a fake-socket reconnect simulation. The vscode layer is never
// imported (it is type-checked by npm run compile, not executed here).
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const dist = join(here, "..", "dist");

const statusLogic = require(join(dist, "statusLogic.js"));
const resilience = require(join(dist, "resilience.js"));
const { ReconnectingTransport } = require(join(dist, "wsTransport.js"));

const T0 = "2026-10-16T09:30:00Z";

function eventFrame(seq, event, payload = {}, taskId = "task-333") {
  return { frame_type: "event", seq, timestamp: T0, event, task_id: taskId, agent_id: "agent-1", payload };
}

function heartbeatFrame(seq) {
  return { frame_type: "heartbeat", seq, timestamp: T0, heartbeat: { kind: "ping", interval_seconds: 30 } };
}

// ---------------------------------------------------------------------------
// AC1: status transitions (idle | busy | error)
// ---------------------------------------------------------------------------

test("status: idle -> busy -> idle across a lifecycle", () => {
  const validatorState = { lastSeq: null };
  let state = statusLogic.initialState();
  const feed = (frame) => {
    const v = statusLogic.validateFrame(frame, validatorState);
    assert.equal(v.kind, "accepted", v.reason);
    validatorState.lastSeq = v.frame.seq;
    state = statusLogic.reduceEvent(state, v.frame);
    return state;
  };
  state = feed(eventFrame(0, "agent:started", { goal: "ship it" }));
  assert.equal(state.status, "busy");
  assert.equal(state.currentTask, "task-333");
  state = feed(eventFrame(1, "agent:thought", { content: "thinking" }));
  assert.equal(state.status, "busy");
  state = feed(eventFrame(2, "tool:invoking", { tool: "repo_read" }));
  state = feed(eventFrame(3, "tool:result", { tool: "repo_read", status: "ok" }));
  state = feed(eventFrame(4, "agent:done", {}));
  assert.equal(state.status, "idle");
  const view = statusLogic.statusBarView(state);
  assert.equal(view.status, "idle");
  assert.match(view.text, /idle/);
});

test("status: agent:error sticks until the next agent:started", () => {
  const vs = { lastSeq: null };
  let state = statusLogic.initialState();
  const feed = (frame) => {
    const v = statusLogic.validateFrame(frame, vs);
    vs.lastSeq = v.frame?.seq ?? vs.lastSeq;
    if (v.kind === "accepted") state = statusLogic.reduceEvent(state, v.frame);
    return v;
  };
  feed(eventFrame(0, "agent:started", { goal: "g" }));
  feed(eventFrame(1, "agent:error", { error_code: "upstream_down", message: "provider chain exhausted", retryable: true }));
  assert.equal(state.status, "error");
  const view = statusLogic.statusBarView(state);
  assert.equal(view.status, "error");
  assert.match(view.text, /error/);
  assert.match(view.tooltip, /upstream_down/);
  // a new start clears the error
  feed(eventFrame(2, "agent:started", { goal: "retry" }));
  assert.equal(state.status, "busy");
});

// ---------------------------------------------------------------------------
// Fail-closed frame validation (poka-yoke per the spec)
// ---------------------------------------------------------------------------

test("validate: malformed frames are dropped with reasons", () => {
  const vs = { lastSeq: null };
  const drops = [
    null,
    "not an object",
    [],
    { frame_type: "other", seq: 0, timestamp: T0 },
    { frame_type: "event", seq: -1, timestamp: T0, event: "agent:done" },
    { frame_type: "event", seq: 0, timestamp: "yesterday", event: "agent:done" },
    { frame_type: "event", seq: 0, timestamp: T0, event: "agent:dancing" },
    { frame_type: "event", seq: 0, timestamp: T0, event: "agent:done", task_id: "not-a-task-id" },
    { frame_type: "event", seq: 0, timestamp: T0, event: "agent:started", task_id: "task-1", payload: [] },
    { frame_type: "event", seq: 0, timestamp: T0, event: "agent:started", task_id: "task-1", payload: {} },
    { frame_type: "event", seq: 0, timestamp: T0, event: "tool:invoking", task_id: "task-1", payload: {} },
    { frame_type: "event", seq: 0, timestamp: T0, event: "tool:result", task_id: "task-1", payload: { tool: "x", status: "weird" } },
    { frame_type: "event", seq: 0, timestamp: T0, event: "agent:error", task_id: "task-1", payload: { error_code: "e" } },
    { frame_type: "heartbeat", seq: 0, timestamp: T0 },
  ];
  for (const raw of drops) {
    const v = statusLogic.validateFrame(raw, vs);
    assert.equal(v.kind, "dropped", `expected drop for ${JSON.stringify(raw)}`);
    assert.equal(v.frame, undefined);
  }
});

test("validate: seq gap triggers resync (spec MUST)", () => {
  const vs = { lastSeq: 5 };
  const v = statusLogic.validateFrame(eventFrame(9, "agent:done"), vs);
  assert.equal(v.kind, "resync");
  assert.match(v.reason, /gap/);
});

// ---------------------------------------------------------------------------
// AC3: backoff + bounded buffer
// ---------------------------------------------------------------------------

test("backoff: exponential with cap and reset", () => {
  const b = new resilience.ReconnectBackoff(1000, 60_000, () => 0); // jitter=0 deterministic
  const delays = [b.next(), b.next(), b.next()];
  assert.deepEqual(delays, [1000, 2000, 4000]);
  for (let i = 0; i < 20; i++) b.next();
  assert.equal(b.next(), 60_000); // capped
  b.reset();
  assert.equal(b.next(), 1000); // reset to base
});

test("backoff: fail-closed constructor", () => {
  assert.throws(() => new resilience.ReconnectBackoff(0, 1000));
  assert.throws(() => new resilience.ReconnectBackoff(2000, 1000));
});

test("buffer: bounded, drops oldest with explicit marker", () => {
  const buf = new resilience.BoundedOutputBuffer(10);
  for (let i = 0; i < 25; i++) buf.push(`line-${i}`);
  assert.equal(buf.size, 10);
  const out = buf.drain();
  assert.equal(out[0], resilience.TRUNCATION_MARKER);
  assert.equal(out.length, 11);
  assert.equal(out[out.length - 1], "line-24");
  // drained buffer resets
  assert.equal(buf.size, 0);
  assert.throws(() => new resilience.BoundedOutputBuffer(5));
});

// ---------------------------------------------------------------------------
// Transport simulation: reconnect + resync + never-throws (AC3)
// ---------------------------------------------------------------------------

class FakeSocket {
  constructor() {
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    this.onclose = null;
    this.closed = false;
    this.sent = [];
  }
  close() { this.closed = true; if (this.onclose) this.onclose(); }
  send(data) { this.sent.push(data); }
  emit(data) { if (this.onmessage) this.onmessage({ data }); }
  fail(err) { if (this.onerror) this.onerror(err); if (this.onclose) this.onclose(); }
}

test("transport: frames pump, statuses derive, drops are logged not thrown", () => {
  const sockets = [];
  const notes = [];
  const frames = [];
  const transport = new ReconnectingTransport("ws://mock", () => {
    const s = new FakeSocket();
    sockets.push(s);
    return s;
  }, {
    onFrame: (f, m) => frames.push({ f, m }),
    onOutput: () => {},
    onStatusNote: (n) => notes.push(n),
    onResync: (r) => notes.push(`RESYNC ${r}`),
  });
  transport.start();
  assert.equal(sockets.length, 1);
  sockets[0].emit(JSON.stringify(eventFrame(0, "agent:started", { goal: "go" })));
  sockets[0].emit(JSON.stringify({ garbage: true }));
  sockets[0].emit(JSON.stringify(heartbeatFrame(1)));
  assert.equal(frames.length, 2); // garbage dropped silently into notes
  assert.equal(transport.state.status, "busy");
  assert.ok(notes.some((n) => n.startsWith("frame dropped")));
  transport.dispose();
});

test("transport: server close schedules a backoff reconnect (no freeze)", () => {
  let timers = [];
  const origSet = globalThis.setTimeout;
  globalThis.setTimeout = ((fn, ms) => { timers.push(ms); return origSet(() => {}, 0); });
  try {
    const sockets = [];
    const transport = new ReconnectingTransport("ws://mock", () => {
      const s = new FakeSocket();
      sockets.push(s);
      return s;
    }, { onFrame: () => {}, onOutput: () => {}, onStatusNote: () => {}, onResync: () => {} },
       new resilience.ReconnectBackoff(1000, 60_000, () => 0));
    transport.start();
    sockets[0].onclose(); // server closed
    assert.deepEqual(timers, [1000]); // scheduled, not thrown
    transport.dispose();
    assert.ok(timers.length >= 1);
  } finally {
    globalThis.setTimeout = origSet;
  }
});

test("transport: factory throwing is contained (never sync-throws into host)", () => {
  const transport = new ReconnectingTransport("ws://mock", () => {
    throw new Error("no websocket runtime");
  }, { onFrame: () => {}, onOutput: () => {}, onStatusNote: () => {}, onResync: () => {} });
  assert.doesNotThrow(() => transport.start());
  transport.dispose();
});

test("output: every event renders a channel line (AC2)", () => {
  const lines = [
    statusLogic.outputLine(eventFrame(0, "agent:started", { goal: "ship" })),
    statusLogic.outputLine(eventFrame(1, "agent:thought", { content: "hmm", truncated: true })),
    statusLogic.outputLine(eventFrame(2, "tool:invoking", { tool: "t", invocation_id: "inv-1" })),
    statusLogic.outputLine(eventFrame(3, "tool:result", { tool: "t", status: "ok", duration_ms: 42 })),
    statusLogic.outputLine(eventFrame(4, "agent:done", {})),
    statusLogic.outputLine(eventFrame(5, "agent:error", { error_code: "e", message: "m", retryable: false })),
    statusLogic.outputLine(heartbeatFrame(6)),
  ];
  assert.match(lines[0], /START/);
  assert.match(lines[1], /truncated/);
  assert.match(lines[2], /inv=inv-1/);
  assert.match(lines[3], /42ms/);
  assert.match(lines[4], /DONE/);
  assert.match(lines[5], /ERROR/);
  assert.match(lines[6], /heartbeat/);
});
