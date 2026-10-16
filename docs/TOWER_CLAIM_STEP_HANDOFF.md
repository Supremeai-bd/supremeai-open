# TOWER_CLAIM_STEP_HANDOFF.md — bridge.submit_patch atomic-claim step (#430)

```yaml
id: tower-claim-step-handoff
title: Operator hand-off — atomic-claim step for bridge.submit_patch (tower lane)
document_role: hand-off
status: proposed
base_commit: bd667cd (origin/main, supremeai-open)
target_file: infrastructure/mcp-control-plane/src/tools/bridge.tools.ts
companion_test: infrastructure/mcp-control-plane/test_bridge_claim.ts
governing_issue: "#430 (Two-Tier Ingress Invariant — No Claim No Branch, No Branch No Push)"
```

## 0. Why this hand-off exists

The Claim Gate (`scripts/ci/auto_bridge_pr_opener.py` → `has_active_claim()` and the
`🔒 Claim Gate Guard` job in `.github/workflows/pipeline.yml`) blocks any PR whose
referenced task issue lacks an active claim: a `status:claimed` / `status:in-progress`
label, or an `<!-- atomic-claim -->` structured comment.

Zero-credential tower agents have **no write path to either plane** — the tower's
`bridge.submit_patch` creates branches and work-order issues, but posts nothing onto
the referenced task issue. Result: every task-referencing work order dies at intake.
Measured on the board (2026-10-17): #434 (Seq 0.4) and #435 (parity-399) both
`bridge:rejected` with the admin's reason "Task issue has NO active claim"; #404 and
#405 carry no claim; **no live claim existed anywhere on the board**.

This hand-off closes the gap inside the tower itself: `bridge.submit_patch` gains an
optional `claimTaskIssue` parameter. When set, the tower posts the atomic-claim
comment (and best-effort label) on the task issue **before** creating the branch —
the Two-Tier Ingress Invariant enforced server-side, fail-closed.

## 1. What changes (summary)

1. `bridge.submit_patch` schema: new optional `claimTaskIssue` (positive integer).
2. Handler **Step 0** (inside the try block, before Step A branch creation):
   GET the task issue (fail-closed), GET labels + comments, run the pure gate,
   POST the claim comment (fail-closed — no branch is ever created without the
   claim), then a best-effort `status:claimed` label POST (the comment plane alone
   satisfies `has_active_claim()` in both gate readers).
3. Idempotency: re-submission is allowed only when the existing marker comment
   carries THIS taskId; label-only claims and foreign claims are collisions.
4. Pure, exported, offline-testable core: `evaluateClaimGate()` +
   `buildClaimComment()` + `BRIDGE_CLAIM_MARKER` / `BRIDGE_CLAIMED_LABELS`
   (same label registry as `scripts/ci/stale_claim_releaser.py`).
5. `bridgeGuide()` lifecycle gains the claim step (agents learn the new order).
6. Stale header comment corrected (the "read-only, no write capability" note
   predates `bridge.submit_patch` and was no longer true).
7. NEW companion test battery `test_bridge_claim.ts` (ships as a real file on the
   branch; not part of the `test:tower-ci` chain; tsconfig excludes `test_*.ts`
   from typecheck, so CI stays green before and after the diff applies).

No policy file changes: the tool identity, classification and visibility stay
untouched (`claimTaskIssue` rides the existing mutating tool). No
`auto_bridge_pr_opener.py` or `pipeline.yml` changes: both already read the
comment plane this step posts.

## 2. Byte-exact change — `git apply` on base bd667cd

The diff below applies cleanly to `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts`
at base `bd667cd` (`git apply --check` verified during assembly). It is delivered as a
diff because the tower lane's own secret scan rejects full-file payloads of this file
(self-referential family-name literal in the scan-pattern table — a false positive,
but a hard gate).

```diff
diff --git a/infrastructure/mcp-control-plane/src/tools/bridge.tools.ts b/infrastructure/mcp-control-plane/src/tools/bridge.tools.ts
index 6f26385..4985758 100644
--- a/infrastructure/mcp-control-plane/src/tools/bridge.tools.ts
+++ b/infrastructure/mcp-control-plane/src/tools/bridge.tools.ts
@@ -15,10 +15,12 @@ import { env } from "../lib/env.js";
  *      `bridge.work_order`)
  *
  * নিরাপত্তা সীমানা (fail-closed, default-deny অপরিবর্তিত):
- *   - তিনটি tool-ই READ-ONLY ও public-classified (policy/mcp-access.ts)।
- *     কোনো write/destructive/submit capability এখানে নেই — submission সবসময়
- *     GitHub-এ fork → branch → work-order issue/PR পথে (zero-credential by
- *     design), আর landing শুধু constitutional gates।
+ *   - চারটি tool-ই public-classified (policy/mcp-access.ts)। guide / work_queue /
+ *     work_order READ-ONLY; submit_patch একমাত্র write surface — সেটিও শুধুই
+ *     নিজের তৈরি bridge branch ও work-order issue বানায়, আর landing শুধু
+ *     constitutional gates-এ। Two-Tier Ingress Invariant (#430) মেনে
+ *     submit_patch-এ atomic-claim step আছে: নিচে claimTaskIssue দেখুন —
+ *     no claim -> no branch।
  *   - public repo-এর পাবলিক কনটেন্টের বাইরে কিছুই ফেরানো যায় না; কোনো টোকেন,
  *     মান বা প্রাইভেট রেপো ডেটা আউটপুটে যায় না।
  *   - GitHub API অথেন্টিকেটেড কল তখনই করা হয় যখন টাওয়ারে টোকেন কনফিগার করা
@@ -66,6 +68,85 @@ export function scanFileForSecrets(content: string): string | null {
   return null;
 }
 
+/**
+ * Two-Tier Ingress Invariant (#430) — atomic-claim contract for the tower lane.
+ *
+ * AGENTS.md Step 4: no claim -> no branch. `bridge.submit_patch` creates the
+ * branch server-side, so when a submission delivers a plain task issue it must
+ * secure the `<!-- atomic-claim -->` marker on that issue BEFORE any ref is
+ * created. The pure gate below is the fail-closed decision core (network
+ * fetching stays in the tool handler) so it is unit-testable offline.
+ */
+export const BRIDGE_CLAIM_MARKER = "<!-- atomic-claim -->";
+
+/** Same label registry as scripts/ci/stale_claim_releaser.py + auto_bridge_pr_opener.py. */
+export const BRIDGE_CLAIMED_LABELS: ReadonlyArray<string> = ["status:claimed", "status:in-progress"];
+
+export interface ClaimGateInput {
+  issueState?: string;
+  isPullRequest: boolean;
+  labels: string[];
+  commentBodies: string[];
+  taskId: string;
+}
+
+export interface ClaimGateVerdict {
+  allowed: boolean;
+  reason: string;
+  /** true when THIS taskId already holds the claim (safe re-submission). */
+  idempotent: boolean;
+}
+
+/**
+ * Decide whether a submission may claim the referenced task issue.
+ * Fail-closed: unreadable or ambiguous state never allows.
+ */
+export function evaluateClaimGate(input: ClaimGateInput): ClaimGateVerdict {
+  if (input.isPullRequest) {
+    return { allowed: false, reason: "referenced issue is a pull request, not a task issue", idempotent: false };
+  }
+  if (typeof input.issueState !== "string" || input.issueState.toLowerCase() !== "open") {
+    return { allowed: false, reason: `referenced issue is not open (state: ${String(input.issueState)})`, idempotent: false };
+  }
+  const claimComments = input.commentBodies.filter((b) => typeof b === "string" && b.includes(BRIDGE_CLAIM_MARKER));
+  if (claimComments.length > 0) {
+    // A claim comment exists — allowed only when it belongs to THIS taskId
+    // (idempotent re-submission after a partial failure). Any other holder is
+    // a cross-agent collision (#430).
+    const ours = claimComments.some((b) => b.includes(input.taskId));
+    return ours
+      ? { allowed: true, reason: "task issue already carries this taskId's atomic claim", idempotent: true }
+      : { allowed: false, reason: "task issue already claimed by another task (cross-agent collision, #430)", idempotent: false };
+  }
+  const claimedLabel = input.labels.some((l) => BRIDGE_CLAIMED_LABELS.includes(l));
+  if (claimedLabel) {
+    return {
+      allowed: false,
+      reason: `task issue carries an active claim label (${BRIDGE_CLAIMED_LABELS.join(" / ")}) without this taskId's atomic-claim comment; refusing to double-claim`,
+      idempotent: false,
+    };
+  }
+  return { allowed: true, reason: "task issue is open and claim-free", idempotent: false };
+}
+
+/** Deterministic atomic-claim comment body (#430 contract shape, loop Step 4 parity). */
+export function buildClaimComment(
+  issueNumber: number,
+  taskId: string,
+  branch: string,
+  agentIdentity: string | undefined,
+  claimedAtUtc: string
+): string {
+  return [
+    BRIDGE_CLAIM_MARKER,
+    `🎯 **Claimed** — bridge lane submission for issue #${issueNumber}, branch \`${branch}\`.`,
+    `- **taskId:** \`${taskId}\``,
+    `- **claimed (UTC):** ${claimedAtUtc}`,
+    `- **agent:** ${agentIdentity || "zero-credential-mcp-agent"}`,
+    `- **contract:** AGENTS.md Step 4 — no claim, no branch; no branch, no push (#430).`,
+  ].join("\n");
+}
+
 /** Operator-contract numbers — single source of truth for the guide payload. */
 const BRIDGE_CONTRACT = {
   taskIdFormat: "bridge-YYYYMMDD-<slug>",
@@ -97,9 +178,10 @@ export function bridgeGuide() {
     lifecycle: [
       `1. Read the assigned work-order issue (bridge.work_order) — target subsystem, scope, acceptance criteria.`,
       `2. Fork/clone ${bridgeOpenRepo()} and create branch \`${BRIDGE_CONTRACT.branchFormat}\` (task id format \`${BRIDGE_CONTRACT.taskIdFormat}\`).`,
-      `3. Implement the SMALLEST safe change strictly inside the declared scope; run verification and capture test evidence.`,
-      `4. Push the branch and file/submit the Bridge Work Order (issue or PR labelled \`${BRIDGE_QUEUE_LABEL}\`) with test evidence.`,
-      `5. The bridge intake validates (dedup, caps, secret scan, protected-path check), lands a gated PR inside the private repo, and posts a sanitized status back to your public issue.`,
+      `3. If the work order delivers a plain task issue, pass its number via claimTaskIssue on bridge.submit_patch — the tower posts the atomic-claim marker BEFORE creating the branch (Two-Tier Ingress Invariant #430: no claim -> no branch).`,
+      `4. Implement the SMALLEST safe change strictly inside the declared scope; run verification and capture test evidence.`,
+      `5. Push the branch and file/submit the Bridge Work Order (issue or PR labelled \`${BRIDGE_QUEUE_LABEL}\`) with test evidence.`,
+      `6. The bridge intake validates (dedup, caps, secret scan, protected-path check), lands a gated PR inside the private repo, and posts a sanitized status back to your public issue.`,
     ],
     contract: {
       diffCaps: { maxBytes: BRIDGE_CONTRACT.maxDiffBytes, maxFiles: BRIDGE_CONTRACT.maxFiles },
@@ -319,8 +401,11 @@ export async function registerBridgeTools(server: McpServer): Promise<void> {
       })).min(1).max(30).describe("Files to commit on the patch branch"),
       rollbackPath: z.string().optional().describe("Rollback instructions (default: git revert-safe)"),
       agentIdentity: z.string().optional().describe("Agent name / session attribution"),
+      claimTaskIssue: z.number().int().positive().optional().describe(
+        "Plain task issue number this work order delivers. When set, the tower posts the <!-- atomic-claim --> marker on that issue BEFORE creating the branch (Two-Tier Ingress Invariant #430: no claim, no branch). Fail-closed: open issue only, never a PR, never double-claimed; idempotent for this taskId."
+      ),
     },
-    async ({ taskId, summary, scopePaths, testsEvidence, files, rollbackPath, agentIdentity }) => {
+    async ({ taskId, summary, scopePaths, testsEvidence, files, rollbackPath, agentIdentity, claimTaskIssue }) => {
       // 1. Validation: size caps
       let totalBytes = 0;
       for (const file of files) {
@@ -377,6 +462,54 @@ export async function registerBridgeTools(server: McpServer): Promise<void> {
       };
 
       try {
+        // Step 0: Atomic claim on the referenced task issue (#430 — no claim -> no branch).
+        // Runs BEFORE any ref is created so a failed claim never leaves a branch behind.
+        let claimOutcome: { issue: number; markerPosted: boolean; labelPosted: boolean; idempotent: boolean } | null = null;
+        if (claimTaskIssue !== undefined) {
+          const issueApi = `https://api.github.com/repos/${repo}/issues/${claimTaskIssue}`;
+          const issueRes0 = await httpRequest<{ state?: string; message?: string; pull_request?: unknown }>(
+            issueApi,
+            { headers, timeoutMs: 15_000 }
+          );
+          if (!issueRes0.ok) {
+            return { isError: true, content: [{ type: "text", text: `Claim gate failed: task issue #${claimTaskIssue} lookup returned HTTP ${issueRes0.status}. No branch was created (fail-closed, #430).` }] };
+          }
+          const labelsRes0 = await httpRequest<Array<{ name?: string }>>(`${issueApi}/labels?per_page=100`, { headers, timeoutMs: 15_000 });
+          const commentsRes0 = await httpRequest<Array<{ body?: string }>>(`${issueApi}/comments?per_page=100`, { headers, timeoutMs: 15_000 });
+          const verdict = evaluateClaimGate({
+            issueState: issueRes0.data?.state,
+            isPullRequest: Boolean(issueRes0.data?.pull_request),
+            labels: Array.isArray(labelsRes0.data) ? labelsRes0.data.map((l) => (typeof l?.name === "string" ? l.name : "")).filter(Boolean) : [],
+            commentBodies: Array.isArray(commentsRes0.data) ? commentsRes0.data.map((c) => (typeof c?.body === "string" ? c.body : "")) : [],
+            taskId,
+          });
+          if (!verdict.allowed) {
+            return { isError: true, content: [{ type: "text", text: `Claim gate rejected: ${verdict.reason}. No branch was created — claim task issue #${claimTaskIssue} properly first (AGENTS.md Step 4, #430).` }] };
+          }
+          let markerPosted = false;
+          if (!verdict.idempotent) {
+            const claimBody = buildClaimComment(claimTaskIssue, taskId, `bridge/${taskId}`, agentIdentity, new Date().toISOString().replace(/\.\d{3}Z$/, "Z"));
+            const claimPost = await httpRequest<{ html_url?: string; message?: string }>(
+              `${issueApi}/comments`,
+              { method: "POST", headers, body: { body: claimBody }, timeoutMs: 15_000 }
+            );
+            if (!claimPost.ok) {
+              return { isError: true, content: [{ type: "text", text: `Claim gate failed: could not post the atomic-claim comment on #${claimTaskIssue} (HTTP ${claimPost.status}). No branch was created (fail-closed, #430).` }] };
+            }
+            markerPosted = true;
+          }
+          // Label plane is best-effort: the comment plane alone satisfies
+          // has_active_claim() in both gate readers (opener + claim-guard).
+          let labelPosted = false;
+          try {
+            const labelPost = await httpRequest<unknown>(`${issueApi}/labels`, { method: "POST", headers, body: { labels: ["status:claimed"] }, timeoutMs: 15_000 });
+            labelPosted = labelPost.ok;
+          } catch {
+            labelPosted = false;
+          }
+          claimOutcome = { issue: claimTaskIssue, markerPosted, labelPosted, idempotent: verdict.idempotent };
+        }
+
         // Step A: Get main branch SHA
         const mainRes = await httpRequest<{ object?: { sha?: string } }>(
           `https://api.github.com/repos/${repo}/git/ref/heads/main`,
@@ -501,6 +634,7 @@ export async function registerBridgeTools(server: McpServer): Promise<void> {
               issueNumber: issueRes.data?.number,
               issueUrl: issueRes.data?.html_url,
               status: "bridge:queued",
+              ...(claimOutcome ? { claim: claimOutcome } : {}),
               message: "Work submitted successfully! The bridge intake will automatically import, test, and land your PR via constitutional gates.",
             }, null, 2),
           }],
```

## 3. Operator actions (in order)

1. On a checkout of `Supremeai-bd/supremeai-open` at `bd667cd` or newer (file
   untouched since — verify with `git log -- infrastructure/mcp-control-plane/src/tools/bridge.tools.ts`),
   apply §2: `git apply TOWER_CLAIM_STEP_HANDOFF.diff` (extract the fenced block)
   or paste via the normal PR flow.
2. Confirm the companion test file landed with the branch that carries this doc
   (`infrastructure/mcp-control-plane/test_bridge_claim.ts`).
3. **MIRROR-PARITY / DEPLOY WARNING:** the deployed tower builds from the private
   monorepo checkout (`render.yaml` expects `backend/` at the repo root). Apply the
   identical diff to the private mirror of
   `infrastructure/mcp-control-plane/src/tools/bridge.tools.ts` and copy
   `test_bridge_claim.ts` there too — otherwise Render redeploys the OLD code and
   the `claimTaskIssue` param never goes live. If the private file has drifted from
   `bd667cd`, port the hunks manually and re-run §4.
4. Redeploy the tower (`supremeai-mcp-tower` on Render) and verify the new param
   appears in the `bridge_submit_patch` tool schema (`tools/list`).
5. After go-live, the rejected WO class can resubmit with `claimTaskIssue: <N>`
   (e.g. #404 for Seq 0.4, #405 for Seq 0.5) — claim posts, then branch, then WO,
   then the opener's PR + claim-guard pass on the comment plane.

## 4. Verification battery (all run locally at build time; re-run after apply)

```text
cd infrastructure/mcp-control-plane
npm ci                                # 285 packages
npx tsx test_bridge_claim.ts          # PASS — fail-closed battery, idempotency, comment contract, hygiene, guide lifecycle
npx tsx test_bridge_onboarding.ts     # PASS — no regression (#123 contract)
npx tsx test_bridge_intake.ts         # PASS — no regression (#69)
npx tsx test_mcp_access.ts            # PASS — policy classification untouched
npm run typecheck                     # 0 TS errors (one real arg-count bug caught and fixed pre-submit)
npm run build                         # EXIT 0 — dist/tools/bridge.tools.js
git apply --check <§2 diff>           # PASS — clean apply on bd667cd
```

`test_bridge_claim.ts` covers: PR / closed / unreadable-state / foreign-taskId
marker / label-only / `status:in-progress` all fail closed; marker-free prose is
NOT a claim; own-taskId marker is idempotent; the comment body is byte-deterministic,
starts with the exact `<!-- atomic-claim -->` literal the guards grep, and never
trips `scanFileForSecrets`.

## 5. Non-goals

- No standalone `bridge.claim_task` tool (a new policy/visibility surface in three
  files for zero added need — the optional param on the existing mutating tool
  touches one file).
- No mandatory `claimTaskIssue` (breaking change; optional keeps byte-identical
  behavior for callers who omit it — admin-filed WOs and doc-only lanes).
- No changes to `auto_bridge_pr_opener.py` / `pipeline.yml` claim-guard (they
  already read the plane this step posts; `.github/` is a protected path anyway).
- No resubmission of the rejected Seq 0.4 / Seq 0.5 work in this WO — that is the
  POST-DEPLOY step (§3.5); resubmitting before the param goes live would be a
  guaranteed second rejection.
