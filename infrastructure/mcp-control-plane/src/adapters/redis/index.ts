/**
 * Read-only Redis health adapter — CHAIN-AWARE (issue #1402 follow-up).
 *
 * Previously this adapter pinged ONLY the canonical Upstash primary account,
 * so when that account hit its 500k/day command ceiling the fleet reported
 * Redis DOWN even though the multi-account failover chain (primary →
 * secondary → tertiary → quaternary → quinary, see lib/redis_chain.ts) was
 * serving every heartbeat/queue write on the next account — a false negative
 * that degraded health sweeps and paged on healthy infrastructure.
 *
 * New contract: walk the account chain; the FIRST account whose PING succeeds
 * represents Redis health. The result reports WHICH account answered and the
 * per-account failures seen along the way. Redis is DOWN only when EVERY
 * account in the chain fails.
 *
 * `readRedisKey`/`getRedisStats` walk the chain too (first responder wins) —
 * note these are debug surfaces; the agent-heartbeat reader performs its own
 * freshest-record merge across ALL accounts and is unaffected.
 */

import { Redis as UpstashRedis } from "@upstash/redis";
import Redis from "ioredis";
import {
  buildAccountChain,
  activeAccountChain,
  markAccountQuotaExhausted,
  responseIndicatesQuotaExhaustion,
  getActiveRedisAccount,
  quotaChainStatus,
  type RedisAccountConfig,
} from "../../lib/redis_chain.js";

type AccountAttempt = {
  account: string;
  mode: "upstash-rest" | "ioredis-tcp";
  ok: boolean;
  error?: string;
};

type ChainClient = {
  mode: "upstash-rest" | "ioredis-tcp";
  account: string;
  ping: () => Promise<string>;
  info: () => Promise<string>;
  get: (key: string) => Promise<unknown>;
};

/** Build a per-call client for one chain account (REST first, then TCP). */
function clientForAccount(account: RedisAccountConfig): ChainClient | null {
  if (account.restUrl && account.restToken) {
    const redis = new UpstashRedis({
      url: account.restUrl,
      token: account.restToken,
    });
    return {
      mode: "upstash-rest",
      account: account.label,
      ping: async () => await redis.ping(),
      info: async () => {
        try {
          // @ts-ignore
          const res = await redis.info();
          return typeof res === "string" ? res : JSON.stringify(res);
        } catch {
          return "INFO command not fully supported on Upstash REST cache.";
        }
      },
      get: async (key: string) => await redis.get(key),
    };
  }
  if (account.tcpUrl) {
    const redisClient = new (Redis as any)(account.tcpUrl, {
      maxRetriesPerRequest: 1,
      connectTimeout: 5000,
      lazyConnect: true,
      enableOfflineQueue: false,
    });
    // Prevent unhandled error event crashes in Node.js on unreachable TCP host
    redisClient.on("error", () => {});
    return {
      mode: "ioredis-tcp",
      account: account.label,
      ping: async () => {
        try {
          return await redisClient.ping();
        } finally {
          redisClient.disconnect();
        }
      },
      info: async () => {
        try {
          const infoStr = await redisClient.info();
          return infoStr;
        } finally {
          redisClient.disconnect();
        }
      },
      get: async (key: string) => {
        try {
          const val = await redisClient.get(key);
          return val;
        } finally {
          redisClient.disconnect();
        }
      },
    };
  }
  return null;
}

async function firstRespondingClient(
  op: (client: ChainClient) => Promise<unknown>,
): Promise<{ client: ChainClient; result: unknown; attempts: AccountAttempt[] }> {
  // Walk active non-exhausted accounts first (auto-rotated pool)
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error("No Redis configuration found (missing REST or TCP credentials)");
  }
  const attempts: AccountAttempt[] = [];
  for (const account of chain) {
    const client = clientForAccount(account);
    if (!client) continue;
    try {
      const result = await op(client);
      attempts.push({ account: client.account, mode: client.mode, ok: true });
      return { client, result, attempts };
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : String(err);
      if (responseIndicatesQuotaExhaustion(0, errMsg)) {
        markAccountQuotaExhausted(client.account);
      }
      attempts.push({
        account: client.account,
        mode: client.mode,
        ok: false,
        error: errMsg,
      });
    }
  }
  const failures = attempts
    .map((a) => `${a.account}: ${a.error ?? "unknown error"}`)
    .join(" | ");
  throw new Error(`All ${attempts.length} Redis account(s) failed: ${failures}`);
}

export async function pingRedis(): Promise<unknown> {
  const start = Date.now();
  const { client, result, attempts } = await firstRespondingClient((c) => c.ping());
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
  const { client, result } = await firstRespondingClient((c) => c.info());
  return {
    mode: client.mode,
    account: client.account,
    activePrimary: getActiveRedisAccount().label,
    statsRaw: result,
    chainStatus: quotaChainStatus(),
  };
}

export async function readRedisKey(key: string): Promise<unknown> {
  const { client, result } = await firstRespondingClient((c) => c.get(key));
  return {
    mode: client.mode,
    account: client.account,
    activePrimary: getActiveRedisAccount().label,
    key,
    value: result ?? null,
  };
}
