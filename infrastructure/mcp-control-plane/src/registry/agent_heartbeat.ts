/**
 * Agent slot heartbeat registry (issue #1402).
 *
 * Real-time online-status layer on top of the policy-side
 * `docs/master_docs/AGENT_SLOT_REGISTRY.yaml`:
 *
 *   ┌──────────┬──────────────────────────────────────────────────────────┐
 *   │ State    │ Meaning                                                  │
 *   ├──────────┼──────────────────────────────────────────────────────────┤
 *   │ online   │ heartbeat written within ONLINE_THRESHOLD_SECONDS (90s)  │
 *   │ stale    │ heartbeat older than 90s but key not yet expired (300s)  │
 *   │ expired  │ key TTL elapsed → no runtime signal (dashboard falls     │
 *   │          │ back to the YAML policy state: assigned / standby)       │
 *   └──────────┴──────────────────────────────────────────────────────────┘
 *
 * Storage contract (shared by all writers — MCP tower, backend agent-10 loop,
 * dashboard API route, scripts/agents/heartbeat_ping.*):
 *
 *   Key:   supremeai:agent-heartbeat:<slot>          (slot = "agent-N")
 *   Value: JSON { slot, agentId, source, clientId?, updatedAtMs, updatedAt }
 *   TTL:   300s (a missed ping does not immediately drop a tool to offline)
 *
 * Writers embed the epoch ms in the value so readers can derive `age`
 * without a separate timestamp key (Upstash REST has no write-time command).
 */

import {
  activeAccountChain,
  buildAccountChain,
  type RedisAccountConfig,
} from "../lib/redis_chain.js";
import {
  runWithAccountChain,
  readAcrossAccountChain,
} from "../adapters/redis/index.js";

export type { RedisAccountConfig };
// Back-compat re-export: chain construction moved to lib/redis_chain.ts but
// test_heartbeat.ts and external consumers import it from this module.
export { buildAccountChain };

export const HEARTBEAT_KEY_PREFIX = "supremeai:agent-heartbeat:";
export const HEARTBEAT_HASH_KEY = "supremeai:agent-heartbeats";
export const HEARTBEAT_TTL_SECONDS = 300;
export const HEARTBEAT_ONLINE_THRESHOLD_SECONDS = 90;
export const SLOT_PATTERN = /^(agent|z\.ai|claude|chatgpt|cursor|gemini|copilot|coder|planner|ci|pr-helper|browser|platform|super)-\d+$/;

export type HeartbeatSource = "mcp-tower" | "backend" | "dashboard" | "cli";

export type HeartbeatRecord = {
  slot: string;
  agentId: string;
  source: HeartbeatSource;
  clientId?: string;
  updatedAtMs: number;
  updatedAt: string; // ISO-8601
};

export type HeartbeatState = "online" | "stale" | "expired";

export type HeartbeatStatusEntry = HeartbeatRecord & {
  ageSeconds: number;
  state: HeartbeatState;
};

/** Validates a slot id. Returns an error message, or null when valid. */
export function validateSlot(slot: string): string | null {
  if (!slot || typeof slot !== "string") return "slot is required";
  if (!SLOT_PATTERN.test(slot)) {
    return `slot must match /^(agent|z\\.ai|claude|chatgpt|cursor|gemini|copilot|coder|planner|ci|pr-helper|browser|platform|super)-\\d+$/ (e.g. "agent-4", "z.ai-1", "claude-2"); got "${slot}"`;
  }
  return null;
}

export function heartbeatKey(slot: string): string {
  return `${HEARTBEAT_KEY_PREFIX}${slot}`;
}

/** Derives the real-time state from a record's age (ms-precision). */
export function deriveState(
  updatedAtMs: number,
  nowMs: number = Date.now(),
): HeartbeatState {
  const ageMs = Math.max(0, nowMs - updatedAtMs);
  if (ageMs < HEARTBEAT_ONLINE_THRESHOLD_SECONDS * 1000) return "online";
  if (ageMs <= HEARTBEAT_TTL_SECONDS * 1000) return "stale";
  return "expired";
}

/** Whole-second age used for display in listings. */
export function ageSecondsOf(updatedAtMs: number, nowMs: number): number {
  return Math.max(0, Math.floor((nowMs - updatedAtMs) / 1000));
}

// ── Redis transport: single shared account-chain implementation (#110) ─────
// Chain construction lives in lib/redis_chain.ts and the per-account client
// factory + quota-aware fallback walk live in adapters/redis/index.ts — the
// ONE implementation for the whole tower (issue #110). This module keeps only
// its heartbeat-specific op bodies: the write path routes through
// runWithAccountChain (first responder wins) and the read path through
// readAcrossAccountChain (merge across accounts, freshest record wins).

// ── Public API ─────────────────────────────────────────────────────────────

export type RecordHeartbeatInput = {
  slot: string;
  agentId?: string;
  source: HeartbeatSource;
  clientId?: string;
};

export type RecordHeartbeatResult = {
  ok: true;
  slot: string;
  agentId: string;
  heartbeatAt: string;
  ttlSeconds: number;
  redisAccount: string;
  onlineThreshold: string;
};

/**
 * Writes a heartbeat for `slot`, walking the account chain until one accepts
 * the write (shared #110 walk). The dashboard merges across the same chain,
 * so any MCP-connected agent becomes visible in real time without running
 * its own HTTP client (issue #1402 recommendation).
 */
export async function recordHeartbeat(
  input: RecordHeartbeatInput,
): Promise<RecordHeartbeatResult> {
  const slotError = validateSlot(input.slot);
  if (slotError) throw new Error(slotError);

  const nowMs = Date.now();
  const record: HeartbeatRecord = {
    slot: input.slot,
    agentId: input.agentId?.trim() || input.slot,
    source: input.source,
    ...(input.clientId ? { clientId: input.clientId } : {}),
    updatedAtMs: nowMs,
    updatedAt: new Date(nowMs).toISOString(),
  };
  const value = JSON.stringify(record);

  const { result } = await runWithAccountChain(
    async (client) => {
      // Primary write (issue #1994): write to hash for single-command HGETALL reading
      await client.hset(HEARTBEAT_HASH_KEY, input.slot, value);
      // Dual-write: maintain individual key with TTL for legacy readers (best-effort)
      await client
        .setEx(heartbeatKey(input.slot), HEARTBEAT_TTL_SECONDS, value)
        .catch(() => {});
      return {
        ok: true as const,
        slot: record.slot,
        agentId: record.agentId,
        heartbeatAt: record.updatedAt,
        ttlSeconds: HEARTBEAT_TTL_SECONDS,
        redisAccount: client.account,
        onlineThreshold: `ping again within ${HEARTBEAT_ONLINE_THRESHOLD_SECONDS}s to stay 'online'`,
      };
    },
    {
      opLabel: "agent heartbeat write",
      noConfigMessage:
        "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — agent heartbeats cannot be stored",
    },
  );
  return result;
}

export type AccountReadStatus = {
  account: string;
  reachable: boolean;
  records: number;
  error?: string;
  /** #2613: এই account দৈনিক-কোটা cooldown-এ আছে কি না (সৎ স্ট্যাটাস, নন-রিচেবল থেকে আলাদা)। */
  quotaCooldown?: boolean;
};

/** Lists every live heartbeat record with derived real-time state. */
export async function listHeartbeats(nowMs: number = Date.now()): Promise<{
  ok: true;
  now: string;
  ttlSeconds: number;
  onlineThresholdSeconds: number;
  accounts: AccountReadStatus[];
  slots: HeartbeatStatusEntry[];
}> {
  // slot → freshest record across accounts (a recovered primary may hold an
  // older copy of a slot that failed over to secondary — keep the freshest).
  const freshest = new Map<string, HeartbeatRecord>();
  const accounts: AccountReadStatus[] = [];

  // বাংলা মন্তব্য (#2613 R2): পড়ার সময়ও cooldown-এ থাকা account-এ একটিও
  // HGETALL পাঠাই না — তবে dashboard-সততার জন্য সেই account-গুলোকে স্পষ্ট
  // quotaCooldown স্ট্যাটাস সহ তালিকায় রাখি (মিথ্যা "unreachable" নয়)।
  const fullChain = buildAccountChain();
  const activeChain = activeAccountChain();
  const activeLabels = new Set(activeChain.map((a) => a.label));
  for (const account of fullChain) {
    if (!activeLabels.has(account.label)) {
      accounts.push({
        account: account.label,
        reachable: false,
        records: 0,
        quotaCooldown: true,
        error: "daily quota exhausted — cooldown until UTC reset (auto read-shift active)",
      });
    }
  }

  const { entries } = await readAcrossAccountChain(
    async (client) => {
      let records = 0;
      // Fast path (issue #1994): single HGETALL command instead of KEYS + N*GET per account
      const hashRecords = await client.hgetall(HEARTBEAT_HASH_KEY);
      let hasRecords = false;
      for (const [slot, raw] of Object.entries(hashRecords)) {
        if (!raw) continue;
        let record: HeartbeatRecord;
        try {
          record = JSON.parse(raw) as HeartbeatRecord;
        } catch {
          continue; // corrupt payload — skip rather than break listing
        }
        hasRecords = true;
        records += 1;
        const existing = freshest.get(slot);
        if (!existing || record.updatedAtMs > existing.updatedAtMs) {
          freshest.set(slot, record);
        }
      }

      // Fallback path: query individual keys if hash is empty (pre-migration writer)
      if (!hasRecords) {
        const keys = await client.keys(`${HEARTBEAT_KEY_PREFIX}*`);
        for (const key of keys.sort()) {
          const raw = await client.get(key);
          if (!raw) continue;
          let record: HeartbeatRecord;
          try {
            record = JSON.parse(raw) as HeartbeatRecord;
          } catch {
            continue; // corrupt payload — skip rather than break the listing
          }
          records += 1;
          const slot = key.slice(HEARTBEAT_KEY_PREFIX.length);
          const existing = freshest.get(slot);
          if (!existing || record.updatedAtMs > existing.updatedAtMs) {
            freshest.set(slot, record);
          }
        }
      }
      return { records };
    },
    {
      opLabel: "agent heartbeat read",
      noConfigMessage:
        "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — agent heartbeats cannot be read",
    },
  );

  for (const entry of entries) {
    const status: AccountReadStatus = {
      account: entry.account,
      reachable: entry.ok,
      records: entry.ok ? entry.value?.records ?? 0 : 0,
    };
    if (!entry.ok) status.error = entry.error;
    accounts.push(status);
  }

  const slots: HeartbeatStatusEntry[] = [...freshest.entries()]
    .map(([slot, record]) => ({
      ...record,
      slot,
      ageSeconds: ageSecondsOf(record.updatedAtMs, nowMs),
      state: deriveState(record.updatedAtMs, nowMs),
    }))
    .sort((a, b) => a.slot.localeCompare(b.slot));

  return {
    ok: true,
    now: new Date(nowMs).toISOString(),
    ttlSeconds: HEARTBEAT_TTL_SECONDS,
    onlineThresholdSeconds: HEARTBEAT_ONLINE_THRESHOLD_SECONDS,
    accounts,
    slots,
  };
}

