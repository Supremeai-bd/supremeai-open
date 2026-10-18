/**
 * #621 queue isolation (acceptance criterion 1) — public-open partition contract.
 *
 * বাংলা মন্তব্য: bridge.work_queue-এর partition চুক্তি এখন pure function দুটিতে
 * বাঁধা আছে — verified (Path A credential) কলার সম্পূর্ণ কিউ দেখে, কিন্তু
 * unverified fallback সেশন (URL guest / slot-denial) শুধু repo:open ও
 * repo-label-বিহীন অর্ডার দেখে। প্রাইভেট-প্লেন টিকেট (repo:infrastructure,
 * repo:api, repo:monorepo, ...) anonymous ভিউতে লিক করতে পারে না।
 *
 * Pure-function tier: no HTTP, no Redis, no credentials (offline-safe per the
 * #116 env-skip contract).
 *
 * Run: npm run test:queue-scope   (wired into test:unit)
 */
import assert from "node:assert/strict";

import { isPublicQueueItem, queueScopeForContext } from "./src/tools/bridge.tools.js";

let passed = 0;
function check(name: string, fn: () => void): void {
  fn();
  passed++;
  console.log(`  ✓ ${name}`);
}

console.log("── 1. isPublicQueueItem: public-open partition predicate ──");

check("repo:open item is public", () => {
  assert.equal(isPublicQueueItem(["P1-high", "repo:open", "status:unclaimed"]), true);
});

check("item with NO repo:* label at all is public (agent-orchestration style)", () => {
  assert.equal(isPublicQueueItem(["P1-high", "status:unclaimed", "area:agent-orchestration"]), true);
});

check("empty label list is public", () => {
  assert.equal(isPublicQueueItem([]), true);
});

check("undefined/null labels are public (defensive)", () => {
  assert.equal(isPublicQueueItem(undefined), true);
  assert.equal(isPublicQueueItem(null), true);
});

check("private-plane repo:infrastructure is NOT public", () => {
  assert.equal(isPublicQueueItem(["P0-critical", "repo:infrastructure", "area:ci"]), false);
});

check("private-plane repo:api is NOT public", () => {
  assert.equal(isPublicQueueItem(["P0-critical", "repo:api", "area:ci"]), false);
});

check("private-plane repo:monorepo is NOT public", () => {
  assert.equal(isPublicQueueItem(["P1-high", "repo:monorepo", "area:core-engine"]), false);
});

check("repo:open overrides sibling private labels (still public)", () => {
  assert.equal(isPublicQueueItem(["repo:open", "P1-high"]), true);
});

check("non-string entries never crash the predicate", () => {
  assert.equal(isPublicQueueItem([undefined as unknown as string, 42 as unknown as string]), true);
});

console.log("── 2. queueScopeForContext: honest evidence classification ──");

check("verified Path A context (no fallbackReason) sees all-open", () => {
  assert.equal(queueScopeForContext({ role: "agent" } as never), "all-open");
  assert.equal(queueScopeForContext({ authenticated: true } as never), "all-open");
});

check("guest fallback context sees public-open", () => {
  assert.equal(queueScopeForContext({ fallbackReason: "anonymous" } as never), "public-open");
});

check("slot-denial fallback contexts also see public-open (fail-closed)", () => {
  assert.equal(queueScopeForContext({ fallbackReason: "slot-credential-missing" } as never), "public-open");
  assert.equal(queueScopeForContext({ fallbackReason: "slot-credential-mismatch" } as never), "public-open");
});

check("empty-string fallbackReason does NOT classify as fallback (defensive)", () => {
  assert.equal(queueScopeForContext({ fallbackReason: "" } as never), "all-open");
});

check("missing context (internal paths / direct handler calls) sees all-open", () => {
  assert.equal(queueScopeForContext(undefined), "all-open");
  assert.equal(queueScopeForContext(null), "all-open");
});

console.log(`\n✅ test_bridge_queue_scope: ${passed} assertions passed — #621 criterion 1 partition contract pinned`);

// The deployed live defect this suite pins: before the fix, the queue handler
// ignored caller evidence entirely (workOrders = queued for EVERY caller) and
// URL guests carried authenticated:true via the pre-production viewerFallback,
// so private-plane tickets leaked into anonymous views (live-verified on
// main@3e07296: tokenless queue read reported callerAuthenticated:true).
