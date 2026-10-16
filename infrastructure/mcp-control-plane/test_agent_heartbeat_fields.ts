/**
 * F2 (audit 2026-10-16) — agent_heartbeat task-ownership fields.
 *
 * House style (see test_heartbeat.ts / test_killswitch_persistence.ts):
 * tsx script, hard asserts, exit non-zero on failure. Zero network: env is
 * scrubbed so the account chain is empty; the validator ordering and pure
 * record builder are exercised without any registry write.
 *
 * Coverage contract:
 *   1. taskId validators: SSOT-exact — 129 chars rejected, 128 ok, ""
 *      (= idle) ok, control chars rejected, bad shape rejected, non-string
 *      rejected.
 *   2. status validators: alive|busy|idle accepted; everything else rejected
 *      (including case variants).
 *   3. ttlSeconds validators: 29/3601 rejected, 30/299/3600 ok, non-integer
 *      and non-number rejected.
 *   4. FAIL-CLOSED ordering: recordHeartbeat with an invalid ownership field
 *      throws the VALIDATOR error (never the "No Redis configuration"
 *      error) — proof that validation precedes any registry write, matching
 *      the slot-validation ordering contract in test_heartbeat.ts.
 *   5. Backward compatibility: buildHeartbeatRecord without ownership fields
 *      emits byte-identical keys to the pre-F2 record shape; with fields,
 *      they ride along verbatim.
 */

import * as path from "node:path";
import { config } from "dotenv";

config({ path: path.resolve(process.cwd(), "../../.env") });

// Scrub the Redis env BEFORE importing the registry (house pattern from
// test_heartbeat.ts) — guarantees zero real writes even with a configured .env.
delete process.env.UPSTASH_REDIS_REST_URL;
delete process.env.UPSTASH_REDIS_REST_TOKEN;
delete process.env.REDIS_URL;
delete process.env.UPSTASH_REDIS_SECONDARY_REST_URL;
delete process.env.UPSTASH_REDIS_SECONDARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_TERTIARY_REST_URL;
delete process.env.UPSTASH_REDIS_TERTIARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUATERNARY_REST_TOKEN;
delete process.env.UPSTASH_REDIS_QUINARY_REST_URL;
delete process.env.UPSTASH_REDIS_QUINARY_REST_TOKEN;

import {
  buildHeartbeatRecord,
  HEARTBEAT_TASK_ID_MAX,
  validateHeartbeatStatus,
  validateHeartbeatTaskId,
  validateHeartbeatTtlSeconds,
  recordHeartbeat,
} from "./src/registry/agent_heartbeat.js";

let passed = 0;
const failures: string[] = [];

function assert(cond: boolean, label: string): void {
  if (cond) {
    passed += 1;
    console.log(`  ✓ ${label}`);
  } else {
    failures.push(label);
    console.error(`  ✗ ${label}`);
  }
}

async function rejectsWith(fn: () => unknown | Promise<unknown>, needle: string, label: string): Promise<void> {
  try {
    await fn();
    failures.push(`${label} — did not throw`);
    console.error(`  ✗ ${label} — did not throw`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes(needle)) {
      passed += 1;
      console.log(`  ✓ ${label}`);
    } else {
      failures.push(`${label} — threw "${msg}" (expected to include "${needle}")`);
      console.error(`  ✗ ${label} — threw "${msg}"`);
    }
  }
}

async function main(): Promise<void> {
  console.log("=== F2: agent_heartbeat task-ownership fields — regression suite ===");

  // ── 1. taskId ────────────────────────────────────────────────────────────
  console.log("\n[1] taskId validation (SSOT heartbeat.schema.json)");
  eq(validateHeartbeatTaskId(""), null, '"" (idle) accepted');
  eq(validateHeartbeatTaskId("bridge-20261016-killswitch-persistence"), null, "normal task id accepted");
  eq(validateHeartbeatTaskId("a".repeat(128)), null, "128 chars accepted (boundary)");
  assert(validateHeartbeatTaskId("a".repeat(129)) !== null, "129 chars rejected (boundary)");
  eq(HEARTBEAT_TASK_ID_MAX, 128, "exported bound = 128");
  assert(validateHeartbeatTaskId("bad id!") !== null, "invalid shape rejected");
  assert(validateHeartbeatTaskId("-leading-dash") !== null, "leading dash rejected (SSOT pattern)");
  assert(validateHeartbeatTaskId("has\x01control") !== null, "control char rejected");
  assert(validateHeartbeatTaskId("has\nnewline") !== null, "newline rejected");
  assert(validateHeartbeatTaskId(undefined as unknown as string) !== null, "non-string rejected");

  // ── 2. status ────────────────────────────────────────────────────────────
  console.log("\n[2] status validation");
  for (const s of ["alive", "busy", "idle"]) {
    eq(validateHeartbeatStatus(s), null, `"${s}" accepted`);
  }
  for (const s of ["ALIVE", "online", "down", "", "dead"]) {
    assert(validateHeartbeatStatus(s) !== null, `"${s}" rejected`);
  }
  assert(validateHeartbeatStatus(42 as unknown as string) !== null, "non-string rejected");

  // ── 3. ttlSeconds ────────────────────────────────────────────────────────
  console.log("\n[3] ttlSeconds validation (30..3600)");
  assert(validateHeartbeatTtlSeconds(29) !== null, "29 rejected (boundary)");
  eq(validateHeartbeatTtlSeconds(30), null, "30 accepted (boundary)");
  eq(validateHeartbeatTtlSeconds(299), null, "299 accepted");
  eq(validateHeartbeatTtlSeconds(3600), null, "3600 accepted (boundary)");
  assert(validateHeartbeatTtlSeconds(3601) !== null, "3601 rejected (boundary)");
  assert(validateHeartbeatTtlSeconds(299.5) !== null, "non-integer rejected");
  assert(validateHeartbeatTtlSeconds("300" as unknown as number) !== null, "non-number rejected");

  // ── 4. fail-closed ordering (validators BEFORE registry write) ──────────
  console.log("\n[4] validators run before any registry write (fail-closed)");
  const redisError = "No Redis configuration found";
  await rejectsWith(
    () => recordHeartbeat({ slot: "agent-4", source: "mcp-tower", ttlSeconds: 29 }),
    "ttlSeconds must be an integer",
    "invalid ttl throws VALIDATOR error, not redis-missing error",
  );
  await rejectsWith(
    () => recordHeartbeat({ slot: "agent-4", source: "mcp-tower", taskId: "has space" }),
    "taskId must match",
    "invalid taskId throws VALIDATOR error",
  );
  await rejectsWith(
    () => recordHeartbeat({ slot: "agent-4", source: "mcp-tower", status: "online" as never }),
    "status must be one of",
    "invalid status throws VALIDATOR error",
  );
  // Sanity: with env scrubbed, a VALID ping still hits the redis-missing
  // error — proving the validator branch sits strictly before the chain walk.
  await rejectsWith(
    () => recordHeartbeat({ slot: "agent-4", source: "mcp-tower", taskId: "t-1", status: "busy", ttlSeconds: 299 }),
    redisError,
    "valid fields proceed to (scrubbed) registry — ordering proven both ways",
  );

  // ── 5. backward-compatible record shape ─────────────────────────────────
  console.log("\n[5] record builder backward compatibility");
  const nowMs = 1_700_000_000_000;
  const legacy = buildHeartbeatRecord({ slot: "agent-4", agentId: "Cline", source: "mcp-tower", clientId: "c1" }, nowMs);
  eq(
    Object.keys(legacy).sort(),
    ["agentId", "clientId", "slot", "source", "updatedAt", "updatedAtMs"],
    "legacy ping: byte-compatible key set (no F2 fields)",
  );
  const owned = buildHeartbeatRecord(
    { slot: "agent-4", source: "mcp-tower", taskId: "t-1", status: "busy", ttlSeconds: 299 },
    nowMs,
  );
  eq(owned.taskId, "t-1", "taskId rides along");
  eq(owned.status, "busy", "status rides along");
  eq(owned.ttlSeconds, 299, "ttlSeconds rides along");
  eq(owned.agentId, "agent-4", "agentId default (slot id) preserved");
  eq(owned.updatedAt, new Date(nowMs).toISOString(), "updatedAt derivation preserved");
  // Old records (no F2 keys) still parse as HeartbeatRecord — optional fields.
  const parsed = JSON.parse(JSON.stringify(legacy));
  eq(parsed.taskId, undefined, "old stored records parse without F2 fields");

  console.log("\n=============================================");
  if (failures.length > 0) {
    console.error(`❌ ${failures.length} assertion(s) FAILED:`);
    for (const f of failures) console.error(`   - ${f}`);
    process.exit(1);
  }
  console.log(`✅ ALL HEARTBEAT FIELD TESTS PASSED (${passed} assertions)`);
}

function eq<T>(actual: T, expected: T, label: string): void {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    passed += 1;
    console.log(`  ✓ ${label}`);
  } else {
    failures.push(`${label} (actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)})`);
    console.error(`  ✗ ${label} — actual=${JSON.stringify(actual)} expected=${JSON.stringify(expected)}`);
  }
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
