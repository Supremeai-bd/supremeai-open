/**
 * Kill-switch persistence tests (audit 2026-10-16 F1 — docs/AUDIT_2026-10-16-intelligence-usability.md).
 *
 * Run: tsx test_killswitch_persistence.ts
 * Offline: no Redis required — covers env gate, constructor fail-closed shape,
 * immediate sync flip semantics, and honest introspection (describe()).
 * The Redis-persist path itself is exercised only with a live chain (documented
 * residual; the store is the same runWithAccountChain engine already covered by
 * test_account_chain_callers.ts / test_redis_auto_rotation.ts).
 */
import { KillSwitchManager, globalKillSwitch } from "./src/remediation/killswitch.js";

let failures = 0;
function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✅ ${name}`);
  } else {
    failures++;
    console.error(`  ❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

const prevGate = process.env.AUTONOMY_DISABLED;

// ── 1. Boot env gate (fail-closed) ──────────────────────────────────────────
console.log("\n▶ AUTONOMY_DISABLED env gate");
process.env.AUTONOMY_DISABLED = "1";
const gated = new KillSwitchManager();
check("env gate '1' → starts disabled", gated.isAutonomyEnabled() === false);
check("describe().envGate true", gated.describe().envGate === true);
check("describe().persistedState 'disabled'", gated.describe().persistedState === "disabled");

process.env.AUTONOMY_DISABLED = "true";
check("env gate 'true' → starts disabled", new KillSwitchManager().isAutonomyEnabled() === false);

delete process.env.AUTONOMY_DISABLED;

// ── 2. No-Redis boot → honest degradation (env-gate + in-memory semantics) ──
console.log("\n▶ no-Redis boot (graceful degradation, honest describe)");
const plain = new KillSwitchManager();
const d = plain.describe();
check("no gate → starts enabled", plain.isAutonomyEnabled() === true);
check("persistEnabled false without chain", d.persistEnabled === false);
check("no fake persistence claims", typeof d.lastPersistError === "string" || d.lastPersistError === null);

// ── 3. Sync flip contract (callers never await) ─────────────────────────────
console.log("\n▶ emergencyStop/enable flip semantics");
plain.emergencyStop();
check("emergencyStop → disabled immediately (sync)", plain.isAutonomyEnabled() === false);
plain.enableAutonomy();
check("enableAutonomy → re-enabled immediately (sync)", plain.isAutonomyEnabled() === true);
plain.emergencyStop();
plain.emergencyStop(); // idempotent
check("emergencyStop idempotent", plain.isAutonomyEnabled() === false);
plain.enableAutonomy();
plain.enableAutonomy(); // idempotent
check("enableAutonomy idempotent", plain.isAutonomyEnabled() === true);

// ── 4. describe() shape (autonomy.status introspection contract) ───────────
console.log("\n▶ describe() introspection shape");
const shape = globalKillSwitch.describe();
check(
  "describe() has all honest-truth keys",
  ["autonomyEnabled", "persistedState", "envGate", "persistEnabled", "lastPersistError", "lastRestoreError"].every(
    (k) => k in shape,
  ),
  JSON.stringify(Object.keys(shape)),
);
check("persistedState enum", ["enabled", "disabled", "unknown"].includes(shape.persistedState));

if (prevGate !== undefined) process.env.AUTONOMY_DISABLED = prevGate;

console.log(failures === 0 ? "\n✅ kill-switch persistence tests: ALL PASS" : `\n❌ ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
