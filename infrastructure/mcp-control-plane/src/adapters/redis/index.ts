/**
 * Redis adapter — THE single account-chain implementation for the tower
 * (issue #110 consolidation).
 *
 * Previously the chain walk + per-account client construction existed here
 * AND was re-implemented by hand in four other modules (agent_heartbeat,
 * mcp_presence ×2, orchestrator_dispatch, client-registry.store), with 7
 * ad-hoc per-account client factories — each copy marking quota/cooldown
 * slightly differently, so rotation policy was "whatever the copy you happen
 * to execute says". All of those route through THIS module now:
 *
 *   - `clientForAccount(account)`  — the ONE per-account client factory
 *     (Upstash REST first, ioredis TCP fallback)
 *   - `runWithAccountChain(op)`    — first-responder walk with the canonical
 *     quota-marking policy (mark exhausted → cooldown → auto-rotate)
 *   - `readAcrossAccountChain(op)` — merge-read across ALL active accounts
 *     (heartbeat/presence listing semantics: freshest record wins)
 *
 * Read-only health surfaces (`pingRedis` / `getRedisStats` / `readRedisKey`)
 * walk the chain too: the FIRST account whose op succeeds represents Redis
 * health. Redis is DOWN only when EVERY account in the chain fails.
 */

import Redis from "ioredis";
import {
  activeAccountChain,
  markAccountQuotaExhausted,
  responseIndicatesQuotaExhaustion,
  getActiveRedisAccount,
  quotaChainStatus,
  type RedisAccountConfig,
} from "../../lib/redis_chain.js";

export type { RedisAccountConfig };

export type ChainClientMode = "upstash-rest" | "ioredis-tcp";

export type AccountAttempt = {
  account: string;
  mode: ChainClientMode;
  ok: boolean;
  error?: string;
};

/**
 * The ONE shared per-account Redis client surface. Covers every operation
 * the routed call sites need (health ping/info, heartbeat hash+dual-write,
 * presence keys/read, orchestrator state, client-registry snapshot).
 */
export type ChainClient = {
  mode: ChainClientMode;
  account: string;
  ping: () => Promise<string>;
  info: () => Promise<string>;
  get: (key: string) => Promise<string | null>;
  /** Persistent SET (no TTL) — client-registry snapshot replication. */
  set: (key: string, value: string) => Promise<void>;
  setEx: (key: string, ttlSeconds: number, value: string) => Promise<void>;
  keys: (pattern: string) => Promise<string[]>;
  hset: (key: string, field: string, value: string) => Promise<void>;
  hgetall: (key: string) => Promise<Record<string, string>>;
};

type TcpRedisConnection = {
  ping(): Promise<string>;
  info(): Promise<string>;
  get(key: string): Promise<string | null>;
  set(key: string, value: string, mode?: "EX", ttl?: number): Promise<unknown>;
  keys(pattern: string): Promise<string[]>;
  hset(key: string, field: string, value: string): Promise<unknown>;
  hgetall(key: string): Promise<Record<string, string>>;
  disconnect(): void;
};

type TcpRedisCtor = new (url: string, opts?: Record<string, unknown>) => TcpRedisConnection;

// Optional ctor override — mcp_presence.registerIoredis (called once at boot)
// delegates here so the TCP fallback always uses the same connection stack.
let tcpRedisCtor: TcpRedisCtor | null = null;

/** Register the ioredis constructor used by the shared TCP fallback. */
export function setTcpRedisCtor(ctor: (new (url: string, opts: object) => unknown) | null): void {
  tcpRedisCtor = ctor as unknown as TcpRedisCtor | null;
}

// ── Upstash REST transport (one stack for the whole tower) ─────────────────
// বাংলা মন্তব্য (#2613 R2): কোটা-ত্রুটি সনাক্ত করে account-কে window-reset
// পর্যন্ত cooldown-এ ফেলি — পরের call-এ chain এই account skip করবে।
function makeRestChainClient(account: RedisAccountConfig): ChainClient {
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
      const errText = await res.text().catch(() => "");
      if (responseIndicatesQuotaExhaustion(res.status, errText)) {
        markAccountQuotaExhausted(account.label);
        throw new Error(
          `Upstash REST [${account.label}] quota exhausted — cooldown until window reset (auto-rotate active)`,
        );
      }
      throw new Error(`Upstash REST [${account.label}] returned HTTP ${res.status}`);
    }
    const payload = (await res.json()) as { result?: unknown; error?: string };
    if (payload.error) {
      if (responseIndicatesQuotaExhaustion(res.status, String(payload.error))) {
        markAccountQuotaExhausted(account.label);
        throw new Error(
          `Upstash REST [${account.label}] quota exhausted (body) — cooldown until window reset (auto-rotate active)`,
        );
      }
      throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
    }
    return payload.result;
  };
  return {
    mode: "upstash-rest",
    account: account.label,
    ping: async () => (await call(["PING"])) as string,
    info: async () => {
      try {
        const res = await call(["INFO"]);
        return typeof res === "string" ? res : JSON.stringify(res);
      } catch {
        return "INFO command not fully supported on Upstash REST cache.";
      }
    },
    get: async (key) => (await call(["GET", key])) as string | null,
    set: async (key, value) => {
      await call(["SET", key, value]);
    },
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

function makeTcpChainClient(account: RedisAccountConfig): ChainClient {
  const Ctor: TcpRedisCtor = tcpRedisCtor ?? (Redis as unknown as TcpRedisCtor);
  const connect = () =>
    new Ctor(account.tcpUrl as string, { maxRetriesPerRequest: 1, connectTimeout: 5000 });
  return {
    mode: "ioredis-tcp",
    account: account.label,
    ping: async () => {
      const c = connect();
      try {
        return await c.ping();
      } finally {
        c.disconnect();
      }
    },
    info: async () => {
      const c = connect();
      try {
        return await c.info();
      } finally {
        c.disconnect();
      }
    },
    get: async (key) => {
      const c = connect();
      try {
        return (await c.get(key)) ?? null;
      } finally {
        c.disconnect();
      }
    },
    set: async (key, value) => {
      const c = connect();
      try {
        await c.set(key, value);
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

/** The ONE per-account client factory (REST first, then TCP; null if unconfigured). */
export function clientForAccount(account: RedisAccountConfig): ChainClient | null {
  if (account.restUrl && account.restToken) return makeRestChainClient(account);
  if (account.tcpUrl) return makeTcpChainClient(account);
  return null;
}

// ── The ONE account-chain walk ──────────────────────────────────────────────

export type RunWithChainOptions = {
  /** Operator-facing label woven into the aggregated failure message. */
  opLabel?: string;
  /** Error thrown when no account is configured (default: canonical message). */
  noConfigMessage?: string;
};

export function noRedisConfigError(opts: RunWithChainOptions | undefined): Error {
  return new Error(
    opts?.noConfigMessage ?? "No Redis configuration found (missing REST or TCP credentials)",
  );
}

function aggregateChainFailure(opLabel: string | undefined, attempts: AccountAttempt[]): Error {
  const failures = attempts
    .map((a) => `${a.account}: ${a.error ?? "unknown error"}`)
    .join(" | ");
  return new Error(`All ${attempts.length} Redis account(s) failed${opLabel ? ` (${opLabel})` : ""}: ${failures}`);
}

/** Canonical quota-marking catch-all: message-based (REST marks precisely from status+body first). */
function markQuotaIfExhausted(account: string, errMsg: string): void {
  if (responseIndicatesQuotaExhaustion(0, errMsg)) {
    markAccountQuotaExhausted(account);
  }
}

/**
 * THE first-responder account-chain walk: try each active (cooldown-free)
 * account in order until `op` succeeds; mark quota-exhausted accounts into
 * cooldown and auto-rotate; throw an aggregated failure when every account
 * rejects. Every fallback-prone Redis call site in the tower routes here.
 */
export async function runWithAccountChain<T>(
  op: (client: ChainClient) => Promise<T>,
  opts: RunWithChainOptions = {},
): Promise<{ result: T; client: ChainClient; attempts: AccountAttempt[] }> {
  const attempts: AccountAttempt[] = [];
  // বাংলা মন্তব্য (#2613 R2): cooldown-এ থাকা account-এ একটিও request না
  // পাঠিয়ে সরাসরি active chain থেকে শুরু — কোটা-ত্রুটি ধরা পড়লেই ওই
  // account window-reset পর্যন্ত cooldown-এ যায় ও পরের account-এ shift হয়।
  for (const account of activeAccountChain()) {
    const client = clientForAccount(account);
    if (!client) continue;
    try {
      const result = await op(client);
      attempts.push({ account: client.account, mode: client.mode, ok: true });
      return { client, result, attempts };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      markQuotaIfExhausted(client.account, errMsg);
      attempts.push({ account: client.account, mode: client.mode, ok: false, error: errMsg });
    }
  }
  // Empty chain (or no usable account) → the explicit no-config error;
  // otherwise every configured account rejected the op → aggregate honestly.
  if (attempts.length === 0) throw noRedisConfigError(opts);
  throw aggregateChainFailure(opts.opLabel, attempts);
}

export type AccountChainReadEntry<T> = AccountAttempt & { value?: T };

/**
 * Merge-read across ALL active accounts (heartbeat/presence listing
 * semantics): runs `op` for every account, never stops at the first
 * responder, and reports per-account outcomes. Individual account failures
 * degrade gracefully — the remaining chain still serves the read.
 */
export async function readAcrossAccountChain<T>(
  op: (client: ChainClient) => Promise<T>,
  opts: RunWithChainOptions = {},
): Promise<{ entries: Array<AccountChainReadEntry<T>> }> {
  const chain = activeAccountChain();
  if (chain.length === 0) throw noRedisConfigError(opts);
  const entries: Array<AccountChainReadEntry<T>> = [];
  for (const account of chain) {
    const client = clientForAccount(account);
    if (!client) continue;
    try {
      const value = await op(client);
      entries.push({ account: client.account, mode: client.mode, ok: true, value });
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      markQuotaIfExhausted(client.account, errMsg);
      entries.push({ account: client.account, mode: client.mode, ok: false, error: errMsg });
    }
  }
  return { entries };
}

// ── Health/debug surfaces (shape-stable contract for health engine + tools) ──

export async function pingRedis(): Promise<unknown> {
  const start = Date.now();
  const { client, result, attempts } = await runWithAccountChain((c) => c.ping());
  return {
    mode: client.mode,
    account: client.account,
    activePrimary: getActiveRedisAccount().label,
    status: result,
    latencyMs: Date.now() - start,
    chainSize: attempts.length,
    attemptedAccounts: attempts.map(({ account, mode, ok, error }) => ({ account, mode, ok, error })),
    chainStatus: quotaChainStatus(),
  };
}

export async function getRedisStats(): Promise<unknown> {
  const { client, result } = await runWithAccountChain((c) => c.info());
  return {
    mode: client.mode,
    account: client.account,
    activePrimary: getActiveRedisAccount().label,
    statsRaw: result,
    chainStatus: quotaChainStatus(),
  };
}

export async function readRedisKey(key: string): Promise<unknown> {
  const { client, result } = await runWithAccountChain((c) => c.get(key));
  return {
    mode: client.mode,
    account: client.account,
    activePrimary: getActiveRedisAccount().label,
    key,
    value: result ?? null,
  };
}
