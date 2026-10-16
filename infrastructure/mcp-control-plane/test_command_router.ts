/**
 * Offline-safe tests for the Command Router (#211 slice 1).
 *
 * বাংলা নোট: কোনো network বা env দরকার নেই — fetch inject করা হয়, তাই এটা
 * clean-env safe (#98 শ্রেণির test-wiring নিয়ম মেনে test:unit-এ যুক্ত)।
 *
 * Covers:
 *  - parseSlashCommand: canonical commands, args, non-commands, junk
 *  - extractLinkedIssues: body keywords (#N + owner/repo#N), branch-name
 *    linkage (contributor/issue-N, bridge-*-issue-N, task-N), dedup + cap
 *  - runLifecycleCleanup: closes issues (200), reconciles already-closed
 *    (404/422), deletes head branch (204), reconciles already-gone (404),
 *    PROTECTED branch guard, tokenless fail-honest degradation, non-merged
 *    payload no-op, runaway cap
 */

import {
  parseSlashCommand,
  registerCommand,
  getRegisteredCommands,
  extractLinkedIssues,
  runLifecycleCleanup,
  registerCommandRouter,
  MAX_LIFECYCLE_ISSUES_PER_EVENT,
  SlashCommand,
} from "./src/events/command_router.js";

let pass = 0;
let fail = 0;
function check(name: string, cond: boolean, detail = ""): void {
  if (cond) {
    pass++;
    console.log(`✅ ${name}${detail ? ` — ${detail}` : ""}`);
  } else {
    fail++;
    console.log(`❌ ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

// ── 1. parseSlashCommand ────────────────────────────────────────────────────
const c1 = parseSlashCommand("/claim");
check("parse /claim", !!c1 && c1.name === "claim" && c1.args.length === 0);
const c2 = parseSlashCommand("  /role coder  ");
check("parse /role coder with args+whitespace", !!c2 && c2.name === "role" && c2.args.join(",") === "coder");
const c3 = parseSlashCommand("this is just a normal comment");
check("non-command returns null", c3 === null);
const c4 = parseSlashCommand("");
check("empty body returns null", c4 === null);
const c5 = parseSlashCommand("/VERIFY");
check("command names case-normalized", !!c5 && c5.name === "verify");

// ── 2. extractLinkedIssues ──────────────────────────────────────────────────
const pr1 = {
  merged: true,
  body: "fixes #12, Closes #34 and resolves OtherOrg/other-repo#56\nalso closes #12 again",
  head: { ref: "contributor/issue-78", repo: { full_name: "Supremeai-bd/supremeai-open" } },
};
const linked1 = extractLinkedIssues(pr1);
const nums1 = linked1.map((l) => `${l.repo || ""}#${l.number}`).sort();
check(
  "extract: keywords + cross-repo + branch linkage, deduped",
  JSON.stringify(nums1) === JSON.stringify(["#12", "#34", "#78", "OtherOrg/other-repo#56"].sort()),
  nums1.join(", "),
);
const linked2 = extractLinkedIssues({
  merged: true,
  body: "no keywords here, refs only: Refs #99",
  head: { ref: "bridge-20261016-issue-77-pr-body", repo: null },
});
check("extract: Refs-only ignored, bridge-*-issue-N linked", linked2.length === 1 && linked2[0].number === 77);
const linked3 = extractLinkedIssues({
  merged: true,
  body: Array.from({ length: 30 }, (_, i) => `Closes #${i + 1}`).join(", "),
  head: { ref: "task-31", repo: null },
});
check("extract: capped at MAX_LIFECYCLE_ISSUES_PER_EVENT", linked3.length === MAX_LIFECYCLE_ISSUES_PER_EVENT);

// ── 3. runLifecycleCleanup (injectable fetch, offline) ─────────────────────
function fakeFetch(responses: Map<string, { status: number }>, calls: string[]) {
  return (async (url: string, init?: Record<string, unknown>) => {
    calls.push(`${init?.method ?? "GET"} ${url}`);
    const key = `${init?.method ?? "GET"} ${url}`;
    return responses.get(key) ?? { status: 404, ok: false };
  }) as never;
}

const callsA: string[] = [];
const resA = await runLifecycleCleanup(
  {
    repository: { full_name: "Supremeai-bd/supremeai-open" },
    pull_request: {
      merged: true,
      number: 300,
      body: "Closes #321",
      head: { ref: "contributor/issue-321", repo: { full_name: "Supremeai-bd/supremeai-open" } },
      base: { ref: "main" },
    },
  },
  {
    token: "test-token-offline",
    log: () => {},
    fetchImpl: fakeFetch(
      new Map([
        ["PATCH https://api.github.com/repos/Supremeai-bd/supremeai-open/issues/321", { status: 200 }],
        ["DELETE https://api.github.com/repos/Supremeai-bd/supremeai-open/git/refs/heads/contributor%2Fissue-321", { status: 204 }],
      ]),
      callsA,
    ),
  },
);
check(
  "cleanup: closes issue + deletes head branch",
  resA.issuesClosed.join(",") === "321" && resA.branchDeleted === "contributor/issue-321" && resA.skipped.length === 0,
  JSON.stringify(resA),
);
check("cleanup: PATCH then DELETE issued", callsA.length === 2 && callsA[0].startsWith("PATCH") && callsA[1].startsWith("DELETE"));

const resB = await runLifecycleCleanup(
  {
    repository: { full_name: "Supremeai-bd/supremeai-open" },
    pull_request: {
      merged: true,
      body: "Closes #400",
      head: { ref: "feat/thing", repo: { full_name: "Supremeai-bd/supremeai-open" } },
      base: { ref: "main" },
    },
  },
  {
    token: "test-token-offline",
    log: () => {},
    fetchImpl: fakeFetch(new Map(), []), // everything 404 → already reconciled
  },
);
check(
  "cleanup: 404 → already-closed / already-gone reconciled idempotently",
  resB.issuesAlreadyClosed.join(",") === "400" && resB.branchAlreadyGone && resB.issuesClosed.length === 0,
  JSON.stringify(resB),
);

const resC = await runLifecycleCleanup(
  {
    repository: { full_name: "Supremeai-bd/supremeai-open" },
    pull_request: {
      merged: true,
      body: "Closes #500",
      head: { ref: "main", repo: { full_name: "Supremeai-bd/supremeai-open" } },
      base: { ref: "main" },
    },
  },
  { token: "t", log: () => {}, fetchImpl: fakeFetch(new Map([["PATCH https://api.github.com/repos/Supremeai-bd/supremeai-open/issues/500", { status: 200 }]]), []) },
);
check(
  "cleanup: head branch main is PROTECTED from deletion",
  resC.branchDeleted === null && !resC.branchAlreadyGone && resC.issuesClosed.join(",") === "500",
  JSON.stringify(resC),
);

const resD = await runLifecycleCleanup(
  {
    repository: { full_name: "Supremeai-bd/supremeai-open" },
    pull_request: { merged: true, body: "Closes #600", head: { ref: "feat/x" } },
  },
  { token: "", log: () => {}, fetchImpl: fakeFetch(new Map(), []) },
);
check(
  "cleanup: tokenless boot degrades fail-honest (no throw, skipped recorded)",
  resD.skipped.length === 1 && resD.skipped[0].includes("GITHUB_TOKEN absent") && resD.issuesClosed.length === 0,
);

const resE = await runLifecycleCleanup(
  { repository: { full_name: "r" }, pull_request: { merged: false, body: "Closes #1" } },
  { token: "t", log: () => {}, fetchImpl: fakeFetch(new Map(), []) },
);
check("cleanup: non-merged payload is a no-op", resE.skipped[0].includes("not a merged"));

// ── 4. router registration + command dispatch (stub gateway) ───────────────
const seen: string[] = [];
const stubGateway = {
  subscribe(listener: (event: any) => void | Promise<void>): void {
    (stubGateway as any).listener = listener;
  },
};
registerCommandRouter(stubGateway as never);
check("router subscribes exactly once", typeof (stubGateway as any).listener === "function");

registerCommand("claim", (cmd: SlashCommand) => {
  seen.push(`claim:${cmd.name}`);
});
const dispatchedEvent = {
  source: "github",
  type: "issue_comment",
  severity: "INFO" as const,
  message: "comment",
  payload: { action: "created", comment: { body: "/claim" } },
  timestamp: new Date().toISOString(),
};
await ((stubGateway as any).listener)(dispatchedEvent);
check("router dispatches /claim to registered handler", seen.join(",") === "claim:claim");

await ((stubGateway as any).listener)({
  ...dispatchedEvent,
  payload: { action: "created", comment: { body: "/not-a-thing" } },
});
check("router logs unmatched command without throwing", seen.join(",") === "claim:claim");

await ((stubGateway as any).listener)({
  ...dispatchedEvent,
  type: "push",
  payload: { ref: "refs/heads/main" },
});
check("router ignores non-comment events for command dispatch", seen.join(",") === "claim:claim");

console.log(`\nRESULT: ${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
