/**
 * In-memory TTL utilities for Redis command-burn reduction (#646).
 *
 * বাংলা মন্তব্য: Upstash free tier-এর ৫০০k মাসিক কোটা বাঁচানোর দুটি হাতিয়ার
 * এক জায়গায় — দুটোই in-memory, প্রক্রিয়া-লোকাল, কোনো অতিরিক্ত Redis
 * কমান্ড খরচ করে না (zero extra Redis commands by design):
 *
 *   1. `TtlCache` / `withL1Cache` — L1 read-through cache। একই key-এর
 *      বারবার read (dashboard health sweep, workforce listing) একটি TTL
 *      উইন্ডোতে একবারই Redis-এ যায়; বাকিগুলো মেমরি থেকে সার্ভ হয়।
 *   2. `WriteDebouncer` — write-collapse। heartbeat (প্রতি slot প্রতি ৪৫s)
 *      ও presence (প্রতি MCP রিকোয়েস্ট) এর মতো sliding-TTL রিফ্রেশ লেখায়
 *      debounce উইন্ডোর ভিতরের ডুপ্লিকেট লেখা Redis-এ যায় না —
 *      state machine-এর online threshold (৯০s) অক্ষত থাকার মতো বড়
 *      ডিফল্ট উইন্ডো (৬০s) বেছে নেওয়া হয়েছে।
 *
 * Both are best-effort observability-preserving: a cache miss or debounced
 * write never changes the caller's success/failure contract — it only
 * removes redundant Redis round-trips.
 */

export type TtlCacheEntry<T> = { value: T; expiresAtMs: number };

const l1Store = new Map<string, TtlCacheEntry<unknown>>();

/** Default L1 window: 5s — dashboard sweeps are ~1/s at worst, so a 5s
 *  dedup collapses bursts without visibly staling the board. */
export const DEFAULT_L1_TTL_MS = 5_000;

/** env দ্বারা নিয়ন্ত্রণযোগ্য L1 TTL; `0` দিলে L1 ক্যাশ পুরোপুরি বন্ধ (opt-out)। */
export function l1CacheTtlMs(envName: string = "REDIS_L1_CACHE_TTL_MS"): number {
  const raw = process.env[envName];
  if (raw === undefined || raw === "") return DEFAULT_L1_TTL_MS;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : DEFAULT_L1_TTL_MS;
}

export function l1Get<T>(key: string, nowMs: number = Date.now()): T | undefined {
  const entry = l1Store.get(key) as TtlCacheEntry<T> | undefined;
  if (!entry) return undefined;
  if (nowMs >= entry.expiresAtMs) {
    l1Store.delete(key);
    return undefined;
  }
  return entry.value;
}

export function l1Set<T>(key: string, value: T, ttlMs: number, nowMs: number = Date.now()): void {
  if (ttlMs <= 0) return; // disabled — never store
  // Bounded: stale entries are pruned lazily; the cache also caps at 512 keys.
  if (l1Store.size >= 512) {
    for (const [k, e] of l1Store) {
      if (nowMs >= e.expiresAtMs) l1Store.delete(k);
    }
    if (l1Store.size >= 512) {
      const firstKey = l1Store.keys().next().value;
      if (firstKey !== undefined) l1Store.delete(firstKey);
    }
  }
  l1Store.set(key, { value, expiresAtMs: nowMs + ttlMs });
}

/** Read-through helper: returns the cached value when fresh, else loads,
 *  stores and returns. Loader throwing = nothing cached (fail-honest). */
export async function withL1Cache<T>(
  key: string,
  ttlMs: number,
  loader: () => Promise<T>,
  nowMs: number = Date.now(),
): Promise<T> {
  if (ttlMs <= 0) return await loader();
  const hit = l1Get<T>(key, nowMs);
  if (hit !== undefined) return hit;
  const value = await loader();
  l1Set(key, value, ttlMs, nowMs);
  return value;
}

/** Test/reset hook — clears every L1 entry. */
export function clearRedisL1Cache(): void {
  l1Store.clear();
}

// ── WriteDebouncer (#646 AC2 — heartbeat/presence write collapse) ──────────

export type DebounceDecision<T> =
  | { skip: false }
  | { skip: true; lastWriteMs: number; metadata?: T };

/**
 * Sliding-window write collapse for periodic refresh writes. NOT a general
 * cache: it stores only the last write time (+ optional metadata such as the
 * account label that accepted the last write) per key.
 *
 * Contract (fail-honest): `check()` is READ-ONLY — it never records.
 * Only `record()` does, and callers invoke it AFTER the real write succeeds,
 * so a failed write never poisons the debounce window.
 */
export class WriteDebouncer<T = undefined> {
  private last = new Map<string, { atMs: number; metadata?: T }>();

  constructor(private windowMs: number | (() => number)) {}

  /**
   * Returns `{skip:true}` when a SUCCESSFUL write was recorded for `key`
   * within the window (caller should NOT hit Redis); otherwise
   * `{skip:false}`. Does not mutate state.
   */
  check(key: string, nowMs: number = Date.now()): DebounceDecision<T> {
    const windowMs = typeof this.windowMs === "function" ? this.windowMs() : this.windowMs;
    if (windowMs <= 0) return { skip: false }; // disabled — always write
    const prev = this.last.get(key);
    if (prev && nowMs - prev.atMs < windowMs) {
      return { skip: true, lastWriteMs: prev.atMs, metadata: prev.metadata };
    }
    return { skip: false };
  }

  /** Records a SUCCESSFUL write (call only after the real write resolved). */
  record(key: string, nowMs: number = Date.now(), metadata?: T): void {
    const windowMs = typeof this.windowMs === "function" ? this.windowMs() : this.windowMs;
    // Bounded map: prune stale entries past 4× window once size grows.
    if (this.last.size >= 512 && windowMs > 0) {
      for (const [k, v] of this.last) {
        if (nowMs - v.atMs >= windowMs * 4) this.last.delete(k);
      }
      if (this.last.size >= 512) {
        const firstKey = this.last.keys().next().value;
        if (firstKey !== undefined) this.last.delete(firstKey);
      }
    }
    this.last.set(key, { atMs: nowMs, metadata });
  }

  /** Test/reset hook. */
  reset(): void {
    this.last.clear();
  }

  /** Force the next `check(key)` to write (e.g. admin forced refresh). */
  invalidate(key: string): void {
    this.last.delete(key);
  }
}
