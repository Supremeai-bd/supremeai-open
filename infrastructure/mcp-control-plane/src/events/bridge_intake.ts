/**
 * #69 — Event-driven bridge intake.
 *
 * Connects the already-deployed `/webhooks/github` route (validated, signed,
 * normalized, dispatched through the existing EventGateway) to the active
 * bridge-intake polling workflow, so new work wakes the agent loop in seconds
 * instead of waiting for the next cron tick.
 *
 * Design constraints (issue #69):
 *  - NO second event bus / NO duplicate webhook endpoint: this module is a
 *    gateway listener on the existing normalizer→gateway pipeline.
 *  - The webhook acknowledgement NEVER waits on downstream work: filtering +
 *    dedupe + outbox append are synchronous and O(1); the GitHub
 *    workflow-dispatch call runs asynchronously afterwards.
 *  - Durability: a JSONL outbox persists every accepted event before it is
 *    dispatched; pending entries are replayed on boot with bounded exponential
 *    backoff and a dead-letter state after maxAttempts.
 *  - Idempotency: redeliveries are collapsed by `X-GitHub-Delivery` id AND by
 *    an event composite key (repo:type:number:action) within a TTL window.
 *  - Least privilege: uses the server-side GITHUB_TOKEN only, never exposed
 *    to webhook callers; nothing from the payload is logged (no secrets).
 *  - Fail-closed: disabled by default (BRIDGE_INTAKE_ENABLED=true to arm),
 *    unknown events/repos/actions are dropped with a reason, and the cron
 *    polling workflow stays in place as the reconciliation fallback.
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import type { NormalizedEvent } from "./normalizer.js";
import { globalEventGateway } from "./gateway.js";
import { env } from "../lib/env.js";

export interface BridgeIntakeConfig {
  /** Master switch — fail-closed. Armed only via BRIDGE_INTAKE_ENABLED=true. */
  enabled: boolean;
  /** Repo owning the polling workflow (default: Supremeai-bd/supremeai-open). */
  repo: string;
  /** Workflow filename for the dispatch API (default: pipeline.yml). */
  workflow: string;
  /** Git ref to dispatch against (default: main). */
  ref: string;
  /** Minimum interval between two actual dispatches (rate limit). */
  minIntervalMs: number;
  /** Outbox retry ceiling before dead-letter. */
  maxAttempts: number;
  /** Durable JSONL outbox path. */
  outboxPath: string;
  /** Server-side GitHub token (workflow scope). Never logged. */
  token?: string;
}

export interface DispatchRequest {
  repo: string;
  workflow: string;
  ref: string;
  inputs: Record<string, unknown>;
}

export type DispatchFn = (req: DispatchRequest, token?: string) => Promise<{ ok: boolean; status: number }>;

export interface OutboxEntry {
  id: string;
  eventKey: string;
  deliveryId?: string;
  createdAt: string;
  status: "pending" | "done" | "dead";
  attempts: number;
  nextAttemptAt: string;
  dispatch: DispatchRequest;
  lastError?: string;
  dispatchedAt?: string;
  /** Measured webhook-to-dispatch latency (enqueue → 2xx from GitHub API). */
  latencyMs?: number;
}

export interface IntakeDecision {
  accept: boolean;
  reason: string;
  eventKey?: string;
}

/** Issue actions that represent new/re-queued work worth waking the loop for. */
const WAKE_ISSUE_ACTIONS = new Set(["opened", "reopened", "labeled"]);
const WAKE_PR_ACTIONS = new Set(["opened", "reopened", "synchronize"]);
const WAKE_COMMENT_ACTIONS = new Set(["created"]);

const DEDUPE_TTL_MS = 30 * 60 * 1000; // 30 min
const DEDUPE_MAX = 1024;
const DONE_KEEP = 100; // audit tail of completed entries kept in the outbox file
const BACKOFF_BASE_MS = 5_000;
const BACKOFF_CAP_MS = 15 * 60 * 1000;

export interface BridgeIntakeDeps {
  now?: () => number;
  dispatch?: DispatchFn;
  schedule?: (fn: () => void, ms: number) => unknown;
  log?: (line: string) => void;
}

export class BridgeIntakeService {
  private readonly config: BridgeIntakeConfig;
  private readonly deps: Required<Pick<BridgeIntakeDeps, "now">> & BridgeIntakeDeps;
  private readonly outbox: OutboxEntry[] = [];
  private readonly seenDeliveries = new Map<string, number>();
  private readonly seenEventKeys = new Map<string, number>();
  private lastDispatchAt = 0;
  private processing = false;
  private replayed = false;

  constructor(config: BridgeIntakeConfig, deps: BridgeIntakeDeps = {}) {
    this.config = config;
    this.deps = { now: deps.now ?? (() => Date.now()), dispatch: deps.dispatch, schedule: deps.schedule, log: deps.log };
    this.loadOutbox();
  }

  // ── Event relevance policy ────────────────────────────────────────────────

  /** Pure decision: is this normalized event worth a wake-up dispatch? */
  public decide(event: NormalizedEvent): IntakeDecision {
    if (event.source !== "github") return { accept: false, reason: `non-github source: ${event.source}` };
    const payload: any = event.payload ?? {};
    const repoFullName = String(payload?.repository?.full_name ?? "");
    if (!repoFullName) return { accept: false, reason: "missing repository identity" };
    if (this.config.repo && repoFullName.toLowerCase() !== this.config.repo.toLowerCase()) {
      return { accept: false, reason: `repo mismatch: ${repoFullName}` };
    }
    const sender = String(payload?.sender?.login ?? "");
    if (sender.endsWith("[bot]")) return { accept: false, reason: `bot sender: ${sender}` };

    const type = event.type;
    const action = String(payload?.action ?? "");
    if (type === "issues" && WAKE_ISSUE_ACTIONS.has(action)) {
      return { accept: true, reason: `issue.${action}`, eventKey: `issue:${repoFullName}:${payload?.issue?.number ?? "?"}:${action}` };
    }
    if (type === "pull_request" && WAKE_PR_ACTIONS.has(action)) {
      return { accept: true, reason: `pr.${action}`, eventKey: `pr:${repoFullName}:${payload?.pull_request?.number ?? "?"}:${action}` };
    }
    if (type === "issue_comment" && WAKE_COMMENT_ACTIONS.has(action)) {
      return { accept: true, reason: `comment.${action}`, eventKey: `comment:${repoFullName}:${payload?.issue?.number ?? "?"}:${action}` };
    }
    return { accept: false, reason: `unsupported event: ${type}.${action}` };
  }

  // ── Gateway listener ──────────────────────────────────────────────────────

  /**
   * Synchronous, fast listener body (gateway fire-and-forget). Acknowledgement
   * latency is bounded by one outbox append — never by the GitHub API call.
   */
  public handle(event: NormalizedEvent): void {
    if (!this.config.enabled) return; // fail-closed: silently inert unless armed
    const decision = this.decide(event);
    if (!decision.accept) {
      this.log(`[BRIDGE_INTAKE] skip (${decision.reason})`);
      return;
    }
    const deliveryId = event.deliveryId;
    if (deliveryId && this.fresh(this.seenDeliveries, deliveryId)) {
      this.log(`[BRIDGE_INTAKE] dedupe: delivery ${deliveryId} already processed`);
      return;
    }
    const eventKey = decision.eventKey ?? "unknown";
    if (this.fresh(this.seenEventKeys, eventKey)) {
      this.log(`[BRIDGE_INTAKE] dedupe: event ${eventKey} already queued in TTL window`);
      return;
    }
    const entry: OutboxEntry = {
      id: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
      eventKey,
      deliveryId,
      createdAt: new Date(this.deps.now!()).toISOString(),
      status: "pending",
      attempts: 0,
      nextAttemptAt: new Date(this.deps.now!()).toISOString(),
      dispatch: { repo: this.config.repo, workflow: this.config.workflow, ref: this.config.ref, inputs: { auto_pr: false } },
    };
    this.outbox.push(entry);
    this.persist();
    this.log(`[BRIDGE_INTAKE] accepted ${eventKey} (delivery=${deliveryId ?? "n/a"}) → outbox ${entry.id}`);
    this.scheduleProcess();
  }

  // ── Dispatch pipeline ─────────────────────────────────────────────────────

  private async processQueue(): Promise<void> {
    if (this.processing) return;
    this.processing = true;
    try {
      for (;;) {
        const now = this.deps.now!();
        const due = this.outbox.find(
          (e) => e.status === "pending" && new Date(e.nextAttemptAt).getTime() <= now,
        );
        if (!due) break;

        const sinceLast = now - this.lastDispatchAt;
        if (this.lastDispatchAt > 0 && sinceLast < this.config.minIntervalMs) {
          const waitMs = this.config.minIntervalMs - sinceLast;
          due.nextAttemptAt = new Date(this.lastDispatchAt + this.config.minIntervalMs).toISOString();
          this.log(`[BRIDGE_INTAKE] rate-limited ${due.eventKey} → queued until ${due.nextAttemptAt}`);
          this.persist();
          this.scheduleProcess(waitMs); // wake exactly when the interval elapses
          break;
        }

        this.lastDispatchAt = now;
        await this.attemptDispatch(due);
      }
    } finally {
      this.processing = false;
      // Anything scheduled while we ran (retries landing now) gets a next tick.
      const stillDue = this.outbox.some(
        (e) => e.status === "pending" && new Date(e.nextAttemptAt).getTime() <= this.deps.now!(),
      );
      if (stillDue) this.scheduleProcess();
    }
  }

  /**
   * Public reconciliation tick (#69): processes whatever is due right now.
   * Lets an external cron/job drain the outbox without waiting for the next
   * webhook, and gives the test suite deterministic clock control.
   */
  public async tick(): Promise<void> {
    await this.processQueue();
  }

  private async attemptDispatch(entry: OutboxEntry): Promise<void> {
    const started = this.deps.now!();
    const fn = this.deps.dispatch ?? defaultDispatch;
    try {
      const res = await fn(entry.dispatch, this.config.token);
      if (!res.ok) throw new Error(`GitHub dispatch API → HTTP ${res.status}`);
      entry.status = "done";
      entry.dispatchedAt = new Date(this.deps.now!()).toISOString();
      entry.latencyMs = this.deps.now!() - started;
      this.log(`[BRIDGE_INTAKE] dispatched ${entry.eventKey} → ${entry.dispatch.repo}/${entry.dispatch.workflow}@${entry.dispatch.ref} (${entry.latencyMs}ms)`);
    } catch (err: any) {
      entry.attempts += 1;
      entry.lastError = String(err?.message ?? err);
      if (entry.attempts >= this.config.maxAttempts) {
        entry.status = "dead";
        this.log(`[BRIDGE_INTAKE] DEAD-LETTER ${entry.eventKey} after ${entry.attempts} attempts: ${entry.lastError}`);
      } else {
        const backoff = Math.min(BACKOFF_BASE_MS * 2 ** (entry.attempts - 1), BACKOFF_CAP_MS);
        entry.nextAttemptAt = new Date(this.deps.now!() + backoff).toISOString();
        this.log(`[BRIDGE_INTAKE] dispatch failed for ${entry.eventKey} (attempt ${entry.attempts}/${this.config.maxAttempts}) → retry at ${entry.nextAttemptAt}: ${entry.lastError}`);
        this.scheduleProcess(backoff); // self-wake: retries happen even with no new events
      }
    } finally {
      this.persist();
    }
  }

  private scheduleProcess(delayMs = 0): void {
    const schedule = this.deps.schedule ?? ((fn, ms) => setTimeout(fn, ms));
    const timer = schedule(() => { void this.processQueue(); }, delayMs);
    if (timer && typeof (timer as any).unref === "function") (timer as any).unref();
  }

  // ── Durability (JSONL outbox) ─────────────────────────────────────────────

  /** Boot-time replay: pending entries survive process restarts. */
  public replayPending(): number {
    if (this.replayed) return 0;
    this.replayed = true;
    const pending = this.outbox.filter((e) => e.status === "pending");
    if (pending.length > 0) {
      this.log(`[BRIDGE_INTAKE] replaying ${pending.length} pending outbox entr${pending.length === 1 ? "y" : "ies"} after restart`);
      this.scheduleProcess();
    }
    return pending.length;
  }

  private loadOutbox(): void {
    try {
      const path = resolve(this.config.outboxPath);
      if (!existsSync(path)) return;
      const lines = readFileSync(path, "utf8").split("\n").filter((l) => l.trim().length > 0);
      for (const line of lines) {
        try { this.outbox.push(JSON.parse(line) as OutboxEntry); } catch { /* skip torn tail line */ }
      }
    } catch (err: any) {
      this.log(`[BRIDGE_INTAKE] outbox load failed (starting clean): ${err?.message}`);
    }
  }

  /** Atomic snapshot write: tmp file + rename (crash-safe, no torn snapshots). */
  private persist(): void {
    try {
      const path = resolve(this.config.outboxPath);
      mkdirSync(dirname(path), { recursive: true });
      const done = this.outbox.filter((e) => e.status !== "pending").slice(-DONE_KEEP);
      const pending = this.outbox.filter((e) => e.status === "pending");
      const snapshot = [...pending, ...done].map((e) => JSON.stringify(e)).join("\n") + "\n";
      const tmp = `${path}.tmp`;
      writeFileSync(tmp, snapshot, "utf8");
      renameSync(tmp, path);
    } catch (err: any) {
      this.log(`[BRIDGE_INTAKE] outbox persist failed: ${err?.message}`);
    }
  }

  // ── Observability ─────────────────────────────────────────────────────────

  public getStatus(): Record<string, unknown> {
    return {
      enabled: this.config.enabled,
      repo: this.config.repo,
      workflow: this.config.workflow,
      ref: this.config.ref,
      pending: this.outbox.filter((e) => e.status === "pending").length,
      done: this.outbox.filter((e) => e.status === "done").length,
      dead: this.outbox.filter((e) => e.status === "dead").length,
      lastDispatchAt: this.lastDispatchAt > 0 ? new Date(this.lastDispatchAt).toISOString() : null,
    };
  }

  private fresh(map: Map<string, number>, key: string): boolean {
    const now = this.deps.now!();
    for (const [k, ts] of map) if (now - ts > DEDUPE_TTL_MS) map.delete(k);
    while (map.size >= DEDUPE_MAX) map.delete(map.keys().next().value as string);
    if (map.has(key)) return true;
    map.set(key, now);
    return false;
  }

  private log(line: string): void {
    const fn = this.deps.log ?? ((l: string) => console.error(l));
    fn(line);
  }
}

/** Default dispatch: GitHub workflow_dispatch API, server-side token only. */
export const defaultDispatch: DispatchFn = async (req, token) => {
  if (!token) return { ok: false, status: 0 }; // fail-closed: no creds → caller retries → dead-letters visibly
  const res = await fetch(`https://api.github.com/repos/${req.repo}/actions/workflows/${req.workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "SupremeAI-MCP-Control-Tower",
    },
    body: JSON.stringify({ ref: req.ref, inputs: req.inputs }),
  });
  return { ok: res.status === 204, status: res.status };
};

// ── Boot wiring (idempotent) ────────────────────────────────────────────────

let registered = false;

/**
 * Registers the intake service as an EventGateway listener (single call per
 * process). Reads its configuration from env; logs one actionable line when
 * disabled so operators can see why events are not waking the loop.
 */
export function registerBridgeIntake(): void {
  if (registered) return;
  registered = true;
  const cfg = env.bridgeIntake;
  const service = new BridgeIntakeService({
    enabled: cfg.enabled,
    repo: cfg.repo,
    workflow: cfg.workflow,
    ref: cfg.ref,
    minIntervalMs: cfg.minIntervalMs,
    maxAttempts: cfg.maxAttempts,
    outboxPath: cfg.outboxPath,
    token: cfg.token,
  });
  if (!cfg.enabled) {
    console.error("[BRIDGE_INTAKE] disabled (set BRIDGE_INTAKE_ENABLED=true + configure the repo webhook to arm event-driven intake)");
    return;
  }
  globalEventGateway.subscribe((event) => service.handle(event));
  service.replayPending();
  console.error(`[BRIDGE_INTAKE] armed → ${cfg.repo}/${cfg.workflow}@${cfg.ref} (min interval ${cfg.minIntervalMs}ms)`);
}
