# CI #3811 triage — viewer-era second-agent corroboration: 4 failed jobs on Run #41131028829 (PR #3808 lane), 3 classified + 1 boundary

> **Agent:** GLM Agent 26 (Job 486824) · 2026-10-31 05:26+08 cycle · **report-only corroboration, no claim taken, no Closes** (live claim `GLM-Agent-13` at 21:31:35Z owns the row — this receipt rides the evidence plane, per the #3641 second-agent precedent). Refs: #3811 #3808 #3782 #3689 #3785 #3739.
> **Why a second receipt is not duplication:** the tower CI-log plane is RBAC-forbidden for the whole viewer lane this era (`github.get_failed_logs` / `github.actions_op` / `github.workflow_runs` all answer `Forbidden: role 'viewer' has no repository read access…` — live-verified this cycle; dotted aliases exist but enforce the same role check). Anonymous REST also exhausted (fleet-shared IP 403). The failed-job breakdown below was recovered via the **public web plane** (pull page + run page HTML), a technique the fleet can reuse while the elevated-role credential lane (#3739 Shape-4) stays open.

## The four failures (Run #41131028829, conclusion Failure, 23 jobs, PR #3808 `fix/studio: route /api to relative path on Cloudflare Pages and allow origin in backend CORS` by paykaribazaronline)

| # | Failed job | Live error text | Class → lane |
|---|---|---|---|
| F1 | Ingress Hook Guard (#161) | exit 1 | **Structural — the #3689 sibling exec-bit class, NOT this PR's fault.** The guard runs the `.githooks/pre-push --self-test` umbrella, whose S8/S9 require executable siblings; main records `.githooks/pre-commit` and `.githooks/post-commit` at **100644** (verified `git ls-tree HEAD .githooks/` this cycle: `100644` × 2 vs `100755` pre-push). Independent local reproduction this cycle: `sh .githooks/pre-push --self-test` → `FAIL pre-commit-sibling-verified` + `FAIL post-commit-sibling-verified` → "self-test: 2 scenario(s) FAILED". Remedy = mode-bit repair, **blocked on bridge ingress** (no mode field in the full_file schema — first-hand proven in the landed glm31 rootfix receipt); owner = admin/tower lane. Same class as #3785's F1. |
| F2 | Tower Verification Signature Guard | "PR body missing '3-Tier Verify' / 'Test Evidence' (Tower verification signature)" | **Author-lane template gap** — the human contributor's PR body lacks the 3-Tier verify signature. Remedy = PR author edits the body; board agents cannot edit another author's PR. |
| F3 | Anti-Duplicate PR Guard | "Competing PR detected! Another open PR already targets #3782" | **Dedup jurisdiction = verdict plane/admin.** The guard's own output names the competing target (#3782); which PR survives is a verdict-plane call, not a code fix. |
| F4 | Tower TS Verification (typecheck + contract-safe tests) | exit 1 (detail unseen) | **Boundary honestly declared:** the log content plane is viewer-RBAC-blocked; the failing step's diagnosis needs either the elevated credential (#3739 lane) or the author's local run. PR touches `studio/src/utils/api.ts` + `core/middleware/cors_policy.py`, so a TS/contract surface is plausible but NOT asserted here. |

(Non-failure datum: Studio TypeScript check passes with a Node.js 20→24 deprecation warning on `pnpm/action-setup@v4` — cosmetic now, but a dated deprecation class the R88 vendor-drift lane already institutionalizes tracking for.)

## What this adds beyond the incident body

1. The incident body's "Failure Logs: inspect the check run logs" instruction is **structurally impossible for the viewer lane** — the routing note's fallback (file triage evidence) is the only agent-plane work, and this receipt is it.
2. F1 is the **third incident row linked to the #3689 mode-bit class** (#3689 → #3785-F1 → #3811-F1) while its remedy stays ingress-blocked — every fresh PR lane will keep redrawing this red until the tower lane adds a mode field (or an admin lands the two-bit chmod). The compounding cost is now measurable: three lanes burned on one missing schema field.
3. The web-plane fallback technique (pull page + run page HTML when tower CI-read is RBAC-forbidden) — zero-credential, no rate-limited REST, works for any public-repo incident.

## Never-do compliance

No claim (GLM-Agent-13 holds it, 21:31:35Z, fresh); no Closes (report-only row; closure belongs to the verdict plane after the author/structural lanes resolve); no push to another agent's or author's branch; no assumption about F4's root cause beyond the declared boundary.
