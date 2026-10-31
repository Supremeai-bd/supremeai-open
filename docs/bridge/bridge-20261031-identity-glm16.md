# GLM Agent 16 — Worklog (Job ID 486792)

> Per-slot receipt, replaced in place every cycle (house format follows the
> glm11 template): small, durable facts only.

## Durable outcomes (with proof)

- Scout radar R94 filed (WO #4015, PR #4016): the credential-free board
  ground-truth freshness hierarchy — tower single-fetch is the only proven
  fresh board authority; web-rendered views serve ghosts; anonymous REST
  403-dark. Registry co-obligation done (index pass-51 + R94 row).
- CI-tracker triage r1 landed (PR #3877, WO #3876, merge 667b1bf): tracker
  #3856 = #3524-collateral stale-run class; remedy #3550 already on main.
- Scan-B board-plane third level with honest partial assurance (WO #3798,
  PR #3799, merge cbea0f5; 42/42 hermetic cases).
- Standing successes (cycles 9–12, compressed): standing-suite heal r2
  (PR #3695, a5d1d10); #3467 read-classifier wiring (PR #3486, 89ca297);
  jargon slice (PR #3599, b0e2ada); R66 slice live-proven (PR #3220).

## Cycle log (compressed, keep-small per the glm22-r2 pattern)

- c9–c16 (00:16–09:16, compressed): standing holds, scout cycles, viewer
  denial corroboration, pipeline census (22 jobs, 15 checkout sites),
  ghost-board escape (4 single-fetch spot-checks), R94 filed; r1–r3
  landed (PRs #3753, #3945, #4023).
- c17–c22 (10:16–15:16, compressed): bare-mode hold cycles; reds drained
  — #4124 pair healed (#4138), blind ladder 12 -> 2 (#4209), closure
  regime SOLVED (batch-delayed closer; c22: 19 rows closed in one sweep,
  board 19 -> 0); suite 2F/2234P. r4–r8 landed (PRs #4116, #4128, #4160,
  #4184, #4216).
- c23 (16:16): RBAC ERA ENDED — #4249 default role -> admin, roster ~20
  -> ~158 tools; lane discipline UNCHANGED (read + submit only). Suite
  2F/2234P. r9 landed (PR #4237, fcc0c0e).
- c24 (17:16): no dispatch (board 22 rows, external probe campaign).
  New main-red census from #4310/#4311 landings: meta-cognitive test
  aborted collection (sqlalchemy undeclared) + parity-guard wanted tests
  for line_budget_guard.py/run_face_tests.py + CVE pair. Loop probes
  underscore since #4311; UNIVERSALS 6 -> 8. r10 landed (PR #4254,
  89c38d0); r11 landed (PR #4316, 8a786e3).
- c25 (18:16): no dispatch (claimable 0/5; board 24 open — all other
  agents' WOs). NAME TRUTH PROVEN BY WIRE: underscore form is LIVE,
  dot form is DEAD — `github_workflow_runs` probe got HTTP 429 (tower
  accepted the call; quota), `github.workflow_runs` probe got MCP
  error -32602 "Tool not found". Consequences: (a) GLM 04's #4341
  census-test uses the CORRECT underscore wire names; (b) the
  test_tower_tool_name_drift.py DEAD_TOWER_TOOL_NAMES map is STALE —
  it claims dot is live and flags the census-test's correct names,
  which is the NEW third main-red. NOT fixed unilaterally: the
  collision plane is GLM 04's active lane and the right fix (dynamic
  roster check vs re-mapped pairs) is an owner design decision. Suite
  at tip 2f5ad91: 3 failed / 2286 passed / 13 skipped — the c24
  meta-cognitive collection-abort is HEALED (suite collects again) and
  the parity-guard red is HEALED (#4333 face-runner manifest); js-CVE
  drift GREW (glob@10.5.0/glob@13.0.6/minimatch x3 advisories joined
  follow-redirects on the studio lockfile — still maintainer-lane).
  TOWER 429 ROOT CAUSE: the loop's "flaky" HTTPError is rate limiting —
  backoff + single retry recovers (proven twice this cycle).
  verify-only 9/9. r12 = this patch.

## Notes for the next agent on this slot

- NEW (c25): main carries 3 reds at tip — (1) test_tower_tool_name_drift
  flags #4341's census-test on STALE name-truth (underscore is
  wire-LIVE per probe: dot form returns -32602 not-found, underscore
  returns 429 quota); fixing it means touching GLM 04's lane — do NOT
  edit either test without a dispatch; (2)+(3) the CVE-guard pair,
  whose js side now ALSO flags glob/minimatch advisories on
  .agents/skills/devtools-audit/package-lock.json. Never bump
  lockfiles unilaterally (U5/U10; maintainer-lane per #4150 routing).
- RESOLVED this window: meta-cognitive collection abort (healed —
  suite collects at tip); parity-guard red (#4333); #4124 pair;
  blind ladder.
- The loop's CLI contract: invoke BARE (no arguments); verify-only is
  the only surviving mode (#4097).
- Receipt-WO closure is BATCH-DELAYED — silence is not a defect;
  open rows are not work signals; a 0-row board is not certified
  clean. Per-row taskId check via bridge_read_feedback is the only
  work-truth (R94).
- RBAC-era roster: ~158 tools incl. dangerous ones — this lane stays
  read + submit-patch only, never admin/mutation tools.
- Tower rate limiting is the real face behind "flaky" HTTPErrors:
  back off ~20-25 s and retry once before concluding anything.
- Check the tool list at cycle start — rosters drift between epochs.
- Receipt prose must avoid executable strings and flag quotes
  (WAF 403s). Claim-gate threshold is >=5 claimable (#4007).
