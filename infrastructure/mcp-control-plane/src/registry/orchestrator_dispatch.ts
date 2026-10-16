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

/**
 * Minimal Redis client over the account chain (GET/SET semantics).
 *
 * F3 (audit 2026-10-16): optional `scan` enables the agent-side poll path
 * (orchestrator_my_tasks). Absent scan = read-only-for-one-key store; the
 * poll tool must fail honestly in that case instead of silently returning
 * an empty list (unknown ≠ no tasks).
 */
export type DispatchStore = {
  get(key: string): Promise<string | null>;
  setEx(key: string, ttlSeconds: number, value: string): Promise<void>;
  scan?(match: string): Promise<{ keys: string[]; partial: boolean }>;
};

/** SCAN page size + page-count bound (fail-honest: partial flag, never a silent hang). */
const SCAN_PAGE_COUNT = 1000;
const SCAN_MAX_PAGES = 20; // 20k keys bound per poll — orchestrate state is ≤ events/day

/**
 * Shared SCAN loop (cursor pagination) used by both REST and TCP store paths.
 * Stops at cursor 0 or SCAN_MAX_PAGES — a bound-exceeded scan reports partial
 * instead of pretending it saw everything (U2 fail-honest).
 */
async function scanAllKeys(
  scanPage: (cursor: string) => Promise<[string, string[]]>,
  match: string,
): Promise<{ keys: string[]; partial: boolean }> {
  const keys: string[] = [];
  let cursor = "0";
  for (let page = 0; page < SCAN_MAX_PAGES; page++) {
    const [next, batch] = await scanPage(cursor);
    keys.push(...batch);
    cursor = next;
    if (cursor === "0") return { keys, partial: false };
  }
  return { keys, partial: true };
}

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
      // F3: SCAN over Upstash REST — same pipeline channel, quota-aware via `call`.
      // partial flag propagates (U2): a page-bound-exceeded scan must never
      // masquerade as a full keyspace view.
      scan: async (match) => {
        const result = await scanAllKeys(async (cursor) => {
          return (await call([
            "SCAN",
            cursor,
            "MATCH",
            match,
            "COUNT",
            String(SCAN_PAGE_COUNT),
          ])) as [string, string[]];
        }, match);
        if (result.partial) {
          console.log(
            `[orchestrator-dispatch] scan partial: exceeded ${SCAN_MAX_PAGES} pages for ${match}`,
          );
        }
        return result;
      },
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
    scan(cursor: string, ...args: string[]): Promise<[string, string[]]>;
  })(tcpAccount.tcpUrl as string, { maxRetriesPerRequest: 2, lazyConnect: false });
  return {
    get: async (key) => client.get(key),
    setEx: async (key, ttl, value) => {
      await client.set(key, value, "EX", ttl);
    },
    // F3: non-blocking SCAN (never KEYS) on the TCP path; partial flag propagates.
    scan: async (match) =>
      scanAllKeys(
        (cursor) => client.scan(cursor, "MATCH", match, "COUNT", String(SCAN_PAGE_COUNT)),
        match,
      ),
  };
}

export type DispatchState = {
  issueRef: string;
  role: string | null;
  assignedSlot: string | null;
  attempts: number;
  log: string[];
  updatedAt: string;
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
  };
  await writeState(store, nextState);
  // Audit trail: the routing decision is always logged server-side (#1803).
  console.log(`[orchestrator-dispatch] ${logLine}`);
  return { decision, state: nextState };
}

// ── F3 (audit 2026-10-16): agent-side poll — close the assignment loop ──────
//
// বাংলা: orchestratorDispatch() একটি সিদ্ধান্ত Redis-এ লেখে কিন্তু কোনো agent
// সেটা পড়তে পারে না — assignment শুধু একটা ledger entry ছিল। এই সেকশনটি
// agent-side poll যোগ করে: slot → আমার assigned tasks।
//
// Loop-closure doctrine: `decision: assigned` becomes truthful as *work
// routed*, not merely a ledger entry. The Telegram dispatch notice variant of
// the audit fix direction is a channel/credentials ADMIN_DECISION — deferred,
// not presumed here (§6).

export type MyTaskEntry = {
  issueRef: string;
  role: string | null;
  assignedSlot: string;
  attempts: number;
  updatedAt: string;
  /** Whole seconds since updatedAt; null when the timestamp is unparseable (honest unknown). */
  ageSeconds: number | null;
  lastAudit: string | null;
};

export type MyTasksResult = {
  slot: string;
  tasks: MyTaskEntry[];
  /** Total orchestrate:* states seen during the scan (assigned + others). */
  scannedStates: number;
  /** Corrupt/unparseable state records skipped during the scan. */
  corruptSkipped: number;
  /** More matching tasks than the limit — result was capped (fail-honest). */
  truncated: boolean;
  /** SCAN page bound exceeded — the scan saw only part of the keyspace. */
  partialScan: boolean;
};

export const MY_TASKS_DEFAULT_LIMIT = 50;

/**
 * Scan every `orchestrate:*` state and collect parsed records.
 * Corrupt records are skipped and counted — never thrown (one bad state must
 * not blind the agent to the rest of the queue).
 */
export async function collectOrchestrateStates(
  store: DispatchStore,
): Promise<{ states: DispatchState[]; keys: number; corrupt: number; partial: boolean }> {
  if (typeof store.scan !== "function") {
    throw new Error(
      "dispatch store does not support scan — orchestrator_my_tasks unavailable (fail-closed: cannot claim an empty queue)",
    );
  }
  const { keys, partial } = await store.scan(`${ORCHESTRATE_STATE_PREFIX}*`);
  const states: DispatchState[] = [];
  let corrupt = 0;
  for (const key of keys) {
    const issueRef = key.slice(ORCHESTRATE_STATE_PREFIX.length);
    if (!issueRef) {
      corrupt++;
      continue;
    }
    const raw = await store.get(key);
    if (!raw) {
      // Key vanished between SCAN and GET (TTL expiry race) — count as skipped.
      corrupt++;
      continue;
    }
    try {
      const parsed = JSON.parse(raw) as Partial<DispatchState>;
      if (typeof parsed !== "object" || parsed === null) {
        corrupt++;
        continue;
      }
      states.push({ ...parsed, issueRef } as DispatchState);
    } catch {
      corrupt++;
    }
  }
  return { states, keys: keys.length, corrupt, partial };
}

/**
 * Agent-side poll (F3): heartbeat slot → my open assignments.
 * States land in this slot via `assigned` or `fallback` decisions — both are
 * real work routed to the slot. escalate/no-candidate carry assignedSlot=null
 * and are excluded naturally.
 *
 * Deterministic order: newest assignment first (updatedAt desc, issueRef tiebreak).
 */
export async function orchestratorMyTasks(input: {
  slot: string;
  store: DispatchStore;
  nowMs?: number;
  limit?: number;
}): Promise<MyTasksResult> {
  const limit = input.limit ?? MY_TASKS_DEFAULT_LIMIT;
  const now = input.nowMs ?? Date.now();
  const { states, keys, corrupt, partial } = await collectOrchestrateStates(input.store);

  const mine = states.filter((s) => s.assignedSlot === input.slot);
  const entries: MyTaskEntry[] = mine.map((s) => {
    const parsedAt = Date.parse(s.updatedAt);
    return {
      issueRef: s.issueRef,
      role: s.role ?? null,
      assignedSlot: s.assignedSlot as string,
      attempts: s.attempts ?? 0,
      updatedAt: s.updatedAt,
      ageSeconds: Number.isFinite(parsedAt) ? Math.max(0, Math.round((now - parsedAt) / 1000)) : null,
      lastAudit: s.log && s.log.length > 0 ? s.log[s.log.length - 1] : null,
    };
  });

  entries.sort((a, b) => {
    const ta = Date.parse(a.updatedAt) || 0;
    const tb = Date.parse(b.updatedAt) || 0;
    if (tb !== ta) return tb - ta;
    return a.issueRef < b.issueRef ? -1 : a.issueRef > b.issueRef ? 1 : 0;
  });

  const truncated = entries.length > limit;
  return {
    slot: input.slot,
    tasks: truncated ? entries.slice(0, limit) : entries,
    scannedStates: keys,
    corruptSkipped: corrupt,
    truncated,
    partialScan: partial,
  };
}
