// ── Upstash multi-account fallback chain (shared) ───────────────────────────
// The fleet's canonical Upstash PRIMARY repeatedly hits its 500k/day command
// ceiling (issue #1402 "Redis" note; live incidents). Liveness and health data
// MUST survive a quota-dead account, so every Redis-facing surface walks the
// vault-provisioned account chain (primary → secondary → tertiary →
// quaternary → quinary; injected by infisical_bootstrap AND mirrored into
// Render service env for vault-independence).
//
// Extracted from registry/agent_heartbeat.ts (issue #1402) so the read-only
// health adapter (adapters/redis) can also report fleet-wide Redis capability
// instead of failing on the primary alone (false DOWN while the chain serves).

import { env } from "./env.js";

export type RedisAccountConfig = {
  label: string;
  restUrl?: string;
  restToken?: string;
  tcpUrl?: string;
};

const CHAIN_ENV_SUFFIXES: Array<[string, string, string]> = [
  ["secondary", "UPSTASH_REDIS_SECONDARY_REST_URL", "UPSTASH_REDIS_SECONDARY_REST_TOKEN"],
  ["tertiary", "UPSTASH_REDIS_TERTIARY_REST_URL", "UPSTASH_REDIS_TERTIARY_REST_TOKEN"],
  ["quaternary", "UPSTASH_REDIS_QUATERNARY_REST_URL", "UPSTASH_REDIS_QUATERNARY_REST_TOKEN"],
  ["quinary", "UPSTASH_REDIS_QUINARY_REST_URL", "UPSTASH_REDIS_QUINARY_REST_TOKEN"],
];

/** Ordered account chain from env (labels match the dashboard's chain). */
export function buildAccountChain(): RedisAccountConfig[] {
  const chain: RedisAccountConfig[] = [];
  const restUrl = env.redis.restUrl;
  let restToken = env.redis.restToken;
  const tcpUrl = env.redis.url;

  // If restUrl has embedded token (e.g. https://default:TOKEN@host), extract it if restToken is missing
  if (restUrl && !restToken) {
    try {
      const parsed = new URL(restUrl);
      const token = decodeURIComponent(parsed.password || parsed.username || "");
      if (token) restToken = token;
    } catch {}
  }

  if (restUrl && restToken) {
    chain.push({ label: process.env.REDIS_ACCOUNT_LABEL || "primary", restUrl, restToken });
  } else if (tcpUrl) {
    chain.push({ label: process.env.REDIS_ACCOUNT_LABEL || "primary", tcpUrl });
  }
  for (const [label, urlKey, tokenKey] of CHAIN_ENV_SUFFIXES) {
    const url = process.env[urlKey];
    const token = process.env[tokenKey];
    if (url && token) chain.push({ label, restUrl: url, restToken: token });
  }

  // If primary was REST and tcpUrl is also provided (e.g. local redis or emergency fallback),
  // append it to the chain as an emergency fallback if all Upstash REST accounts exhaust quota.
  if (restUrl && restToken && tcpUrl) {
    chain.push({ label: "tcp-fallback", tcpUrl });
  }

  return chain;
}

// ── কোটা-উইন্ডো ও অটো-রোটেশন cooldown registry (#26 / #2613 — free-tier permanent fix) ────
// বাংলা মন্তব্য: Upstash free tier-এর 500k মাসিক কোটা শেষ হলে REST API HTTP 400 +
// "max requests limit ..." মার্কার-সহ body দেয় (Issue #26)। এই shared registry মার্কার দেখা
// মাত্রই ওই account-কে পরবর্তী উইন্ডো রিসেট (মাসিক বা দৈনিক) পর্যন্ত cooldown-এ ফেলে —
// ফলে tower-এর সব Redis-পথ (heartbeat read/write, orchestrator dispatch, health)
// exhausted account-এ একটিও wasted request না পাঠিয়ে সরাসরি পরের account-এ
// auto-rotate করে (primary → secondary → tertiary → quaternary → quinary)।
// উইন্ডো শেষ হলে কোটা রিসেট পেয়ে account স্বয়ংক্রিয়ভাবে পুনরায় রোটেশন পুলে ফিরে আসে।
export const QUOTA_EXCEEDED_MARKER = "max requests limit";

const quotaCooldownUntil = new Map<string, number>();

/**
 * সক্রিয় কোটার রিসেট সময় (ms epoch)।
 * Upstash free tier-এর 500k লিমিট মূলত **মাসিক** (#26) — মাসের ১ তারিখ 00:00 UTC রিসেট।
 * legacy opt-out হিসেবে UPSTASH_QUOTA_WINDOW=daily দিলে দৈনিক মধ্যরাত ধরে।
 */
export function nextQuotaResetEpochMs(nowMs: number = Date.now()): number {
  const windowType = (process.env.UPSTASH_QUOTA_WINDOW || "monthly").toLowerCase();
  const d = new Date(nowMs);
  if (windowType === "daily" || windowType === "day") {
    const nextMidnight = Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + 1, 0, 0, 0, 0);
    return nextMidnight + 60_000;
  }
  // Default: Monthly reset (1st of next month at 00:00 UTC + 60s grace)
  const nextMonth = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1, 0, 0, 0, 0);
  return nextMonth + 60_000;
}

/** পরবর্তী UTC মধ্যরাত + ৬০s grace (ms epoch) — legacy compatibility। */
export function nextUtcResetEpochMs(nowMs: number = Date.now()): number {
  return nextQuotaResetEpochMs(nowMs);
}

/** ওই account-কে কোটা cooldown-এ ফেলে ও পরের অ্যাকাউন্টে অটো-রোটেট করে (R2)। */
export function markAccountQuotaExhausted(label: string, untilMs: number = nextQuotaResetEpochMs()): void {
  const prev = quotaCooldownUntil.get(label) ?? 0;
  if (untilMs > prev) {
    quotaCooldownUntil.set(label, untilMs);
    console.warn(
      `[redis-chain] Upstash account "${label}" কোটা শেষ — ` +
        `cooldown until ${new Date(untilMs).toISOString()} (স্বয়ংক্রিয় auto-rotate সক্রিয়)।`,
    );
  }
}

/** ম্যানুয়াল বা অ্যাডমিন কল দ্বারা একটি অ্যাকাউন্টকে অবিলম্বে cooldown/rotate করা। */
export function forceRotateAccount(label: string, untilMs: number = nextQuotaResetEpochMs()): void {
  markAccountQuotaExhausted(label, untilMs);
}

/** Account কি এই মুহূর্তে কোটা cooldown-এ? (মেয়াদ শেষ হলে entry পরিষ্কার হয়) */
export function isAccountQuotaExhausted(label: string, nowMs: number = Date.now()): boolean {
  const until = quotaCooldownUntil.get(label);
  if (until === undefined) return false;
  if (nowMs >= until) {
    quotaCooldownUntil.delete(label);
    return false;
  }
  return true;
}

/**
 * Cooldown-মুক্ত account-দের chain (R2)। সব account cooldown-এ থাকলে পুরো
 * chain ফিরিয়ে দাও — সময়-হিসাবে ভুল হলেও fleet-wide blackout এড়াতে
 * (graceful degradation, AGENTS.md invariant #3)।
 */
export function activeAccountChain(nowMs: number = Date.now()): RedisAccountConfig[] {
  const chain = buildAccountChain();
  const active = chain.filter((account) => !isAccountQuotaExhausted(account.label, nowMs));
  return active.length > 0 ? active : chain;
}

/**
 * বর্তমানে সক্রিয় অটো-রোটেটেড Primary অ্যাকাউন্ট (চেইনের প্রথম সুস্থ অ্যাকাউন্ট)।
 */
export function getActiveRedisAccount(nowMs: number = Date.now()): RedisAccountConfig {
  const active = activeAccountChain(nowMs);
  return active[0] ?? buildAccountChain()[0] ?? { label: "primary", restUrl: env.redis.restUrl, tcpUrl: env.redis.url };
}

/** REST response-এ কোটা-ত্রুটির মার্কার আছে কি না (status + body উভয় থেকে)। */
export function responseIndicatesQuotaExhaustion(status: number, body: string): boolean {
  if (status === 429 || status === 402) return true;
  if (!body) return false;
  const lower = body.toLowerCase();
  return (
    lower.includes(QUOTA_EXCEEDED_MARKER) ||
    lower.includes("err max requests limit exceeded") ||
    lower.includes("requests limit exceeded") ||
    lower.includes("request limit exceeded") ||
    lower.includes("daily request limit") ||
    lower.includes("monthly request limit") ||
    lower.includes("rate limit exceeded") ||
    lower.includes("quota exceeded") ||
    lower.includes("quota exhausted") ||
    lower.includes("bandwidth limit exceeded") ||
    lower.includes("too many requests") ||
    lower.includes("payment required") ||
    lower.includes("over quota") ||
    (status === 400 && lower.includes("limit"))
  );
}

// ── Preemptive quota ledger (#646 — 480k soft threshold) ───────────────────
// বাংলা মন্তব্য: প্রতিক্রিয়াশীল (reactive) রোটেশন কোটার হার্ড সীমা ভাঙার
// পরে — অর্থাৎ একটি ব্যর্থ রিকোয়েস্ট খেয়ে ফেলার পরে — ঘটে। #646 এটিকে
// প্রিএম্পটিভ (preemptive) করে: প্রতিটি account-এ সত্যিই পাঠানো Redis
// command-এর একটি লোকাল মাসিক লেজার এখানে রাখা হয়; ব্যবহার ≥ ৯৬% (ডিফল্ট
// 500k-এর 480k) হলেই account-টি উইন্ডো রিসেট পর্যন্ত soft-cooldown-এ চলে যায় —
// একই cooldown registry (quotaCooldownUntil) ব্যবহার করে, তাই
// activeAccountChain() হার্ড 500k সীমা স্পর্শের আগেই পরের account-এ ঘুরে যায়
// এবং কোনো রিকোয়েস্ট কখনোই হার্ড বাউন্ডারিতে হিট করে না।
//
// উইন্ডো: Upstash free tier মাসিক (মাসের ১ তারিখ 00:00 UTC রিসেট) —
// currentQuotaWindowStartMs() দিয়ে রোলওভার শনাক্ত হয়; নতুন উইন্ডোতে কাউন্ট
// স্বয়ংক্রিয়ভাবে ০ হয় এবং cooldown মেয়াদও nextQuotaResetEpochMs পর্যন্ত।
//
// সীমা-কনফিগ: UPSTASH_QUOTA_LIMIT (ডিফল্ট 500000), UPSTASH_QUOTA_SOFT_THRESHOLD
// (ডিফল্ট ৯৬% = 480000)। Getter ফাংশন — টেস্টে env পাল্টানো যায়।

export function quotaLimit(): number {
  const v = Number(process.env.UPSTASH_QUOTA_LIMIT);
  return Number.isFinite(v) && v > 0 ? v : 500_000;
}

export function quotaSoftThreshold(): number {
  const v = Number(process.env.UPSTASH_QUOTA_SOFT_THRESHOLD);
  if (Number.isFinite(v) && v > 0) return v;
  return Math.floor(quotaLimit() * 0.96);
}

/** বর্তমান মাসিক UTC কোটা উইন্ডোর শুরু (মাসের ১ তারিখ 00:00 UTC)। */
export function currentQuotaWindowStartMs(nowMs: number = Date.now()): number {
  const d = new Date(nowMs);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1, 0, 0, 0, 0);
}

type UsageLedgerEntry = { windowStartMs: number; commands: number };
const usageLedger = new Map<string, UsageLedgerEntry>();

/** ওই account-এর বর্তমান উইন্ডোর command কাউন্ট (উইন্ডো বদলালে ০)। */
export function accountUsageCommands(label: string, nowMs: number = Date.now()): number {
  const entry = usageLedger.get(label);
  if (!entry || entry.windowStartMs !== currentQuotaWindowStartMs(nowMs)) return 0;
  return entry.commands;
}

/**
 * ওই account-এ এইমাত্র পাঠানো n টি command লেজারে যোগ করে; কাউন্ট সফট
 * থ্রেশহোল্ড ছুঁলে প্রিএম্পটিভ soft-cooldown মার্ক করে (#646)। ফেরত দেয়
 * আপডেটেড কাউন্ট।
 */
export function recordRedisCommands(label: string, commands: number, nowMs: number = Date.now()): number {
  const n = Math.round(commands);
  if (!Number.isFinite(n) || n <= 0) return accountUsageCommands(label, nowMs);
  const windowStartMs = currentQuotaWindowStartMs(nowMs);
  const entry = usageLedger.get(label);
  const freshWindow = !entry || entry.windowStartMs !== windowStartMs;
  const updated = (freshWindow ? 0 : entry.commands) + n;
  usageLedger.set(label, { windowStartMs, commands: updated });
  if (updated >= quotaSoftThreshold() && !isAccountQuotaExhausted(label, nowMs)) {
    markAccountQuotaExhausted(label, nextQuotaResetEpochMs(nowMs));
    console.warn(
      `[redis-chain] "${label}" প্রিএম্পটিভ কোটা রোটেশন (#646): ${updated} commands >= ` +
        `সফট থ্রেশহোল্ড ${quotaSoftThreshold()} — হার্ড ${quotaLimit()} সীমা স্পর্শের আগেই পরের account-এ rotate।`,
    );
  }
  return updated;
}

/**
 * #646 প্রিএম্পটিভ গার্ড — পাঠানোর আগে n টি command রিজার্ভ করে; রিজার্ভের
 * ফলে সফট থ্রেশহোল্ড অতিক্রম হলে quota-shaped error ছুঁড়ে দেয় যাতে
 * runWithAccountChain ইঞ্জিন ওই রিকোয়েস্টটি পরের account-এ সরিয়ে নেয় —
 * অর্থাৎ থ্রেশহোল্ড-ক্রসিং রিকোয়েস্টটি পর্যন্ত ওই account-এ যায় না।
 * রক্ষণশীল পক্ষ: স্কিপ হওয়া command-ও কাউন্ট হয় (আন্ডার-কাউন্ট কখনো নয়)।
 */
export function quotaGuard(account: RedisAccountConfig, commands: number, nowMs: number = Date.now()): void {
  const projected = recordRedisCommands(account.label, commands, nowMs);
  if (projected >= quotaSoftThreshold()) {
    throw new RedisQuotaExhaustedError(
      account.label,
      `Upstash [${account.label}] প্রিএম্পটিভ কোটা রোটেশন (#646): রিজার্ভে ${projected} commands >= ` +
        `সফট থ্রেশহোল্ড ${quotaSoftThreshold()} — হার্ড সীমা স্পর্শের আগেই chain-এ পরের account ব্যবহার হচ্ছে`,
    );
  }
}

/** পর্যবেক্ষণের জন্য per-account usage snapshot (redis.rotation_status)। */
export function redisUsageLedgerStatus(nowMs: number = Date.now()): Array<{
  label: string;
  commands: number;
  limit: number;
  softThreshold: number;
  percentUsed: number;
  preemptivelyCooled: boolean;
}> {
  return buildAccountChain().map((account) => {
    const commands = accountUsageCommands(account.label, nowMs);
    return {
      label: account.label,
      commands,
      limit: quotaLimit(),
      softThreshold: quotaSoftThreshold(),
      percentUsed: Math.round((commands / quotaLimit()) * 10000) / 100,
      preemptivelyCooled: isAccountQuotaExhausted(account.label, nowMs),
    };
  });
}

// ── Last-successful-contact tracker (#646 health-sweep quota guard) ─────────
// বাংলা মন্তব্য: background health sweep প্রতি interval-এ Redis PING পাঠিয়ে
// কোটা পোড়ায়। সাম্প্রতিক সফল contact-এর প্রমাণ থাকলে (ডিফল্ট < ৩০s) sweep
// probe-টি বাদ দেওয়া যায় — adapters/redis pingRedis() এই ট্র্যাকার দেখে।

export type RedisContactInfo = { ms: number; account: string; mode: string };

let lastContact: RedisContactInfo | null = null;

/** একটি সফল Redis command/contact রেকর্ড করে (REST/TCP wrapper-রা ডাকে)। */
export function noteRedisContact(account: string, mode: string, nowMs: number = Date.now()): void {
  lastContact = { ms: nowMs, account, mode };
}

/** সর্বশেষ সফল contact ও তার বয়স ms-এ; কখনো হয়নি হলে null। */
export function lastRedisContact(nowMs: number = Date.now()): { ageMs: number; account: string; mode: string } | null {
  if (!lastContact) return null;
  return {
    ageMs: Math.max(0, nowMs - lastContact.ms),
    account: lastContact.account,
    mode: lastContact.mode,
  };
}

/** Health-sweep probe skip উইন্ডো (ms) — env REDIS_HEALTH_PROBE_SKIP_MS, ডিফল্ট 30s (#646)। */
export function redisHealthProbeSkipMs(): number {
  const v = Number(process.env.REDIS_HEALTH_PROBE_SKIP_MS);
  return Number.isFinite(v) && v >= 0 ? v : 30_000;
}

/** পর্যবেক্ষণের জন্য cooldown snapshot (invariant #5 — fleet observability)। */
export function quotaChainStatus(nowMs: number = Date.now()): { label: string; cooldownUntil: string | null; isActivePrimary: boolean }[] {
  const activePrimary = getActiveRedisAccount(nowMs).label;
  const chain = buildAccountChain();
  if (chain.length === 0) {
    return [{ label: "primary", cooldownUntil: null, isActivePrimary: true }];
  }
  return chain.map((account) => {
    const until = quotaCooldownUntil.get(account.label);
    return {
      label: account.label,
      cooldownUntil: until && nowMs < until ? new Date(until).toISOString() : null,
      isActivePrimary: account.label === activePrimary,
    };
  });
}

// ── Single account-chain walk engine (#110) ─────────────────────────────────
// The first-responder fallback walk (try accounts in order, mark quota-exhausted
// ones into cooldown, fail with aggregated errors) used to be re-implemented by
// hand in four modules. This is the ONE walk — every fallback path routes
// through it, so rotation policy is whatever this file says, not whichever
// copy happened to execute.

/** Thrown by an op when the response is a daily-quota exhaustion (auto-shift). */
export class RedisQuotaExhaustedError extends Error {
  readonly accountLabel: string;
  constructor(accountLabel: string, message?: string) {
    super(message ?? `Upstash [${accountLabel}] দৈনিক কোটা শেষ — UTC রিসেট পর্যন্ত cooldown`);
    this.name = "RedisQuotaExhaustedError";
    this.accountLabel = accountLabel;
  }
}

export type ChainWalkAttempt = {
  account: string;
  ok: boolean;
  error?: string;
};

export type ChainWalkResult<T> = {
  value: T;
  /** The account whose op succeeded (the one that "answered"). */
  account: RedisAccountConfig;
  attempts: ChainWalkAttempt[];
};

export type RunWithAccountChainOptions = {
  /**
   * Skip an account without attempting it and without recording an attempt
   * (e.g. REST-only callers skipping TCP-only accounts).
   */
  skip?: (account: RedisAccountConfig) => boolean;
  /**
   * Build the aggregated all-accounts-failed error. Defaults to
   * `All <n> Redis account(s) failed: <label>: <err> | ...`. Callers that
   * had a caller-specific message keep it byte-identical through this hook.
   */
  aggregateError?: (attempts: ChainWalkAttempt[]) => Error;
};

/**
 * Walk the ACTIVE (cooldown-free) account chain; the first account whose op
 * resolves wins. A thrown error records the attempt and moves to the next
 * account; quota-shaped failures (RedisQuotaExhaustedError, or a message that
 * matches responseIndicatesQuotaExhaustion) additionally mark the account into
 * cooldown so the rest of the fleet skips it until UTC reset. When every
 * account failed, throws the aggregated error (via aggregateError hook).
 *
 * This is the only place in src/ that iterates `activeAccountChain()` directly
 * for failover (#110 AC1) — the canonical read-only health walker in
 * adapters/redis keeps its own loop over a captured chain reference, and the
 * fan-out MERGE readers (presence/heartbeat listing) are deliberately NOT
 * routed here: their semantics are "read every account, freshest wins", not
 * "stop at the first responder".
 */
export async function runWithAccountChain<T>(
  op: (account: RedisAccountConfig) => Promise<T>,
  opts: RunWithAccountChainOptions = {},
): Promise<ChainWalkResult<T>> {
  const chain = activeAccountChain();
  if (chain.length === 0) {
    throw new Error("No Redis configuration found (missing REST or TCP credentials)");
  }
  const attempts: ChainWalkAttempt[] = [];
  for (const account of activeAccountChain()) {
    if (opts.skip?.(account)) continue;
    try {
      const value = await op(account);
      attempts.push({ account: account.label, ok: true });
      return { value, account, attempts };
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (err instanceof RedisQuotaExhaustedError || responseIndicatesQuotaExhaustion(0, message)) {
        markAccountQuotaExhausted(account.label);
      }
      attempts.push({ account: account.label, ok: false, error: message });
    }
  }
  if (opts.aggregateError) {
    throw opts.aggregateError(attempts);
  }
  const failures = attempts
    .map((a) => `${a.account}: ${a.error ?? "unknown error"}`)
    .join(" | ");
  throw new Error(`All ${attempts.length} Redis account(s) failed: ${failures}`);
}
