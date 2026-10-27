/**
 * P0 #1360 test suite — hot-read LRU cache, three-tier alert ladder,
 * persistent cooldown ledger.
 *
 * Credentials-free (runs in test:tower-ci). Zero Redis commands: every
 * scenario uses the in-memory primitives and a temp-dir ledger file.
 */
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  hotLruGet,
  hotLruSet,
  withHotReadCache,
  hotReadCacheStats,
  resetHotReadCache,
  hotLruCapacity,
} from "./src/lib/hot_read_cache.js";
import { quotaTierFor } from "./src/lib/redis_chain.js";
import {
  cooldownLedgerPath,
  isCooldownLedgerEnabled,
  readLedgerFile,
  validLedgerStamps,
  persistCooldownStamp,
  persistCooldownClear,
  deleteCooldownLedgerFile,
  type LedgerEntry,
} from "./src/lib/cooldown_ledger.js";

// ── isolated env: ledger into a fresh temp dir, kill all tier env overrides ──
const tmpDir = mkdtempSync(join(tmpdir(), "redis-p0-test-"));
const ledgerPath = join(tmpDir, "cooldown-ledger.json");
process.env.REDIS_COOLDOWN_LEDGER_PATH = ledgerPath;
delete process.env.REDIS_QUOTA_ALERT_PCT;
delete process.env.REDIS_QUOTA_HIGH_PCT;
delete process.env.REDIS_QUOTA_CRIT_PCT;
delete process.env.REDIS_HOT_LRU_CAPACITY;
delete process.env.REDIS_HOT_LRU_TTL_MS;

const now = Date.now();
const WINDOW_START = now - 1000; // any value; validation compares equality with the entry
const SOFT = 480_000;

function entry(untilMs: number, count: number): LedgerEntry {
  return { cooldownUntilMs: untilMs, usage: { count, windowStartMs: WINDOW_START }, stampedAtMs: now };
}

try {
  // ══ 1. Hot-read LRU: hit/miss telemetry + ≥50% absorption acceptance ══════
  console.log("[1] hot-read LRU telemetry + absorption");
  resetHotReadCache();
  // Simulated workload: 100 lookups over 10 keys where 60 are redundant
  // repeats of already-seen keys (the redundant-lookup shape of dashboard
  // sweeps + heartbeat listings).
  const seen = new Map<string, number>();
  const workload: string[] = [];
  for (let i = 0; i < 100; i++) {
    const key = `hot:key:${i % 10}`;
    workload.push(key);
    seen.set(key, (seen.get(key) ?? 0) + 1);
  }
  let remoteCalls = 0;
  for (const key of workload) {
    await withHotReadCache(key, 30_000, async () => {
      remoteCalls += 1; // stands in for a Redis GET
      return `value-of-${key}`;
    });
  }
  const stats = hotReadCacheStats();
  assert.equal(stats.size, 10, "bounded workload of 10 keys must hold 10 entries");
  assert.equal(remoteCalls, 10, "each distinct key loads exactly once");
  assert.equal(stats.hits, 90, "90 redundant lookups must be cache hits");
  assert.ok((stats.hitRatePct ?? 0) >= 50, `acceptance: hit rate ≥ 50% (got ${stats.hitRatePct}%)`);
  console.log(`    hits=${stats.hits} misses=${stats.misses} hitRatePct=${stats.hitRatePct} remoteCalls=${remoteCalls}`);

  // ══ 2. LRU eviction order + capacity bound ════════════════════════════════
  console.log("[2] LRU eviction order");
  resetHotReadCache();
  process.env.REDIS_HOT_LRU_CAPACITY = "2";
  assert.equal(hotLruCapacity(), 2);
  hotLruSet("a", 1, 30_000, now);
  hotLruSet("b", 2, 30_000, now);
  assert.equal(hotLruGet<number>("a", now + 1), 1, "touch a → a is MRU, b is LRU");
  hotLruSet("c", 3, 30_000, now + 2); // capacity 2 → b (LRU) evicted
  assert.equal(hotLruGet<number>("b", now + 3), undefined, "b must have been evicted");
  assert.equal(hotLruGet<number>("a", now + 3), 1, "a survives (was touched)");
  assert.equal(hotLruGet<number>("c", now + 3), 3, "c survives (just inserted)");
  assert.ok(hotReadCacheStats(now + 3).evictions >= 1, "eviction counted");
  delete process.env.REDIS_HOT_LRU_CAPACITY;

  // ══ 3. TTL expiry + kill switch + fail-honest loader ══════════════════════
  console.log("[3] TTL expiry, kill switch, loader-throw");
  resetHotReadCache();
  hotLruSet("k", "v", 50, now);
  assert.equal(hotLruGet<string>("k", now + 60), undefined, "expired entry drops");
  assert.equal(hotReadCacheStats(now + 60).expiredDrops, 1, "expiry counted");
  hotLruSet("gone", "v", 0, now); // ttl 0 = never stored
  assert.equal(hotLruGet<string>("gone", now), undefined);
  process.env.REDIS_HOT_LRU_CAPACITY = "0";
  let loaderRan = 0;
  await withHotReadCache("x", 30_000, async () => {
    loaderRan += 1;
    return "always";
  });
  await withHotReadCache("x", 30_000, async () => {
    loaderRan += 1;
    return "always";
  });
  assert.equal(loaderRan, 2, "capacity 0 disables the cache entirely (loader every call)");
  delete process.env.REDIS_HOT_LRU_CAPACITY;
  resetHotReadCache();
  await assert.rejects(
    () =>
      withHotReadCache("boom", 30_000, async () => {
        throw new Error("redis down");
      }),
    /redis down/,
  );
  assert.equal(hotReadCacheStats().sets, 0, "failed loader must not store (fail-honest)");

  // ══ 4. Three-tier alert ladder (80/90/95) ═════════════════════════════════
  console.log("[4] quota tier ladder");
  assert.equal(quotaTierFor(79.9), null);
  assert.equal(quotaTierFor(80), "warn");
  assert.equal(quotaTierFor(89.9), "warn");
  assert.equal(quotaTierFor(90), "high", "#1360: the 90% middle rung must exist");
  assert.equal(quotaTierFor(94.9), "high");
  assert.equal(quotaTierFor(95), "crit");
  assert.equal(quotaTierFor(100), "crit");
  assert.equal(quotaTierFor(null), null);
  // env-overridable (explicit args win)
  assert.equal(quotaTierFor(85, 85, 90, 95), "warn");
  assert.equal(quotaTierFor(96, 80, 90, 96), "crit");

  // ══ 5. Ledger: disabled by default (byte-identical legacy behavior) ═══════
  console.log("[5] ledger opt-in gate");
  delete process.env.REDIS_COOLDOWN_LEDGER_PATH;
  assert.equal(cooldownLedgerPath(), null);
  assert.equal(isCooldownLedgerEnabled(), false);
  persistCooldownStamp("primary", now + 86_400_000, { count: SOFT, windowStartMs: WINDOW_START });
  assert.equal(existsSync(ledgerPath), false, "no writes while disabled");
  process.env.REDIS_COOLDOWN_LEDGER_PATH = ledgerPath;

  // ══ 6. Ledger: stamp → reload → validated hydration ═══════════════════════
  console.log("[6] ledger persistence round-trip");
  assert.ok(readLedgerFile() !== null, "enabled read returns a file object (empty when absent)");
  persistCooldownStamp("primary", now + 86_400_000, { count: 499_999, windowStartMs: WINDOW_START }, now);
  persistCooldownStamp("secondary", now + 86_400_000, { count: 481_000, windowStartMs: WINDOW_START }, now);
  assert.ok(existsSync(ledgerPath), "file written when enabled");
  const raw = JSON.parse(readFileSync(ledgerPath, "utf8"));
  assert.equal(raw.version, 1);
  assert.ok(raw.entries.primary, "primary stamp persisted");
  const restored = validLedgerStamps(["primary", "secondary"], SOFT, WINDOW_START, now);
  assert.equal(restored.size, 2, "both valid stamps hydrate");
  assert.equal(restored.get("primary")?.usage.count, 499_999);

  // ══ 7. Ledger validation: expiry, stale window, invariant mis-stamp ═══════
  console.log("[7] ledger validation guards");
  persistCooldownStamp("expired", now - 1, { count: 499_999, windowStartMs: WINDOW_START }, now);
  persistCooldownStamp("stale-window", now + 86_400_000, { count: 499_999, windowStartMs: WINDOW_START - 86_400_000 }, now);
  persistCooldownStamp("mis-stamp", now + 86_400_000, { count: 100, windowStartMs: WINDOW_START }, now);
  const strict = validLedgerStamps(
    ["primary", "secondary", "expired", "stale-window", "mis-stamp"],
    SOFT,
    WINDOW_START,
    now,
  );
  assert.equal(strict.size, 2, "expired / stale-window / mis-stamp stamps must NOT hydrate");
  assert.ok(!strict.has("expired") && !strict.has("stale-window") && !strict.has("mis-stamp"));
  // unknown label (not in chain) never hydrates
  const chainScoped = validLedgerStamps(["primary"], SOFT, WINDOW_START, now);
  assert.equal(chainScoped.size, 1, "chain-label scoping enforced");

  // ══ 8. Ledger clear + corrupt-file fail-open ══════════════════════════════
  console.log("[8] ledger clear + fail-open");
  persistCooldownClear("secondary");
  assert.ok(!("secondary" in (readLedgerFile() as { entries: Record<string, unknown> }).entries), "cleared stamp removed");
  // corrupt the file → read must fail-open with empty entries, never throw
  const { writeFileSync } = await import("node:fs");
  writeFileSync(ledgerPath, "{{{not json", "utf8");
  const corrupt = readLedgerFile();
  assert.ok(corrupt && Object.keys(corrupt.entries).length === 0, "corrupt ledger fails open as empty");
  // mis-stamp guard inside validLedgerStamps still holds after corruption recovery

  console.log("\nAll P0 #1360 tests passed.");
} finally {
  delete process.env.REDIS_COOLDOWN_LEDGER_PATH;
  delete process.env.REDIS_HOT_LRU_CAPACITY;
  try {
    rmSync(tmpDir, { recursive: true, force: true });
  } catch {
    // best-effort cleanup
  }
  void deleteCooldownLedgerFile;
}
