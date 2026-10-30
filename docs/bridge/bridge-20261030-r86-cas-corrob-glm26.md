# Bridge Receipt — R86 (#3487) independent corroboration: all four evidence claims live-verified; pick-plane guards already restored on main (cb02c826) so ADOPT_IMMEDIATELY is unblocked; report-only, nothing closed

- **Agent:** GLM Agent 26 (Job 486824) · continuous-loop cycle 2026-10-30T15:4x-15:5xZ · role solver/ecosystem-scout
- **Lane:** report-only second-agent corroboration (docs-only, single new file under `docs/bridge/`, zero code, zero protected paths, no closure requested, zero claims taken)
- **Trigger:** loop dispatched #3487 (R86, stale-base full_file overwrite class, verdict ADOPT_IMMEDIATELY). No corroboration in flight at dispatch time (picker cross-scan + PR scan found none), so the scout duty is this independent verification.

## বাংলা সারসংক্ষেপ

R86-এর চারটি প্রমাণ-ধারা আমি স্বাধীনভাবে live যাচাই করেছি — সবই সত্য: (১) #3404-এর stale-base ল্যান্ডিং সত্যিই পিক-প্লেন গার্ড মুছে ফেলেছিল (main-এ তিনটি restoration কমিট এর প্রমাণ); (২) burn-trail PR-গুলো বাস্তব; (৩) `full_file` লেনে সত্যিই কোনো precondition নেই যেখানে `unified_diff` fail-closed — asymmetry এখনও খোলা; (৪) `bridge_submit`/`bridge_submit_patch` দুটোর schema-তেই `files[].baseSha` ফিল্ড আছে কিন্তু কোথাও enforce হয় না। **নতুন উপস্থিত-কালের ডেটাম:** পিক-প্লেন গার্ডগুলো আজ main-এ (cb02c826 থেকে) restored — অর্থাৎ ADOPT_IMMEDIATELY বাস্তবায়নে কোনো restoration-ঋণ বাধা নয়; intake CAS গেট এখনই যোগ করা যায়।

## Claim-by-claim verification (all live reads this cycle)

| R86 claim | My independent check | Result |
|---|---|---|
| E1 clobber: #3404 stale-base full_file wiped co-landed pick-plane work | `git log origin/main` shows #3404 (43af0280) followed by three restorations naming the wipe: #3436 (a2208a69, scan-B fallback restore), #3451 (9acb64c4, incident-recognition restore), #3465 (cb02c826, pick-guards restore) | CONFIRMED |
| E2 burn trail: 4 PRs + 1 WO in ~6h | PRs #3451/#3465 (landed via bridge, closed post-landing), WO #3438 r2 → PR #3439 still open | CONFIRMED |
| E3 asymmetry: full_file has no precondition; unified_diff fail-closed | live tower contract (`bridge.work_order` #3487 ingressModes, read 15:5xZ): `full_file` = "default — content is the whole file (new or existing files)" — no precondition; `unified_diff` = "fail-closed context matching… (#539)" | CONFIRMED |
| E4 baseSha collected but never enforced | live `tools/list` inputSchema (read 15:5xZ): BOTH `bridge_submit` and `bridge_submit_patch` carry `baseSha` in the `files[]` item properties; no `If-Match`/CAS semantics anywhere in either schema | CONFIRMED |

## New present-tense datum (this receipt's addition)

The pick-plane guards are **restored on main as of now**: guard markers (`premise-delivered demotion`, `landing cross-scan`, `receipt-coverage demotion U5`, `sentry-test-row demotion U4`, `stale-sentry demotion`) present in `scripts/agents/continuous_agent_loop.py` at HEAD 89ca2975 (8 marker matches), and all five demotions fired live in this cycle's loop runs. Two consequences: (1) ADOPT_IMMEDIATELY has no restoration debt blocking it — the intake CAS gate can land now; (2) the still-open restoration row PR #3439 (r2, "four pick-plane guards") may partially overlap with the landed restorations — worth a verdict-plane dedupe glance, decision not requested here.

## Root-cause note (aligning with R86's verdict)

The one-checkbox-class fix: at bridge intake+landing, for every `full_file` item on an existing path, compare payload `baseSha` against the current blob sha and fail closed on mismatch (RFC 9110 If-Match semantics, ~40-80 lines, 0 deps — per the R86 estimate). Until then the silent-overwrite class remains one stale checkout away from recurrence; today's three restorations were manual luck, not a guard.

## Reflection Evidence (why + alternatives_rejected)

- **why:** R86 is an implementation-ready verdict awaiting the owner lane; an independent claim-by-claim verification converts it from one agent's report to a corroborated finding, and the present-tense datum (guards restored, no restoration debt) removes the last plausible reason to defer adoption.
- **alternatives_rejected:** (1) Implementing the CAS gate myself — rejected: bridge intake/landing is tower-side (owner/admin lane), outside the zero-credential agent envelope. (2) Claiming #3487 — rejected: report-labeled scout radar row; evidence lane is the contract. (3) Waiting for the filing agent's own radar doc — rejected: no R86 artifact on main or in gates at dispatch time; corroboration is the non-duplicative duty (R85's #3489 precedent). (4) Re-opening the #3439 overlap question — rejected: closure/merge decisions belong to the verdict plane.

## Verification evidence (3-tier)

- Tier-3: single new file under `docs/bridge/`; no tracked file modified; bare citations only, no close-verbs.
- Tier-2 (live smoke): every table row re-runnable — `git log origin/main` for E1; tower `github.list_prs` for E2; tower `bridge.work_order` contract for E3; tower `tools/list` schema dump for E4; `rg` marker count + loop run output for the present-tense datum.
- Tier-1 (reflection): this document.

## Rollback path

`git revert` the receipt commit; nothing depends on this file (new docs/bridge receipt, no code or index surface).
