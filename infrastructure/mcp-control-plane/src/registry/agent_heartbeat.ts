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

import { env } from "../lib/env.js";
import Redis from "ioredis";
import {
  activeAccountChain,
  buildAccountChain,
  markAccountQuotaExhausted,
  responseIndicatesQuotaExhaustion,
  type RedisAccountConfig,
} from "../lib/redis_chain.js";

export type { RedisAccountConfig };
// Back-compat re-export: chain construction moved to lib/redis_chain.ts but
// test_heartbeat.ts and external consumers import it from this module.
export { buildAccountChain };

export const HEARTBEAT_KEY_PREFIX = "supremeai:agent-heartbeat:";
export const HEARTBEAT_HASH_KEY = "supremeai:agent-heartbeats";
export const HEARTBEAT_TTL_SECONDS = 300;
export const HEARTBEAT_ONLINE_THRESHOLD_SECONDS = 90;
export const SLOT_PATTERN = /^agent-\d+$/;

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
    return `slot must match /^agent-\\d+$/ (e.g. "agent-4"); got "${slot}"`;
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

// ── Redis transport: Upstash multi-account fallback chain ──────────────────
// Chain construction lives in lib/redis_chain.ts (shared with the read-only
// health adapter so fleet health reflects real chain capability). This module
// keeps the write path: walk the chain until one account accepts the write,
// and the read path: merge across accounts keeping the freshest record.

type HeartbeatRedisClient = {
  mode: "upstash-rest" | "ioredis-tcp";
  account: string;
  get: (key: string) => Promise<string | null>;
  setEx: (key: string, ttlSeconds: number, value: string) => Promise<void>;
  keys: (pattern: string) => Promise<string[]>;
  hset: (key: string, field: string, value: string) => Promise<void>;
  hgetall: (key: string) => Promise<Record<string, string>>;
};

// buildAccountChain() moved to lib/redis_chain.ts (shared with adapters/redis)

function makeRestClient(account: RedisAccountConfig): HeartbeatRedisClient {
  const restUrl = account.restUrl as string;
  const auth = `Bearer ${account.restToken}`;
  const call = async (body: unknown[]): Promise<unknown> => {
    const res = await fetch(restUrl, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      // বাংলা মন্তব্য (#2613 R2): কোটা-ত্রুটি সনাক্ত করে account-কে UTC রিসেট
      // পর্যন্ত cooldown-এ ফেলি — পরের মুহূর্তেই chain এই account skip করবে।
      const errText = await res.text().catch(() => "");
      if (responseIndicatesQuotaExhaustion(res.status, errText)) {
        markAccountQuotaExhausted(account.label);
        throw new Error(
          `Upstash REST [${account.label}] দৈনিক কোটা শেষ — UTC রিসেট পর্যন্ত cooldown`,
        );
      }
      throw new Error(`Upstash REST [${account.label}] returned HTTP ${res.status}`);
    }
    const payload = (await res.json()) as { result?: unknown; error?: string };
    if (payload.error) {
      if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
        markAccountQuotaExhausted(account.label);
        throw new Error(
          `Upstash REST [${account.label}] দৈনিক কোটা শেষ (body) — UTC রিসেট পর্যন্ত cooldown`,
        );
      }
      throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
    }
    return payload.result;
  };
  return {
    mode: "upstash-rest",
    account: account.label,
    get: async (key) => (await call(["GET", key])) as string | null,
    setEx: async (key, ttl, value) => {
      await call(["SET", key, value, "EX", String(ttl)]);
    },
    keys: async (pattern) => (await call(["KEYS", pattern])) as string[],
    hset: async (key, field, value) => {
      await call(["HSET", key, field, value]);
    },
    hgetall: async (key) => {
      const raw = await call(["HGETALL", key]);
      const result: Record<string, string> = {};
      if (!raw) return result;
      if (Array.isArray(raw)) {
        for (let i = 0; i < raw.length; i += 2) {
          const k = String(raw[i]);
          const v = String(raw[i + 1] ?? "");
          if (k) result[k] = v;
        }
      } else if (typeof raw === "object") {
        for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
          if (v != null) result[k] = typeof v === "string" ? v : JSON.stringify(v);
        }
      }
      return result;
    },
  };
}

function makeTcpClient(account: RedisAccountConfig): HeartbeatRedisClient {
  const connect = () =>
    new (Redis as unknown as new (
      url: string,
      opts?: object,
    ) => {
      get: (key: string) => Promise<string | null>;
      set: (key: string, value: string, mode: "EX", ttl: number) => Promise<void>;
      keys: (pattern: string) => Promise<string[]>;
      hset: (key: string, field: string, value: string) => Promise<number>;
      hgetall: (key: string) => Promise<Record<string, string>>;
      disconnect: () => void;
    })(account.tcpUrl as string, { maxRetriesPerRequest: 1, connectTimeout: 5000 });
  return {
    mode: "ioredis-tcp",
    account: account.label,
    get: async (key) => {
      const c = connect();
      try {
        return await c.get(key);
      } finally {
        c.disconnect();
      }
    },
    setEx: async (key, ttl, value) => {
      const c = connect();
      try {
        await c.set(key, value, "EX", ttl);
      } finally {
        c.disconnect();
      }
    },
    keys: async (pattern) => {
      const c = connect();
      try {
        return await c.keys(pattern);
      } finally {
        c.disconnect();
      }
    },
    hset: async (key, field, value) => {
      const c = connect();
      try {
        await c.hset(key, field, value);
      } finally {
        c.disconnect();
      }
    },
    hgetall: async (key) => {
      const c = connect();
      try {
        return (await c.hgetall(key)) || {};
      } finally {
        c.disconnect();
      }
    },
  };
}

function makeClient(account: RedisAccountConfig): HeartbeatRedisClient {
  return account.restUrl && account.restToken
    ? makeRestClient(account)
    : makeTcpClient(account);
}

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
 * the write. The dashboard merges across the same chain, so any MCP-connected
 * agent becomes visible in real time without running its own HTTP client
 * (issue #1402 recommendation).
 */
export async function recordHeartbeat(
  input: RecordHeartbeatInput,
): Promise<RecordHeartbeatResult> {
  const slotError = validateSlot(input.slot);
  if (slotError) throw new Error(slotError);

  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error(
      "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — agent heartbeats cannot be stored",
    );
  }

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

  // বাংলা মন্তব্য (#2613 R2): কোটা cooldown-এ থাকা account-এ একটিও request
  // না পাঠিয়ে সরাসরি active chain (cooldown-মুক্ত) থেকে write শুরু করি।
  const failures: string[] = [];
  for (const account of activeAccountChain()) {
    try {
      const client = makeClient(account);
      // Primary write (issue #1994): write to hash for single-command HGETALL reading
      await client.hset(HEARTBEAT_HASH_KEY, input.slot, value);
      // Dual-write: maintain individual key with TTL for legacy readers
      await client.setEx(
        heartbeatKey(input.slot),
        HEARTBEAT_TTL_SECONDS,
        value,
      ).catch(() => {});
      return {
        ok: true,
        slot: record.slot,
        agentId: record.agentId,
        heartbeatAt: record.updatedAt,
        ttlSeconds: HEARTBEAT_TTL_SECONDS,
        redisAccount: account.label,
        onlineThreshold: `ping again within ${HEARTBEAT_ONLINE_THRESHOLD_SECONDS}s to stay 'online'`,
      };
    } catch (err) {
      failures.push((err as Error).message);
    }
  }
  throw new Error(
    `All ${chain.length} Redis account(s) rejected the heartbeat write: ${failures.join(" | ")}`,
  );
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
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error(
      "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — agent heartbeats cannot be read",
    );
  }

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

  for (const account of activeChain) {
    const status: AccountReadStatus = { account: account.label, reachable: false, records: 0 };
    try {
      const client = makeClient(account);
      // Fast path (issue #1994): single HGETALL command instead of KEYS + N*GET per account
      const hashRecords = await client.hgetall(HEARTBEAT_HASH_KEY);
      status.reachable = true;
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
        status.records += 1;
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
          status.records += 1;
          const slot = key.slice(HEARTBEAT_KEY_PREFIX.length);
          const existing = freshest.get(slot);
          if (!existing || record.updatedAtMs > existing.updatedAtMs) {
            freshest.set(slot, record);
          }
        }
      }
    } catch (err) {
      status.error = (err as Error).message;
    }
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

