/**
 * Orchestrator dispatch routing tests (issue #1803).
 *
 * Run: tsx test_orchestrator_dispatch.ts
 * Pure decision logic — no Redis/network required (FakeStore + injected slots).
 */
import {
  decideRoute,
  LEGACY_SLOT_ROLES,
  MAX_RETRIES,
  ORCHESTRATE_STATE_PREFIX,
  readState,
  roleForEvent,
  roleFromSlot,
  ROLE_EVENT_MAP,
  writeState,
  type DispatchState,
} from "./src/registry/orchestrator_dispatch.js";
import type { HeartbeatStatusEntry } from "./src/registry/agent_heartbeat.js";

let failures = 0;
function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✅ ${name}`);
  } else {
    failures++;
    console.error(`  ❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

function slot(name: string, state: "online" | "stale" | "expired", ageSeconds = 30): HeartbeatStatusEntry {
  return {
    slot: name,
    agentId: name,
    source: "mcp-tower",
    updatedAtMs: Date.now() - ageSeconds * 1000,
    updatedAt: new Date().toISOString(),
    ageSeconds,
    state,
  };
}

// ── roleFromSlot ────────────────────────────────────────────────────────────
console.log("\n▶ roleFromSlot (registry-driven, no hardcoded vendor identity)");
check("pool prefix coder-5 → coder", roleFromSlot("coder-5") === "coder");
check("pool prefix ci-2 → ci", roleFromSlot("ci-2") === "ci");
check("pool prefix pr-helper-1 → pr-helper", roleFromSlot("pr-helper-1") === "pr-helper");
check("legacy agent-3 → coder", roleFromSlot("agent-3") === "coder");
check("legacy agent-5 → ci", roleFromSlot("agent-5") === "ci");
check("legacy agent-10 → super fallback via pool prefix? (no) → null or override", roleFromSlot("agent-10") === null);
check("override table wins", roleFromSlot("agent-10", { super: ["agent-10"] }) === "super");
check("unknown slot → null", roleFromSlot("mystery-9") === null);

// ── roleForEvent (deterministic map) ────────────────────────────────────────
console.log("\n▶ roleForEvent (deterministic event → lane map)");
check("issues.opened → planner", roleForEvent("issues", "opened") === "planner");
check("pull_request.opened → pr-helper", roleForEvent("pull_request", "opened") === "pr-helper");
check("workflow_run.failure → ci", roleForEvent("workflow_run", "failure") === "ci");
check("handoff label overrides map", roleForEvent("issues", "labeled", "handoff:coder") === "coder");
check("unknown combo → null", roleForEvent("issues", "closed") === null);

// ── decideRoute (offline skip / fallback / retry / escalate) ────────────────
console.log("\n▶ decideRoute — heartbeat-based selection");
const onlineCoder = [slot("coder-2", "online", 30), slot("agent-10", "stale", 600)];
const assigned = decideRoute({ role: "coder", onlineSlots: onlineCoder, attempts: 0 });
check("online coder selected", assigned.decision === "assigned" && assigned.assignedSlot === "coder-2");
check("reason documents age", assigned.reason.includes("age 30s"));

console.log("\n▶ decideRoute — offline agent skipped");
const staleOnly = [slot("coder-1", "stale", 400), slot("coder-3", "expired", 9000)];
const skip = decideRoute({ role: "coder", onlineSlots: staleOnly, attempts: 0 });
check("stale/expired skipped → no-candidate (retry budget left)", skip.decision === "no-candidate");

console.log("\n▶ decideRoute — SupremeAI fallback (#1439 rule 2)");
const superOnline = [slot("coder-1", "stale", 400), slot("super-1", "online", 20)];
const fallback = decideRoute({ role: "coder", onlineSlots: superOnline, attempts: 0 });
check("no online coder → super lane fallback", fallback.decision === "fallback" && fallback.assignedSlot === "super-1");

console.log("\n▶ decideRoute — max retry 3 + human escalation (#1439 rule 3)");
const escalated = decideRoute({ role: "coder", onlineSlots: [], attempts: MAX_RETRIES });
check("attempts>=3 → escalate", escalated.decision === "escalate");
const atLimit = decideRoute({ role: "coder", onlineSlots: [], attempts: MAX_RETRIES - 1 });
check("attempts<3 → still retrying", atLimit.decision === "no-candidate");

// ── state store contract (FakeStore — same GET/SET semantics) ───────────────
console.log("\n▶ dispatch state (supremeai:orchestrate:<issue>)");
class FakeStore {
  data = new Map<string, string>();
  async get(key: string): Promise<string | null> {
    return this.data.get(key) ?? null;
  }
  async setEx(key: string, _ttl: number, value: string): Promise<void> {
    this.data.set(key, value);
  }
}
const store = new FakeStore();
const empty = await readState(store as never, "123");
check("fresh state attempts=0", empty.attempts === 0);
const state: DispatchState = { ...empty, attempts: 1, assignedSlot: "coder-2", role: "coder", log: ["x"] };
await writeState(store as never, state);
check("state key uses orchestrate prefix", store.data.has(`${ORCHESTRATE_STATE_PREFIX}123`));
const reloaded = await readState(store as never, "123");
check("state round-trips", reloaded.attempts === 1 && reloaded.assignedSlot === "coder-2");

// ── constants ───────────────────────────────────────────────────────────────
console.log("\n▶ constants");
check("ROLE_EVENT_MAP has 3 phase-C events", Object.keys(ROLE_EVENT_MAP).length === 3);
check("legacy table mirrors governance YAML (spot check)", LEGACY_SLOT_ROLES["agent-2"] === "pr-helper" && LEGACY_SLOT_ROLES["agent-5"] === "ci");

console.log(`\n${failures === 0 ? "✅ ALL CHECKS PASSED" : `❌ ${failures} FAILURES`}`);
process.exit(failures === 0 ? 0 : 1);
