/**
 * F1 (audit 2026-10-16) — persistent kill switch regression suite.
 *
 * House style (see test_bridge_intake.ts): tsx script, hard asserts, exit
 * non-zero on the first failure. Zero network: the REST caller and account
 * chain are injected fakes, and the env gate is toggled via injectable
 * envGet — no process.env mutation, no real Redis.
 *
 * Coverage contract (T2 tier):
 *   1. AUTONOMY_DISABLED env gate ("1" and "true", case-insensitive) boots
 *      DISABLED; enableAutonomy() is refused while the gate stands.
 *   2. No-Redis boot degrades honestly (VOLATILE state, loud log, never
 *      crashes; persistence not armed).
 *   3. Boot restore: store "disabled" → boots disabled; store "enabled" →
 *      boots enabled; fresh store (null) → boots enabled.
 *   4. FAIL-CLOSED: restore failure (unreachable store / corrupt record /
 *      missing boolean) boots DISABLED with lastRestoreError captured.
 *   5. emergencyStop / enableAutonomy: sync flip is immediate and idempotent;
 *      armed flips persist the record (writer payload shape asserted).
 *   6. Persist failure is captured in lastPersistError and never throws.
 *   7. describe() exposes the full introspection snapshot.
 */

import type { RedisAccountConfig } from "./src/lib/redis_chain.js";
import {
  KillSwitchManager,
  KILL_SWITCH_STATE_KEY,
  type KillSwitchRestCaller,
} from "./src/remediation/killswitch.js";

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

const ACCOUNT: RedisAccountConfig = { label: "primary", restUrl: "https://rest.example", restToken: "t" };
const CHAIN = [ACCOUNT];

type Store = Map<string, string>;

/** Fake REST caller backed by a Map; optional failure injection. */
function fakeRestCall(store: Store, opts: { failGet?: boolean; failSet?: boolean } = {}): KillSwitchRestCaller {
  return async (_account, command) => {
    const [op, key, value] = command as [string, string, string?];
    if (op === "GET") {
      if (opts.failGet) throw new Error("injected GET failure");
      return store.has(key) ? store.get(key)! : null;
    }
    if (op === "SET") {
      if (opts.failSet) throw new Error("injected SET failure");
      store.set(key, value!);
      return "OK";
    }
    throw new Error(`fakeRestCall: unsupported op ${op}`);
  };
}

interface Log {
  lines: string[];
  errors: string[];
}

function makeDeps(
  store: Store | null,
  env: Record<string, string | undefined>,
  opts: { failGet?: boolean; failSet?: boolean } = {},
): { deps: any; log: Log } {
  const log: Log = { lines: [], errors: [] };
  const deps = {
    now: () => 1_700_000_000_000,
    restCall: store ? fakeRestCall(store, opts) : undefined,
    chainBuilder: () => (store ? CHAIN : []),
    envGet: (name: string) => env[name],
    log: (line: string) => log.lines.push(line),
    errorLog: (line: string) => log.errors.push(line),
  } as any;
  return { deps, log };
}

async function main(): Promise<void> {
  console.log("=== F1: persistent kill switch — regression suite ===");

  // ── 1. Env gate ──────────────────────────────────────────────────────────
  console.log("\n[1] AUTONOMY_DISABLED env gate");
  {
    for (const gateVal of ["1", "true", "TRUE", "True"]) {
      const { deps, log } = makeDeps(null, { AUTONOMY_DISABLED: gateVal });
      const ks = new KillSwitchManager(deps);
      eq(ks.isAutonomyEnabled(), false, `gate=${gateVal} boots DISABLED`);
      eq(ks.describe().envGateDisabled, true, `gate=${gateVal} introspects envGateDisabled`);
      assert(log.errors.some((l) => l.includes("AUTONOMY_DISABLED")), `gate=${gateVal} boots with loud log`);
    }
    {
      const { deps } = makeDeps(null, { AUTONOMY_DISABLED: "0" });
      const ks = new KillSwitchManager(deps);
      eq(ks.isAutonomyEnabled(), true, "gate=0 does NOT disable");
    }
    {
      const { deps } = makeDeps(null, {});
      const ks = new KillSwitchManager(deps);
      eq(ks.isAutonomyEnabled(), true, "unset gate boots enabled (legacy default)");
    }
    // enableAutonomy refused under gate
    {
      const { deps } = makeDeps(null, { AUTONOMY_DISABLED: "1" });
      const ks = new KillSwitchManager(deps);
      ks.enableAutonomy();
      eq(ks.isAutonomyEnabled(), false, "enableAutonomy REFUSED while env gate stands");
    }
  }

  // ── 2. No-Redis honest degradation ──────────────────────────────────────
  console.log("\n[2] no-Redis boot (VOLATILE, never crashes)");
  {
    const { deps, log } = makeDeps(null, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    const snap = ks.describe();
    eq(snap.persistenceArmed, false, "persistence NOT armed without Redis");
    assert(snap.lastPersistError?.includes("VOLATILE") === true, "honest VOLATILE introspection");
    assert(log.errors.some((l) => l.includes("VOLATILE")), "loud VOLATILE boot log");
    eq(ks.isAutonomyEnabled(), true, "legacy default (enabled) preserved without Redis");
    ks.emergencyStop(); // must not throw
    eq(ks.isAutonomyEnabled(), false, "in-memory emergencyStop still works");
    assert(log.errors.some((l) => l.includes("VOLATILE") && l.includes("flip is VOLATILE")), "flip logs volatility honestly");
  }

  // ── 3. Boot restore ─────────────────────────────────────────────────────
  console.log("\n[3] boot restore from store");
  {
    const store: Store = new Map([[KILL_SWITCH_STATE_KEY, JSON.stringify({ autonomyEnabled: false, updatedAt: "x" })]]);
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), false, "store=disabled → boots DISABLED");
    eq(ks.describe().persistedState, "disabled", "persistedState introspection = disabled");
  }
  {
    const store: Store = new Map([[KILL_SWITCH_STATE_KEY, JSON.stringify({ autonomyEnabled: true, updatedAt: "x" })]]);
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), true, "store=enabled → boots enabled");
    eq(ks.describe().persistedState, "enabled", "persistedState introspection = enabled");
  }
  {
    const store: Store = new Map(); // fresh store — first boot ever
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), true, "fresh store (no record) → boots enabled");
  }
  {
    // env gate + armed store: gate wins, store synced to "disabled"
    const store: Store = new Map([[KILL_SWITCH_STATE_KEY, JSON.stringify({ autonomyEnabled: true, updatedAt: "x" })]]);
    const { deps } = makeDeps(store, { AUTONOMY_DISABLED: "1" });
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), false, "env gate outranks store at boot");
    eq(store.get(KILL_SWITCH_STATE_KEY), JSON.stringify({ autonomyEnabled: false, updatedAt: new Date(1_700_000_000_000).toISOString(), writer: "mcp-control-plane/killswitch.ts" }), "store synced to disabled under gate");
  }

  // ── 4. FAIL-CLOSED restore failures ─────────────────────────────────────
  console.log("\n[4] restore failure fails CLOSED");
  {
    const { deps, log } = makeDeps(new Map(), {}, { failGet: true });
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), false, "unreachable store → boots DISABLED (fail-closed)");
    assert(ks.describe().lastRestoreError?.includes("injected GET failure") === true, "lastRestoreError captured");
    assert(log.errors.some((l) => l.includes("failing CLOSED")), "loud fail-closed log");
  }
  {
    const store: Store = new Map([[KILL_SWITCH_STATE_KEY, "{not-json"]]);
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), false, "corrupt record → boots DISABLED (refusing to guess)");
  }
  {
    const store: Store = new Map([[KILL_SWITCH_STATE_KEY, JSON.stringify({ nope: 1 })]]);
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    eq(ks.isAutonomyEnabled(), false, "record lacking boolean → boots DISABLED");
  }

  // ── 5. Flip persistence + idempotency ───────────────────────────────────
  console.log("\n[5] sync flips + armed persistence");
  {
    const store: Store = new Map();
    const { deps } = makeDeps(store, {});
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    ks.emergencyStop();
    eq(ks.isAutonomyEnabled(), false, "emergencyStop flips synchronously");
    eq(store.get(KILL_SWITCH_STATE_KEY), JSON.stringify({ autonomyEnabled: false, updatedAt: new Date(1_700_000_000_000).toISOString(), writer: "mcp-control-plane/killswitch.ts" }), "stop persisted to store");
    ks.emergencyStop(); // idempotent
    eq(store.get(KILL_SWITCH_STATE_KEY), JSON.stringify({ autonomyEnabled: false, updatedAt: new Date(1_700_000_000_000).toISOString(), writer: "mcp-control-plane/killswitch.ts" }), "second stop is a no-op (same record)");
    ks.enableAutonomy();
    eq(ks.isAutonomyEnabled(), true, "enableAutonomy flips synchronously");
    eq(JSON.parse(store.get(KILL_SWITCH_STATE_KEY)!).autonomyEnabled, true, "enable persisted to store");
    ks.enableAutonomy(); // idempotent
    eq(JSON.parse(store.get(KILL_SWITCH_STATE_KEY)!).autonomyEnabled, true, "second enable is a no-op");
  }
  {
    // emergencyStop stops the scheduler (existing behavior preserved)
    const { deps } = makeDeps(new Map(), {});
    const ks = new KillSwitchManager(deps);
    let stopped = 0;
    const mod = await import("./src/tasks/engine.js");
    const orig = mod.globalTaskEngine.stopBackgroundScheduler;
    mod.globalTaskEngine.stopBackgroundScheduler = () => { stopped += 1; orig.call(mod.globalTaskEngine); };
    ks.emergencyStop();
    await new Promise((r) => setTimeout(r, 20));
    eq(stopped >= 1, true, "emergencyStop still stops the background scheduler");
    mod.globalTaskEngine.stopBackgroundScheduler = orig;
  }

  // ── 6. Persist failure honesty ──────────────────────────────────────────
  console.log("\n[6] persist failure never throws");
  {
    const { deps, log } = makeDeps(new Map(), {}, { failSet: true });
    const ks = new KillSwitchManager(deps);
    await ks.initPersistence();
    ks.emergencyStop(); // persist will fail — must not throw
    await new Promise((r) => setTimeout(r, 20));
    eq(ks.isAutonomyEnabled(), false, "in-memory flip stands despite persist failure");
    assert(ks.describe().lastPersistError?.includes("injected SET failure") === true, "lastPersistError captured");
    assert(log.errors.some((l) => l.includes("persist FAILED")), "loud persist-failure log");
  }

  // ── 7. describe() snapshot shape ────────────────────────────────────────
  console.log("\n[7] describe() introspection");
  {
    const { deps } = makeDeps(new Map(), {});
    const ks = new KillSwitchManager(deps);
    const snap = ks.describe();
    for (const key of ["autonomyEnabled", "envGateDisabled", "persistenceArmed", "persistedState", "lastPersistError", "lastRestoreError", "stateKey"]) {
      assert(key in snap, `describe() exposes ${key}`);
    }
    eq(snap.stateKey, KILL_SWITCH_STATE_KEY, "stateKey is the canonical store key");
  }

  console.log("\n=============================================");
  if (failures.length > 0) {
    console.error(`❌ ${failures.length} assertion(s) FAILED:`);
    for (const f of failures) console.error(`   - ${f}`);
    process.exit(1);
  }
  console.log(`✅ ALL KILL SWITCH PERSISTENCE TESTS PASSED (${passed} assertions)`);
}

main().catch((err) => {
  console.error("FATAL:", err);
  process.exit(1);
});
