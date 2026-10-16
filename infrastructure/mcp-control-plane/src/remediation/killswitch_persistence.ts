/**
 * Kill-switch persistence — Redis-backed emergency autonomy state (#340).
 *
 * Problem (issue #340 AC1): `src/remediation/killswitch.ts` keeps the
 * autonomy flag in memory only. Every restart resurrects autonomy — an
 * operator's emergency stop silently evaporates on the next deploy, which is
 * exactly the wrong default for a KILL switch.
 *
 * This module is a DROP-IN persistence layer for the live tower:
 *   - pure-new-file delivery (the bridge cannot apply hunks against live
 *     private files — see docs/KILLSWITCH_PERSISTENCE.md for the 3-line
 *     operator integration diff into killswitch.ts / index.ts);
 *   - every Redis-facing surface walks the vault-provisioned account chain
 *     (house law, src/lib/redis_chain.ts header) — persistence must survive
 *     a quota-dead primary exactly like heartbeats do;
 *   - the state key carries NO TTL: an emergency stop must never expire.
 *
 * Hermeticity contract: importing this module performs ZERO I/O and ZERO
 * credential reads. `../lib/redis_chain.js` is loaded lazily inside the
 * default port resolver (mirrors the `await import("ioredis")` boot pattern
 * in src/index.ts), so offline harnesses can inject fake ports and never
 * touch Redis/dotenv at all (selftest_killswitch_persistence.ts).
 *
 * Storage contract:
 *   Key:   supremeai:autonomy-killswitch        (single global flag, no TTL)
 *   Value: JSON KillSwitchPersistedState (schemaVersion 1, unknown versions
 *          are rejected fail-closed by parsePersistedState)
 *
 * বাংলা মন্তব্য: জরুরি স্টপ-এর পরেও রিস্টার্টে autonomy ফিরে আসা ছিল একটি
 * নিরাপত্তা-গর্ত (#340 AC1)। এই মডিউল kill-switch অবস্থা Redis account-chain-এ
 * স্থায়ীভাবে লেখে (কোনো TTL নেই — কিল-সুইচ কখনো নীরবে মেয়াদোত্তীর্ণ হয় না) এবং
 * বুটে সেই অবস্থা পুনঃপ্রয়োগ করার পোর্টা দেয়। প্রতিটি লেখা/পড়া chain-walk
 * ইঞ্জিন (runWithAccountChain) দিয়ে যায় — প্রাইমারি কোটা-মৃত হলে স্বয়ংক্রিয়ভাবে
 * পরের account (secondary → tertiary → …) উত্তর দেয়।
 */

// ── Public types ────────────────────────────────────────────────────────────

/** JSON payload stored under KILLSWITCH_STATE_KEY. */
export type KillSwitchPersistedState = {
  /** true = autonomy re-enabled explicitly; false = emergency stop. */
  autonomyEnabled: boolean;
  /** Why the flag moved (e.g. "emergency-stop", "admin-re-enable"). */
  reason: string;
  /** Admin/client id that moved the flag (audit trail, may be omitted). */
  requestedBy?: string;
  /** Epoch ms of the state change (writer clock). */
  updatedAtMs: number;
  /** ISO-8601 twin of updatedAtMs for human readers. */
  updatedAt: string;
  /** Storage schema version — currently 1; unknown versions fail closed. */
  schemaVersion: 1;
};

/**
 * Minimal synchronous-shape Redis port (read one key, write one key with NO
 * TTL). Injectable for hermetic tests; the default resolver walks the real
 * Upstash REST/TCP account chain from src/lib/redis_chain.ts.
 */
export type KillSwitchRedisPort = {
  readonly account: string;
  get: (key: string) => Promise<string | null>;
  /** Unconditional SET — deliberately NOT SETEX: kill-switch state never expires. */
  set: (key: string, value: string) => Promise<void>;
};

export type KillSwitchPersistResult = {
  ok: boolean;
  key: string;
  /** The account whose write won (undefined when every account failed). */
  account?: string;
  attempts: Array<{ account: string; ok: boolean; error?: string }>;
};

export type KillSwitchLoadResult =
  | { outcome: "absent" }
  | { outcome: "loaded"; state: KillSwitchPersistedState }
  | { outcome: "corrupt"; reason: string }
  | { outcome: "unreachable"; reason: string };

/**
 * Boot-restore verdict. `fresh` = no persisted state (brand-new deployment —
 * autonomy stays enabled, the documented default); `disabled` = an operator
 * stopped autonomy and the integration MUST re-apply the stop; `enabled` =
 * an explicit re-enable was persisted; `unreachable`/`corrupt` = Redis could
 * not answer truthfully at boot (integration logs an ERROR banner and keeps
 * the documented default — bricking boot would be worse; every emergencyStop
 * re-persists and heals the key).
 */
export type KillSwitchRestoreOutcome =
  | "fresh"
  | "disabled"
  | "enabled"
  | "unreachable"
  | "corrupt";

export type KillSwitchRestoreResult = {
  outcome: KillSwitchRestoreOutcome;
  state: KillSwitchPersistedState | null;
  reason?: string;
};

/** Structural mirror of lib/redis_chain.ts's account type (TS structural typing). */
type RedisAccountConfig = {
  label: string;
  restUrl?: string;
  restToken?: string;
  tcpUrl?: string;
};

/** Structural mirror of the chain-walk engine's result shape (#110). */
type ChainWalkAttempt = { account: string; ok: boolean; error?: string };
type ChainWalk = <T>(
  op: (account: RedisAccountConfig) => Promise<T>,
) => Promise<{ value: T; account: RedisAccountConfig; attempts: ChainWalkAttempt[] }>;

// ── Constants ───────────────────────────────────────────────────────────────

export const KILLSWITCH_STATE_KEY = "supremeai:autonomy-killswitch";
export const KILLSWITCH_SCHEMA_VERSION = 1 as const;

// ── Fail-closed parsing ─────────────────────────────────────────────────────

/**
 * Parses a raw GET payload into state, or explains why it cannot be trusted.
 * Unknown schemaVersion, non-object JSON, missing/NaN updatedAtMs, or an
 * autonomyEnabled that is not boolean → corrupt (never guessed).
 */
export function parsePersistedState(raw: string | null): KillSwitchPersistedState | { corruptReason: string } {
  if (raw === null || raw === "") return { corruptReason: "empty payload" };
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    return { corruptReason: `JSON.parse failed: ${(err as Error).message}` };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { corruptReason: "payload is not a JSON object" };
  }
  const obj = parsed as Record<string, unknown>;
  if (obj.schemaVersion !== KILLSWITCH_SCHEMA_VERSION) {
    return {
      corruptReason: `unsupported schemaVersion ${JSON.stringify(obj.schemaVersion)} (expected ${KILLSWITCH_SCHEMA_VERSION})`,
    };
  }
  if (typeof obj.autonomyEnabled !== "boolean") {
    return { corruptReason: "autonomyEnabled must be boolean" };
  }
  if (typeof obj.reason !== "string" || obj.reason.length === 0) {
    return { corruptReason: "reason must be a non-empty string" };
  }
  if (typeof obj.updatedAtMs !== "number" || !Number.isFinite(obj.updatedAtMs) || obj.updatedAtMs < 0) {
    return { corruptReason: "updatedAtMs must be a non-negative finite number" };
  }
  if (typeof obj.updatedAt !== "string") {
    return { corruptReason: "updatedAt must be an ISO-8601 string" };
  }
  if (obj.requestedBy !== undefined && typeof obj.requestedBy !== "string") {
    return { corruptReason: "requestedBy must be a string when present" };
  }
  const state: KillSwitchPersistedState = {
    autonomyEnabled: obj.autonomyEnabled,
    reason: obj.reason,
    updatedAtMs: obj.updatedAtMs,
    updatedAt: obj.updatedAt,
    schemaVersion: KILLSWITCH_SCHEMA_VERSION,
  };
  if (obj.requestedBy !== undefined) state.requestedBy = obj.requestedBy as string;
  return state;
}

export function isPersistedState(
  value: KillSwitchPersistedState | { corruptReason: string },
): value is KillSwitchPersistedState {
  return typeof (value as { corruptReason?: string }).corruptReason !== "string";
}

// ── Default Redis ports (lazy — keep module import hermetic) ────────────────

type RedisChainModule = {
  runWithAccountChain: ChainWalk;
};

let chainModulePromise: Promise<RedisChainModule> | null = null;

async function loadChainModule(): Promise<RedisChainModule> {
  if (!chainModulePromise) {
    // Dynamic-string import (`as string`): the dependency is resolved at
    // RUNTIME only, so type-checking this file never drags lib/env.ts (and
    // its dotenv import) into hermetic/offline harnesses. The runtime shape
    // check below + the structural ChainWalk type keep the call site typed.
    chainModulePromise = import("../lib/redis_chain.js" as string).then((m) => {
      const mod = m as unknown as RedisChainModule;
      if (typeof mod.runWithAccountChain !== "function") {
        throw new Error("lib/redis_chain.js did not expose runWithAccountChain — account-chain law violated");
      }
      return mod;
    });
  }
  return chainModulePromise;
}

/** Builds the REST port for one chain account (Upstash POST, single command). */
export function makeRestPort(account: RedisAccountConfig): KillSwitchRedisPort {
  const restUrl = account.restUrl as string;
  const auth = `Bearer ${account.restToken}`;
  const call = async (command: string[]): Promise<unknown> => {
    const res = await fetch(restUrl, {
      method: "POST",
      headers: { Authorization: auth, "Content-Type": "application/json" },
      body: JSON.stringify(command),
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) throw new Error(`Upstash REST [${account.label}] returned HTTP ${res.status}`);
    const payload = (await res.json()) as { result?: unknown; error?: string };
    if (payload.error) throw new Error(`Upstash error [${account.label}]: ${payload.error}`);
    return payload.result;
  };
  return {
    account: account.label,
    get: async (key) => (await call(["GET", key])) as string | null,
    set: async (key, value) => {
      await call(["SET", key, value]);
    },
  };
}

/** Builds the TCP (ioredis) port for one chain account — lazy import. */
export async function makeTcpPort(account: RedisAccountConfig): Promise<KillSwitchRedisPort> {
  const ioredis = (await import("ioredis" as string).catch(() => null)) as
    | { default: new (url: string, opts?: object) => RedisTcpLike }
    | null;
  if (!ioredis) {
    throw new Error(`ioredis unavailable — TCP-only account "${account.label}" cannot serve the kill switch`);
  }
  const client = new ioredis.default(account.tcpUrl as string, { maxRetriesPerRequest: 1, connectTimeout: 5000 });
  return {
    account: account.label,
    get: async (key) => {
      try {
        return await client.get(key);
      } finally {
        client.disconnect();
      }
    },
    set: async (key, value) => {
      try {
        await client.set(key, value);
      } finally {
        client.disconnect();
      }
    },
  };
}

type RedisTcpLike = {
  get: (key: string) => Promise<string | null>;
  set: (key: string, value: string) => Promise<void>;
  disconnect: () => void;
};

/**
 * Default port: the first account of the ACTIVE (cooldown-free) chain that
 * answers. Kept behind a function so importing this module never resolves
 * credentials (hermetic contract).
 */
export async function makeDefaultPort(): Promise<KillSwitchRedisPort> {
  const chain = await loadChainModule();
  const probe = await chain.runWithAccountChain(async (account) => {
    const port = account.restUrl && account.restToken ? makeRestPort(account) : await makeTcpPort(account);
    // Cheap liveness probe — PING-equivalent: a GET on the state key doubles
    // as both reachability proof and the read the caller wants anyway.
    await port.get(KILLSWITCH_STATE_KEY);
    return account;
  });
  const account = probe.account;
  return account.restUrl && account.restToken ? makeRestPort(account) : await makeTcpPort(account);
}

// ── Public API ──────────────────────────────────────────────────────────────

export type PersistKillSwitchInput = {
  autonomyEnabled: boolean;
  reason: string;
  requestedBy?: string;
  nowMs?: number;
  /** Injectable port (tests / custom transports). Default: account-chain walk. */
  port?: KillSwitchRedisPort;
  /** Injectable chain walk (tests). Default: lib/redis_chain runWithAccountChain. */
  chain?: ChainWalk;
};

/**
 * Persists the kill-switch state through the account chain (or an injected
 * port). Returns ok:false WITH the full attempt ledger when every account
 * failed — the integration must surface that loudly, because a failed
 * persist means the stop will NOT survive a restart.
 */
export async function persistKillSwitchState(input: PersistKillSwitchInput): Promise<KillSwitchPersistResult> {
  const nowMs = input.nowMs ?? Date.now();
  const state: KillSwitchPersistedState = {
    autonomyEnabled: input.autonomyEnabled,
    reason: input.reason,
    updatedAtMs: nowMs,
    updatedAt: new Date(nowMs).toISOString(),
    schemaVersion: KILLSWITCH_SCHEMA_VERSION,
  };
  if (input.requestedBy !== undefined) state.requestedBy = input.requestedBy;
  const value = JSON.stringify(state);

  if (input.port) {
    try {
      await input.port.set(KILLSWITCH_STATE_KEY, value);
      return { ok: true, key: KILLSWITCH_STATE_KEY, account: input.port.account, attempts: [{ account: input.port.account, ok: true }] };
    } catch (err) {
      return {
        ok: false,
        key: KILLSWITCH_STATE_KEY,
        attempts: [{ account: input.port.account, ok: false, error: (err as Error).message }],
      };
    }
  }

  const chain = input.chain ?? (await loadChainModule()).runWithAccountChain;
  try {
    const walk = await chain(async (account) => {
      const port = account.restUrl && account.restToken ? makeRestPort(account) : await makeTcpPort(account);
      await port.set(KILLSWITCH_STATE_KEY, value);
      return account.label;
    });
    return {
      ok: true,
      key: KILLSWITCH_STATE_KEY,
      account: walk.value,
      attempts: walk.attempts,
    };
  } catch (err) {
    return {
      ok: false,
      key: KILLSWITCH_STATE_KEY,
      attempts: extractAttempts(err),
    };
  }
}

/** Normalizes an aggregated chain-walk error back into the attempt ledger. */
function extractAttempts(err: unknown): Array<{ account: string; ok: boolean; error?: string }> {
  const message = (err as Error)?.message ?? String(err);
  const attempts: Array<{ account: string; ok: boolean; error?: string }> = [];
  // runWithAccountChain aggregates: "All <n> Redis account(s) failed: <label>: <err> | ..."
  const aggregate = /All \d+ Redis account\(s\) failed: (.*)$/s.exec(message);
  const body = aggregate ? aggregate[1] : message;
  for (const part of body.split(" | ")) {
    const sep = part.indexOf(": ");
    if (sep === -1) {
      attempts.push({ account: "unknown", ok: false, error: part });
    } else {
      attempts.push({ account: part.slice(0, sep), ok: false, error: part.slice(sep + 2) });
    }
  }
  return attempts.length > 0 ? attempts : [{ account: "unknown", ok: false, error: message }];
}

export type LoadKillSwitchOptions = {
  port?: KillSwitchRedisPort;
  chain?: ChainWalk;
};

/** Reads the persisted state (single account read via chain walk). */
export async function loadKillSwitchState(opts: LoadKillSwitchOptions = {}): Promise<KillSwitchLoadResult> {
  let raw: string | null;
  try {
    raw = await readThroughChain(opts);
  } catch (err) {
    return { outcome: "unreachable", reason: (err as Error).message };
  }
  if (raw === null) return { outcome: "absent" }; // key missing → fresh deployment
  const parsed = parsePersistedState(raw);
  if (!isPersistedState(parsed)) return { outcome: "corrupt", reason: parsed.corruptReason };
  return { outcome: "loaded", state: parsed };
}

async function readThroughChain(opts: LoadKillSwitchOptions): Promise<string | null> {
  if (opts.port) return opts.port.get(KILLSWITCH_STATE_KEY);
  const chain = opts.chain ?? (await loadChainModule()).runWithAccountChain;
  const walk = await chain(async (account) => {
    const port = account.restUrl && account.restToken ? makeRestPort(account) : await makeTcpPort(account);
    return port.get(KILLSWITCH_STATE_KEY);
  });
  return walk.value;
}

/**
 * Boot-restore verdict for the live tower. Pure decision over the load
 * result — the integration maps `disabled` → `globalKillSwitch.emergencyStop()`
 * and everything else stays default-enabled with the mandated ERROR/log line.
 */
export function deriveRestoreOutcome(load: KillSwitchLoadResult): KillSwitchRestoreResult {
  switch (load.outcome) {
    case "absent":
      return { outcome: "fresh", state: null };
    case "loaded":
      return load.state.autonomyEnabled
        ? { outcome: "enabled", state: load.state }
        : { outcome: "disabled", state: load.state };
    case "corrupt":
      return { outcome: "corrupt", state: null, reason: load.reason };
    case "unreachable":
      return { outcome: "unreachable", state: null, reason: load.reason };
  }
}

export async function restoreKillSwitchOnBoot(opts: LoadKillSwitchOptions = {}): Promise<KillSwitchRestoreResult> {
  return deriveRestoreOutcome(await loadKillSwitchState(opts));
}
