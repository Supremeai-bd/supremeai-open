/**
 * wsTransport.ts — reconnecting WebSocket transport (issue #333 AC3).
 *
 * The vscode WebSocket factory is INJECTED (extension layer may wire the
 * 'ws' package or a global); tests inject a fake. Contract:
 *  - callbacks only — the transport never throws synchronously into the
 *    extension host (an unhandled throw here would freeze the window);
 *  - every incoming message goes through validateFrame (fail-closed);
 *  - seq-gap verdicts surface as onResync and the transport reconnects;
 *  - server close / error -> backoff reconnect (unless dispose()d).
 */

import { ReconnectBackoff } from "./resilience";
import { validateFrame, type StatusFrame, type MonitorState } from "./statusLogic";

export interface WsLike {
  close(): void;
  send(data: string): void;
  onmessage: ((ev: { data: unknown }) => void) | null;
  onerror: ((err: unknown) => void) | null;
  onclose: (() => void) | null;
  onopen: (() => void) | null;
}

export type WsFactory = (url: string) => WsLike;

export interface TransportHandlers {
  onFrame: (frame: StatusFrame, state: MonitorState) => void;
  onOutput: (line: string) => void;
  onStatusNote: (note: string) => void;
  onResync: (reason: string) => void;
}

export class ReconnectingTransport {
  private disposed = false;
  private ws: WsLike | null = null;
  private backoff: ReconnectBackoff;
  private monitor: MonitorState;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSeq: number | null = null;

  constructor(
    private readonly url: string,
    private readonly wsFactory: WsFactory,
    private readonly handlers: TransportHandlers,
    backoff?: ReconnectBackoff,
  ) {
    this.backoff = backoff ?? new ReconnectBackoff();
    this.monitor = { status: "idle", currentTask: null, lastEvent: null, lastSeq: null, errorSummary: null };
  }

  get state(): MonitorState {
    return this.monitor;
  }

  get isConnected(): boolean {
    return this.ws !== null && this.reconnectTimer === null;
  }

  start(): void {
    if (this.disposed) return;
    this.open();
  }

  dispose(): void {
    this.disposed = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      try { ws.onclose = null; ws.close(); } catch { /* best-effort dispose */ }
    }
  }

  private open(): void {
    if (this.disposed) return;
    let ws: WsLike;
    try {
      ws = this.wsFactory(this.url);
    } catch (err) {
      this.handlers.onStatusNote(`websocket factory failed: ${String(err)}`);
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.backoff.reset();
      this.handlers.onStatusNote(`connected: ${this.url}`);
    };
    ws.onmessage = (ev) => this.ingest(ev.data);
    ws.onerror = (err) => {
      this.handlers.onStatusNote(`websocket error: ${String(err)}`);
    };
    ws.onclose = () => {
      this.ws = null;
      if (!this.disposed) {
        this.handlers.onStatusNote("connection closed - reconnecting with backoff");
        this.scheduleReconnect();
      }
    };
  }

  /** Feed one raw message through the fail-closed frame validator. */
  ingest(raw: unknown): void {
    let parsed = raw;
    if (typeof raw === "string" || (raw && typeof (raw as { byteLength?: unknown }).byteLength === "number")) {
      try {
        parsed = JSON.parse(String(raw));
      } catch {
        this.handlers.onStatusNote("frame dropped: message is not valid JSON");
        return;
      }
    }
    const verdict = validateFrame(parsed, { lastSeq: this.lastSeq });
    if (verdict.kind === "dropped") {
      this.handlers.onStatusNote(`frame dropped: ${verdict.reason}`);
      return;
    }
    if (verdict.kind === "resync") {
      this.lastSeq = null;
      this.handlers.onResync(verdict.reason);
      // Spec: a receiver seeing a gap MUST resync. Reconnect (fresh seq
      // space) rather than replaying stale state.
      if (this.ws) {
        const ws = this.ws;
        this.ws = null;
        try { ws.onclose = null; ws.close(); } catch { /* closing for resync */ }
      }
      this.scheduleReconnect();
      return;
    }
    this.lastSeq = verdict.frame.seq;
    this.monitor = reduceSafe(this.monitor, verdict.frame);
    this.handlers.onFrame(verdict.frame, this.monitor);
  }

  private scheduleReconnect(): void {
    if (this.disposed || this.reconnectTimer !== null) return;
    const delay = this.backoff.next();
    this.handlers.onStatusNote(`reconnect in ${delay}ms (attempt ${this.backoff.attempts})`);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.open();
    }, delay);
  }
}

import { reduceEvent } from "./statusLogic";
function reduceSafe(state: MonitorState, frame: StatusFrame): MonitorState {
  try {
    return reduceEvent(state, frame);
  } catch {
    return state; // reducer must never break the pump (AC3)
  }
}
