/**
 * Preemptive quota rotation + command burn-rate regression tests (#646).
 *
 * AC coverage (issue #646):
 *   1.  Soft threshold = 96% of the configured monthly limit (480k of 500k
 *       default), env-overridable.
 *   2.  Usage ledger counts commands per account per monthly window; window
 *       rollover resets the count and the account rejoins the pool.
 *   3.  Crossing the soft threshold PREEMPTIVELY rotates to the next account
 *       — before the hard limit is ever reachable.
 *   4.  quotaGuard throws a quota-shaped error so the chain engine shifts the
 *       request to the next account without wasting it.
 *   5.  L1 in-memory list cache eliminates redundant reads; writes invalidate.
 *   6.  Heartbeat/presence write debounce skips identical sub-second writes.
 *   7.  Health-sweep probe skip: recent successful contact (<30s) short-
 *       circuits pingRedis() without a PING command.
 *
 * Run: npm run test:preemptive-rotation   (wired into test:unit)
 * Depends only on module-level contracts — no real network (fetch is mocked).
 */
import assert from "node:assert/strict";
import {
  accountUsageCommands,
  activeAccountChain,
  getActiveRedisAccount,
  isAccountQuotaExhausted,
  lastRedisContact,
  nextQuotaResetEpochMs,
  noteRedisContact,
  quotaGuard,
  quotaLimit,
  quotaSoftThreshold,
  recordRedisCommands,
  redisHealthProbeSkipMs,
  redisUsageLedgerStatus,
  RedisQuotaExhaustedError,
} from "./src/lib/redis_chain.js";
import { L1Cache } from "./src/lib/l1_cache.js";
import { listHeartbeats, recordHeartbeat } from "./src/registry/agent_heartbeat.js";
import { listPresence, recordPresence } from "./src/registry/mcp_presence.js";
import { pingRedis } from "./src/adapters/redis/index.js";

// ── Chain under test: primary + secondary, both REST, both succeed normally ─
process.env.UPSTASH_REDIS_REST_URL = "https://primary.preempt-test.invalid";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.preempt-test.invalid";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
for (const k of [
  "UPSTASH_REDIS_TERTIARY_REST_URL", "UPSTASH_REDIS_TERTIARY_REST_TOKEN",
  "UPSTASH_REDIS_QUATERNARY_REST_URL", "UPSTASH_REDIS_QUATERNARY_REST_TOKEN",
  "UPSTASH_REDIS_QUINARY_REST_URL", "UPSTASH_REDIS_QUINARY_REST_TOKEN",
  "REDIS_URL", "REDIS_ACCOUNT_LABEL",
]) delete process.env[k];

/** Cooldown registry is module-global — clear entries like quota-routing does. */
function resetCooldowns(labels: string[]): void {
  for (const label of labels) isAccountQuotaExhausted(label, 8_200_000_000_000);
}

// ── Mock fetch: every account answers every command successfully ───────────
const realFetch = globalThis.fetch.bind(globalThis);
const calls: { host: string; command: string }[] = [];
(globalThis as unknown as { fetch: typeof fetch }).fetch = (async (input: unknown, init?: RequestInit) => {
  const url = new URL(String(input));
  const payload = JSON.parse(String(init?.body ?? "[]")) as unknown[];
  // Hand-rolled clients send flat pipelines (["HGETALL", key]); the
  // @upstash/redis SDK (adapter path) sends [["ping"]] and expects an ARRAY
  // response of { result } — answer both wire shapes correctly.
  const first = payload[0];
  const command = Array.isArray(first) ? String(first[0] ?? "?").toUpperCase() : String(first ?? "?");
  calls.push({ host: url.host, command });
  if (command === "PING") {
    // Upstash pipeline results are JSON-encoded; the SDK re-parses strings.
    return new Response(JSON.stringify([{ result: '"PONG"' }]), { status: 200 });
  }
  let result: unknown = null;
  switch (command) {
    case "HGETALL":
      result = {};
      break;
    case "KEYS":
      result = [];
      break;
    default:
      result = "OK";
  }
  return new Response(JSON.stringify({ result }), { status: 200 });
}) as typeof fetch;

// ── 1. Threshold defaults + env override ────────────────────────────────────
delete process.env.UPSTASH_QUOTA_LIMIT;
delete process.env.UPSTASH_QUOTA_SOFT_THRESHOLD;
assert.equal(quotaLimit(), 500_000, "default monthly limit must be 500,000 (#646)");
assert.equal(quotaSoftThreshold(), 480_000, "default soft threshold must be 480,000 = 96% (#646)");
process.env.UPSTASH_QUOTA_LIMIT = "100000";
assert.equal(quotaSoftThreshold(), 96_000, "soft threshold defaults to 96% of configured limit");
process.env.UPSTASH_QUOTA_SOFT_THRESHOLD = "70000";
assert.equal(quotaSoftThreshold(), 70_000, "explicit UPSTASH_QUOTA_SOFT_THRESHOLD must win");
console.log("✅ 1. soft threshold = 96% of limit, env-overridable (500k → 480k default)");

// ── 2. Usage ledger + monthly window rollover ───────────────────────────────
process.env.UPSTASH_QUOTA_SOFT_THRESHOLD = "480000";
delete process.env.UPSTASH_QUOTA_LIMIT;
const baseNow = Date.now();
// Synthetic label — pure ledger math, isolated from chain-rotation sections.
const label2 = "ledger-probe";
assert.equal(accountUsageCommands(label2, baseNow), 0, "fresh ledger starts at 0");
assert.equal(recordRedisCommands(label2, 10, baseNow), 10, "recordRedisCommands returns the updated count");
assert.equal(recordRedisCommands(label2, 5, baseNow + 1_000), 15, "commands accumulate within the same window");
assert.equal(accountUsageCommands(label2, baseNow + 2_000), 15);
const nextWindow = baseNow + 31 * 24 * 3600 * 1000; // ~next month
assert.equal(accountUsageCommands(label2, nextWindow), 0, "window rollover resets the count to 0");
console.log("✅ 2. usage ledger accumulates per monthly window and resets on rollover");

// ── 3. PREEMPTIVE rotation before the hard limit ────────────────────────────
// Scaled model: limit 12, soft threshold 10 → rotate at 10; hard 12 (the
// real-world 500k) is NEVER reachable, exactly like 480k of 500k.
process.env.UPSTASH_QUOTA_LIMIT = "12";
process.env.UPSTASH_QUOTA_SOFT_THRESHOLD = "10";
resetCooldowns(["primary", "secondary"]);
assert.equal(getActiveRedisAccount().label, "primary", "sanity: primary starts active");
assert.equal(recordRedisCommands("primary", 9, Date.now()), 9);
assert.ok(!isAccountQuotaExhausted("primary"), "9 < 10 → still in the pool");
assert.equal(recordRedisCommands("primary", 1, Date.now()), 10, "crossing 10 = the 480k moment");
assert.ok(isAccountQuotaExhausted("primary"), ">= soft threshold → preemptively cooled");
assert.equal(getActiveRedisAccount().label, "secondary", "rotation happened BEFORE the hard limit (10 < 12)");
assert.ok(!activeAccountChain().some((a) => a.label === "primary"), "cooled account excluded from the active chain");
console.log("✅ 3. crossing the 96% soft threshold rotates BEFORE the hard 500k boundary");

// ── 4. quotaGuard throws quota-shaped → engine shifts without wasting it ────
// (section-3 scaled env intentionally still active here: limit 12, threshold 10)
assert.throws(() => quotaGuard({ label: "primary" } as never, 1), RedisQuotaExhaustedError,
  "quotaGuard must throw the engine-recognized error at/over threshold");
assert.doesNotThrow(() => quotaGuard({ label: "guard-fresh" } as never, 1),
  "healthy (below-threshold) account accepts reservations");
// Window reset → account rejoins the pool automatically (AC: cooldown until
// the window reset date, e.g. 2026-11-01T00:01Z).
const afterReset = nextQuotaResetEpochMs() + 60_000;
assert.ok(!isAccountQuotaExhausted("primary", afterReset), "after window reset the account rejoins");
console.log("✅ 4. quotaGuard quota-shaped error + automatic pool rejoin after reset");

// ── 5. Observability: usage ledger status + contact tracker ────────────────
process.env.UPSTASH_QUOTA_LIMIT = "500000";
process.env.UPSTASH_QUOTA_SOFT_THRESHOLD = "480000";
resetCooldowns(["primary", "secondary"]);
// "secondary" ledger is untouched so far → exactly 250000 after this call.
recordRedisCommands("secondary", 250_000, Date.now());
const usage = redisUsageLedgerStatus();
const secondaryUsage = usage.find((u) => u.label === "secondary");
assert.ok(secondaryUsage, "ledger lists every chain account");
assert.equal(secondaryUsage.commands, 250_000);
assert.equal(secondaryUsage.limit, 500_000);
assert.equal(secondaryUsage.softThreshold, 480_000);
assert.equal(secondaryUsage.percentUsed, 50, "percentUsed math (50% of 500k)");
assert.equal(secondaryUsage.preemptivelyCooled, false);
noteRedisContact("primary", "upstash-rest", Date.now() - 5_000);
const contact = lastRedisContact();
assert.ok(contact, "contact tracker records the last success");
assert.ok(contact.ageMs >= 4_900 && contact.ageMs <= 5_100, "ageMs math is ms-precise");
assert.equal(redisHealthProbeSkipMs(), 30_000, "health probe skip window defaults to 30s");
console.log("✅ 5. usage ledger + last-contact observability surfaces");

// ── 6. L1 cache semantics ───────────────────────────────────────────────────
const cache = new L1Cache<number>(1_000);
cache.set("k", 42);
assert.equal(cache.get("k"), 42, "cache hit within TTL");
assert.equal(cache.get("k", Date.now() + 1_001), undefined, "TTL expiry evicts");
cache.set("k", 7);
cache.delete("k");
assert.equal(cache.get("k"), undefined, "explicit invalidation");
const tiny = new L1Cache<number>(60_000, 2);
tiny.set("a", 1); tiny.set("b", 2); tiny.set("c", 3);
assert.equal(tiny.size, 2, "max-entries bound enforced (eviction)");
console.log("✅ 6. L1 cache: hit, TTL expiry, invalidate, bounded eviction");

// ── 7. Heartbeat write debounce (identical sub-second writes skipped) ───────
resetCooldowns(["primary", "secondary"]);
calls.length = 0;
const hb1 = await recordHeartbeat({ slot: "agent-646", source: "mcp-tower" });
assert.equal(hb1.ok, true);
assert.ok(!("debounced" in hb1 && hb1.debounced), "first write is a real write");
const callsAfterFirst = calls.length;
assert.ok(callsAfterFirst >= 2, "hash-first dual-write contract preserved (HSET + SET)");
const hb2 = await recordHeartbeat({ slot: "agent-646", source: "mcp-tower" });
assert.equal(hb2.debounced, true, "identical back-to-back write is debounced (#646)");
assert.equal(calls.length, callsAfterFirst, "debounced write sends ZERO Redis commands");
const hb3 = await recordHeartbeat({ slot: "agent-646", agentId: "different-identity", source: "mcp-tower" });
assert.ok(!(hb3 as { debounced?: boolean }).debounced, "fingerprint change forces a real write (identity re-register never masked)");
assert.ok(calls.length > callsAfterFirst, "real write went through after fingerprint change");
console.log("✅ 7. heartbeat write debounce: identical → 0 commands, fingerprint change → real write");

// ── 8. List L1 cache + invalidation on write ───────────────────────────────
resetCooldowns(["primary", "secondary"]);
calls.length = 0;
await listHeartbeats();
const fetchesFirstList = calls.length;
assert.ok(fetchesFirstList >= 1, "first list reads from the chain");
await listHeartbeats();
assert.equal(calls.length, fetchesFirstList, "second rapid list is served from L1 cache (0 commands, #646 ≥50% read-cut)");
await recordHeartbeat({ slot: "agent-647", source: "dashboard" });
assert.ok(calls.length > fetchesFirstList, "write itself goes to Redis");
await listHeartbeats();
assert.ok(calls.length > fetchesFirstList + 1, "list cache was invalidated by the write — fresh read");
console.log("✅ 8. listHeartbeats L1 cache: hit → 0 commands; write invalidates → fresh read");

// ── 9. Presence write debounce + workforce/presence cache interplay ────────
resetCooldowns(["primary", "secondary"]);
calls.length = 0;
await recordPresence({ clientName: "ChatGPT-646", clientId: "cid-1", protocol: "streamable-http" });
const presenceCallsAfterFirst = calls.length;
const pr2 = await recordPresence({ clientName: "ChatGPT-646", clientId: "cid-1", protocol: "streamable-http" });
assert.equal(pr2.debounced, true, "presence identical back-to-back write is debounced");
assert.equal(calls.length, presenceCallsAfterFirst, "debounced presence write sends ZERO commands");
await listPresence();
const afterPresenceList = calls.length;
await listPresence();
assert.equal(calls.length, afterPresenceList, "listPresence L1 cache hit (0 commands)");
console.log("✅ 9. presence debounce + presence list cache");

// ── 10. Health-sweep probe skip after recent successful contact ────────────
resetCooldowns(["primary", "secondary"]);
calls.length = 0;
noteRedisContact("primary", "upstash-rest", Date.now());
const ping1 = (await pingRedis()) as { probeSkipped?: boolean; status?: string; account?: string };
assert.equal(ping1.probeSkipped, true, "recent contact → probe skipped (#646 AC)");
assert.equal(ping1.status, "PONG", "consumer contract preserved (system.tools expects PONG)");
assert.equal(ping1.account, "primary", "skip reports WHICH account had the recent contact");
assert.equal(calls.length, 0, "skip path sends ZERO PING commands");
// Stale contact (> 30s) → real probe happens.
noteRedisContact("primary", "upstash-rest", Date.now() - 31_000);
const ping2 = (await pingRedis()) as { probeSkipped?: boolean; status?: string };
assert.equal(ping2.probeSkipped, false, "stale contact → real probe");
assert.equal(ping2.status, "PONG");
assert.ok(calls.length >= 1, "real probe sent exactly one PING through the chain");
console.log("✅ 10. health-sweep probe skip window (recent → 0 commands, stale → real probe)");

// ── Cleanup ────────────────────────────────────────────────────────────────
(globalThis as unknown as { fetch: typeof fetch }).fetch = realFetch;
resetCooldowns(["primary", "secondary"]);

console.log("ALL PREEMPTIVE-ROTATION & BURN-RATE TESTS PASSED (#646) — 10/10 sections");
