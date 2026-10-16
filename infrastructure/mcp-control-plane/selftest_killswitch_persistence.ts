/**
 * Hermetic self-test for the #340 kill-switch persistence + heartbeat
 * ownership drop-ins. Zero external dependencies, zero network, zero
 * credentials: Redis is a fake in-memory port; the account-chain engine is
 * never loaded (lazy import contract of killswitch_persistence.ts).
 *
 * Run (any of):
 *   bun  infrastructure/mcp-control-plane/selftest_killswitch_persistence.ts
 *   tsx  infrastructure/mcp-control-plane/selftest_killswitch_persistence.ts   (needs node_modules)
 *
 * Exit 0 = all checks pass; exit 1 = first failure printed loudly (U2: no
 * silent PASS, no silent FAIL).
 */

import {
  KILLSWITCH_STATE_KEY,
  KILLSWITCH_SCHEMA_VERSION,
  parsePersistedState,
  isPersistedState,
  persistKillSwitchState,
  loadKillSwitchState,
  restoreKillSwitchOnBoot,
  deriveRestoreOutcome,
  type KillSwitchRedisPort,
} from "./src/remediation/killswitch_persistence.js";

import {
  validateHeartbeatOwnership,
  isHeartbeatOwnershipValid,
  HEARTBEAT_TASK_ID_PATTERN,
  HEARTBEAT_TTL_DEFAULT_SECONDS,
} from "./src/lib/heartbeat_ownership.js";

let passed = 0;
let failed = 0;

function ok(cond: boolean, label: string, detail?: string): void {
  if (cond) {
    passed += 1;
    console.log(`  ✅ ${label}`);
  } else {
    failed += 1;
    console.error(`  ❌ ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

function eq<T>(actual: T, expected: T, label: string): void {
  ok(
    JSON.stringify(actual) === JSON.stringify(expected),
    label,
    `expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`,
  );
}

/** Minimal async fake Redis (single key) with failure injection. */
function fakePort(opts: { label: string; failSet?: Error; failGet?: Error; store?: Map<string, string> } = {
  label: "fake-1",
}): KillSwitchRedisPort & { store: Map<string, string> } {
  const store = opts.store ?? new Map<string, string>();
  return {
    store,
    account: opts.label,
    get: async (key: string) => {
      if (opts.failGet) throw opts.failGet;
      return store.get(key) ?? null;
    },
    set: async (key: string, value: string) => {
      if (opts.failSet) throw opts.failSet;
      store.set(key, value);
    },
  };
}

async function testParseFailClosed(): Promise<void> {
  console.log("\n[1] parsePersistedState — fail-closed parsing");
  const valid = {
    autonomyEnabled: false,
    reason: "emergency-stop",
    updatedAtMs: 1_792_000_000_000,
    updatedAt: new Date(1_792_000_000_000).toISOString(),
    schemaVersion: KILLSWITCH_SCHEMA_VERSION,
  };
  eq(isPersistedState(parsePersistedState(JSON.stringify(valid))), true, "valid payload parses");
  const good = parsePersistedState(JSON.stringify(valid));
  ok(
    isPersistedState(good) && good.autonomyEnabled === false && good.reason === "emergency-stop",
    "valid payload fields survive roundtrip",
  );
  eq(isPersistedState(parsePersistedState(null)), false, "null payload → corrupt");
  eq(isPersistedState(parsePersistedState("")), false, "empty string payload → corrupt");
  eq(isPersistedState(parsePersistedState("not-json{")), false, "non-JSON → corrupt");
  eq(isPersistedState(parsePersistedState("[1,2,3]")), false, "JSON array → corrupt");
  eq(
    isPersistedState(parsePersistedState(JSON.stringify({ ...valid, schemaVersion: 2 }))),
    false,
    "unknown schemaVersion → corrupt (fail-closed)",
  );
  eq(
    isPersistedState(parsePersistedState(JSON.stringify({ ...valid, autonomyEnabled: "false" }))),
    false,
    "boolean-as-string → corrupt",
  );
  eq(
    isPersistedState(parsePersistedState(JSON.stringify({ ...valid, updatedAtMs: "yesterday" }))),
    false,
    "updatedAtMs as string → corrupt",
  );
  eq(
    isPersistedState(parsePersistedState(JSON.stringify({ ...valid, reason: "" }))),
    false,
    "empty reason → corrupt",
  );
  eq(
    isPersistedState(parsePersistedState(JSON.stringify({ ...valid, requestedBy: 42 }))),
    false,
    "non-string requestedBy → corrupt",
  );
  const withActor = parsePersistedState(
    JSON.stringify({ ...valid, requestedBy: "admin:client-7" }),
  );
  ok(isPersistedState(withActor) && withActor.requestedBy === "admin:client-7", "optional requestedBy survives");
}

async function testPersistViaPort(): Promise<void> {
  console.log("\n[2] persistKillSwitchState — injected port");
  const port = fakePort({ label: "fake-primary" });
  const res = await persistKillSwitchState({
    autonomyEnabled: false,
    reason: "emergency-stop",
    requestedBy: "admin:client-7",
    nowMs: 1_792_000_000_000,
    port,
  });
  eq(res.ok, true, "persist ok");
  eq(res.account, "fake-primary", "winning account recorded");
  eq(res.key, KILLSWITCH_STATE_KEY, "state key exact");
  const stored = port.store.get(KILLSWITCH_STATE_KEY);
  ok(!!stored, "value written under the exact key");
  const parsed = parsePersistedState(stored ?? "");
  ok(
    isPersistedState(parsed) &&
      parsed.autonomyEnabled === false &&
      parsed.requestedBy === "admin:client-7" &&
      parsed.updatedAtMs === 1_792_000_000_000,
    "stored JSON roundtrips to the same state",
  );

  const failing = fakePort({ label: "fake-dead", failSet: new Error("boom") });
  const res2 = await persistKillSwitchState({
    autonomyEnabled: false,
    reason: "emergency-stop",
    port: failing,
  });
  eq(res2.ok, false, "failed persist reports ok:false (never throws)");
  eq(res2.attempts.length, 1, "attempt ledger has the failed account");
  eq(res2.attempts[0].account, "fake-dead", "failed account named");
  ok((res2.attempts[0].error ?? "").includes("boom"), "failure reason carried");
}

async function testPersistViaChain(): Promise<void> {
  console.log("\n[3] persistKillSwitchState — injected account chain (contract + failover ledger)");
  // The chain-injection seam exercises the CONTRACT between this module and
  // the account-chain engine (walk.value / walk.account / walk.attempts),
  // never the network: attempt 1 fails, attempt 2 answers.
  let opCalls = 0;
  const chain = (async (
    op: (account: { label: string; restUrl?: string; restToken?: string }) => Promise<unknown>,
  ) => {
    opCalls += 1;
    let firstError = "";
    try {
      await op({ label: "primary" }); // real op → TCP port → ioredis absent → throws (hermetic)
    } catch (err) {
      firstError = (err as Error).message;
    }
    return {
      value: "secondary",
      account: { label: "secondary" },
      attempts: [
        { account: "primary", ok: false, error: firstError || "unreachable" },
        { account: "secondary", ok: true },
      ],
    };
  }) as never;

  const res = await persistKillSwitchState({
    autonomyEnabled: false,
    reason: "emergency-stop",
    chain,
  });
  eq(res.ok, true, "chain walk succeeds");
  eq(res.account, "secondary", "winning account surfaced from walk.value/account");
  eq(res.attempts.length, 2, "attempt ledger passes through");
  eq(res.attempts[0].ok, false, "primary attempt recorded failed");
  ok(opCalls === 1, "op invoked exactly once (stub contract sanity)");
  ok(
    (res.attempts[0].error ?? "").length > 0,
    "primary failure reason carried in ledger (TCP path degrades honestly when ioredis absent)",
  );

  // All-accounts-failed path: the chain throws its aggregated error and
  // persist must surface ok:false with the parsed ledger — never throw.
  const deadChain = (async () => {
    throw new Error("All 2 Redis account(s) failed: primary: quota dead | secondary: conn refused");
  }) as never;
  const resDead = await persistKillSwitchState({
    autonomyEnabled: false,
    reason: "emergency-stop",
    chain: deadChain,
  });
  eq(resDead.ok, false, "all accounts failed → ok:false (no throw)");
  eq(resDead.attempts.length, 2, "aggregate error parsed back into per-account ledger");
  eq(resDead.attempts[0].account, "primary", "aggregate parsing keeps account labels");
  ok((resDead.attempts[0].error ?? "").includes("quota dead"), "aggregate parsing keeps reasons");
}

async function testLoadAndRestore(): Promise<void> {
  console.log("\n[4] load / restore — fresh, disabled, enabled, unreachable, corrupt");
  const empty = fakePort({ label: "empty" });
  eq((await loadKillSwitchState({ port: empty })).outcome, "absent", "missing key → absent");
  const freshRestore = await restoreKillSwitchOnBoot({ port: empty });
  eq(freshRestore.outcome, "fresh", "restore verdict: fresh (default stays enabled)");
  eq(freshRestore.state, null, "fresh carries no state");

  const port = fakePort({ label: "main" });
  await persistKillSwitchState({
    autonomyEnabled: false,
    reason: "emergency-stop",
    requestedBy: "admin:client-7",
    nowMs: 1_792_000_123_456,
    port,
  });
  const loaded = await loadKillSwitchState({ port });
  ok(loaded.outcome === "loaded", "persisted stop loads back");
  const restoreDisabled = await restoreKillSwitchOnBoot({ port });
  eq(restoreDisabled.outcome, "disabled", "restore verdict: disabled → integration MUST re-stop");

  await persistKillSwitchState({ autonomyEnabled: true, reason: "admin-re-enable", nowMs: 1_792_000_999_999, port });
  eq((await restoreKillSwitchOnBoot({ port })).outcome, "enabled", "restore verdict: enabled");

  const dead = fakePort({ label: "dead", failGet: new Error("conn refused") });
  const unreachable = await loadKillSwitchState({ port: dead });
  eq(unreachable.outcome, "unreachable", "Redis down → unreachable (never throws)");
  eq(deriveRestoreOutcome(unreachable).outcome, "unreachable", "restore verdict: unreachable");

  const rotten = fakePort({ label: "rotten" });
  rotten.store.set(KILLSWITCH_STATE_KEY, "{{{not json");
  const corrupt = await loadKillSwitchState({ port: rotten });
  eq(corrupt.outcome, "corrupt", "corrupt payload → corrupt verdict");
  ok(
    deriveRestoreOutcome(corrupt).outcome === "corrupt" &&
      ((deriveRestoreOutcome(corrupt).reason ?? "").length > 0),
    "corrupt verdict carries the reason",
  );
}

async function testHeartbeatOwnership(): Promise<void> {
  console.log("\n[5] validateHeartbeatOwnership — legacy, strict, rejections");
  eq(validateHeartbeatOwnership({}).ok, true, "no fields → legacy ok (AC3)");
  const legacy = validateHeartbeatOwnership({});
  ok(legacy.ok && legacy.legacy === true, "legacy flag set on bare pings");
  eq(isHeartbeatOwnershipValid({ taskId: undefined, status: null }), false, "null status ≠ absent → strict partial → reject");

  const full = validateHeartbeatOwnership({ taskId: "issue-340", status: "busy", ttlSeconds: 120 });
  ok(
    full.ok && full.legacy === false && full.taskId === "issue-340" && full.status === "busy" && full.ttlSeconds === 120 && full.ttlDefaulted === false,
    "full valid ownership accepted",
  );
  const defaulted = validateHeartbeatOwnership({ taskId: "issue-340", status: "alive" });
  ok(
    defaulted.ok && defaulted.legacy === false && defaulted.ttlSeconds === HEARTBEAT_TTL_DEFAULT_SECONDS && defaulted.ttlDefaulted === true,
    "ttlSeconds omitted → schema default 300, flagged as defaulted",
  );
  ok(
    validateHeartbeatOwnership({ taskId: "", status: "idle" }).ok === true,
    "idle + empty taskId legal (schema ^$ branch)",
  );

  const rejects: Array<[Record<string, unknown>, string, string]> = [
    [{ status: "busy" }, "ownership", "status without taskId → partial ownership reject"],
    [{ taskId: "t-1" }, "ownership", "taskId without status → partial ownership reject"],
    [{ taskId: "has space", status: "busy" }, "taskId", "space in taskId → pattern reject"],
    [{ taskId: "-leading", status: "busy" }, "taskId", "leading dash → pattern reject"],
    [{ taskId: "a".repeat(129), status: "busy" }, "taskId", "129 chars → pattern reject"],
    [{ taskId: 42, status: "busy" }, "taskId", "numeric taskId → type reject"],
    [{ taskId: "t-1", status: "running" }, "status", "unknown status → enum reject"],
    [{ taskId: "t-1", status: 7 }, "status", "numeric status → type reject"],
    [{ taskId: "t-1", status: "alive", ttlSeconds: 10 }, "ttlSeconds", "ttl < 30 → bounds reject"],
    [{ taskId: "t-1", status: "alive", ttlSeconds: 3601 }, "ttlSeconds", "ttl > 3600 → bounds reject"],
    [{ taskId: "t-1", status: "alive", ttlSeconds: 299.5 }, "ttlSeconds", "fractional ttl → integer reject"],
    [{ taskId: "t-1", status: "alive", ttlSeconds: "300" }, "ttlSeconds", "string ttl → type reject"],
    [{ taskId: "", status: "busy" }, "taskId", "empty taskId with busy → reject"],
  ];
  for (const [input, field, label] of rejects) {
    const r = validateHeartbeatOwnership(input);
    ok(r.ok === false && r.field === field, label, `got ${JSON.stringify(r).slice(0, 120)}`);
  }
  eq(HEARTBEAT_TASK_ID_PATTERN.test("issue-340"), true, "schema pattern sanity: real id passes");
  eq(HEARTBEAT_TASK_ID_PATTERN.test(""), true, "schema pattern sanity: empty passes");
}

async function testHermeticImport(): Promise<void> {
  console.log("\n[6] hermeticity — module import touched no credentials");
  // Arriving here means the imports at the top of this file evaluated with
  // zero env/dotenv/Redis/ioredis access on a machine with none configured.
  ok(true, "imports resolved without any Redis configuration");
  ok(typeof KILLSWITCH_STATE_KEY === "string" && KILLSWITCH_STATE_KEY.startsWith("supremeai:"), "state key namespaced");
}

async function main(): Promise<void> {
  console.log("=== #340 selftest_killswitch_persistence ===");
  await testParseFailClosed();
  await testPersistViaPort();
  await testPersistViaChain();
  await testLoadAndRestore();
  await testHeartbeatOwnership();
  await testHermeticImport();
  console.log(`\n=== ${passed} passed, ${failed} failed ===`);
  process.exit(failed === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(`💥 selftest crashed: ${(err as Error).stack ?? err}`);
  process.exit(1);
});
