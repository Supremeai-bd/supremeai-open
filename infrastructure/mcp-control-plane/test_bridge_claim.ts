import assert from "node:assert/strict";
import {
  BRIDGE_CLAIM_MARKER,
  BRIDGE_CLAIMED_LABELS,
  buildClaimComment,
  evaluateClaimGate,
  bridgeGuide,
  scanFileForSecrets,
} from "./src/tools/bridge.tools.js";

/**
 * Atomic-claim contract tests for bridge.submit_patch (#430 — Two-Tier
 * Ingress Invariant: no claim -> no branch; no branch -> no push).
 *
 * বাংলা মন্তব্য: যাচাই হয় —
 *   ১. claim gate সব fail-closed পথ ধরে (PR, বন্ধ issue, অন্যের claim, label-only claim)
 *   ২. নিজের taskId-র claim থাকলে idempotent re-submission অনুমোদিত
 *   ৩. claim comment নির্ধারিত চুক্তি-আকৃতি মানে (marker, taskId, branch, contract লাইন)
 *   ৪. comment body secret-scan পরিষ্কার + guards-দের পড়া marker আক্ষরিক স্ট্রিং
 *   ৫. guide lifecycle claim step বহন করে (agents নতুন ক্রম শিখবে)
 */

const TASK = "bridge-20261017-tower-claim-step";
const OTHER = "bridge-20261017-some-other-task";

// ─── ১. fail-closed paths ────────────────────────────────────────────────────
{
  const pr = evaluateClaimGate({ isPullRequest: true, issueState: "open", labels: [], commentBodies: [], taskId: TASK });
  assert.equal(pr.allowed, false, "pull request must never be claimable");
  assert.match(pr.reason, /pull request/);

  const closed = evaluateClaimGate({ isPullRequest: false, issueState: "closed", labels: [], commentBodies: [], taskId: TASK });
  assert.equal(closed.allowed, false, "closed issue must never be claimable");
  assert.match(closed.reason, /not open/);

  const missing = evaluateClaimGate({ isPullRequest: false, labels: [], commentBodies: [], taskId: TASK });
  assert.equal(missing.allowed, false, "unreadable state must fail closed");
  assert.match(missing.reason, /not open/);

  const otherMarker = evaluateClaimGate({
    isPullRequest: false,
    issueState: "open",
    labels: [],
    commentBodies: [`${BRIDGE_CLAIM_MARKER}\nClaimed by ${OTHER}`],
    taskId: TASK,
  });
  assert.equal(otherMarker.allowed, false, "another taskId's claim must collide");
  assert.equal(otherMarker.idempotent, false);
  assert.match(otherMarker.reason, /collision/);

  const labelOnly = evaluateClaimGate({
    isPullRequest: false,
    issueState: "open",
    labels: ["status:claimed"],
    commentBodies: [],
    taskId: TASK,
  });
  assert.equal(labelOnly.allowed, false, "label-only claim must not be double-claimed");
  assert.match(labelOnly.reason, /claim label/);

  const inProgressLabel = evaluateClaimGate({
    isPullRequest: false,
    issueState: "open",
    labels: ["status:in-progress", "P2-medium"],
    commentBodies: [],
    taskId: TASK,
  });
  assert.equal(inProgressLabel.allowed, false, "status:in-progress counts as an active claim");

  // A comment that merely SAYS "claim" without the structured marker is NOT a claim.
  const wordOnly = evaluateClaimGate({
    isPullRequest: false,
    issueState: "open",
    labels: [],
    commentBodies: ["I would like to claim this issue please."],
    taskId: TASK,
  });
  assert.equal(wordOnly.allowed, true, "marker-free prose is not a claim");
  assert.equal(wordOnly.idempotent, false);
}

// ─── ২. idempotent re-submission ────────────────────────────────────────────
{
  const own = evaluateClaimGate({
    isPullRequest: false,
    issueState: "open",
    labels: ["status:claimed"],
    commentBodies: [`${BRIDGE_CLAIM_MARKER}\nClaimed for ${TASK}`],
    taskId: TASK,
  });
  assert.equal(own.allowed, true, "own taskId's existing claim allows safe re-submission");
  assert.equal(own.idempotent, true);

  const fresh = evaluateClaimGate({ isPullRequest: false, issueState: "open", labels: ["P2-medium", "repo:open"], commentBodies: [], taskId: TASK });
  assert.deepEqual(fresh, { allowed: true, reason: "task issue is open and claim-free", idempotent: false });
}

// ─── ৩. claim comment contract shape ────────────────────────────────────────
{
  const stamp = "2026-10-17T12:34:56Z";
  const body = buildClaimComment(404, TASK, `bridge/${TASK}`, "zai-autonomous-contributor (session 30)", stamp);
  assert.ok(body.startsWith(BRIDGE_CLAIM_MARKER), "comment must start with the structured marker");
  assert.ok(body.includes(`\`${TASK}\``), "taskId present");
  assert.ok(body.includes(`bridge/${TASK}`), "branch present");
  assert.ok(body.includes("no claim, no branch"), "contract line present");
  assert.ok(body.includes("#404"), "issue number present");
  assert.ok(body.includes("session 30"), "agent identity present");

  const again = buildClaimComment(404, TASK, `bridge/${TASK}`, "zai-autonomous-contributor (session 30)", stamp);
  assert.equal(body, again, "comment construction is deterministic");

  const anon = buildClaimComment(404, TASK, `bridge/${TASK}`, undefined, stamp);
  assert.ok(anon.includes("zero-credential-mcp-agent"), "anonymous identity degrades to the documented default");

  // Marker registry parity: the exact strings the public guards grep for.
  assert.equal(BRIDGE_CLAIM_MARKER, "<!-- atomic-claim -->");
  assert.deepEqual([...BRIDGE_CLAIMED_LABELS], ["status:claimed", "status:in-progress"]);
}

// ─── ৪. secret hygiene ──────────────────────────────────────────────────────
{
  const stamp = "2026-10-17T12:34:56Z";
  const body = buildClaimComment(404, TASK, `bridge/${TASK}`, "zai-autonomous-contributor (session 30)", stamp);
  assert.equal(scanFileForSecrets(body), null, "claim comment must never trip the secret scan");
  assert.equal(scanFileForSecrets(`${BRIDGE_CLAIM_MARKER}\n- **taskId:** ${TASK}`), null);
}

// ─── ৫. guide lifecycle carries the claim step ──────────────────────────────
{
  const guide = bridgeGuide();
  assert.ok(guide.lifecycle.length >= 6, "lifecycle grew by the claim step");
  assert.ok(
    guide.lifecycle.some((l) => l.includes("claimTaskIssue") && l.includes("atomic-claim")),
    "lifecycle teaches the claimTaskIssue flow"
  );
  assert.ok(guide.contract.diffCaps.maxBytes === 200 * 1024, "contract numbers unchanged");
}

console.log("PASS test_bridge_claim.ts — claim gate fail-closed battery, idempotency, comment contract, hygiene, guide lifecycle");
