/**
 * Preemptive quota rotation + command-burn reduction regression test (#646).
 *
 * AC1 — Preemptive rotation at the 96% soft threshold (default 480,000):
 *   the account must LEAVE the active rotation pool BEFORE the 500k ceiling
 *   produces a rejected request. The mock never serves a quota error, so any
 *   rotation observed in this test is provably pre-error (zero failed
 *   requests) — exactly the contract that reactive-only rotation broke in
 *   the live incident (ERR ... Limit: 500000, Usage: 500002).
 *
 * AC2 — Root-cause command consumption optimization:
 *   - heartbeat/presence write debounce collapses duplicate refresh writes;
 *   - L1 read-through cache collapses dashboard sweep bursts;
 *   - usage truth-tiering: local counter → quota error body parse →
 *     authoritative remaining-headers.
 *
 * Run: npm run test:preemptive-rotation   (wired into test:unit)
 */
import assert from "node:assert/strict";

import {
  activeAccountChain,
  isAccountQuotaExhausted,
  noteQuotaErrorUsage,
  noteRedisCommands,
  noteRedisResponseHeaders,
  quotaChainStatus,
  redisUsageSnapshot,
  resetRedisUsageTracking,
  upstashCommandLimit,
  upstashSoftThreshold,
} from "./src/lib/redis_chain.js";
import { clearRedisL1Cache } from "./src/lib/ttl_cache.js";
import { recordHeartbeat, resetRedisWriteDebounce } from "./src/registry/agent_heartbeat.js";
import { recordPresence, resetPresenceWriteDebounce } from "./src/registry/mcp_presence.js";

// ── Chain under test: two REST accounts ─────────────────────────────────────
process.env.UPSTASH_REDIS_REST_URL = "https://primary.preempt-test.invalid";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.preempt-test.invalid";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
for (const k of [
  "UPSTASH_REDIS_TERTIARY_REST_URL", "UPSTASH_REDIS_TERTIARY_REST_TOKEN",
  "UPSTASH_REDIS_QUATERNARY_REST_URL", "UPSTASH_REDIS_QUATERNARY_REST_TOKEN",
  "UPSTASH_REDIS_QUINARY_REST_URL", "UPSTASH_REDIS_QUINARY_REST_TOKEN",
  "REDIS_URL",
]) delete process.env[k];

// Thresholds/debounce are env-tunable per scenario (window reads env at call time).
const realFetch = globalThis.fetch.bind(globalThis);
const calls: { host: string; command: string }[] = [];
let serveQuotaError = false;

(globalThis as unknown as { fetch: typeof fetch }).fetch = (async (input: unknown, init?: RequestInit) => {
  const url = new URL(String(input));
  const payload = JSON.parse(String(init?.body ?? "[]")) as string[];
  calls.push({ host: url.host, command: payload[0] ?? "?" });
  if (serveQuotaError && url.host.startsWith("primary.")) {
    return new Response("ERR max requests limit exceeded. Limit: 500000, Usage: 500002", { status: 400 });
  }
  return new Response(JSON.stringify({ result: payload[0] === "KEYS" ? [] : "OK" }), { status: 200 });
}) as typeof fetch;

/** Full isolation between scenarios. */
function resetAll(): void {
  for (const label of ["primary", "secondary"]) {
    isAccountQuotaExhausted(label, 8_200_000_000_000); // expire-check deletes the entry
  }
  resetRedisUsageTracking();
  resetRedisWriteDebounce();
  resetPresenceWriteDebounce();
  clearRedisL1Cache();
  calls.length = 0;
  serveQuotaError = false;
}

const hosts = () => calls.map((c) => c.host);
const primaryCalls = () => calls.filter((c) => c.host.startsWith("primary.")).length;

// ── 0. Threshold geometry: default 96% of 500k = 480,000 ────────────────────
delete process.env.UPSTASH_COMMAND_LIMIT;
delete process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD;
assert.equal(upstashCommandLimit(), 500_000);
assert.equal(upstashSoftThreshold(), 480_000, "default soft threshold must be 480k (96% of 500k)");
assert.equal(upstashSoftThreshold() < upstashCommandLimit(), true);

// ── 1. AC1 — local-count preemptive rotation with ZERO failed requests ──────
{
  resetAll();
  process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD = "5";
  // Every heartbeat write = 2 commands (HSET + SET). Threshold 5 → after the
  // 3rd write's HSET (count 5→6 by the SET) the primary must be out of the pool.
  for (const slot of ["agent-31", "agent-32", "agent-33"]) {
    const r = await recordHeartbeat({ slot, source: "mcp-tower" });
    assert.equal(r.ok, true);
    assert.notEqual(r.debounced, true);
  }
  assert.ok(primaryCalls() >= 5, "primary must have served the commands up to the threshold");
  assert.ok(!hosts().slice(0, 5).every((h) => h.startsWith("secondary.")), "first writes start on primary");
  // The 4th write must NOT touch primary — rotated preemptively, no error seen.
  calls.length = 0;
  const r4 = await recordHeartbeat({ slot: "agent-34", source: "mcp-tower" });
  assert.equal(r4.ok, true);
  assert.equal(r4.redisAccount, "secondary", "4th write must land on secondary after preemptive rotation");
  assert.equal(primaryCalls(), 0, "ZERO requests may hit the rotated-out account (no failed request possible)");
  assert.ok(isAccountQuotaExhausted("primary"), "primary visibly in cooldown after soft-threshold hit");
  const status = quotaChainStatus().find((s) => s.label === "primary");
  assert.ok(status?.cooldownUntil, "quotaChainStatus must expose the preemptive cooldown");
  assert.ok(status?.usage && status.usage.softThresholdHit, "usage snapshot must flag softThresholdHit");
  delete process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD;
}

// ── 2. Remaining-header authority → preemptive rotation (pure unit) ─────────
{
  resetAll();
  process.env.UPSTASH_COMMAND_LIMIT = "100";
  process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD = "80";
  const consumed = noteRedisResponseHeaders(
    "primary",
    new Headers({ "x-upstash-remaining-requests": "19" }),
  );
  assert.equal(consumed, true, "remaining header must be recognized");
  assert.ok(isAccountQuotaExhausted("primary"), "used=81 >= threshold=80 → preemptive rotation");
  assert.equal(activeAccountChain()[0].label, "secondary");
  const snap = redisUsageSnapshot().find((s) => s.label === "primary");
  assert.equal(snap?.estimatedCommands, 81, "usage derived from limit - remaining");
  delete process.env.UPSTASH_COMMAND_LIMIT;
  delete process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD;
}

// ── 3. Quota error body parse records REAL usage (truth correction) ─────────
{
  resetAll();
  noteQuotaErrorUsage("secondary", "ERR max requests limit exceeded. Limit: 500000, Usage: 499999");
  assert.ok(isAccountQuotaExhausted("secondary"), "499999 >= 480k → account rotates");
  const snap = redisUsageSnapshot().find((s) => s.label === "secondary");
  assert.equal(snap?.estimatedCommands, 499999, "error-body usage overrides the local lower bound");
  // Non-matching bodies are ignored (no false usage).
  resetAll();
  noteQuotaErrorUsage("primary", "some unrelated error");
  assert.equal(isAccountQuotaExhausted("primary"), false);
}

// ── 4. AC2 — heartbeat write debounce collapses duplicate refreshes ─────────
{
  resetAll();
  process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD = "999999999";
  process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS = "60";
  const r1 = await recordHeartbeat({ slot: "agent-41", source: "mcp-tower" });
  assert.equal(r1.ok, true);
  assert.notEqual(r1.debounced, true);
  const afterFirst = calls.length;
  assert.ok(afterFirst >= 2, "first write = HSET + SET on Redis");
  const r2 = await recordHeartbeat({ slot: "agent-41", source: "mcp-tower" });
  assert.equal(r2.ok, true);
  assert.equal(r2.debounced, true, "second write within the window must be debounced");
  assert.equal(calls.length, afterFirst, "debounced write must not touch Redis");
  // Different slot → independent window → still writes.
  const r3 = await recordHeartbeat({ slot: "agent-42", source: "mcp-tower" });
  assert.notEqual(r3.debounced, true);
  assert.ok(calls.length > afterFirst);
  // Reset hook restores independent-write semantics for tests.
  resetRedisWriteDebounce();
  const r4 = await recordHeartbeat({ slot: "agent-41", source: "mcp-tower" });
  assert.notEqual(r4.debounced, true, "after reset the same slot writes again");
  delete process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD;
  delete process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS;
}

// ── 5. AC2 — presence write debounce (per client key) ────────────────────────
{
  resetAll();
  process.env.REDIS_PRESENCE_DEBOUNCE_SECONDS = "60";
  const p1 = await recordPresence({ clientName: "Cursor", clientId: "c-1", protocol: "streamable-http" });
  assert.equal(p1.ok, true);
  assert.notEqual(p1.debounced, true);
  const afterFirst = calls.length;
  const p2 = await recordPresence({ clientName: "Cursor", clientId: "c-1", protocol: "streamable-http" });
  assert.equal(p2.debounced, true);
  assert.equal(calls.length, afterFirst, "presence refresh within window must not touch Redis");
  const p3 = await recordPresence({ clientName: "Cursor", clientId: "c-2", protocol: "streamable-http" });
  assert.notEqual(p3.debounced, true, "different client id → separate window");
  resetPresenceWriteDebounce();
  const p4 = await recordPresence({ clientName: "Cursor", clientId: "c-1", protocol: "streamable-http" });
  assert.notEqual(p4.debounced, true);
  delete process.env.REDIS_PRESENCE_DEBOUNCE_SECONDS;
}

// ── 6. AC2 — L1 read-through cache collapses sweep bursts ───────────────────
{
  resetAll();
  process.env.REDIS_L1_CACHE_TTL_MS = "5000";
  await recordHeartbeat({ slot: "agent-61", source: "mcp-tower" }); // seed one record
  process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS = "0";
  resetRedisWriteDebounce();
  calls.length = 0;
  const first = await listHeartbeatsSafe();
  const afterFirst = calls.length;
  assert.ok(afterFirst > 0, "first sweep must read Redis");
  const second = await listHeartbeatsSafe();
  assert.equal(calls.length, afterFirst, "second sweep within TTL must be served from L1");
  assert.deepEqual(second.slots.map((s) => s.slot), first.slots.map((s) => s.slot));
  clearRedisL1Cache();
  await listHeartbeatsSafe();
  assert.ok(calls.length > afterFirst, "after cache clear the sweep reads Redis again");
  delete process.env.REDIS_L1_CACHE_TTL_MS;
  delete process.env.REDIS_HEARTBEAT_DEBOUNCE_SECONDS;
}

async function listHeartbeatsSafe() {
  const { listHeartbeats } = await import("./src/registry/agent_heartbeat.js");
  return await listHeartbeats();
}

// ── 7. Local counter drives preemptive rotation directly (unit) ─────────────
{
  resetAll();
  process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD = "3";
  noteRedisCommands("primary", 1);
  noteRedisCommands("primary", 1);
  assert.equal(isAccountQuotaExhausted("primary"), false, "below threshold → still active");
  noteRedisCommands("primary", 1); // hits 3
  assert.ok(isAccountQuotaExhausted("primary"), "threshold hit → preemptive cooldown");
  delete process.env.UPSTASH_PREEMPTIVE_ROTATION_THRESHOLD;
}

// ── Cleanup ──────────────────────────────────────────────────────────────────
resetAll();
(globalThis as unknown as { fetch: typeof fetch }).fetch = realFetch;

console.log("ALL PREEMPTIVE-ROTATION TESTS PASSED (#646) — 7/7 scenarios: zero failed requests before rotation, debounce + L1 cache active");
