/**
 * MCP interactive-client auto-presence registry (issue #3297).
 *
 * বাংলা মন্তব্য: অটোনোমাস Git worker-রা (AGENT_SLOT_REGISTRY + branch lease)
 * ইতিমধ্যে heartbeat-এ দেখা যায়, কিন্তু MCP Tower-এ যুক্ত interactive AI
 * client-রা (ChatGPT, Claude Desktop, Gemini, Cursor, Copilot) MCP প্রোটোকলে
 * client-side heartbeat না পাঠানোয় অদৃশ্য ছিল। এই মডিউল request-interception
 * ভিত্তিক auto-presence স্তর — প্রতিটি MCP রিকোয়েস্ট (initialize, সেশন
 * activity, SSE connect) থেকে identity বের করে Redis-এ sliding-TTL presence
 * key লেখে।
 *
 * Storage contract (heartbeat-এর মতোই — সব writer একই চুক্তি মানে):
 *
 *   Key:   supremeai:mcp-presence:<clientName>:<clientId>
 *   Value: JSON { clientName, clientId, protocol, tenantId, updatedAtMs, updatedAt }
 *   TTL:   300s sliding (প্রতিটি রিকোয়েস্টে refresh — MCP-তে client-side
 *          heartbeat নেই, তাই যেকোনো কার্যকলাপই liveness-এর প্রমাণ)
 *
 * Unified workforce (#3297 §2): `listWorkforce()` — autonomous builder
 * (agent_heartbeat) + interactive assistant (presence) — উভয়ের merged ভিউ,
 * পরিষ্কার শ্রেণিবিভাগসহ। orchestrator_dispatch ইচ্ছাকৃতভাবে
 * autonomous-only থাকবে (issue dispatch কখনোই একটি চ্যাট-সেশনে যাবে না)।
 */

import {
  ageSecondsOf,
  deriveState,
  listHeartbeats,
  type HeartbeatState,
  type HeartbeatStatusEntry,
} from "./agent_heartbeat.js";
import { activeAccountChain, noteRedisContact, quotaGuard, RedisQuotaExhaustedError, responseIndicatesQuotaExhaustion, runWithAccountChain, type RedisAccountConfig } from "../lib/redis_chain.js";
import { L1Cache } from "../lib/l1_cache.js";

export const PRESENCE_KEY_PREFIX = "supremeai:mcp-presence:";
export const PRESENCE_TTL_SECONDS = 300;

// ── #646 command burn-rate guards ────────────────────────────────────
// PRESENCE_WRITE_DEBOUNCE_MS: প্রতিটি MCP রিকোয়েস্টে presence write হয় —
// একই client-এর sub-second পরপর লেখা sliding TTL-এর জন্য অপ্রয়োজনীয়।
// PRESENCE_LIST_CACHE_TTL_MS / WORKFORCE_LIST_CACHE_TTL_MS: dashboard দ্রুত
// পরপর listPresence()/listWorkforce() কলের L1 in-memory cache।
export const PRESENCE_WRITE_DEBOUNCE_MS = (() => {
  const v = Number(process.env.PRESENCE_WRITE_DEBOUNCE_MS);
  return Number.isFinite(v) && v >= 0 ? v : 2_000;
})();
export const PRESENCE_LIST_CACHE_TTL_MS = (() => {
  const v = Number(process.env.PRESENCE_LIST_CACHE_TTL_MS);
  return Number.isFinite(v) && v >= 0 ? v : 20_000;
})();
export const WORKFORCE_LIST_CACHE_TTL_MS = (() => {
  const v = Number(process.env.WORKFORCE_LIST_CACHE_TTL_MS);
  return Number.isFinite(v) && v >= 0 ? v : 15_000;
})();

export type PresenceProtocol = "streamable-http" | "sse" | "stdio" | "custom";

export type PresenceRecord = {
  clientName: string;
  clientId: string;
  protocol: PresenceProtocol;
  tenantId?: string;
  updatedAtMs: number;
  updatedAt: string; // ISO-8601
};

export type PresenceStatusEntry = PresenceRecord & {
  ageSeconds: number;
  // #112: single HeartbeatState definition lives in agent_heartbeat.ts
  // (imported above) — the local re-declaration drifted toward silent SSOT rot.
  state: HeartbeatState;
};

export type WorkforceKind = "autonomous_builder" | "interactive_assistant";

export type WorkforceEntry =
  | ({ kind: "autonomous_builder" } & HeartbeatStatusEntry)
  | ({ kind: "interactive_assistant" } & PresenceStatusEntry);

export type WorkforceSummary = {
  ok: true;
  now: string;
  counts: {
    total: number;
    autonomousBuilders: number;
    interactiveAssistants: number;
    onlineAutonomous: number;
    onlineInteractive: number;
  };
  agents: WorkforceEntry[];
  /** সৎ অবক্ষয় (#3297): একটি উৎস ব্যর্থ হলে কারণসহ চিহ্নিত — নীরব শূন্য নয়। */
  errors?: { presence?: string; heartbeats?: string };
};

/** key-অংশ থেকে ':' সরায় — key সবসময় <name>:<id> দুই-অংশ পার্সেবল থাকে। */
export function sanitizePresenceToken(raw: string): string {
  return String(raw ?? "")
    .replace(/:/g, "_")
    .replace(/[\r\n\t]/g, " ")
    .trim()
    .slice(0, 64);
}

export function presenceKey(clientName: string, clientId: string): string {
  const name = sanitizePresenceToken(clientName) || "unknown-client";
  const id = sanitizePresenceToken(clientId) || "unknown-id";
  return `${PRESENCE_KEY_PREFIX}${name}:${id}`;
}

/**
 * MCP `initialize` request body থেকে clientInfo.name বের করে (MCP spec:
 * params.clientInfo = { name, version })। Batch request-এ প্রথম initialize
 * নেওয়া হয়। না পেলে undefined — caller fallback ব্যবহার করবে।
 */
export function extractClientInfoName(body: unknown): string | undefined {
  const messages = Array.isArray(body) ? body : [body];
  for (const msg of messages) {
    if (!msg || typeof msg !== "object") continue;
    const m = msg as { method?: unknown; params?: unknown };
    if (m.method !== "initialize") continue;
    const params = m.params as { clientInfo?: { name?: unknown } } | undefined;
    const name = params?.clientInfo?.name;
    if (typeof name === "string" && name.trim()) return name.trim().slice(0, 64);
  }
  return undefined;
}

// ── Redis transport: heartbeat-এর একই account-chain walker ─────────────────
// (Upstash REST + ioredis TCP উভয় মোড; কোটা cooldown-সচেতন)

type PresenceRedisClient = {
  get: (key: string) => Promise<string | null>;
  setEx: (key: string, ttlSeconds: number, value: string) => Promise<void>;
  keys: (pattern: string) => Promise<string[]>;
};

function makeRestPresenceClient(account: RedisAccountConfig): PresenceRedisClient {
  const restUrl = account.restUrl as string;
  const auth = `Bearer ${account.restToken}`;
  const call = async (body: unknown[]): Promise<unknown> => {
    // #646 preemptive quota guard (heartbeat REST client-এর একই চুক্তি)।
    quotaGuard(account, body.length);
    const res = await fetch(restUrl, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      // #110: quota-shape detection aligned with the heartbeat REST client —
      // the RedisQuotaExhaustedError is what makes runWithAccountChain mark
      // this account into cooldown and shift to the next one. Presence used
      // to be the one routed path with NO quota marking; now all are identical.
      const errText = await res.text().catch(() => "");
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
        throw new RedisQuotaExhaustedError(
          account.label,
          `Upstash REST [${account.label}] দৈনিক কোটা শেষ (body) — UTC রিসেট পর্যন্ত cooldown`,
        );
      }
      throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
    }
    noteRedisContact(account.label, "upstash-rest"); // #646: health-sweep skip সিগন্যাল
    return payload.result;
  };
  return {
    get: async (key) => (await call(["GET", key])) as string | null,
    setEx: async (key, ttl, value) => {
      await call(["SET", key, value, "EX", String(ttl)]);
    },
    keys: async (pattern) => (await call(["KEYS", pattern])) as string[],
  };
}

function makeTcpPresenceClient(account: RedisAccountConfig): PresenceRedisClient {
  // বাংলা: lazy dynamic import এড়িয়ে heartbeat-এর একই সরল factory-প্যাটার্ন —
  // presence-এর জন্য ioredis ছোট scoped connection ব্যবহার করে।
  const Redis = (
    globalThis as unknown as {
      __presenceRedisCtor?: new (url: string, opts: object) => {
        get: (k: string) => Promise<string | null>;
        set: (k: string, v: string, mode: "EX", ttl: number) => Promise<void>;
        keys: (p: string) => Promise<string[]>;
        disconnect: () => void;
      };
    }
  ).__presenceRedisCtor;
  if (!Redis) {
    throw new Error(
      `TCP Redis account [${account.label}] ব্যবহারের আগে ioredis লোড করতে হবে (registerIoredis())`,
    );
  }
  const connect = () => new Redis(account.tcpUrl as string, { maxRetriesPerRequest: 1, connectTimeout: 5000 });
  return {
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
  };
}

let ioredisCtor: (new (url: string, opts: object) => unknown) | null = null;

/** index.ts boot-এ একবার ডাকে — presence TCP fallback-এর জন্য ioredis ctor। */
export function registerIoredis(ctor: new (url: string, opts: object) => unknown): void {
  ioredisCtor = ctor;
  (globalThis as unknown as { __presenceRedisCtor?: unknown }).__presenceRedisCtor =
    ctor as unknown as never;
}

function makePresenceClient(account: RedisAccountConfig): PresenceRedisClient {
  if (account.restUrl && account.restToken) return makeRestPresenceClient(account);
  return makeTcpPresenceClient(account);
}

// ── Public API ──────────────────────────────────────────────────────────────

export type RecordPresenceInput = {
  clientName: string;
  clientId: string;
  protocol: PresenceProtocol;
  tenantId?: string;
};

export type RecordPresenceResult = {
  ok: true;
  key: string;
  ttlSeconds: number;
  /** #646: true হলে debounced উত্তর — রিমোট লেখা হয়নি। */
  debounced?: boolean;
};

// ── #646 write debounce + list caches ───────────────────────────────────
// presenceKey → { fingerprint, ms }: একই client identity-এর পরপর identical
// লেখা PRESENCE_WRITE_DEBOUNCE_MS-এর মধ্যে হলে রিমোটে যায় না।
type PresenceFingerprint = string;
const lastPresenceWrite = new Map<string, { fingerprint: PresenceFingerprint; ms: number }>();
const presenceListCache = new L1Cache<PresenceListResult>(PRESENCE_LIST_CACHE_TTL_MS);
const workforceListCache = new L1Cache<WorkforceSummary>(WORKFORCE_LIST_CACHE_TTL_MS);

function presenceFingerprint(input: RecordPresenceInput): string {
  return [input.clientName, input.clientId, input.protocol, input.tenantId ?? ""].join("\u0000");
}

/**
 * একটি interactive client-এর presence লেখে/রিফ্রেশ করে (sliding TTL)।
 * Caller-রা সাধারণত fire-and-forget ব্যবহার করবে:
 * `void recordPresence(...).catch(() => undefined)` — presence কখনোই
 * মূল MCP রিকোয়েস্ট-পাথ ভাঙবে না (#3297 fail-open by design)।
 */
export async function recordPresence(
  input: RecordPresenceInput,
): Promise<RecordPresenceResult> {
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error(
      "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — MCP presence cannot be stored",
    );
  }
  const nowMs = Date.now();
  const record: PresenceRecord = {
    clientName: sanitizePresenceToken(input.clientName) || "unknown-client",
    clientId: sanitizePresenceToken(input.clientId) || "unknown-id",
    protocol: input.protocol,
    ...(input.tenantId ? { tenantId: input.tenantId } : {}),
    updatedAtMs: nowMs,
    updatedAt: new Date(nowMs).toISOString(),
  };
  const key = presenceKey(record.clientName, record.clientId);
  const value = JSON.stringify(record);

  // #646 write debounce: identical fingerprint-এর সাম্প্রতিক লেখা থাকলে রিমোট
  // command না পাঠিয়ে সত্য উত্তর (sliding TTL ইতিমধ্যে রিফ্রেশ হয়ে গেছে)।
  const fingerprint = presenceFingerprint(input);
  const last = lastPresenceWrite.get(key);
  if (
    last &&
    last.fingerprint === fingerprint &&
    nowMs - last.ms < PRESENCE_WRITE_DEBOUNCE_MS
  ) {
    return { ok: true, key, ttlSeconds: PRESENCE_TTL_SECONDS, debounced: true };
  }
  // #110: chain-walk + quota-marking through the single engine; the failure
  // message stays byte-identical to the deleted hand-rolled loop.
  const chainLength = chain.length;
  await runWithAccountChain(
    async (acct) => {
      await makePresenceClient(acct).setEx(key, PRESENCE_TTL_SECONDS, value);
      return acct.label;
    },
    {
      aggregateError: (attempts) =>
        new Error(
          `All ${chainLength} Redis account(s) rejected the presence write: ${attempts
            .map((a) => a.error ?? "unknown error")
            .join(" | ")}`,
        ),
    },
  );
  // #646: সফল লেখার পরে debounce ledger + list caches invalidation।
  lastPresenceWrite.set(key, { fingerprint, ms: nowMs });
  if (lastPresenceWrite.size > 512) {
    for (const [k, entry] of lastPresenceWrite) {
      if (nowMs - entry.ms >= PRESENCE_WRITE_DEBOUNCE_MS) lastPresenceWrite.delete(k);
    }
  }
  presenceListCache.clear();
  workforceListCache.clear();
  return { ok: true, key, ttlSeconds: PRESENCE_TTL_SECONDS };
}

export type PresenceListResult = {
  ok: true;
  now: string;
  ttlSeconds: number;
  clients: PresenceStatusEntry[];
};

/** সব সক্রিয় interactive-client presence (সব account-chain merge, freshest wins)। */
export async function listPresence(nowMs: number = Date.now()): Promise<PresenceListResult> {
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error(
      "No Redis configuration found (set UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN, or REDIS_URL) — MCP presence cannot be read",
    );
  }
  // #646 L1 cache: fail-loud চুক্তির পরে; `now` প্রতিবার টাটকা।
  const cached = presenceListCache.get("list", nowMs);
  if (cached) return { ...cached, now: new Date(nowMs).toISOString() };
  const freshest = new Map<string, PresenceRecord>();
  const pattern = `${PRESENCE_KEY_PREFIX}*`;
  for (const account of chain) {
    try {
      const client = makePresenceClient(account);
      const keys = await client.keys(pattern);
      for (const key of keys.sort()) {
        const raw = await client.get(key);
        if (!raw) continue;
        let record: PresenceRecord;
        try {
          record = JSON.parse(raw) as PresenceRecord;
        } catch {
          continue; // corrupt payload — skip, listing ভাঙবে না
        }
        const existing = freshest.get(key);
        if (!existing || record.updatedAtMs > existing.updatedAtMs) {
          freshest.set(key, record);
        }
      }
    } catch {
      // বাংলা: একটি account unreachable হলে বাকি chain থেকেই পড়া চলবে
    }
  }
  const clients: PresenceStatusEntry[] = [...freshest.entries()]
    .map(([key, record]) => ({
      ...record,
      clientId: record.clientId || key.slice(PRESENCE_KEY_PREFIX.length),
      ageSeconds: ageSecondsOf(record.updatedAtMs, nowMs),
      state: deriveState(record.updatedAtMs, nowMs),
    }))
    .sort((a, b) => a.clientName.localeCompare(b.clientName));
  const result: PresenceListResult = {
    ok: true,
    now: new Date(nowMs).toISOString(),
    ttlSeconds: PRESENCE_TTL_SECONDS,
    clients,
  };
  presenceListCache.set("list", result, nowMs);
  return result;
}

/**
 * Unified workforce view (#3297 §2) — autonomous builder + interactive
 * assistant একসাথে, শ্রেণিবিভাগসহ। সৎ-অবক্ষয়: একটি উৎস ব্যর্থ হলে
 * `errors`-এ কারণ থাকবে, অন্যটি দিয়ে ফলাফল আসবে; দুটোই ব্যর্থ হলে throw।
 */
export async function listWorkforce(nowMs: number = Date.now()): Promise<WorkforceSummary> {
  // #646 L1 cache: dashboard refresh-এ দুই উৎসের merged পড়া একটিই command-এ
  // দামি না — cache hit-এ কোনো Redis command যায় না। fail-loud ফাংশন হিসেবে
  // শুধু সফল ফলাফলই cache হয়; উভয় উৎস ব্যর্থ হলে আগের মতোই throw।
  const cached = workforceListCache.get("workforce", nowMs);
  if (cached) return { ...cached, now: new Date(nowMs).toISOString() };
  const errors: { presence?: string; heartbeats?: string } = {};
  let heartbeatResult: Awaited<ReturnType<typeof listHeartbeats>> | null = null;
  let presenceResult: PresenceListResult | null = null;
  try {
    heartbeatResult = await listHeartbeats(nowMs);
  } catch (err) {
    errors.heartbeats = (err as Error).message;
  }
  try {
    presenceResult = await listPresence(nowMs);
  } catch (err) {
    errors.presence = (err as Error).message;
  }
  if (!heartbeatResult && !presenceResult) {
    // দুটো উৎসই অক্ষম — সৎ fail-loud
    throw new Error(
      `Unified workforce unavailable — heartbeats: ${errors.heartbeats ?? "n/a"} | presence: ${errors.presence ?? "n/a"}`,
    );
  }

  const builders: WorkforceEntry[] = (heartbeatResult?.slots ?? []).map((slot) => ({
    kind: "autonomous_builder" as const,
    ...slot,
  }));
  const assistants: WorkforceEntry[] = (presenceResult?.clients ?? []).map((c) => ({
    kind: "interactive_assistant" as const,
    ...c,
  }));
  const agents = [...builders, ...assistants].sort((a, b) => {
    if (a.kind !== b.kind) return a.kind === "autonomous_builder" ? -1 : 1;
    return (a.updatedAtMs - b.updatedAtMs) * -1;
  });
  const summary: WorkforceSummary = {
    ok: true,
    now: new Date(nowMs).toISOString(),
    counts: {
      total: builders.length + assistants.length,
      autonomousBuilders: builders.length,
      interactiveAssistants: assistants.length,
      onlineAutonomous: builders.filter((b) => b.state === "online").length,
      onlineInteractive: assistants.filter((a) => a.state === "online").length,
    },
    agents,
    ...(Object.keys(errors).length ? { errors } : {}),
  };
  workforceListCache.set("workforce", summary, nowMs);
  return summary;
}
