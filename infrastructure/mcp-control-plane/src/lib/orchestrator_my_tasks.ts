/**
 * orchestrator_my_tasks — agent-side poll that closes the assignment loop
 * (audit F3, 2026-10-16; drop-in lane per WO #390's pure-new-file pattern).
 *
 * বাংলা: orchestratorDispatch() একটি সিদ্ধান্ত Redis-এ লেখে কিন্তু কোনো agent
 * সেটা পড়তে পারে না — assignment শুধু একটা ledger entry ছিল। এই মডিউল
 * agent-side poll দেয়: slot → আমার assigned tasks।
 *
 * HERMETIC BY DESIGN (the #352-class lesson): zero static imports, zero I/O at
 * module load, zero credential reads. The registry's live types are mirrored as
 * STRUCTURAL types — the module compiles against either mirror (public or
 * private) and cannot break on private-main drift. The operator wiring (see
 * docs/ORCHESTRATOR_MY_TASKS.md §3) passes the registry's SSOT constants
 * (ORCHESTRATE_STATE_PREFIX, MAX_RETRIES) at the call site so no literal
 * duplication ever becomes authoritative.
 *
 * Contract highlights (all asserted by test_orchestrator_my_tasks.ts):
 *  - SCAN only, never KEYS; cursor-paginated, page-count bounded; a bound-exceeded
 *    scan reports `partialScan: true` instead of pretending it saw everything (U2).
 *  - A store without `scan` fails CLOSED: the poll tool must error honestly rather
 *    than fabricate an empty queue (unknown ≠ no tasks).
 *  - Corrupt / vanished / bare-prefix state records are skipped AND counted —
 *    one bad record never blinds the agent to the rest of the queue.
 *  - Deterministic order: newest assignment first, issueRef ascending tiebreak.
 *  - `assigned` and `fallback` decisions both count as routed work; escalate /
 *    no-candidate carry null assignedSlot and exclude naturally.
 *  - Honest ages: unparseable timestamps yield `ageSeconds: null`, never a guess.
 */

/** Minimal Redis client surface needed for the poll (structural superset of the registry's DispatchStore). */
export type ScanCapableStore = {
  get(key: string): Promise<string | null>;
  setEx(key: string, ttlSeconds: number, value: string): Promise<void>;
  scan?(match: string): Promise<{ keys: string[]; partial: boolean }>;
};

/**
 * Structural mirror of the registry's DispatchState (only the fields the poll
 * consumes; unknown extra fields pass through untouched for forward-compat).
 */
export type OrchestrateStateRecord = {
  issueRef: string;
  role?: string | null;
  assignedSlot?: string | null;
  attempts?: number;
  updatedAt: string;
  log?: string[];
  [extra: string]: unknown;
};

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

/** SCAN page size + page-count bound (fail-honest: partial flag, never a silent hang). */
export const SCAN_PAGE_COUNT = 1000;
export const SCAN_MAX_PAGES = 20; // 20k keys bound per poll — orchestrate state is ≤ events/day

/**
 * Redis key prefix for orchestrator dispatch state. SSOT lives in
 * src/registry/orchestrator_dispatch.ts (ORCHESTRATE_STATE_PREFIX); the lib
 * default mirrors it for standalone use and the operator wiring passes the
 * registry constant explicitly (docs §3) so the two can never silently drift.
 */
export const DEFAULT_ORCHESTRATE_STATE_PREFIX = "supremeai:orchestrate:";

/**
 * Shared SCAN loop (cursor pagination) usable by both REST and TCP store paths.
 * Stops at cursor 0 or SCAN_MAX_PAGES — a bound-exceeded scan reports partial
 * instead of pretending it saw everything (U2 fail-honest).
 */
export async function scanAllKeys(
  scanPage: (cursor: string) => Promise<[string, string[]]>,
  _match: string,
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

/**
 * Scan every `orchestrate:*` state and collect parsed records.
 * Corrupt records are skipped and counted — never thrown (one bad state must
 * not blind the agent to the rest of the queue).
 */
export async function collectOrchestrateStates(
  store: ScanCapableStore,
  opts?: { statePrefix?: string },
): Promise<{ states: OrchestrateStateRecord[]; keys: number; corrupt: number; partial: boolean }> {
  if (typeof store.scan !== "function") {
    throw new Error(
      "dispatch store does not support scan — orchestrator_my_tasks unavailable (fail-closed: cannot claim an empty queue)",
    );
  }
  const statePrefix = opts?.statePrefix ?? DEFAULT_ORCHESTRATE_STATE_PREFIX;
  const { keys, partial } = await store.scan(`${statePrefix}*`);
  const states: OrchestrateStateRecord[] = [];
  let corrupt = 0;
  for (const key of keys) {
    const issueRef = key.slice(statePrefix.length);
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
      const parsed = JSON.parse(raw) as Partial<OrchestrateStateRecord>;
      if (typeof parsed !== "object" || parsed === null) {
        corrupt++;
        continue;
      }
      states.push({ ...parsed, issueRef } as OrchestrateStateRecord);
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
  store: ScanCapableStore;
  nowMs?: number;
  limit?: number;
  statePrefix?: string;
}): Promise<MyTasksResult> {
  const limit = input.limit ?? MY_TASKS_DEFAULT_LIMIT;
  const now = input.nowMs ?? Date.now();
  const { states, keys, corrupt, partial } = await collectOrchestrateStates(input.store, {
    statePrefix: input.statePrefix,
  });

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

/**
 * Agent-facing report formatter for orchestrator_my_tasks (F3) — PURE, exported
 * for regression tests (same doctrine as buildHeartbeatRecord: the MCP handler
 * stays a thin auth+catch wrapper; all logic is unit-testable with an injected
 * store).
 *
 * `maxRetries` is the operator-supplied registry constant (MAX_RETRIES, default 3)
 * used for the attempts display — the lib never hardcodes private tunables.
 */
export function myTasksReport(
  result: MyTasksResult,
  opts?: { maxRetries?: number; truncatedLimit?: number },
): string {
  const maxRetries = opts?.maxRetries ?? 3;
  const flags: string[] = [];
  if (result.truncated) flags.push(`truncated to ${opts?.truncatedLimit ?? MY_TASKS_DEFAULT_LIMIT}`);
  if (result.partialScan) flags.push("partial scan (page bound exceeded)");
  if (result.corruptSkipped > 0) flags.push(`${result.corruptSkipped} corrupt state(s) skipped`);
  const header =
    result.tasks.length === 0
      ? `📭 no orchestrator tasks assigned to slot ${result.slot}`
      : `📋 orchestrator tasks for slot ${result.slot}: ${result.tasks.length}`;
  const lines = [
    header,
    ...result.tasks.map((t, i) => {
      const age = t.ageSeconds === null ? "age unknown" : `age ${t.ageSeconds}s`;
      const audit = t.lastAudit ? `\n   audit: ${t.lastAudit}` : "";
      return `${i + 1}. issue ${t.issueRef} — role ${t.role ?? "n/a"}, attempts ${t.attempts}/${maxRetries}, ${age}${audit}`;
    }),
    `(scanned ${result.scannedStates} orchestrate state(s)${flags.length ? ` — ${flags.join(", ")}` : ""})`,
  ];
  return lines.join("\n");
}
