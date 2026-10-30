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
  getActiveRedisAccount,
  noteQuotaErrorUsage,
  noteRedisCommands,
  RedisQuotaExhaustedError,
  responseIndicatesQuotaExhaustion,
  runWithAccountChain,
  type RedisAccountConfig,
} from "../lib/redis_chain.js";
import { WriteDebouncer, l1CacheTtlMs, withL1Cache } from "../lib/ttl_cache.js";

export type { RedisAccountConfig };
// Back-compat re-export: chain construction moved to lib/redis_chain.ts but
// test_heartbeat.ts and external consumers import it from this module.
export { buildAccountChain };

export const HEARTBEAT_KEY_PREFIX = "supremeai:agent-heartbeat:";
export const HEARTBEAT_HASH_KEY = "supremeai:agent-heartbeats";
export const HEARTBEAT_TTL_SECONDS = 300;
export const HEARTBEAT_ONLINE_THRESHOLD_SECONDS = 90;

// #1641 (audit: tower slot registry retains expired heartbeats aged 21–24 days):
// বাংলা: legacy individual key-র 300s TTL আছে, কিন্তু HEARTBEAT_HASH_KEY-এর
// ফিল্ডের কোনো TTL নেই — HSET চিরকাল বাঁচে। ফলে মরা slot-গুলো রেজিস্ট্রিতে
// জমতে থাকে (প্রমাণিত: 21–24 দিন ধরে expired, এক query window-এ 13→14)।
// নিচের read-time lazy reaper: expired এবং grace (ডিফল্ট ২৪ঘ, env
// REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS, 0 = expiry-তেই) ছাড়িয়ে গেলে সেই
// ফিল্ড HDEL করে ডিফল্ট listing থেকে বাদ — একই পাঠে `archived`-এ একবার
// দেখানো হয় (forensics), পরের পাঠে সম্পূর্ণ অদৃশ্য। ফিরে-আসা agent নিজেই
// HSET করে নতুন রেকর্ড লেখে — মোছা কোনো তথ্য হারায় না।
export const HEARTBEAT_ARCHIVE_GRACE_SECONDS_DEFAULT = 4 * 3600; // 4 hours TTL auto-scavenge

export function archiveGraceSeconds(): number {
  const raw = Number(process.env.REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS);
  return Number.isFinite(raw) && raw >= 0 ? raw : HEARTBEAT_ARCHIVE_GRACE_SECONDS_DEFAULT;
}
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

// ── #646 AC2: heartbeat write debounce (Redis command-burn reduction) ──────
// বাংলা: heartbeat প্রতি slot প্রতি ~৪৫s লেখে (HSET + SET = ২ কমান্ড)। Online
// threshold ৯০s — তাই ৬০s উইন্ডোর ভিতরের ডুপ্লিকেট লেখা Redis-এ না গিয়েও
// state machine অক্ষত থাকে: সর্বোচ্চ staleness ৬০s < ৯০s (state এখনো "online"),
// আর missed-writer detection সর্বোচ্চ ৬০s দেরিতে হয় (স্বীকার্য)। ৪৫s-পিং চক্রে
// প্রায় ৫০% লেখা বাঁচে। env REDIS_HEARTBEAT_DEBOUNCE_SECONDS=0 দিলে বন্ধ।
export const HEARTBEAT_WRITE_DEBOUNCE_SECONDS = (() => {
  const raw = Number(process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS);
  return Number.isFinite(raw) && raw >= 0 ? raw : 60;
})();
// Window reads env dynamically (per check/record) — operators can tune or
// disable (0) at runtime, and tests can toggle per scenario without reload.
const heartbeatWriteDebouncer = new WriteDebouncer<{ account: string }>(() => {
  const raw = Number(process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS);
  return (Number.isFinite(raw) && raw >= 0 ? raw : 60) * 1000;
});

/** Test/reset hook — debounce state মুছে দেয় (টেস্টগুলো স্বাধীনভাবে লেখা যাচাই করুক)। */
export function resetRedisWriteDebounce(): void {
  heartbeatWriteDebouncer.reset();
}

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

/**
 * #1641: স্টোর-করা record → listing entry (pure, Redis ছাড়া টেস্টযোগ্য)।
 * agentId normalization: পুরনো লেখকের রেকর্ডে agentId null/ফাঁকা থাকলে
 * slot-id-ই সৎ পরিচয় — listing-এ কখনো null দেখাবে না।
 */
export function buildStatusEntry(
  slot: string,
  record: HeartbeatRecord,
  nowMs: number,
): HeartbeatStatusEntry {
  return {
    ...record,
    slot,
    agentId: record.agentId?.trim() || slot,
    ageSeconds: ageSecondsOf(record.updatedAtMs, nowMs),
    state: deriveState(record.updatedAtMs, nowMs),
  };
}

export type SlotPartition = {
  /** ডিফল্ট listing: online/stale + grace-ভিতরের expired (সৎ "expired" স্টেট দৃশ্যমান)। */
  slots: HeartbeatStatusEntry[];
  /** grace ছাড়ানো মরা entry — এই পাঠে একবার দেখানো হয়, তারপর reaped। */
  archived: HeartbeatStatusEntry[];
  /** HDEL করার জন্য slot নাম (hash ফিল্ড)। */
  reapTargets: string[];
};

/**
 * #1641 (pure): grace-সীমা অনুযায়ী listing ভাগ করে। expired = >300s;
 * grace (ডিফল্ট ২৪ঘ) ছাড়িয়ে গেলেই archive+reap — ২৪ঘ-ভিতরের মরা slot
 * অপারেটরকে দেখাতে থাকে (recent-death forensics), তারপর সৎভাবে সরে যায়।
 */
export function partitionSlots(
  entries: HeartbeatStatusEntry[],
  nowMs: number,
  graceSeconds: number = archiveGraceSeconds(),
): SlotPartition {
  const grace = Math.max(0, graceSeconds);
  const slots: HeartbeatStatusEntry[] = [];
  const archived: HeartbeatStatusEntry[] = [];
  for (const entry of entries) {
    if (entry.state === "expired" && entry.ageSeconds > grace) {
      archived.push(entry);
    } else {
      slots.push(entry);
    }
  }
  return { slots, archived, reapTargets: archived.map((e) => e.slot) };
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
  /** #1641: lazy reaper — মরা hash ফিল্ড মোছে (fields খালি হলে no-op)। */
  hdel: (key: string, fields: string[]) => Promise<void>;
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
      // বাংলা মন্তব্য (#2613 R2): কোটা-ত্রুটি সনাক্ত হলে cooldown-marking এখন
      // runWithAccountChain ইঞ্জিন করে (#110) — client শুধু quota-শেপড error
      // throw করে, একটাই marking policy থাকে।
      const errText = await res.text().catch(() => "");
      // #646: error body-তে প্রকৃত usage থাকলে সত্যে সংশোধন (reactive fallback)।
      noteQuotaErrorUsage(account.label, errText);
      if (responseIndicatesQuotaExhaustion(res.status, errText)) {
        throw new RedisQuotaExhaustedError(
          account.label,
          `Upstash REST [${account.label}] দৈনিক কোটা শেষ — UTC রিসেট পর্যন্ত cooldown`,
        );
      }
      throw new Error(`Upstash REST [${account.label}] returned HTTP ${res.status}`);
    }
    const payload = (await res.json()) as { result?: unknown; error?: string };
    if (payload.error) {
      if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
        noteQuotaErrorUsage(account.label, String(payload.error));
        throw new RedisQuotaExhaustedError(
          account.label,
          `Upstash REST [${account.label}] দৈনিক কোটা শেষ (body) — UTC রিসেট পর্যন্ত cooldown`,
        );
      }
      throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
    }
    // #646 AC1: সফল কমান্ড গণনা — preemptive rotation-এর প্রাথমিক সত্য-উৎস।
    noteRedisCommands(account.label, 1);
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
    hdel: async (key, fields) => {
      if (!fields.length) return;
      await call(["HDEL", key, ...fields]);
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
      hdel: (key: string, ...fields: string[]) => Promise<number>;
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
    hdel: async (key, fields) => {
      if (!fields.length) return;
      const c = connect();
      try {
        await c.hdel(key, ...fields);
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
  /** #646: true হলে এই কলটি debounce উইন্ডোর কারণে Redis-এ যায়নি —
   *  আগের লেখাই সর্বশেষ সত্য (state machine অক্ষত)। */
  debounced?: boolean;
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

  // #646 AC2: debounce চেক — উইন্ডোর ভিতরের ডুপ্লিকেট লেখা Redis-এ যায় না।
  // chain-validation-এর পরে বসানো হয়েছে, তাই "No Redis configuration" error
  // আগের মতোই throw হয় (CI contract অক্ষত)।
  const debounceDecision = heartbeatWriteDebouncer.check(`hb:${input.slot}`, nowMs);
  if (debounceDecision.skip) {
    const lastWriteMs = debounceDecision.lastWriteMs;
    return {
      ok: true,
      slot: input.slot,
      agentId: input.agentId?.trim() || input.slot,
      heartbeatAt: new Date(lastWriteMs).toISOString(),
      ttlSeconds: HEARTBEAT_TTL_SECONDS,
      redisAccount: debounceDecision.metadata?.account ?? getActiveRedisAccount().label,
      onlineThreshold: `ping again within ${HEARTBEAT_ONLINE_THRESHOLD_SECONDS}s to stay 'online'`,
      debounced: true,
    };
  }

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
  // #110: chain-walk + quota-marking এখন একটাই ইঞ্জিন (runWithAccountChain) —
  // কপি করা loop নেই; ব্যর্থতার বার্তা আগের মতোই (byte-identical)।
  const chainLength = chain.length;
  const { account } = await runWithAccountChain(
    async (acct) => {
      const client = makeClient(acct);
      // Primary write (issue #1994): write to hash for single-command HGETALL reading
      await client.hset(HEARTBEAT_HASH_KEY, input.slot, value);
      // Dual-write: maintain individual key with TTL for legacy readers
      await client.setEx(
        heartbeatKey(input.slot),
        HEARTBEAT_TTL_SECONDS,
        value,
      ).catch(() => {});
      return acct.label;
    },
    {
      aggregateError: (attempts) =>
        new Error(
          `All ${chainLength} Redis account(s) rejected the heartbeat write: ${attempts
            .map((a) => a.error ?? "unknown error")
            .join(" | ")}`,
        ),
    },
  );
  // #646: লেখা সফল হলেই debounce রেকর্ড — ব্যর্থ লেখা কখনো উইন্ডো পয়জন করবে না।
  heartbeatWriteDebouncer.record(`hb:${input.slot}`, Date.now(), { account: account.label });
  return {
    ok: true,
    slot: record.slot,
    agentId: record.agentId,
    heartbeatAt: record.updatedAt,
    ttlSeconds: HEARTBEAT_TTL_SECONDS,
    redisAccount: account.label,
    onlineThreshold: `ping again within ${HEARTBEAT_ONLINE_THRESHOLD_SECONDS}s to stay 'online'`,
  };
}

export type AccountReadStatus = {
  account: string;
  reachable: boolean;
  records: number;
  error?: string;
  /** #2613: এই account দৈনিক-কোটা cooldown-এ আছে কি না (সৎ স্ট্যাটাস, নন-রিচেবল থেকে আলাদা)। */
  quotaCooldown?: boolean;
};

/** Lists every live heartbeat record with derived real-time state.
 *  #646 AC2: L1 read-through cache (default 5s, env REDIS_L1_CACHE_TTL_MS,
 *  0 = off) — dashboard sweep burst একটি TTL উইন্ডোতে একবারই Redis-এ যায়।
 *  #1641: expired-এর grace (ডিফল্ট ২৪ঘ) ছাড়িয়ে গেলে সেই slot ডিফল্ট listing
 *  থেকে বাদ + hash থেকে lazy-reap (HDEL) — একই পাঠে `archived`-এ একবার
 *  ফরেনসিক-ভিউ, পরের পাঠে অদৃশ্য। রেজিস্ট্রি এখন আর মরা slot জমায় না। */
export async function listHeartbeats(nowMs: number = Date.now()): Promise<{
  ok: true;
  now: string;
  ttlSeconds: number;
  onlineThresholdSeconds: number;
  archiveGraceSeconds: number;
  accounts: AccountReadStatus[];
  slots: HeartbeatStatusEntry[];
  /** #1641: grace ছাড়ানো মরা entry — এই পাঠেই সর্বশেষ দেখা। */
  archived?: HeartbeatStatusEntry[];
  /** #1641: যেসব hash ফিল্ড HDEL করা হলো। */
  reapTargets?: string[];
}> {
  return withL1Cache("l1:agent-heartbeats", l1CacheTtlMs(), () => listHeartbeatsFresh(nowMs), nowMs);
}

async function listHeartbeatsFresh(nowMs: number): Promise<{
  ok: true;
  now: string;
  ttlSeconds: number;
  onlineThresholdSeconds: number;
  archiveGraceSeconds: number;
  accounts: AccountReadStatus[];
  slots: HeartbeatStatusEntry[];
  archived?: HeartbeatStatusEntry[];
  reapTargets?: string[];
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
  // #1641: reachable client-দের রেখে দিই — reaper-এর HDEL এদের কাছেই যাবে।
  const reachableClients: HeartbeatRedisClient[] = [];

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
      reachableClients.push(client);
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

  // #1641: buildStatusEntry — agentId normalization (null/ফাঁকা → slot-id),
  // বয়স ও state ডেরিভেশন এক জায়গায় (pure, টেস্টযোগ্য)।
  const entries = [...freshest.entries()]
    .map(([slot, record]) => buildStatusEntry(slot, record, nowMs))
    .sort((a, b) => a.slot.localeCompare(b.slot));

  // #1641: grace ছাড়ানো মরা slot → ডিফল্ট listing থেকে বাদ + hash থেকে
  // lazy-reap (HDEL)। জানা সীমাবদ্ধতা (সৎ মন্তব্য): read→HDEL মাইক্রো-সেকেন্ড
  // window-এ ঠিক ওই slot ফিরে এসে re-ping করলে সদ্য-লেখা রেকর্ডও মুছে যেতে
  // পারে — ২৪ দিনের মৃত agent-এর ঠিক ওই মুহূর্তে ফেরার সম্ভাবনা নগণ্য, আর
  // ফিরলেও ৪৫s cadence-এ পরের ping-এ স্লট আবার online দেখায়।
  const { slots, archived, reapTargets } = partitionSlots(entries, nowMs);
  if (reapTargets.length) {
    for (const client of reachableClients) {
      try {
        await client.hdel(HEARTBEAT_HASH_KEY, reapTargets);
      } catch {
        // বাংলা: reaping best-effort — এই পাঠে ব্যর্থ হলে পরের পাঠে আবার চেষ্টা
      }
    }
  }

  return {
    ok: true,
    now: new Date(nowMs).toISOString(),
    ttlSeconds: HEARTBEAT_TTL_SECONDS,
    onlineThresholdSeconds: HEARTBEAT_ONLINE_THRESHOLD_SECONDS,
    archiveGraceSeconds: archiveGraceSeconds(),
    accounts,
    slots,
    ...(archived.length ? { archived, reapTargets } : {}),
  };
}

