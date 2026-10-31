# GLM Agent 22 — Worklog (Job ID 486813)

> Post-#3524 archive restart — pre-archive lane history (2026-10-30: gate-census
> r4 WO #3317, compaction WO #3325, duplicate-service census + this worklog's
> first two cycles via PR #3443, skip-with-evidence WO #3493/PR #3494) lives in
> supremeai-archive. This file is the per-slot receipt: small, durable facts
> only, replaced in place every cycle.

## Durable outcomes (with proof)

- Identity registered: GLM Agent 22, Job 486813, hourly cron cadence; door =
  self-healing MCP tower client (session auto-reinit) → AGENTS.md/bridge_guide
  → verify-only 8/8 before every pick.
- Slot disciplines (earned the hard way): quote guard output only inside its
  own next-free exclusion context (citation-ghost class); tower diff parser
  takes pure unified diffs only; before serving any row check open WOs AND
  merged receipts AND parent lanes — skip-with-evidence beats a duplicate;
  coverage probes only match a row's own number (parent-alias blind spot).

## Cycle 1 (2026-10-31 02:2x+08) — P0 3663 independent verification + deploy-window matrix

- Dispatch #3663 (P0 security, filed 02:14+08 by GLM Agent 14): anonymous
  sessions resolve to global admin via the fail-open admin fallback. Claim
  GRANT_NEW 18:28:26Z; every cited site corroborated on HEAD 1cb17fa
  (fallbacks L988/1020/1119 — L1119 is a third fallback line the fix must
  cover; equality sites 935/992/1123/1230; kill path L1459).
- Live corroboration (read-only, zero destructive): anonymous tools/list 158
  descriptors incl. 6 destructive-class; client_list scope star, 88 rows —
  matches the filer exactly.
- NEW contribution: deploy-window compatibility matrix from the policy source
  — the whole bridge/identity/health front door is already public-class
  (#123/S0.4, #1787), so the viewer-default flip is fleet-safe today; only
  the github read family degrades (3 owner options recorded). Receipt:
  bridge-20261031-3663-independent-verification-glm22.md. No patch, no Closes
  — owner lane (deploy-policy/HITL), concurred with the filer's routing.

## Cycle 2 (2026-10-31 03:2x+08) — P0 3663 acceptance criteria made executable

- Pick: no clean pick — preflight P0 hold (#3663 open, status:unclaimed, 21
  open PRs, no fix in flight; WOs #3670/#3672/#3676 report-only). Idempotency
  check per Invariant 5 before touching the row.
- Contribution: scripts/tower/p0_3663_acceptance_probe.py — the issue's 3
  acceptance criteria as a machine-checkable, read-only, allowlisted probe
  (self-test 12/12; SSOT URL import; no hardcoded endpoint; honest
  INDETERMINATE for own-ctx instead of third-party-role misclassification).
- Live 19:33Z: client_list 88 rows EXPOSED + kill_switch/list_secrets/
  tenant_create anonymously visible; exit codes make it a deploy-window gate.
  Receipt: bridge-20261031-3663-acceptance-probe-glm22.md. No claim, no Closes.

## Cycle 3 (2026-10-31 06:2x+08) — P0 3663 closed: post-redeploy acceptance verified

- PR #3732 (probe) merged as cf71130. Owner landed the fix: all three
  fallbacks now `?? DEFAULT_GUEST_ROLE // #3663 fail-closed` — L1119 (my
  third-site finding) covered. P0 gate lifted: "zero open P0 blockers".
- Probe r2 — its own first real verdict caught two of my defects: aggregation
  else-branch mislabeled mixed no-exposure as "FAIL-OPEN STILL LIVE"
  (false-alarm class), and the redeploy's deny arrives as deny PROSE in the
  content envelope, not a JSON-RPC error plane. Both fixed; self-test 17/17.
- Live acceptance 06:3x+08 (exit 3): NO EXPOSURE OBSERVED — client_list deny
  prose (default-deny RBAC), 20 anonymous tools (was 158), zero destructive;
  bridge front door intact as the Cycle-1 matrix predicted. Full 3/3 needs a
  whoami-class viewer tool (owner option recorded in the receipt).
- Dispatch #3858 (PR #3534 parity guard): feedback plane shows LIVE claim
  (contributor-agent 22:25:18Z, minutes old) → skip-with-evidence, no
  stampede. Verify 8/8 on f1677a5 before and after.

## Cycle 4 (2026-10-31 07:2x+08) — RBAC redeploy's audit-plane blindspot receipted

- PR #3905 (probe r2) merged as 34615ec; no specific dispatch (role-locked
  cadence run). Found the one unreceipted post-redeploy consequence: loop's
  13 github.list_prs call sites vs anonymous toolset github.* = 0 → PR-plane
  audit dark (U2) every run, landing-cohort CI status owner-plane only.
- Receipt: bridge-20261031-rbac-prplane-blindspot-glm22.md — impact ledger
  (what holds vs what's lost) + 3 owner options (A narrow viewer re-exposure,
  B ci.landing_overview tool, C accept dark plane), guard note: any toolset
  change must keep the #3663 probe green. Report-only, no claim, no Closes.

## Cycle 5 (2026-10-31 08:2x+08) — #4009 class root-caused: branch-gone demotion

- Dispatch #4009 (CI incident, Run #41149642412): live chain proved ROW-
  CLOSED-UNDER-US — run failed on a head branch that is now 404 with zero
  PRs; #3050 guard can't see it (deleted run never in the main window).
  #4009 closed administratively mid-cycle, corroborating the diagnosis.
- Repo-side guard fix in continuous_agent_loop.py: _lsremote_ref_exists
  (git ls-remote --exit-code, credential/rate-limit-free — post-RBAC
  lesson) wired for real branch-name refs; main and <n>/merge keep their
  recorded contracts; hostile tokens refused; fail-open intact. Tests
  21/21 (5 new pins) + live note reproduction; verify 8/8 on 48d8252.
- Receipt: bridge-20261031-4009-branchgone-demotion-glm22.md. No claim,
  no Closes (closure credit belongs to the verdict plane).
