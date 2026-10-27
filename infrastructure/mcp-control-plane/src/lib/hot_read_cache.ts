/**
 * Hot-read LRU cache — P0 #1360 (AIQ-078/091) deliverable A.
 *
 * বাংলা মন্তব্য: Upstash free-tier 500k কোটার সবচেয়ে সস্তা প্রতিরোধ —
 * একই key-এর বারবার read Redis-এ না পাঠানো। `ttl_cache.ts`-এর L1 (৫s)
 * শুধু burst-collapse (dashboard sweep); এই স্তরটি **sustained hot keys**-এর
 * জন্য — bounded LRU + TTL + hit/miss telemetry, যাতে #1360-এর acceptance
 * ("in-memory caching layer absorbs at least 50% of redundant key lookups")
 * অনুমান নয়, পরিমাপযোগ্য সত্য হয়।
 *
 * Contract (fail-honest, mirrors withL1Cache):
 *  - Loader throw propagates; nothing is cached on failure.
 *  - `undefined` is never stored (sentinel-free: value-level emptiness is
 *    stored as-is, only `undefined` means "not cached").
 *  - TTL 0 / negative = cache disabled for that call (loader runs always).
 *  - Zero extra Redis commands by design (in-memory only).
 *
 * Eviction: true LRU — Map re-insertion moves a key to the MRU end on read;
 * overflow evicts the LRU end (first key). Capacity 0 → disabled.
 */

export type HotLruEntry<T> = { value: T; expiresAtMs: number };

export type HotLruStats = {
  hits: number;
  misses: number;
  sets: number;
  evictions: number;
  expiredDrops: number;
  size: number;
  capacity: number;
  /** hits / (hits+misses), percent rounded to 2 decimals; null when no lookups yet. */
  hitRatePct: number | null;
};

const store = new Map<string, HotLruEntry<unknown>>();
const counters = { hits: 0, misses: 0, sets: 0, evictions: 0, expiredDrops: 0 };

/** Default capacity: bounded at 1024 hot keys (env REDIS_HOT_LRU_CAPACITY). */
export function hotLruCapacity(): number {
  const raw = Number(process.env.REDIS_HOT_LRU_CAPACITY);
  return Number.isFinite(raw) && raw >= 0 ? Math.floor(raw) : 1024;
}

/** Default TTL for hot reads: 30s (env REDIS_HOT_LRU_TTL_MS; 0 = disabled). */
export function hotLruTtlMs(envName: string = "REDIS_HOT_LRU_TTL_MS"): number {
  const raw = process.env[envName];
  if (raw === undefined || raw === "") return 30_000;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 30_000;
}

function evictIfNeeded(capacity: number, nowMs: number): void {
  if (capacity <= 0) return;
  if (store.size < capacity) return;
  // First pass: drop expired entries (they are already dead weight).
  for (const [k, e] of store) {
    if (nowMs >= e.expiresAtMs) {
      store.delete(k);
      counters.evictions += 1;
      if (store.size < capacity) return;
    }
  }
  // Second pass: true LRU eviction from the oldest end.
  while (store.size >= capacity) {
    const oldest = store.keys().next().value;
    if (oldest === undefined) break;
    store.delete(oldest);
    counters.evictions += 1;
  }
}

/** Raw get: returns the cached value when present and fresh (counts telemetry). */
export function hotLruGet<T>(key: string, nowMs: number = Date.now()): T | undefined {
  const entry = store.get(key) as HotLruEntry<T> | undefined;
  if (!entry) {
    counters.misses += 1;
    return undefined;
  }
  if (nowMs >= entry.expiresAtMs) {
    store.delete(key);
    counters.expiredDrops += 1;
    counters.misses += 1;
    return undefined;
  }
  // LRU refresh: re-insert to move to the MRU end.
  store.delete(key);
  store.set(key, entry);
  counters.hits += 1;
  return entry.value;
}

/** Raw set: stores a value (bounded, LRU-evicting). ttlMs <= 0 stores nothing. */
export function hotLruSet<T>(key: string, value: T, ttlMs: number, nowMs: number = Date.now()): void {
  if (ttlMs <= 0) return;
  const capacity = hotLruCapacity();
  if (capacity <= 0) return;
  evictIfNeeded(capacity, nowMs);
  // Re-set moves the key to the MRU end (fresh writes are hot by definition).
  store.delete(key);
  store.set(key, { value, expiresAtMs: nowMs + ttlMs });
  counters.sets += 1;
}

/** Read-through helper: cache hit returns without touching Redis; miss loads
 *  once, stores, returns. Loader throw = nothing cached (fail-honest). */
export async function withHotReadCache<T>(
  key: string,
  ttlMs: number,
  loader: () => Promise<T>,
  nowMs: number = Date.now(),
): Promise<T> {
  if (ttlMs <= 0 || hotLruCapacity() <= 0) return await loader();
  const hit = hotLruGet<T>(key, nowMs);
  if (hit !== undefined) return hit;
  const value = await loader();
  if (value !== undefined) hotLruSet(key, value, ttlMs, nowMs);
  return value;
}

/** Telemetry snapshot — the ≥50% absorption acceptance is measured here. */
export function hotReadCacheStats(nowMs: number = Date.now()): HotLruStats {
  const total = counters.hits + counters.misses;
  return {
    hits: counters.hits,
    misses: counters.misses,
    sets: counters.sets,
    evictions: counters.evictions,
    expiredDrops: counters.expiredDrops,
    size: store.size,
    capacity: hotLruCapacity(),
    hitRatePct: total === 0 ? null : Math.round((counters.hits * 10000) / total) / 100,
  };
}

/** Test/reset hook — clears entries AND counters. */
export function resetHotReadCache(): void {
  store.clear();
  counters.hits = 0;
  counters.misses = 0;
  counters.sets = 0;
  counters.evictions = 0;
  counters.expiredDrops = 0;
}
