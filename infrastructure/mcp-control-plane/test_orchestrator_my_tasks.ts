/**
 * Orchestrator my-tasks poll tests (audit F3, 2026-10-16; drop-in lane).
 *
 * বাংলা: dispatch লিখতো, পড়তো কেউ না — এই suite প্রমাণ করে agent-side poll
 * সঠিকভাবে কাজ করে (filter / ordering / honesty flags / fail-closed)।
 *
 * Run: tsx test_orchestrator_my_tasks.ts   (or: bun test_orchestrator_my_tasks.ts)
 * Pure logic — no Redis/network required (FakeScanStore + injected states).
 * Imports ONLY the hermetic lib module (src/lib/orchestrator_my_tasks.ts) —
 * zero coupling to either mirror (public or private main).
 */
import {
  collectOrchestrateStates,
  DEFAULT_ORCHESTRATE_STATE_PREFIX as ORCHESTRATE_STATE_PREFIX,
  MY_TASKS_DEFAULT_LIMIT,
  myTasksReport,
  orchestratorMyTasks,
  type OrchestrateStateRecord,
  type ScanCapableStore,
} from "./src/lib/orchestrator_my_tasks.js";

let failures = 0;
function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✅ ${name}`);
  } else {
    failures++;
    console.error(`  ❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function state(
  issueRef: string,
  assignedSlot: string | null,
  updatedAt: string,
  role: string | null = "coder",
  attempts = 0,
  log: string[] = [],
): OrchestrateStateRecord {
  return { issueRef, role, assignedSlot, attempts, log, updatedAt };
}

/** Direct store write with the exact JSON shape the registry's writeState produces —
 *  controlled timestamps require bypassing any write-time stamping (session-15 lesson). */
async function putState(store: FakeScanStore, rec: OrchestrateStateRecord): Promise<void> {
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}${rec.issueRef}`, JSON.stringify(rec));
}

/** In-memory store with SCAN (same GET/SET/SCAN semantics as the real adapters). */
class FakeScanStore {
  data = new Map<string, string>();
  scanPartial = false;
  async get(key: string): Promise<string | null> {
    return this.data.get(key) ?? null;
  }
  async setEx(key: string, _ttl: number, value: string): Promise<void> {
    this.data.set(key, value);
  }
  async scan(match: string): Promise<{ keys: string[]; partial: boolean }> {
    const escaped = match.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const re = new RegExp("^" + escaped.replace(/\\\*/g, ".*") + "$");
    const keys = [...this.data.keys()].filter((k) => re.test(k)).sort();
    return { keys, partial: this.scanPartial };
  }
}

/** Store without scan — models a legacy read-only-for-one-key store. */
class NoScanStore {
  async get(_key: string): Promise<string | null> {
    return null;
  }
  async setEx(_key: string, _ttl: number, _value: string): Promise<void> {
    /* noop */
  }
}

const NOW = Date.parse("2026-10-16T12:00:00.000Z");

// ── basic filter: only my assignments ───────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — filter by assignedSlot");
{
  const store = new FakeScanStore();
  await putState(store, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  await putState(store, state("52", "coder-3", "2026-10-16T11:58:00.000Z"));
  await putState(store, state("53", null, "2026-10-16T11:57:00.000Z"));
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check("only my assignment returned", r.tasks.length === 1 && r.tasks[0].issueRef === "51");
  check("scannedStates counts all 3 states (assigned + others)", r.scannedStates === 3);
  check("corruptSkipped 0", r.corruptSkipped === 0);
  check("not truncated, not partial", r.truncated === false && r.partialScan === false);
  check("entry carries slot + role", r.tasks[0].assignedSlot === "coder-2" && r.tasks[0].role === "coder");
}

// ── fallback assignments are real work too ──────────────────────────────────
console.log("\n▶ orchestratorMyTasks — fallback assignment included");
{
  const store = new FakeScanStore();
  await putState(store, state("77", "super-1", "2026-10-16T11:00:00.000Z", "planner"));
  const r = await orchestratorMyTasks({ slot: "super-1", store, nowMs: NOW });
  check("fallback-assigned state visible to the fallback slot", r.tasks.length === 1 && r.tasks[0].issueRef === "77");
}

// ── ordering: newest first, issueRef tiebreak ───────────────────────────────
console.log("\n▶ orchestratorMyTasks — deterministic ordering");
{
  const store = new FakeScanStore();
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}10`, JSON.stringify(state("10", "coder-2", "2026-10-16T10:00:00.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}30`, JSON.stringify(state("30", "coder-2", "2026-10-16T11:00:00.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}20`, JSON.stringify(state("20", "coder-2", "2026-10-16T11:00:00.000Z")));
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check(
    "newest first; tie broken by issueRef ascending",
    JSON.stringify(r.tasks.map((t) => t.issueRef)) === JSON.stringify(["20", "30", "10"]),
    `got ${JSON.stringify(r.tasks.map((t) => t.issueRef))}`,
  );
}

// ── ageSeconds: correct math + honest unknown ───────────────────────────────
console.log("\n▶ orchestratorMyTasks — age accounting");
{
  const store = new FakeScanStore();
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}51`, JSON.stringify(state("51", "coder-2", "2026-10-16T11:59:30.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}99`, JSON.stringify(state("99", "coder-2", "not-a-timestamp")));
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check("ageSeconds computed from updatedAt", r.tasks.find((t) => t.issueRef === "51")?.ageSeconds === 30);
  check("unparseable timestamp → ageSeconds null (honest unknown)", r.tasks.find((t) => t.issueRef === "99")?.ageSeconds === null);
}

// ── honesty: corrupt / vanished / bare-prefix keys ──────────────────────────
console.log("\n▶ collectOrchestrateStates — corrupt records skipped, never fatal");
{
  const store = new FakeScanStore();
  await putState(store, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}bad`, "{not json");
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}gone`, "irrelevant");
  store.data.set(ORCHESTRATE_STATE_PREFIX, "{}"); // bare prefix — no issueRef
  const realGet = store.get.bind(store);
  store.get = async (key: string) => (key === `${ORCHESTRATE_STATE_PREFIX}gone` ? null : realGet(key));
  const c = await collectOrchestrateStates(store);
  check("valid state parsed with issueRef from key", c.states.length === 1 && c.states[0].issueRef === "51");
  check("corrupt + vanished + bare-prefix all counted", c.corrupt === 3, `got ${c.corrupt}`);
  check("keys counts every scanned key", c.keys === 4);
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check("poll survives corrupt store — my task still returned", r.tasks.length === 1 && r.corruptSkipped === 3);
}

// ── truncation cap ──────────────────────────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — honest truncation");
{
  const store = new FakeScanStore();
  for (let i = 0; i < 5; i++) {
    await putState(store, state(`${100 + i}`, "ci-1", `2026-10-16T1${i}:00:00.000Z`));
  }
  const r = await orchestratorMyTasks({ slot: "ci-1", store, nowMs: NOW, limit: 2 });
  check("limit respected", r.tasks.length === 2);
  check("truncated flag true", r.truncated === true);
  check("default limit constant exported", MY_TASKS_DEFAULT_LIMIT === 50);
}

// ── partial scan propagation (U2) ───────────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — partial scan surfaced, never silent");
{
  const store = new FakeScanStore();
  store.scanPartial = true;
  await putState(store, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check("partialScan flag propagates to the result", r.partialScan === true);
}

// ── fail-closed: store without scan must throw, not fake an empty queue ─────
console.log("\n▶ collectOrchestrateStates — no-scan store fails closed");
{
  let threw = "";
  try {
    await collectOrchestrateStates(new NoScanStore() as unknown as ScanCapableStore);
  } catch (err) {
    threw = err instanceof Error ? err.message : String(err);
  }
  check("throws honest scan-unsupported error", threw.includes("does not support scan"));
}

// ── empty store: genuinely empty queue ──────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — empty store");
{
  const store = new FakeScanStore();
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  check("zero tasks, zero scanned, no error", r.tasks.length === 0 && r.scannedStates === 0 && !r.truncated);
}

// ── statePrefix injection (drift-safe SSOT wiring) ──────────────────────────
console.log("\n▶ orchestratorMyTasks — custom statePrefix honored");
{
  const store = new FakeScanStore();
  store.data.set("custom:orch:9", JSON.stringify(state("9", "coder-2", "2026-10-16T11:00:00.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}8`, JSON.stringify(state("8", "coder-2", "2026-10-16T11:00:00.000Z")));
  const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW, statePrefix: "custom:orch:" });
  check("only custom-prefix states scanned", r.scannedStates === 1 && r.tasks[0]?.issueRef === "9");
}

// ── report builder (tool-format layer) ──────────────────────────────────────
console.log("\n▶ myTasksReport — agent-facing formatting");
{
  const emptyResult = await orchestratorMyTasks({ slot: "coder-9", store: new FakeScanStore(), nowMs: NOW });
  const empty = myTasksReport(emptyResult);
  check("empty report is explicit per-slot", empty.includes("no orchestrator tasks assigned to slot coder-9"));
  check("empty report still shows the scan count", empty.includes("scanned 0 orchestrate state(s)"));

  const store = new FakeScanStore();
  await putState(
    store,
    state("51", "coder-2", "2026-10-16T11:59:00.000Z", "coder", 0, [
      "[2026-10-16T11:59:00Z] issues.opened role=coder → assigned (coder-2): online coder slot",
    ]),
  );
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}bad`, "///");
  const result = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
  const report = myTasksReport(result, { maxRetries: 3 });
  check("header lists slot + count", report.includes("orchestrator tasks for slot coder-2: 1"));
  check("numbered entry with issueRef + role + attempts", /1\. issue 51 — role coder, attempts 0\/3,/.test(report));
  check("last audit line surfaced", report.includes("audit: [2026-10-16T11:59:00Z] issues.opened"));
  check("corrupt-skip flag surfaced", report.includes("1 corrupt state(s) skipped"));
  check("scan summary line present", report.includes("scanned 2 orchestrate state(s)"));

  const store2 = new FakeScanStore();
  for (let i = 0; i < 3; i++) {
    await putState(store2, state(`${200 + i}`, "ci-1", `2026-10-16T1${i}:00:00.000Z`));
  }
  const truncatedResult = await orchestratorMyTasks({ slot: "ci-1", store: store2, nowMs: NOW, limit: 2 });
  const truncated = myTasksReport(truncatedResult, { truncatedLimit: 2 });
  check("truncation flag surfaced in report", truncated.includes("truncated to 2"));
}

// ── determinism: identical inputs → identical report bytes ──────────────────
console.log("\n▶ determinism — same store, same slot, byte-identical report");
{
  async function build(): Promise<string> {
    const store = new FakeScanStore();
    await putState(store, state("51", "coder-2", "2026-10-16T11:59:00.000Z", "coder", 1, ["a"]));
    await putState(store, state("52", "coder-2", "2026-10-16T11:58:00.000Z", "reviewer", 0, ["b"]));
    const r = await orchestratorMyTasks({ slot: "coder-2", store, nowMs: NOW });
    return myTasksReport(r, { maxRetries: 3 });
  }
  const [x, y] = [await build(), await build()];
  check("two runs byte-identical", x === y);
}

console.log("\n=============================================");
if (failures === 0) {
  console.log("✅ ALL ORCHESTRATOR MY-TASKS TESTS PASSED");
} else {
  console.error(`❌ ${failures} CHECK(S) FAILED`);
  process.exit(1);
}
