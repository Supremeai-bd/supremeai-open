/**
 * Agent heartbeat contract tests (issue #1402).
 *
 * Pure-logic coverage — no Redis required. Verifies:
 *   1. Slot validation accepts "agent-N" and rejects everything else
 *   2. State derivation matches the spec: ≤90s online, >90s stale, >300s expired
 *   3. Key layout matches the shared cross-service contract
 *   4. recordHeartbeat fails with a CLEAR error when Redis is unconfigured
 *      (fail-loud, not silently "ok")
 *
 * Run: npm run test:heartbeat   (wired into test:unit)
 */
import assert from "node:assert/strict";

import {
  HEARTBEAT_HASH_KEY,
  HEARTBEAT_KEY_PREFIX,
  HEARTBEAT_ONLINE_THRESHOLD_SECONDS,
  HEARTBEAT_TTL_SECONDS,
  archiveGraceSeconds,
  buildAccountChain,
  buildStatusEntry,
  deriveState,
  heartbeatKey,
  listHeartbeats,
  partitionSlots,
  recordHeartbeat,
  validateSlot,
} from "./src/registry/agent_heartbeat.js";

// ── 1. Slot validation ─────────────────────────────────────────────────────
assert.equal(validateSlot("agent-1"), null);
assert.equal(validateSlot("agent-11"), null);
assert.equal(validateSlot("agent-042"), null);
assert.ok(validateSlot("")?.includes("required"));
assert.ok(validateSlot("agent-")?.includes("must match"));
assert.ok(validateSlot("agent-4-extra")?.includes("must match"));
assert.ok(validateSlot("Agent-4")?.includes("must match"));
assert.ok(validateSlot("agent_4")?.includes("must match"));
assert.ok(validateSlot("agent-4\n")?.includes("must match"));
assert.ok(validateSlot("supremeai:agent-heartbeat:agent-4")?.includes("must match"));

// ── 2. Key layout (shared contract with dashboard + backend + scripts) ─────
assert.equal(heartbeatKey("agent-4"), "supremeai:agent-heartbeat:agent-4");
assert.equal(HEARTBEAT_HASH_KEY, "supremeai:agent-heartbeats");
assert.ok(HEARTBEAT_KEY_PREFIX.endsWith(":"));
assert.equal(HEARTBEAT_TTL_SECONDS, 300);
assert.equal(HEARTBEAT_ONLINE_THRESHOLD_SECONDS, 90);

// ── 3. State derivation ────────────────────────────────────────────────────
const now = 1_700_000_000_000;
assert.equal(deriveState(now - 0, now), "online");
assert.equal(deriveState(now - 45_000, now), "online"); // spec cadence
assert.equal(deriveState(now - 89_999, now), "online"); // < 90s
assert.equal(deriveState(now - 90_000, now), "stale"); // 90s–300s → stale
assert.equal(deriveState(now - 299_999, now), "stale");
assert.equal(deriveState(now - 300_000, now), "stale"); // TTL boundary inclusive
assert.equal(deriveState(now - 300_001, now), "expired"); // key gone
assert.equal(deriveState(now - 3_600_000, now), "expired");
assert.equal(deriveState(now + 5_000, now), "online"); // clock skew tolerated

// ── 4. Redis-unconfigured behaviour (CI / misconfigured deploy) ────────────
// The sandbox/CI runs without Upstash env vars → both calls must throw the
// explicit "No Redis configuration" error rather than pretend success.
delete process.env.UPSTASH_REDIS_REST_URL;
delete process.env.UPSTASH_REDIS_REST_TOKEN;
delete process.env.UPSTASH_REDIS_SECONDARY_REST_URL;
delete process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_TERTIARY_REST_URL;
delete process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_QUINARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUINARY_REST_TOKEN;
delete process.env.REDIS_URL;

assert.equal(buildAccountChain().length, 0);

let recordErr: unknown;
try {
  await recordHeartbeat({ slot: "agent-4", source: "mcp-tower" });
} catch (err) {
  recordErr = err;
}
assert.ok(recordErr instanceof Error);
assert.match((recordErr as Error).message, /No Redis configuration found/);

let listErr: unknown;
try {
  await listHeartbeats();
} catch (err) {
  listErr = err;
}
assert.ok(listErr instanceof Error);
assert.match((listErr as Error).message, /No Redis configuration found/);

// recordHeartbeat validates BEFORE touching Redis — invalid slot fails even
// without Redis configured.
let slotErr: unknown;
try {
  await recordHeartbeat({ slot: "not-a-slot", source: "mcp-tower" });
} catch (err) {
  slotErr = err;
}
assert.ok(slotErr instanceof Error);
assert.match((slotErr as Error).message, /must match/);

// ── 5. Account chain assembly (quota-failover, issue #1402 "Redis" note) ───
process.env.UPSTASH_REDIS_REST_URL = "https://primary.upstash.io";
process.env.UPSTASH_REDIS_REST_TOKEN = "t1";
assert.deepEqual(
  buildAccountChain().map((a) => a.label),
  ["primary"],
);

process.env.UPSTASH_REDIS_SECONDARY_REST_URL = "https://secondary.upstash.io";
process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN = "t2";
process.env.UPSTASH_REDIS_TERTIARY_REST_URL = "https://tertiary.upstash.io";
process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN = "t3";
process.env.UPSTASH_REDIS_QUATERNARY_REST_URL = "https://quaternary.upstash.io";
process.env.UPSTASH_REDIS_QUATERNARY_REST_TOKEN = "t4";
process.env.UPSTASH_REDIS_QUINARY_REST_URL = "https://quinary.upstash.io";
process.env.UPSTASH_REDIS_QUINARY_REST_TOKEN = "t5";
const fullChain = buildAccountChain();
assert.deepEqual(
  fullChain.map((a) => a.label),
  ["primary", "secondary", "tertiary", "quaternary", "quinary"],
);
assert.ok(fullChain.every((a) => a.restUrl && a.restToken));

// A partial chain skips misconfigured accounts (url without token).
delete process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN;
assert.deepEqual(
  buildAccountChain().map((a) => a.label),
  ["primary", "secondary", "quaternary", "quinary"],
);
process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN = "t3";

// TCP-only primary (REDIS_URL without REST vars) still yields a chain.
delete process.env.UPSTASH_REDIS_REST_URL;
delete process.env.UPSTASH_REDIS_REST_TOKEN;
process.env.REDIS_URL = "rediss://default:pw@primary.upstash.io:6379";
const tcpChain = buildAccountChain();
assert.equal(tcpChain.length, 5);
assert.equal(tcpChain[0].label, "primary");
assert.equal(tcpChain[0].tcpUrl, "rediss://default:pw@primary.upstash.io:6379");
delete process.env.REDIS_URL;

// ── 5. #1641 archive partition + entry normalization (pure logic) ──────────
// Tower slot registry retained expired heartbeats aged 21–24 days because the
// heartbeat HASH has no field TTL (legacy keys die at 300s, hash fields don't).
// The read-time lazy reaper partitions expired-beyond-grace slots out of the
// default listing and HDELs them (best-effort) — bounded registry growth.

const t0 = 1_700_000_000_000;
const rec = (ageMs: number, agentId?: string | null) => ({
  slot: "agent-1",
  agentId: (agentId ?? undefined) as string,
  source: "mcp-tower" as const,
  updatedAtMs: t0 - ageMs,
  updatedAt: new Date(t0 - ageMs).toISOString(),
});

// agentId normalization: legacy null/blank records show the slot id, never null.
assert.equal(buildStatusEntry("agent-9", rec(0, null as unknown as string), t0).agentId, "agent-9");
assert.equal(buildStatusEntry("agent-9", rec(0, "   "), t0).agentId, "agent-9");
assert.equal(
  buildStatusEntry("agent-9", rec(0, "supremeai-coder-1"), t0).agentId,
  "supremeai-coder-1",
);
assert.equal(buildStatusEntry("agent-9", rec(45_000), t0).state, "online");

const entries = [
  buildStatusEntry("agent-1", rec(45_000), t0), // online
  buildStatusEntry("agent-2", rec(200_000), t0), // stale
  buildStatusEntry("agent-3", rec(600_000), t0), // expired, within default 24h grace
  buildStatusEntry("agent-5", rec(21 * 86_400_000), t0), // expired 21 days → archive
  buildStatusEntry("agent-7", rec(86_400_000), t0), // exactly 24h old = grace boundary inclusive → still listed
];

// Default grace (24h): dead-beyond-grace leaves the listing; recent death stays visible.
const pDefault = partitionSlots(entries, t0);
assert.deepEqual(pDefault.slots.map((e) => e.slot), ["agent-1", "agent-2", "agent-3", "agent-7"]);
assert.deepEqual(pDefault.archived.map((e) => e.slot), ["agent-5"]);
assert.deepEqual(pDefault.reapTargets, ["agent-5"]);
assert.equal(pDefault.archived[0].state, "expired"); // honest state, not silently rewritten

// grace=0: every expired entry leaves the default listing immediately (audit-strict mode).
const pZero = partitionSlots(entries, t0, 0);
assert.deepEqual(pZero.slots.map((e) => e.slot), ["agent-1", "agent-2"]);
assert.deepEqual(pZero.reapTargets, ["agent-3", "agent-5", "agent-7"]);

// Tiny grace never archives online/stale entries (state machine preserved).
const pTiny = partitionSlots(entries, t0, 100);
assert.deepEqual(pTiny.slots.map((e) => e.slot), ["agent-1", "agent-2"]);
assert.deepEqual(pTiny.reapTargets, ["agent-3", "agent-5", "agent-7"]);

// Negative grace clamps to 0 (no accidental full-archive of fresh entries).
process.env.REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS = "-5";
assert.equal(archiveGraceSeconds(), 86_400); // invalid → default
process.env.REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS = "0";
assert.equal(archiveGraceSeconds(), 0);
process.env.REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS = "3600";
assert.equal(archiveGraceSeconds(), 3600);
delete process.env.REDIS_HEARTBEAT_ARCHIVE_GRACE_SECONDS;
assert.equal(archiveGraceSeconds(), 86_400);

console.log("agent heartbeat contract tests passed");
