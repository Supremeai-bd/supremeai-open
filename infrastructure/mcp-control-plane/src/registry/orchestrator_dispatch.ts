/**
 * Orchestrator dispatch routing engine (issue #1803, #1439 Phase D).
 *
 * বাংলা: event → কোন role দরকার → heartbeat দেখে online agent → task assign।
 *
 * Core design rules (#1439, pre-set):
 * 1. Agent instance বদলায়, role fixed — slot model (AGENT_SLOT_REGISTRY.yaml)
 * 2. Inactive agent → SupremeAI (super lane) fallback → human escalate
 * 3. Max retry = 3 per task, তারপর human escalation
 * 4. Routing decision deterministic + auditable (কেন কোন agent পেলো)
 *
 * Registry-driven (no hardcoded vendor/agent identity): role↔slot mapping is
 * derived from slot-name pool prefixes (coder-N, ci-N, …) and the documented
 * legacy slot table mirrored from AGENT_SLOT_REGISTRY.yaml — overridable via
 * the ORCHESTRATOR_ROLE_POOLS env JSON without code changes.
 */

import { env } from "../lib/env.js";
import {
  activeAccountChain,
  RedisQuotaExhaustedError,
  responseIndicatesQuotaExhaustion,
  runWithAccountChain,
} from "../lib/redis_chain.js";
import {
  listHeartbeats,
  type HeartbeatStatusEntry,
} from "./agent_heartbeat.js";

export const ORCHESTRATE_STATE_PREFIX = "supremeai:orchestrate:";
export const STATE_TTL_SECONDS = 30 * 24 * 3600; // 30 days of task history
export const MAX_RETRIES = 3;
/** F3: assignments older than this are considered abandoned (state TTL is 30d). */
export const ASSIGNMENT_FRESH_WINDOW_SECONDS = 24 * 3600;

/** Deterministic event → required lane map (Phase C event set). */
export const ROLE_EVENT_MAP: Record<string, string> = {
  "issues.opened": "planner",
  "pull_request.opened": "pr-helper",
  "workflow_run.failure": "ci",
};

/**
 * Legacy slot → lane table — MIRRORED from docs/master_docs/AGENT_SLOT_REGISTRY.yaml
 * (legacy_migration_target pools). Overridable via ORCHESTRATOR_ROLE_POOLS env JSON
 * ({"coder": ["agent-3", "agent-6"], ...}) so governance changes need no code edit.
 */
export const LEGACY_SLOT_ROLES: Record<string, string> = {
  "agent-1": "planner",
  "agent-2": "pr-helper",
  "agent-3": "coder",
  "agent-5": "ci",
  "agent-6": "coder",
  "agent-7": "coder",
  "agent-8": "pr-helper",
  "agent-11": "platform",
  "agent-12": "ci",
  "agent-13": "browser",
};

const POOL_PREFIX_ROLES: Array<[RegExp, string]> = [
  [/^planner-\d+$/, "planner"],
  [/^coder-\d+$/, "coder"],
  [/^ci-\d+$/, "ci"],
  [/^pr-helper-\d+$/, "pr-helper"],
  [/^browser-\d+$/, "browser"],
  [/^platform-\d+$/, "platform"],
  [/^super-\d+$/, "super"],
  [/^(z\.ai|claude|chatgpt|cursor|gemini|copilot)-\d+$/, "coder"],
];

/** Resolve a slot id to its lane — pool prefix first, then legacy table. */
export function roleFromSlot(slot: string, overrides?: Record<string, string[]>): string | null {
  for (const [pattern, role] of POOL_PREFIX_ROLES) {
    if (pattern.test(slot)) return role;
  }
  if (overrides) {
    for (const [role, slots] of Object.entries(overrides)) {
      if (slots.includes(slot)) return role;
    }
  }
  return LEGACY_SLOT_ROLES[slot] ?? null;
}

export function loadRolePoolOverrides(): Record<string, string[]> | undefined {
  const raw = process.env.ORCHESTRATOR_ROLE_POOLS;
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw) as Record<string, string[]>;
    return typeof parsed === "object" && parsed !== null ? parsed : undefined;
  } catch {
    return undefined;
  }
}

/** Map a normalized webhook event to its required lane (deterministic). */
export function roleForEvent(event: string, action: string, handoffLabel?: string | null): string | null {
  if (event === "issues" && action === "labeled" && handoffLabel?.startsWith("handoff:")) {
    return handoffLabel.slice("handoff:".length).toLowerCase();
  }
  return ROLE_EVENT_MAP[`${event}.${action}`] ?? null;
}

export type RouteDecision = {
  decision: "assigned" | "fallback" | "escalate" | "no-candidate";
  assignedSlot: string | null;
  role: string | null;
  reason: string;
};

/**
 * Pure, deterministic routing decision — unit-testable without Redis.
 *
 * Preference order: online agent in the required lane → any online super-lane
 * agent (SupremeAI fallback, #1439 rule 2) → escalate (max retries reached)
 * → no-candidate (retry budget remains).
 */
export function decideRoute(input: {
  role: string | null;
  onlineSlots: HeartbeatStatusEntry[];
  attempts: number;
  overrides?: Record<string, string[]>;
}): RouteDecision {
  const { role, onlineSlots, attempts, overrides } = input;
  if (!role) {
    return { decision: "no-candidate", assignedSlot: null, role: null, reason: "event has no required lane" };
  }
  if (attempts >= MAX_RETRIES) {
    return {
      decision: "escalate",
      assignedSlot: null,
      role,
      reason: `max retries (${MAX_RETRIES}) exhausted — human escalation required`,
    };
  }
  const online = onlineSlots.filter((s) => s.state === "online");
  const roleMatch = online.find((s) => roleFromSlot(s.slot, overrides) === role);
  if (roleMatch) {
    return {
      decision: "assigned",
      assignedSlot: roleMatch.slot,
      role,
      reason: `online ${role} slot (age ${roleMatch.ageSeconds}s ≤ 90s threshold)`,
    };
  }
  const superMatch = online.find((s) => roleFromSlot(s.slot, overrides) === "super");
  if (superMatch) {
    return {
      decision: "fallback",
      assignedSlot: superMatch.slot,
      role,
      reason: `no online ${role} slot — SupremeAI fallback via ${superMatch.slot}`,
    };
  }
  return {
    decision: "no-candidate",
    assignedSlot: null,
    role,
    reason: `no online ${role} or super slot — retry ${attempts + 1}/${MAX_RETRIES} on next evaluation`,
  };
}

/** Minimal Redis client over the account chain (GET/SET/KEYS semantics). */
type DispatchStore = {
  get(key: string): Promise<string | null>;
  setEx(key: string, ttlSeconds: number, value: string): Promise<void>;
  keys(pattern: string): Promise<string[]>;
};

export async function makeDispatchStore(): Promise<DispatchStore> {
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error("No Redis configuration — orchestrator dispatch state unavailable");
  }

  // বাংলা মন্তব্য (#2613 R2): আগে এখানে chain[0] (primary) hardcode ছিল —
  // primary-র দৈনিক কোটা শেষ হলে পুরো orchestrator dispatch-path ভেঙে
  // যেত। এখন প্রতিটি call-এ active (cooldown-মুক্ত) account-দের মধ্যে
  // chain-walk করা হয় — কোটা-ত্রুটি ধরা পড়লেই ওই account UTC রিসেট
  // পর্যন্ত cooldown-এ যায় ও পরের account-এ shift হয় (#2452 free-tier fix)।
  const restAccounts = chain.filter((account) => account.restUrl && account.restToken);
  if (restAccounts.length > 0) {
    const call = async (body: unknown[]): Promise<unknown> => {
      // #110: the chain walk + quota marking is now the single engine
      // (runWithAccountChain) — the hand-rolled loop (with its own lastErr
      // bookkeeping and inline markAccountQuotaExhausted calls) is gone.
      // Aggregation semantics preserved: rethrow the LAST failure, exactly
      // like the old loop did.
      try {
        const { value } = await runWithAccountChain(
          async (account) => {
            const res = await fetch(account.restUrl as string, {
              method: "POST",
              headers: {
                Authorization: `Bearer ${account.restToken}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify(body),
              signal: AbortSignal.timeout(10_000),
            });
            if (!res.ok) {
              const errText = await res.text().catch(() => "");
              if (responseIndicatesQuotaExhaustion(res.status, errText)) {
                throw new RedisQuotaExhaustedError(
                  account.label,
                  `Upstash REST [${account.label}] দৈনিক কোটা শেষ — UTC রিসেট পর্যন্ত cooldown`,
                );
              }
              throw new Error(`Upstash REST [${account.label}] HTTP ${res.status}`);
            }
            const payload = (await res.json()) as { result?: unknown; error?: string };
            if (payload.error) {
              if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
                throw new RedisQuotaExhaustedError(
                  account.label,
                  `Upstash REST [${account.label}] দৈনিক কোটা শেষ (body) — cooldown পর্যন্ত shift`,
                );
              }
              throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
            }
            return payload.result;
          },
          {
            skip: (account) => !account.restUrl || !account.restToken,
            aggregateError: (attempts) => {
              const last = attempts[attempts.length - 1]?.error;
              return last
                ? new Error(last)
                : new Error("orchestrator dispatch: all chain accounts failed");
            },
          },
        );
        return value;
      } catch (err) {
        throw err instanceof Error
          ? err
          : new Error("orchestrator dispatch: all chain accounts failed");
      }
    };
    return {
      get: async (key) => (await call(["GET", key])) as string | null,
      setEx: async (key, ttl, value) => {
        await call(["SET", key, value, "EX", String(ttl)]);
      },
      keys: async (pattern) => (await call(["KEYS", pattern])) as string[],
    };
  }
  const tcpAccount = chain.find((account) => account.tcpUrl);
  if (!tcpAccount) {
    throw new Error("No Redis configuration — orchestrator dispatch state unavailable");
  }
  const { Redis } = await import("ioredis");
  const client = new (Redis as unknown as new (url: string, opts: object) => {
    get(key: string): Promise<string | null>;
    set(key: string, value: string, mode: "EX", ttl: number): Promise<"OK">;
    keys(pattern: string): Promise<string[]>;
  })(tcpAccount.tcpUrl as string, { maxRetriesPerRequest: 2, lazyConnect: false });
  return {
    get: async (key) => client.get(key),
    setEx: async (key, ttl, value) => {
      await client.set(key, value, "EX", ttl);
    },
    keys: async (pattern) => client.keys(pattern),
  };
}

export type DispatchState = {
  issueRef: string;
  role: string | null;
  assignedSlot: string | null;
  attempts: number;
  log: string[];
  updatedAt: string;
  /** F3: last routing decision kind — persisted so listOpenAssignments can
   *  distinguish open assignments from no-candidate/escalate terminal states. */
  decisionHint?: "assigned" | "fallback" | "escalate" | "no-candidate";
};

export async function readState(store: DispatchStore, issueRef: string): Promise<DispatchState> {
  const raw = await store.get(`${ORCHESTRATE_STATE_PREFIX}${issueRef}`);
  const base: DispatchState = {
    issueRef,
    role: null,
    assignedSlot: null,
    attempts: 0,
    log: [],
    updatedAt: new Date().toISOString(),
  };
  if (!raw) return base;
  try {
    return { ...base, ...(JSON.parse(raw) as Partial<DispatchState>) };
  } catch {
    return base;
  }
}

export async function writeState(store: DispatchStore, state: DispatchState): Promise<void> {
  await store.setEx(
    `${ORCHESTRATE_STATE_PREFIX}${state.issueRef}`,
    STATE_TTL_SECONDS,
    JSON.stringify({ ...state, updatedAt: new Date().toISOString() }),
  );
}

/**
 * Full dispatch: heartbeat-based selection + state record + decision audit log.
 * Returns the decision and the (updated) task state.
 */
/** An open (assigned/fallback) routing assignment read back from dispatch state. */
export type OpenAssignment = {
  issueRef: string;
  role: string | null;
  assignedSlot: string;
  decision: "assigned" | "fallback";
  attempts: number;
  updatedAt: string;
  ageSeconds: number;
};

/**
 * F3 (audit 2026-10-16): list OPEN routing assignments from dispatch state.
 * Closes the dispatch loop: assigned agents poll this (via orchestrator_my_tasks)
 * instead of decisions living and dying in a log line. Store injectable for
 * offline tests; defaults to the live account-chain store.
 */
export async function listOpenAssignments(
  nowMs: number = Date.now(),
  store?: DispatchStore,
): Promise<{ ok: true; now: string; assignments: OpenAssignment[]; stateKeysScanned: number }> {
  const dispatchStore = store ?? (await makeDispatchStore());
  const keys = await dispatchStore.keys(`${ORCHESTRATE_STATE_PREFIX}*`);
  const assignments: OpenAssignment[] = [];
  for (const key of keys.sort()) {
    const raw = await dispatchStore.get(key);
    if (!raw) continue;
    let state: DispatchState;
    let decisionKind: DispatchState["decisionHint"];
    try {
      state = JSON.parse(raw) as DispatchState;
      decisionKind = state.decisionHint;
    } catch {
      continue; // corrupt state — skip, never break the listing
    }
    if (
      (decisionKind === "assigned" || decisionKind === "fallback") &&
      state.assignedSlot
    ) {
      const updatedMs = Date.parse(state.updatedAt) || 0;
      const ageSeconds = Math.max(0, Math.floor((nowMs - updatedMs) / 1000));
      if (ageSeconds <= ASSIGNMENT_FRESH_WINDOW_SECONDS) {
        assignments.push({
          issueRef: state.issueRef || key.slice(ORCHESTRATE_STATE_PREFIX.length),
          role: state.role ?? null,
          assignedSlot: state.assignedSlot,
          decision: decisionKind,
          attempts: state.attempts ?? 0,
          updatedAt: state.updatedAt,
          ageSeconds,
        });
      }
    }
  }
  return {
    ok: true,
    now: new Date(nowMs).toISOString(),
    assignments: assignments.sort((a, b) => a.issueRef.localeCompare(b.issueRef)),
    stateKeysScanned: keys.length,
  };
}

/**
 * Best-effort Telegram dispatch notice (F3 half 2). Env-unconfigured or failing
 * sends are non-blocking and logged honestly — deterministic protections stay
 * authoritative (CONSUMERS.md §6: AI/notify output is advisory).
 */
export async function notifyDispatchDecision(decision: RouteDecision, issueRef: string): Promise<void> {
  if (decision.decision !== "assigned" && decision.decision !== "escalate") return;
  if (!env.notify.telegramBotToken || !env.notify.telegramChatId) {
    console.log(`[orchestrator-dispatch] notify skipped: telegram unconfigured (${decision.decision} on ${issueRef})`);
    return;
  }
  try {
    const { sendTelegram } = await import("../adapters/notify/actions.js");
    const text =
      decision.decision === "assigned"
        ? `🧭 Orchestrator: ${issueRef} → ${decision.role} @ ${decision.assignedSlot}\n${decision.reason}`
        : `🚨 Orchestrator ESCALATION: ${issueRef} needs human input (${decision.role ?? "n/a"})\n${decision.reason}`;
    await sendTelegram(text);
  } catch (err) {
    console.error(`[orchestrator-dispatch] notify failed (non-blocking): ${(err as Error).message}`);
  }
}

export async function orchestratorDispatch(input: {
  issueRef: string;
  event: string;
  action: string;
  handoffLabel?: string | null;
  store?: DispatchStore;
  nowMs?: number;
}): Promise<{ decision: RouteDecision; state: DispatchState }> {
  const store = input.store ?? (await makeDispatchStore());
  const state = await readState(store, input.issueRef);

  const role = roleForEvent(input.event, input.action, input.handoffLabel) ?? state.role;
  const heartbeats = await listHeartbeats(input.nowMs ?? Date.now());
  const decision = decideRoute({
    role,
    onlineSlots: heartbeats.slots,
    attempts: state.attempts,
    overrides: loadRolePoolOverrides(),
  });

  const logLine = `[${new Date().toISOString()}] ${input.event}.${input.action} role=${role ?? "n/a"} → ${decision.decision}${decision.assignedSlot ? ` (${decision.assignedSlot})` : ""}: ${decision.reason}`;
  const nextState: DispatchState = {
    issueRef: input.issueRef,
    role,
    assignedSlot: decision.assignedSlot ?? state.assignedSlot,
    attempts: decision.decision === "no-candidate" ? state.attempts + 1 : 0,
    log: [...state.log, logLine].slice(-50),
    updatedAt: new Date().toISOString(),
    decisionHint: decision.decision,
  };
  await writeState(store, nextState);
  // Audit trail: the routing decision is always logged server-side (#1803).
  console.log(`[orchestrator-dispatch] ${logLine}`);
  // F3 half 2: best-effort notify (never blocks, never throws — see fn doc).
  await notifyDispatchDecision(decision, input.issueRef);
  return { decision, state: nextState };
}
