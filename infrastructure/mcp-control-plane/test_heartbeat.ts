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
  buildAccountChain,
  deriveState,
  heartbeatKey,
  listHeartbeats,
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

console.log("agent heartbeat contract tests passed");
