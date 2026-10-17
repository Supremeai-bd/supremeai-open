/**
 * Tiny in-memory L1 read cache (#646 — Redis command burn-rate optimization).
 *
 * বাংলা মন্তব্য: Upstash free tier-এর মাসিক 500k command কোটা-র সবচেয়ে বড়
 * অপচয় হলো repeated read listing (dashboard refresh / health sweep প্রতি
 * কয়েক সেকেন্ডে HGETALL / KEYS + N*GET পাঠায়)। এই মডিউল একটি সর্বনিম্ন
 * TTL-ভিত্তিক in-process cache — একই তালিকা 15–30s-এর মধ্যে আবার চাইলে
 * রিমোট Redis-এ একটিও command না পাঠিয়ে মেমরি থেকে উত্তর দেয় (#646 AC:
 * redundant read traffic ≥ 50% কমানো)।
 *
 * সরলতা-চুক্তি (P0 Law of Minimal Elegance):
 *   - TTL expiry + opportunistic eviction, কোনো timer/interval নেই
 *   - max-entries বাউন্ড (ডিফল্ট 16) — মেমরি ceiling নিশ্চিত
 *   - writer-রা `delete`/`clear` দিয়ে সাথে সাথে invalidate করে — লেখার পরেই
 *     পরবর্তী পড়া সৎ (fresh) থাকে, stale-read বাগ ক্লাস বন্ধ
 */

export type L1CacheEntry<T> = { value: T; expiresAtMs: number };

export class L1Cache<T> {
  private store = new Map<string, L1CacheEntry<T>>();

  constructor(
    private readonly ttlMs: number,
    private readonly maxEntries: number = 16,
  ) {
    if (!Number.isFinite(ttlMs) || ttlMs <= 0) {
      throw new Error(`L1Cache ttlMs must be a positive number; got ${ttlMs}`);
    }
  }

  /** Cached value বা undefined (মেয়াদ শেষ হলে entry মুছে যায়)। */
  get(key: string, nowMs: number = Date.now()): T | undefined {
    const entry = this.store.get(key);
    if (!entry) return undefined;
    if (nowMs >= entry.expiresAtMs) {
      this.store.delete(key);
      return undefined;
    }
    return entry.value;
  }

  set(key: string, value: T, nowMs: number = Date.now()): void {
    if (this.store.size >= this.maxEntries && !this.store.has(key)) {
      // সবচেয়ে তাড়াতাড়ি মেয়াদ শেষ হওয়া entry বাদ (allocation-free eviction)
      let oldestKey = "";
      let oldest = Infinity;
      for (const [k, v] of this.store) {
        if (v.expiresAtMs < oldest) {
          oldest = v.expiresAtMs;
          oldestKey = k;
        }
      }
      if (oldestKey) this.store.delete(oldestKey);
    }
    this.store.set(key, { value, expiresAtMs: nowMs + this.ttlMs });
  }

  delete(key: string): void {
    this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }

  get size(): number {
    return this.store.size;
  }
}
