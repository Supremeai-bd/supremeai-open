/**
 * statusLogic.ts — PURE status-bar state machine (issue #333 AC1).
 *
 * Consumes validated websocket-events frames (WEBSOCKET_SPEC.md section 1)
 * and derives the agent status: idle | busy | error. Zero vscode imports —
 * fully unit-testable offline; the extension layer only renders the state.
 *
 * Frame validation is fail-closed per the spec's poka-yoke clause: a frame
 * whose envelope fields are malformed is DROPPED (with a reason), never
 * half-interpreted. Seq gaps trigger a RESYNC signal (spec: a receiver
 * seeing a gap MUST resync rather than replay stale state).
 */

export type AgentStatus = "idle" | "busy" | "error";

export interface StatusFrame {
  frame_type: "event" | "heartbeat";
  seq: number;
  timestamp: string;
  event?: string;
  task_id?: string;
  agent_id?: string;
  payload?: unknown;
  heartbeat?: { kind?: string; interval_seconds?: number; timeout_seconds?: number };
}

export const EVENT_NAMES = [
  "agent:started",
  "agent:thought",
  "tool:invoking",
  "tool:result",
  "agent:done",
  "agent:error",
] as const;

export type FrameVerdict =
  | { kind: "accepted"; frame: StatusFrame }
  | { kind: "dropped"; reason: string }
  | { kind: "resync"; reason: string };

const RFC3339_RE = /^\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})$/;
const TASK_ID_RE = /^task-[a-zA-Z0-9_-]{1,64}$/;

/** Validate one raw frame against the WEBSOCKET_SPEC envelope contract. */
export function validateFrame(raw: unknown, state: { lastSeq: number | null }): FrameVerdict {
  if (raw === null || typeof raw !== "object" || Array.isArray(raw)) {
    return { kind: "dropped", reason: "frame is not a JSON object" };
  }
  const f = raw as Record<string, unknown>;
  if (f.frame_type !== "event" && f.frame_type !== "heartbeat") {
    return { kind: "dropped", reason: `frame_type '${String(f.frame_type)}' not in enum` };
  }
  if (typeof f.seq !== "number" || !Number.isInteger(f.seq) || f.seq < 0) {
    return { kind: "dropped", reason: "seq must be an integer >= 0" };
  }
  if (typeof f.timestamp !== "string" || !RFC3339_RE.test(f.timestamp)) {
    return { kind: "dropped", reason: "timestamp must be RFC 3339 UTC" };
  }
  // Ordering: seq increases by 1 per connection (spec section 1). A gap is
  // the client's resync signal — never replay stale state over it.
  if (state.lastSeq !== null && f.seq > state.lastSeq + 1) {
    return { kind: "resync", reason: `seq gap ${state.lastSeq} -> ${f.seq}` };
  }
  if (f.frame_type === "heartbeat") {
    const hb = f.heartbeat;
    if (hb === null || typeof hb !== "object" ||
        (hb as { kind?: unknown }).kind !== "ping" && (hb as { kind?: unknown }).kind !== "pong") {
      return { kind: "dropped", reason: "heartbeat frames carry a ping/pong body" };
    }
    return { kind: "accepted", frame: f as unknown as StatusFrame };
  }
  // event frame: event tag + payload pinning
  const event = f.event;
  if (typeof event !== "string" || !(EVENT_NAMES as readonly string[]).includes(event)) {
    return { kind: "dropped", reason: `event '${String(event)}' not in the 6-value catalog` };
  }
  if (typeof f.task_id !== "string" || !TASK_ID_RE.test(f.task_id)) {
    return { kind: "dropped", reason: "event frames carry a task-<id> task_id" };
  }
  if (f.payload !== undefined && (f.payload === null || typeof f.payload !== "object" || Array.isArray(f.payload))) {
    return { kind: "dropped", reason: "payload must be an object when present" };
  }
  const p = (f.payload ?? {}) as Record<string, unknown>;
  switch (event) {
    case "agent:started":
      if (typeof p.goal !== "string" || p.goal.length === 0) {
        return { kind: "dropped", reason: "agent:started requires payload.goal" };
      }
      break;
    case "agent:thought":
      if (typeof p.content !== "string") {
        return { kind: "dropped", reason: "agent:thought requires payload.content" };
      }
      break;
    case "tool:invoking":
      if (typeof p.tool !== "string") {
        return { kind: "dropped", reason: "tool:invoking requires payload.tool" };
      }
      break;
    case "tool:result":
      if (typeof p.tool !== "string" || (p.status !== "ok" && p.status !== "error")) {
        return { kind: "dropped", reason: "tool:result requires payload.tool + status ok|error" };
      }
      break;
    case "agent:error":
      if (typeof p.error_code !== "string" || typeof p.message !== "string" || typeof p.retryable !== "boolean") {
        return { kind: "dropped", reason: "agent:error requires error_code + message + retryable" };
      }
      break;
    // agent:done has only optional fields
  }
  return { kind: "accepted", frame: f as unknown as StatusFrame };
}

export interface StatusBarView {
  status: AgentStatus;
  text: string; // includes the icon glyph prefix (no emoji, editor-safe)
  tooltip: string;
}

/**
 * Derive the status-bar view from the running state.
 * AC1: idle, busy, error — with honest last-event context in the tooltip.
 */
export function statusBarView(state: MonitorState): StatusBarView {
  switch (state.status) {
    case "busy":
      return {
        status: "busy",
        text: `$(sync~spin) SupremeAI: busy`,
        tooltip: `Task ${state.currentTask ?? "?"} — last event ${state.lastEvent ?? "-"} (seq ${state.lastSeq ?? "-"})`,
      };
    case "error":
      return {
        status: "error",
        text: `$(error) SupremeAI: error`,
        tooltip: `Last failure: ${state.errorSummary ?? "agent:error"} (seq ${state.lastSeq ?? "-"})`,
      };
    default:
      return {
        status: "idle",
        text: `$(circle-slash) SupremeAI: idle`,
        tooltip: "No active agent task.",
      };
  }
}

export interface MonitorState {
  status: AgentStatus;
  currentTask: string | null;
  lastEvent: string | null;
  lastSeq: number | null;
  errorSummary: string | null;
}

export function initialState(): MonitorState {
  return { status: "idle", currentTask: null, lastEvent: null, lastSeq: null, errorSummary: null };
}

/**
 * Reduce one ACCEPTED event frame into the monitor state.
 * Terminal frames end a task (done -> idle, error -> error sticky until the
 * next agent:started).
 */
export function reduceEvent(state: MonitorState, frame: StatusFrame): MonitorState {
  if (frame.frame_type === "heartbeat") {
    return { ...state, lastSeq: frame.seq };
  }
  const next: MonitorState = {
    ...state,
    lastSeq: frame.seq,
    lastEvent: frame.event ?? null,
  };
  switch (frame.event) {
    case "agent:started":
      return { ...next, status: "busy", currentTask: frame.task_id ?? null, errorSummary: null };
    case "agent:thought":
    case "tool:invoking":
    case "tool:result":
      return next; // busy persists (started required first per lifecycle)
    case "agent:done":
      return { ...next, status: "idle", currentTask: null };
    case "agent:error": {
      const p = (frame.payload ?? {}) as { error_code?: string; message?: string };
      return {
        ...next,
        status: "error",
        errorSummary: `${p.error_code ?? "error"}: ${(p.message ?? "").slice(0, 120)}`,
      };
    }
    default:
      return next;
  }
}

/** Render one accepted frame as an OutputChannel line (AC2). */
export function outputLine(frame: StatusFrame): string {
  const t = frame.timestamp;
  if (frame.frame_type === "heartbeat") {
    return `${t} heartbeat ${frame.heartbeat?.kind ?? "ping"}`;
  }
  const p = (frame.payload ?? {}) as Record<string, unknown>;
  switch (frame.event) {
    case "agent:started":
      return `${t} START  ${frame.task_id} goal: ${String(p.goal).slice(0, 80)}`;
    case "agent:thought":
      return `${t} THINK  ${String(p.content).slice(0, 200)}${p.truncated ? " (truncated)" : ""}`;
    case "tool:invoking":
      return `${t} CALL   ${String(p.tool)}${p.invocation_id ? ` inv=${String(p.invocation_id)}` : ""}`;
    case "tool:result":
      return `${t} RESULT ${String(p.tool)} status=${String(p.status)}${p.duration_ms ? ` (${String(p.duration_ms)}ms)` : ""}`;
    case "agent:done":
      return `${t} DONE   ${frame.task_id}`;
    case "agent:error":
      return `${t} ERROR  ${String(p.error_code)}: ${String(p.message).slice(0, 160)}`;
    default:
      return `${t} event  ${String(frame.event)}`;
  }
}
