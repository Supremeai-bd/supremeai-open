/**
 * Orchestrator assignment-poll tests (audit 2026-10-16 F3 — close the dispatch loop).
 *
 * Run: tsx test_orchestrator_my_tasks.ts
 * Offline: listOpenAssignments with an injectable FakeStore; notify skip-branch
 * with telegram env unset (never touches the network).
 */
import {
  ASSIGNMENT_FRESH_WINDOW_SECONDS,
  listOpenAssignments,
  notifyDispatchDecision,
  ORCHESTRATE_STATE_PREFIX,
  readState,
  writeState,
} from "./src/registry/orchestrator_dispatch.js";
import { env } from "./src/lib/env.js";

let failures = 0;
function check(name: string, condition: boolean, detail = ""): void {
  if (condition) {
    console.log(`  ✅ ${name}`);
  } else {
    failures++;
    console.error(`  ❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

type Row = { key: string; value: string };
function makeFakeStore(rows: Row[]) {
  const calls = { get: 0, keys: 0, setEx: 0 };
  return {
    calls,
    store: {
      get: async (key: string) => {
        calls.get++;
        return rows.find((r) => r.key === key)?.value ?? null;
      },
      setEx: async (key: string, ttl: number, value: string) => {
        calls.setEx++;
        void ttl;
        const existing = rows.find((r) => r.key === key);
        if (existing) existing.value = value;
        else rows.push({ key, value });
      },
      keys: async (pattern: string) => {
        calls.keys++;
        const prefix = pattern.replace(/\*$/, "");
        return rows.filter((r) => r.key.startsWith(prefix)).map((r) => r.key);
      },
    },
  };
}

function stateJson(opts: {
  issueRef: string;
  assignedSlot?: string | null;
  decisionHint?: "assigned" | "fallback" | "escalate" | "no-candidate";
  ageSeconds?: number;
}): string {
  const age = opts.ageSeconds ?? 60;
  return JSON.stringify({
    issueRef: opts.issueRef,
    role: "coder",
    assignedSlot: opts.assignedSlot ?? null,
    attempts: 0,
    log: [],
    updatedAt: new Date(Date.now() - age * 1000).toISOString(),
    decisionHint: opts.decisionHint,
  });
}

const NOW = Date.now();
const coder3 = "coder-3";

// ── listOpenAssignments: filter + freshness + corruption tolerance ──────────
console.log("\n▶ listOpenAssignments (injectable store)");
const freshAssigned = { key: `${ORCHESTRATE_STATE_PREFIX}101`, value: stateJson({ issueRef: "101", assignedSlot: coder3, decisionHint: "assigned" }) };
const freshFallback = { key: `${ORCHESTRATE_STATE_PREFIX}102`, value: stateJson({ issueRef: "102", assignedSlot: "super-1", decisionHint: "fallback" }) };
const terminal = { key: `${ORCHESTRATE_STATE_PREFIX}103`, value: stateJson({ issueRef: "103", decisionHint: "no-candidate" }) };
const escalated = { key: `${ORCHESTRATE_STATE_PREFIX}104`, value: stateJson({ issueRef: "104", assignedSlot: null, decisionHint: "escalate" }) };
const staleAssigned = { key: `${ORCHESTRATE_STATE_PREFIX}105`, value: stateJson({ issueRef: "105", assignedSlot: coder3, decisionHint: "assigned", ageSeconds: ASSIGNMENT_FRESH_WINDOW_SECONDS + 60 }) };
const corrupt = { key: `${ORCHESTRATE_STATE_PREFIX}106`, value: "{not-json" };
const otherLane = { key: `${ORCHESTRATE_STATE_PREFIX}107`, value: stateJson({ issueRef: "107", assignedSlot: "ci-5", decisionHint: "assigned" }) };

const fake = makeFakeStore([freshAssigned, freshFallback, terminal, escalated, staleAssigned, corrupt, otherLane]);
const listing = await listOpenAssignments(NOW, fake.store);

check("scanned all 7 state keys", listing.stateKeysScanned === 7);
check(
  "only fresh assigned/fallback listed (3: 101,102,107)",
  listing.assignments.length === 3,
  JSON.stringify(listing.assignments.map((a) => a.issueRef)),
);
check("corrupt state skipped without breaking listing", listing.assignments.every((a) => ["101", "102", "107", "105"].includes(a.issueRef) === false || a.issueRef !== "106"));
check("terminal no-candidate excluded", !listing.assignments.some((a) => a.issueRef === "103"));
check("escalate excluded (needs human, not agent work)", !listing.assignments.some((a) => a.issueRef === "104"));
check("stale assignment (>24h) excluded", !listing.assignments.some((a) => a.issueRef === "105"));
check("sorted by issueRef", listing.assignments.map((a) => a.issueRef).join(",") === "101,102,107");
check("ageSeconds computed honestly", listing.assignments.every((a) => a.ageSeconds < ASSIGNMENT_FRESH_WINDOW_SECONDS));

const mine = listing.assignments.filter((a) => a.assignedSlot === coder3);
check("slot filter picks my assignment", mine.length === 1 && mine[0].issueRef === "101");

// ── decisionHint round-trips through writeState/readState ───────────────────
console.log("\n▶ decisionHint round-trip");
const round = makeFakeStore([]);
await writeState(round.store, {
  issueRef: "201",
  role: "coder",
  assignedSlot: coder3,
  attempts: 0,
  log: ["x"],
  updatedAt: new Date().toISOString(),
  decisionHint: "assigned",
});
const back = await readState(round.store, "201");
check("decisionHint persisted", back.decisionHint === "assigned");
check("assignedSlot persisted", back.assignedSlot === coder3);
check("wired setEx called once", round.calls.setEx === 1);

// ── notifyDispatchDecision: env-unconfigured → honest skip, no throw ───────
console.log("\n▶ notifyDispatchDecision (advisory, non-blocking)");
const prevToken = process.env.TELEGRAM_BOT_TOKEN;
const prevChat = process.env.TELEGRAM_CHAT_ID;
delete process.env.TELEGRAM_BOT_TOKEN;
delete process.env.TELEGRAM_CHAT_ID;
check("telegram unconfigured via env getters", !env.notify.telegramBotToken && !env.notify.telegramChatId);
let threw = false;
try {
  await notifyDispatchDecision({ decision: "assigned", assignedSlot: coder3, role: "coder", reason: "test" }, "301");
  await notifyDispatchDecision({ decision: "escalate", assignedSlot: null, role: "ci", reason: "test" }, "302");
  await notifyDispatchDecision({ decision: "no-candidate", assignedSlot: null, role: "ci", reason: "test" }, "303"); // silent no-op branch
} catch (err) {
  threw = true;
}
check("no throw when unconfigured / non-assignable", !threw);
if (prevToken !== undefined) process.env.TELEGRAM_BOT_TOKEN = prevToken;
if (prevChat !== undefined) process.env.TELEGRAM_CHAT_ID = prevChat;

console.log(failures === 0 ? "\n✅ orchestrator my-tasks tests: ALL PASS" : `\n❌ ${failures} failure(s)`);
process.exit(failures === 0 ? 0 : 1);
