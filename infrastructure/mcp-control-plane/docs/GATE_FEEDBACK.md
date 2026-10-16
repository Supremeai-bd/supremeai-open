# GATE_FEEDBACK — One-Call Gate Verdicts for bridge.work_order

**Audit finding N3 (P1, docs/COMPLEXITY_REDUCTION_2026-10-16.md, WO #370)** · delivery lane: pure-new-file drop-in (per the WO #390-pattern proven for issue #340 and WO #393 for F3).

---

## 1. Problem

`bridge.work_order` returns an issue's `labels` + `body` but **never its comments** — and gate verdicts (rejection reasons, intake receipts, reviewer questions) are written as issue comments. Consequence: submitters were structurally blind to gate feedback. **Four rejection waves** (the #347-class r1–r4 sequence, root-caused by differential forensics) each required out-of-band board reads to understand *why* a work order died. Finding N3 priced this at the top of the tower lane; the implementing slice for it (#371) was rejected on a separate intake constraint (N10, below), leaving the fix undelivered.

This slice delivers the extraction core and its suite as **new files**, with the two wiring hunks riding as byte-exact operator diffs (§3) — the same hand-off as WO #390 §3 / WO #376 Appendix A / WO #393 §3.

## 2. Design

Two new artifacts, **zero bytes changed on any existing file** (hunks against live control-plane files die on private-mirror drift — the #352-class lesson, r1–r4 all died with `patch does not apply`):

| File | Role |
|---|---|
| `src/tools/gate_feedback.ts` | Pure extraction core: `clipCommentExcerpt` (whitespace-collapse + 600-char clip), `extractGateFeedback` (newest-wins, fail-open), `GateFeedback`/`GateFeedbackField` types. **Zero imports, zero I/O, zero credentials.** Content preserved byte-exact from the twice-intake-reviewed r2 branch (rejected on lane mechanics, not content). |
| `test_gate_feedback.ts` | 34-assert offline suite, imports ONLY the lib. Runs under `tsx` and `bun`. |

Contract highlights (all machine-asserted):

- **Fail-open everywhere** — any malformed input (non-array, non-object entries, non-string bodies, whitespace-only bodies) yields `null`; the additive-optional field can never fail the whole `work_order` read.
- **Newest-wins, order-independent** — the extractor picks by `created_at`, not array position, so `desc` and `asc` fetch orders agree (asserted both ways). Ties / missing timestamps resolve to the FIRST entry — deterministic, matching the desc-ordered fetch the wiring performs.
- **Fail-honest shape tolerance** — the intake's status-comment template is owned by the private-side pipeline and is NOT observable from this lane; classifying comment shapes would be false-classification risk (U2). Instead the newest non-empty public comment is surfaced **verbatim, clipped** — the agent reads the real verdict, not our guess of it.
- **Single-line safety** — excerpts are whitespace-collapsed; raw newlines/tabs never survive (log-safe).
- **Honest absence** — no comments → `commentCount: 0, latest: null`; fetch failure → `fetchFailed: true` (unknown ≠ silent-empty).

## 3. Operator integration diffs (byte-exact, 2 files)

These hunks wire the surface into the live control plane. They are **operator-side by design**: existing control-plane files drift between the public mirror and private main, so integration rides as documentation instead of bridge hunks.

### 3.1 `src/tools/bridge.tools.ts` — add the `gateFeedback` field

**Why a doc hunk, not a whole-file payload:** `bridge.tools.ts` legitimately quotes the scanner's own family name in its pre-existing `SECRET_SCAN_PATTERNS` table (landed via the private sync lane). Submitting the wired file whole trips the intake scanner on a self-referential false positive — finding **N10**. The hunk is 2 anchors; hand-application is the N10-compliant path.

Anchor 1 — import block (after `env` import):

```diff
 import { httpRequest } from "../lib/http.js";
 import { env } from "../lib/env.js";
+import { extractGateFeedback, type GateFeedbackField } from "./gate_feedback.js";
```

Anchor 2 — inside the `bridge.work_order` handler, immediately after `const item = normalizeQueueItem(res.data);` (before the `return {`):

```diff
         const item = normalizeQueueItem(res.data);
+        // N3 (docs/COMPLEXITY_REDUCTION_2026-10-16.md): surface the newest
+        // public status comment so submitters can read gate verdicts directly
+        // (fail-open — additive-optional field; never fails the whole read).
+        let gateFeedback: GateFeedbackField = { commentCount: item.comments, latest: null };
+        if (item.comments > 0) {
+          try {
+            let cres = await httpRequest<unknown>(
+              `https://api.github.com/repos/${repo}/issues/${number}/comments?per_page=20&sort=created&direction=desc`,
+              { headers: await githubHeaders(true), timeoutMs: 15_000 }
+            );
+            if (!cres.ok && (cres.status === 401 || cres.status === 403)) {
+              cres = await httpRequest<unknown>(
+                `https://api.github.com/repos/${repo}/issues/${number}/comments?per_page=20&sort=created&direction=desc`,
+                { headers: await githubHeaders(false), timeoutMs: 15_000 }
+              );
+            }
+            if (cres.ok) {
+              gateFeedback = { commentCount: item.comments, latest: extractGateFeedback(cres.data) };
+            } else {
+              gateFeedback = { commentCount: item.comments, latest: null, fetchFailed: true };
+            }
+          } catch {
+            gateFeedback = { commentCount: item.comments, latest: null, fetchFailed: true };
+          }
+        }
         return {
```

Anchor 3 — the same handler's JSON response body (after `body: clipBody(res.data.body),`):

```diff
             text: JSON.stringify({
               ...item,
               body: clipBody(res.data.body),
+              gateFeedback,
               contract: bridgeGuide().contract,
             }, null, 2),
```

(The parked r2 patch's cosmetic blank-line hunk after `clipBody` is intentionally dropped — whitespace-only, no semantic content.)

Auth fallback note: the double fetch (App token, then retry on 401/403) mirrors the existing `work_order` issue-fetch pattern directly above the anchor; if the private main has moved to a shared helper, the operator may substitute it — the extractor call and payload shape are the contract.

### 3.2 `package.json` — wire the suite into both batteries

Three one-line edits (script values are single long lines; anchors are the tail ends):

1. Append `&& npm run test:gate-feedback` to the **end of the `test:unit` value** (anchor: `... && npm run test:hybrid-repo-access`).
2. Append `&& npm run --silent test:gate-feedback` to the **end of the `test:tower-ci` value** (anchor: `... && npm run --silent test:memory-sidecar`).
3. Add the script entry after `"test:remediation"`:

```diff
     "test:remediation": "tsx scripts/test-runner.ts test_remediation.ts",
+    "test:gate-feedback": "tsx test_gate_feedback.ts",
     "test:wiring-guard": "tsx scripts/test-runner.ts --guard"
```

## 4. Response contract (additive-optional `gateFeedback`)

| Field | Type | Meaning |
|---|---|---|
| `commentCount` | `number` | Mirrors the issue's `comments` count already returned by the item. |
| `latest` | `GateFeedback \| null` | `{ at, excerpt }` — newest non-empty public comment, whitespace-collapsed, 600-char clipped with honest `[clipped N chars]` suffix; `at` = `created_at` (empty string when absent). `null` = no surfacable comment. |
| `fetchFailed` | `boolean` (optional) | Present `true` only when the comments fetch errored — the agent knows *unknown* is not *none*. |

The field is additive-optional: unapplied wiring (or pre-wiring consumers) sees byte-identical responses as today. RBAC, pagination, and the `bridge.work_order` classification surface are unchanged (covered by `test_bridge_onboarding`).

## 5. Post-integration verification

1. `npm run test:gate-feedback` → 34/34 asserts, exit 0.
2. `npm run test:unit` → full battery green including the new tail entry.
3. Call `bridge.work_order` on any WO with ≥1 comment (e.g. a rejected slice) → response carries `gateFeedback.latest.excerpt` with the verdict text; on a 0-comment issue → `latest: null`, `commentCount: 0`.
4. Rate-limit sanity: the fetch fires only when `comments > 0` — 0-comment reads add zero GitHub API calls.

## 6. Non-goals

- **Comment shape classification** — deliberately not attempted (fail-honest; the template is private-side, see §2). If the pipeline later publishes a stable verdict template, a classifier can layer on top of `extractGateFeedback` without breaking it.
- **Threaded replies / review bodies** — issue comments only; PR review threads are a different API surface.
- **Historical backfill** — one call, newest verdict; a `gateFeedback.history` variant is trivial follow-up if asked.
- **N10 scanner fix** — separate slice, separate decision (scanner pattern-awareness vs. table quoting).
