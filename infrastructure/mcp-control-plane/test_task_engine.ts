/**
 * #2596 — Task Queue & Lease State Machine contract tests.
 *
 * বাংলা মন্তব্য: লিজ লক, ডুপ্লিকেট ক্লেইম রিজেকশন, হার্টবিট এক্সপায়ার — তিনটিই
 * এই ফাইলে নেটওয়ার্ক ছাড়াই (memory-only) প্রমাণ করা হয়। চালানো:
 *   npx tsx test_task_engine.ts
 */

import assert from "node:assert/strict";
import {
  LEASE_TTL_MS,
  applyGitHubSnapshot,
  claimTask,
  completeTask,
  extractPriorityLabel,
  getTask,
  heartbeatTask,
  isGithubLocked,
  isLeaseExpired,
  listTasks,
  parsePriority,
  rankTasks,
  redisAvailable,
  taskQueueStatus,
  type TaskRecord,
  type GitHubIssueSnapshot,
} from "./src/tasks/task-registry.js";

// ── Env hygiene: memory-only মোড নিশ্চিত (কোনো Redis account নেই) ──────────
for (const key of Object.keys(process.env)) {
  if (key.startsWith("UPSTASH_") || key === "REDIS_URL") delete process.env[key];
}

const T0 = 1_800_000_000_000; // নির্দিষ্ট epoch — determinism
const T1 = T0 + 60_000;
const T_EXPIRED = T0 + LEASE_TTL_MS + 1;

function ghIssue(number: number, labels: string[] = [], title = `task #${number}`): GitHubIssueSnapshot {
  return { number, title, labels, html_url: `https://github.com/x/y/issues/${number}` };
}

// ═══ 1. Priority parsing & ranking ═════════════════════════════════════════
{
  assert.equal(extractPriorityLabel(["P1-high", "area:backend"]), "P1-high");
  assert.equal(extractPriorityLabel(["area:backend"]), null);
  assert.ok(parsePriority(["P0-critical"]) < parsePriority(["P1-high"]));
  assert.ok(parsePriority(["P1-high"]) < parsePriority(["P2-medium"]));
  assert.ok(parsePriority(["P2-medium"]) < parsePriority(["P3-low"]));
  assert.ok(parsePriority(["P3-low"]) < parsePriority([])); // লেবেলহীন সবার নিচে, কিন্তু কিউতে

  const mk = (issue: number, labels: string[]): TaskRecord => ({
    issue,
    title: `t${issue}`,
    priority: labels[0] ?? "unlabeled",
    labels,
    state: "UNCLAIMED",
    updatedAtMs: T0,
    updatedAt: new Date(T0).toISOString(),
  });
  const ranked = rankTasks([mk(300, []), mk(301, ["P2-medium"]), mk(302, ["P0-critical"]), mk(303, ["P2-medium"])]);
  assert.deepEqual(ranked.map((t) => t.issue), [302, 301, 303, 300]); // priority asc, তারপর oldest-first
  console.log("✓ 1. priority parsing + ranking (P0→P3→unlabeled, oldest-first tiebreak)");
}

// ═══ 2. Lease expiry (pure) ════════════════════════════════════════════════
{
  const leased: TaskRecord = {
    issue: 1, title: "x", priority: "P1-high", labels: ["P1-high"], state: "LEASED",
    claimedBy: "agent-1", claimToken: "tok", leaseExpiresAtMs: T0 + LEASE_TTL_MS,
    updatedAtMs: T0, updatedAt: new Date(T0).toISOString(),
  };
  assert.equal(isLeaseExpired(leased, T0 + LEASE_TTL_MS - 1), false);
  assert.equal(isLeaseExpired(leased, T0 + LEASE_TTL_MS), true); // সীমানায় expired
  assert.equal(isLeaseExpired({ ...leased, state: "UNCLAIMED" }, T0 + 10 * LEASE_TTL_MS), false); // লিজ না থাকলে প্রশ্নই নেই
  assert.equal(isLeaseExpired({ ...leased, leaseExpiresAtMs: undefined }, T0), true); // অসঙ্গত রেকর্ড → fail-safe
  console.log("✓ 2. lease expiry boundary (TTL প্রান্তে expired; UNCLAIMED কখনো নয়)");
}

// ═══ 3. GitHub snapshot merge: add + PR-filter + external completion ═══════
{
  const r1 = applyGitHubSnapshot(
    [ghIssue(101, ["P1-high"]), ghIssue(102, ["P2-medium"]), { number: 103, title: "pr entry", pull_request: {} } as GitHubIssueSnapshot],
    T0,
  );
  assert.equal(r1.added, 2); // PR এন্ট্রি (#103) কিউতে ঢুকবে না
  assert.equal(r1.updated, 0);
  assert.equal(getTask(103), undefined);

  // আপডেট: টাইটেল/লেবেল বদলালো, লিজ-স্টেট অক্ষুণ্ণ; #102 এই স্ন্যাপশটে নেই → external completion
  const claim = claimTask({ issue: 101, slot: "agent-1" }, T0);
  assert.equal(claim.ok, true);
  const r2 = applyGitHubSnapshot([ghIssue(101, ["P0-critical"], "retitled")], T1);
  assert.equal(r2.updated, 1);
  assert.equal(r2.externallyCompleted, 1); // #102 স্ন্যাপশট থেকে বিদায় → external-complete
  const after = getTask(101);
  assert.equal(after?.title, "retitled");
  assert.equal(after?.labels[0], "P0-critical");
  assert.equal(after?.state, "LEASED"); // লিজ GitHub-এর রিফ্রেশে হারায় না

  // #102-এর external-completion চিহ্ন যাচাই (উপরের r2-তেই ঘটেছে)
  const r3 = applyGitHubSnapshot([ghIssue(101, ["P0-critical"], "retitled")], T1 + 1);
  assert.equal(r3.externallyCompleted, 0); // ইতিমধ্যে COMPLETED — আর গণনা হবে না
  assert.equal(getTask(102)?.state, "COMPLETED");
  assert.equal(getTask(102)?.completionKind, "external");
  console.log("✓ 3. GitHub sync merge (add/refresh; PR-filter; external-complete)");
}

// ═══ 4. Claim: race-safety, duplicate rejection, github-lock, idempotency ═══
{
  applyGitHubSnapshot([ghIssue(110, ["P1-high"]), ghIssue(111, ["P2-medium", "status:in-progress"])], T0);

  // এজেন্ট-১ প্রথমে পেল
  const c1 = claimTask({ issue: 110, slot: "agent-1", agent: "coder-1" }, T0);
  assert.equal(c1.ok, true);
  if (c1.ok) {
    assert.equal(c1.task.state, "LEASED");
    assert.match(c1.claimToken, /^[0-9a-f-]{36}$/); // UUID লিজ-টোকেন
    assert.equal(c1.leaseExpiresAtMs, T0 + LEASE_TTL_MS);
    assert.equal(c1.idempotentReclaim, false);
  }

  // এজেন্ট-২ পরে একই টাস্ক চাইলো → lease-held 409
  const c2 = claimTask({ issue: 110, slot: "agent-2" }, T0 + 1000);
  assert.equal(c2.ok, false);
  if (!c2.ok) {
    assert.equal(c2.reason, "lease-held");
    assert.equal(c2.heldBy?.slot, "agent-1");
  }

  // একই slot আবার ক্লেইম → idempotent, একই টোকেন
  const c3 = claimTask({ issue: 110, slot: "agent-1" }, T0 + 2000);
  assert.equal(c3.ok, true);
  if (c3.ok && c1.ok) {
    assert.equal(c3.claimToken, c1.claimToken);
    assert.equal(c3.idempotentReclaim, true);
  }

  // legacy GitHub-লেবেল লক (status:in-progress) → টাওয়ার-লিজ নিষিদ্ধ
  assert.equal(isGithubLocked(getTask(111) as TaskRecord), true);
  const c4 = claimTask({ issue: 111, slot: "agent-2" }, T0);
  assert.equal(c4.ok, false);
  if (!c4.ok) assert.equal(c4.reason, "github-locked");

  // অবৈধ slot ফরম্যাট → rejected
  const c5 = claimTask({ issue: 110, slot: "not-a-slot" }, T0);
  assert.equal(c5.ok, false);

  // কিউতে নেই এমন ইস্যু → 404
  const c6 = claimTask({ issue: 999, slot: "agent-1" }, T0);
  assert.equal(c6.ok, false);
  if (!c6.ok) assert.equal(c6.reason, "not-found");
  console.log("✓ 4. atomic claim (duplicate 409; same-slot idempotent; github-lock; validation)");
}

// ═══ 5. হার্টবিট এক্সপায়ার → ghost reclaim; stale টোকেন মৃত ═══════════════
{
  applyGitHubSnapshot([ghIssue(120, ["P1-high"])], T0);
  const c1 = claimTask({ issue: 120, slot: "agent-1" }, T0);
  assert.equal(c1.ok, true);
  const oldToken = c1.ok ? c1.claimToken : "";

  // হার্টবিট রিনিউ — টোকেন সঠিক
  const hb1 = heartbeatTask({ issue: 120, slot: "agent-1", claimToken: oldToken }, T0 + 5 * 60_000);
  assert.equal(hb1.ok, true);
  if (hb1.ok) assert.equal(hb1.leaseExpiresAtMs, T0 + 5 * 60_000 + LEASE_TTL_MS);

  // ভুল টোকেন → 409
  const hb2 = heartbeatTask({ issue: 120, slot: "agent-1", claimToken: "forged" }, T0 + 6 * 60_000);
  assert.equal(hb2.ok, false);
  if (!hb2.ok) assert.equal(hb2.reason, "token-mismatch");

  // ভুল slot → 409
  const hb3 = heartbeatTask({ issue: 120, slot: "agent-2", claimToken: oldToken }, T0 + 6 * 60_000);
  assert.equal(hb3.ok, false);
  if (!hb3.ok) assert.equal(hb3.reason, "slot-mismatch");

  // ⏰ হার্টবিট-রিনিউ ধরে হিসাব: hb1 (T0+5min) পরে লিজের নতুন মেয়াদ
  // T0+5min+TTL — তার পরেও আর কোনো হার্টবিট নেই → লিজ অটো-রিলিজ।
  const T_DEAD = T0 + 5 * 60_000 + LEASE_TTL_MS + 1;
  const c2 = claimTask({ issue: 120, slot: "agent-2" }, T_DEAD);
  assert.equal(c2.ok, true);
  assert.equal(getTask(120)?.claimedBy, "agent-2");

  // পুরনো এজেন্টের টোকেন এখন অচল — complete করতে গেলে প্রত্যাখ্যাত
  const done1 = completeTask({ issue: 120, slot: "agent-1", claimToken: oldToken }, T_DEAD + 1);
  assert.equal(done1.ok, false);
  if (!done1.ok) assert.equal(done1.reason, "slot-mismatch");

  // নতুন মালিক ঠিকঠাক সম্পন্ন করতে পারে (knowledge transaction সহ)
  const newToken = c2.ok ? c2.claimToken : "";
  const done2 = completeTask(
    {
      issue: 120, slot: "agent-2", claimToken: newToken,
      knowledge: { why: "ghost-state নির্মূল প্রমাণিত", alternatives_rejected: ["GitHub-label-only lock"] },
    },
    T_DEAD + 2,
  );
  assert.equal(done2.ok, true);
  const finished = getTask(120);
  assert.equal(finished?.state, "COMPLETED");
  assert.equal(finished?.completionKind, "local");
  assert.equal(finished?.knowledge?.why, "ghost-state নির্মূল প্রমাণিত");
  assert.deepEqual(finished?.knowledge?.alternatives_rejected, ["GitHub-label-only lock"]);
  console.log("✓ 5. heartbeat TTL + ghost reclaim + stale-token death + complete transaction");
}

// ═══ 6. Complete: already-completed rejection ══════════════════════════════
{
  applyGitHubSnapshot([ghIssue(130, ["P3-low"])], T0);
  const c = claimTask({ issue: 130, slot: "agent-3" }, T0);
  assert.equal(c.ok, true);
  const tok = c.ok ? c.claimToken : "";
  assert.equal(completeTask({ issue: 130, slot: "agent-3", claimToken: tok }, T1).ok, true);
  const again = completeTask({ issue: 130, slot: "agent-3", claimToken: tok }, T1 + 1);
  assert.equal(again.ok, false);
  if (!again.ok) assert.equal(again.reason, "already-completed");
  const claimCompleted = claimTask({ issue: 130, slot: "agent-4" }, T1 + 2);
  assert.equal(claimCompleted.ok, false);
  if (!claimCompleted.ok) assert.equal(claimCompleted.reason, "completed");
  console.log("✓ 6. completion finality (double-complete 410; completed পুনরায় claim নয়)");
}

// ═══ 7. Queue status + memory-only graceful degradation ════════════════════
{
  assert.equal(redisAvailable(), false); // env মুছে ফেলা হয়েছে — memory-only
  const status = taskQueueStatus(T_EXPIRED);
  assert.equal(status.memoryOnly, true);
  assert.equal(status.leaseTtlMs, LEASE_TTL_MS);
  assert.ok(status.total >= 3); // উপরের সিনারিওগুলোর রেকর্ড কিউতে আছে
  const listed = listTasks();
  assert.ok(listed.length >= 3);
  // সব লিস্টেড রেকর্ডে claimToken রাখা হয়নি এমন নিশ্চয়তা নেই (মডিউল স্তরে) —
  // HTTP স্তরে স্ট্রিপ হয়; এখানে শুধু অবস্থা-গণনা যাচাই।
  console.log(`✓ 7. queue status (total=${status.total}, leased=${status.leased}, completed=${status.completed}) + memory-only mode`);
}

console.log("\nTask engine contract tests passed — লিজ লক, ডুপ্লিকেট ক্লেইম রিজেকশন, হার্টবিট এক্সপায়ার সবই প্রমাণিত (#2596)");
