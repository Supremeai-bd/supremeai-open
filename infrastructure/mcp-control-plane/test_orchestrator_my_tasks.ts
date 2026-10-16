/**
 * Orchestrator my-tasks poll tests (audit F3, 2026-10-16).
 *
 * বাংলা: dispatch লিখতো, পড়তো কেউ না — এই suite প্রমাণ করে agent-side poll
 * সঠিকভাবে কাজ করে (filter / ordering / honesty flags / fail-closed)।
 *
 * Run: tsx test_orchestrator_my_tasks.ts
 * Pure logic — no Redis/network required (FakeScanStore + injected states).
 */
import {
  collectOrchestrateStates,
  MY_TASKS_DEFAULT_LIMIT,
  ORCHESTRATE_STATE_PREFIX,
  orchestratorMyTasks,
  writeState,
  type DispatchState,
  type DispatchStore,
} from "./src/registry/orchestrator_dispatch.js";
import { myTasksReport } from "./src/tools/orchestrator.tools.js";

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
): DispatchState {
  return { issueRef, role, assignedSlot, attempts, log, updatedAt };
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
  await writeState(store as unknown as DispatchStore, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  await writeState(store as unknown as DispatchStore, state("52", "coder-3", "2026-10-16T11:58:00.000Z"));
  await writeState(store as unknown as DispatchStore, state("53", null, "2026-10-16T11:57:00.000Z"));
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
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
  await writeState(store as unknown as DispatchStore, state("77", "super-1", "2026-10-16T11:00:00.000Z", "planner"));
  const r = await orchestratorMyTasks({ slot: "super-1", store: store as unknown as DispatchStore, nowMs: NOW });
  check("fallback-assigned state visible to the fallback slot", r.tasks.length === 1 && r.tasks[0].issueRef === "77");
}

// ── ordering: newest first, issueRef tiebreak ───────────────────────────────
console.log("\n▶ orchestratorMyTasks — deterministic ordering");
{
  const store = new FakeScanStore();
  // NOTE: writeState stamps updatedAt at write time — controlled timestamps
  // must be written directly to the store (same JSON shape writeState produces).
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}10`, JSON.stringify(state("10", "coder-2", "2026-10-16T10:00:00.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}30`, JSON.stringify(state("30", "coder-2", "2026-10-16T11:00:00.000Z")));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}20`, JSON.stringify(state("20", "coder-2", "2026-10-16T11:00:00.000Z")));
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
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
  const raw = JSON.stringify(state("99", "coder-2", "not-a-timestamp"));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}99`, raw);
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
  check("ageSeconds computed from updatedAt", r.tasks.find((t) => t.issueRef === "51")?.ageSeconds === 30);
  check("unparseable timestamp → ageSeconds null (honest unknown)", r.tasks.find((t) => t.issueRef === "99")?.ageSeconds === null);
}

// ── honesty: corrupt / vanished / bare-prefix keys ──────────────────────────
console.log("\n▶ collectOrchestrateStates — corrupt records skipped, never fatal");
{
  const store = new FakeScanStore();
  await writeState(store as unknown as DispatchStore, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}bad`, "{not json");
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}gone`, "irrelevant");
  store.data.set(ORCHESTRATE_STATE_PREFIX, "{}"); // bare prefix — no issueRef
  const realGet = store.get.bind(store);
  store.get = async (key: string) => (key === `${ORCHESTRATE_STATE_PREFIX}gone` ? null : realGet(key));
  const c = await collectOrchestrateStates(store as unknown as DispatchStore);
  check("valid state parsed with issueRef from key", c.states.length === 1 && c.states[0].issueRef === "51");
  check("corrupt + vanished + bare-prefix all counted", c.corrupt === 3, `got ${c.corrupt}`);
  check("keys counts every scanned key", c.keys === 4);
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
  check("poll survives corrupt store — my task still returned", r.tasks.length === 1 && r.corruptSkipped === 3);
}

// ── truncation cap ──────────────────────────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — honest truncation");
{
  const store = new FakeScanStore();
  for (let i = 0; i < 5; i++) {
    await writeState(store as unknown as DispatchStore, state(`${100 + i}`, "ci-1", `2026-10-16T1${i}:00:00.000Z`));
  }
  const r = await orchestratorMyTasks({ slot: "ci-1", store: store as unknown as DispatchStore, nowMs: NOW, limit: 2 });
  check("limit respected", r.tasks.length === 2);
  check("truncated flag true", r.truncated === true);
  check("default limit constant exported", MY_TASKS_DEFAULT_LIMIT === 50);
}

// ── partial scan propagation (U2) ───────────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — partial scan surfaced, never silent");
{
  const store = new FakeScanStore();
  store.scanPartial = true;
  await writeState(store as unknown as DispatchStore, state("51", "coder-2", "2026-10-16T11:59:00.000Z"));
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
  check("partialScan flag propagates to the result", r.partialScan === true);
}

// ── fail-closed: store without scan must throw, not fake an empty queue ─────
console.log("\n▶ collectOrchestrateStates — no-scan store fails closed");
{
  let threw = "";
  try {
    await collectOrchestrateStates(new NoScanStore() as unknown as DispatchStore);
  } catch (err) {
    threw = err instanceof Error ? err.message : String(err);
  }
  check("throws honest scan-unsupported error", threw.includes("does not support scan"));
}

// ── empty store: genuinely empty queue ──────────────────────────────────────
console.log("\n▶ orchestratorMyTasks — empty store");
{
  const store = new FakeScanStore();
  const r = await orchestratorMyTasks({ slot: "coder-2", store: store as unknown as DispatchStore, nowMs: NOW });
  check("zero tasks, zero scanned, no error", r.tasks.length === 0 && r.scannedStates === 0 && !r.truncated);
}

// ── report builder (tool-format layer) ──────────────────────────────────────
console.log("\n▶ myTasksReport — agent-facing formatting");
{
  const empty = await myTasksReport("coder-9", new FakeScanStore() as unknown as DispatchStore);
  check("empty report is explicit per-slot", empty.includes("no orchestrator tasks assigned to slot coder-9"));
  check("empty report still shows the scan count", empty.includes("scanned 0 orchestrate state(s)"));

  const store = new FakeScanStore();
  await writeState(
    store as unknown as DispatchStore,
    state("51", "coder-2", "2026-10-16T11:59:00.000Z", "coder", 0, ["[2026-10-16T11:59:00Z] issues.opened role=coder → assigned (coder-2): online coder slot"]),
  );
  store.data.set(`${ORCHESTRATE_STATE_PREFIX}bad`, "///");
  const report = await myTasksReport("coder-2", store as unknown as DispatchStore);
  check("header lists slot + count", report.includes("orchestrator tasks for slot coder-2: 1"));
  check("numbered entry with issueRef + role + attempts", /1\. issue 51 — role coder, attempts 0\/3,/.test(report));
  check("last audit line surfaced", report.includes("audit: [2026-10-16T11:59:00Z] issues.opened"));
  check("corrupt-skip flag surfaced", report.includes("1 corrupt state(s) skipped"));
  check("scan summary line present", report.includes("scanned 2 orchestrate state(s)"));

  const store2 = new FakeScanStore();
  for (let i = 0; i < 3; i++) {
    await writeState(store2 as unknown as DispatchStore, state(`${200 + i}`, "ci-1", `2026-10-16T1${i}:00:00.000Z`));
  }
  const truncated = await myTasksReport("ci-1", store2 as unknown as DispatchStore, { limit: 2 });
  check("truncation flag surfaced in report", truncated.includes("truncated to"));
}

console.log("\n=============================================");
if (failures === 0) {
  console.log("✅ ALL ORCHESTRATOR MY-TASKS TESTS PASSED");
} else {
  console.error(`❌ ${failures} CHECK(S) FAILED`);
  process.exit(1);
}
