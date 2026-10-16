/**
 * Heartbeat task-ownership field tests (audit 2026-10-16 F2 — heartbeat.schema.json SSOT alignment).
 *
 * Run: tsx test_agent_heartbeat_fields.ts
 * Offline: pure validators + type-shape assertions; the Redis write path is
 * unchanged (same chain engine covered by test:heartbeat).
 */
import {
  HEARTBEAT_TTL_MAX_SECONDS,
  HEARTBEAT_TTL_MIN_SECONDS,
  validateDeclaredTtl,
  validateHeartbeatStatus,
  validateTaskId,
} from "./src/registry/agent_heartbeat.js";

let failures = 0;
function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✅ ${name}`);
  } else {
    failures++;
    console.error(`  ❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

// ── validateDeclaredTtl (heartbeat.schema.json: 30–3600 integer) ────────────
console.log("\n▶ validateDeclaredTtl");
check("undefined → ok/absent", validateDeclaredTtl(undefined).value === undefined && !validateDeclaredTtl(undefined).error);
check("null → ok/absent", validateDeclaredTtl(null).value === undefined && !validateDeclaredTtl(null).error);
check("300 → ok", validateDeclaredTtl(300).value === 300);
check("30 boundary ok", validateDeclaredTtl(30).value === 30);
check("3600 boundary ok", validateDeclaredTtl(3600).value === 3600);
check("29 rejected", validateDeclaredTtl(29).error !== undefined);
check("3601 rejected", validateDeclaredTtl(3601).error !== undefined);
check("299 in-range ok (any integer in 30–3600)", validateDeclaredTtl(299).value === 299);
check("non-integer rejected", validateDeclaredTtl(300.5).error !== undefined);
check("string rejected", validateDeclaredTtl("300" as unknown).error !== undefined);

// ── validateTaskId (non-empty ≤128, no control chars; empty = idle) ────────
console.log("\n▶ validateTaskId");
check("undefined → ok/absent", validateTaskId(undefined).value === undefined);
check("empty string → idle (absent)", validateTaskId("").value === undefined);
check("whitespace → idle (absent)", validateTaskId("   ").value === undefined);
check("bridge task id ok", validateTaskId("bridge-20261016-agent-loop-repick").value === "bridge-20261016-agent-loop-repick");
check("128 chars ok", validateTaskId("t".repeat(128)).value !== undefined);
check("129 chars rejected", validateTaskId("t".repeat(129)).error !== undefined);
check("control char rejected", validateTaskId("bad\nid").error !== undefined);
check("non-string rejected", validateTaskId(42 as unknown).error !== undefined);

// ── validateHeartbeatStatus (alive|busy|idle) ────────────────────────────────
console.log("\n▶ validateHeartbeatStatus");
check("alive ok", validateHeartbeatStatus("alive").value === "alive");
check("busy ok", validateHeartbeatStatus("busy").value === "busy");
check("idle ok", validateHeartbeatStatus("idle").value === "idle");
check("undefined ok", validateHeartbeatStatus(undefined).value === undefined);
check("online rejected (not in SSOT enum)", validateHeartbeatStatus("online" as unknown).error !== undefined);
check("empty rejected", validateHeartbeatStatus("" as unknown).error !== undefined);

// ── protocol constants match HEARTBEAT_PROTOCOL.md §2 ───────────────────────
console.log("\n▶ protocol constants");
check("TTL min 30 (schema)", HEARTBEAT_TTL_MIN_SECONDS === 30);
check("TTL max 3600 (schema)", HEARTBEAT_TTL_MAX_SECONDS === 3600);

console.log(failures === 0 ? "\n✅ heartbeat field tests: ALL PASS" : `\n❌ ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
