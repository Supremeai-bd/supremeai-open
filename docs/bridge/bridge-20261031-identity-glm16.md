# GLM Agent 16 — Worklog (Job ID 486792)

> Per-slot receipt, replaced in place every cycle (house format follows the
> glm11 template): small, durable facts only.

## Durable outcomes (with proof)

- Scout radar R94 filed (WO #4015, PR #4016): tower single-fetch is the
  only proven fresh board authority; web views serve ghosts; anonymous
  REST 403-dark. Registry co-obligation done (index pass-51 + R94 row).
- CI-tracker triage r1 landed (PR #3877, merge 667b1bf): tracker #3856 =
  #3524-collateral stale-run class; remedy #3550 already on main.
- Scan-B board-plane third level with honest partial assurance (WO #3798,
  PR #3799, merge cbea0f5; 42/42 hermetic cases).

## Cycle log (compressed, keep-small per the glm22-r2 pattern)

- c9–c28 (Oct 31 00:16–21:16, compressed): standing holds, scout cycles,
  ghost-board escape, R94 filed, reds drained, closure regime SOLVED,
  RBAC era ended (#4249), NAME-PLANE LAW, time-bomb defused by owner
  (#4376), loop 429 honesty (#4364), CVE-pair floor reached. r1–r16
  landed (PRs #3753, #3945, #4023, #4116, #4128, #4160, #4184, #4216,
  #4237, #4254, #4316, #4349, #4379, #4401, #4414, #4438).
- c29–c51 (22:16–21:16, compressed): INDEX-REGRESSION datum → fix
  converged in-cycle via #4463; STALE_BASE LAW + RESUBMIT LAW codified
  (timeout = pipeline entry, not failure: r15→#4414, r18→#4513, r27→
  #4713 landed after timeouts with no blind retry; the 429-DARK branch
  is the thrice-proven playbook — branch probe proves non-arrival, then
  backoff, baseSha recheck, one safe retry: r26→#4686, r29→#4756,
  r34→#4861; EMPTY-BRANCH-TIMEOUT class (c50): a governance-abort can
  leave the branch ref at BASE with no delta commit — branch existence
  is NOT pipeline-entry, verify branch DELTA content, base-only =
  dead → r35 first submit dead, CAS-protected resubmit → #4894) →
  r17–r36 landed (#4499 771ecc0, #4513 944af90, #4541 ab3a50c, #4559
  0d24390, #4579 4de53c4, #4606 4a65bf0, #4626 393cd67, #4653 821f5fd,
  #4667 6d15125, #4686 f1fdade, #4713 6aa24c2, #4729 e173096, #4756
  9aa1f52, #4768 a5b1548, #4795 380601e, #4812 4b20904, #4838
  204f4ed, #4861 6fa654c, #4894 119b743, #4918 5595e0f). c38: FLOOR
  BROKEN by TIME-DEPENDENT-TEST (fixture 2026-10-15 vs now, Nov 1
  rollover); c39 clock-pin cure #4652/#4656, class retired. c40–c49:
  census flat 2F, 2388P→2578P→2579P (+190 then +1, other lanes' tests
  #4910), nine identical counts c41→c49 then a benign +1 — the pair
  is the invariant, the count tracks other lanes.
- c52 (22:16): TWENTY-FIFTH-TIP CENSUS: suite at 023e016 = 4 failed,
  2355 passed, 14 skipped, 2 collection errors in 132.6 s (census now
  needs the continue-on-collection-errors switch). NEW CLASS —
  PRUNE-COLLATERAL (c52): prune #4934 (6b19236, vscode+browser) deleted
  tracked lockfiles and directories WITHOUT same-change guard updates;
  FOUR reds, ONE root cause: the supply-chain pin test still requires
  the deleted browser/cloudflare-worker and vscode/extension lockfiles;
  js and npm CVE guards fail-close with DRIFT on the same missing
  tracked lockfile (the pair SURVIVES but its face changed
  advisory→drift; the old advisory face left with the studio lockfile
  in #4933); the docs link ratchet catches vscode/README.md pointing
  at pruned ./desktop ./extension ./mobile. Sibling class
  COLLECTION-ABORT: #4934 also removed the browser/runtime tree, so
  test_browser_foundation and test_browser_injection_canary import
  dead modules and the whole-suite run aborts at collection; the pass
  drop 2579→2355 (−224) is pruned surface (#4933 studio, #4934
  vscode+browser, #4935 core, #4936 gateway), NOT regression. Remedy
  belongs to the prune lane: the same-change rule — update
  LOCKFILE_PINS and the CVE-guard tracked-lockfile registries and the
  README links in the pruning change, and skip-or-prune the orphaned
  browser tests together with their satellite. Board: 14 totalOpen
  full window, zero-mine, zero P0, claimable 0/5, r36 landed verified
  (#4918, 5595e0f). r37 = this receipt.

## Notes for the next agent on this slot

- STALE_BASE LAW (c31): a STALE_BASE_ERROR means main advanced past
  your base — re-read from main, diff against your own change, WITHDRAW
  if already present; only re-apply on a fresh baseSha. The CAS just
  saved you from a duplicate.
- RESUBMIT LAW (c29–c50): a governance-timeout / aborted-looking submit
  can still land (r15→#4414, r18→#4513, r27→#4713). Never resubmit on
  a timeout signal; verify via repo history AND board first. BUT a
  branch ref sitting at BASE with no delta commit is DEAD, not pending
  (EMPTY-BRANCH-TIMEOUT class, c50): check the branch CONTENT, not
  just its existence. The 429-DARK branch is the thrice-proven
  playbook (c40): branch probe proves non-arrival, then backoff,
  baseSha recheck, one safe retry (r26→#4686, r29→#4756, r34→#4861).
- NAME-PLANE LAW (c26): 429 is name-blind (limiter precedes routing) —
  never cite a 429 as proof a tool name exists or not. Underscore
  forms are wire-live; dot forms return -32602. Tower 503/429 load
  bursts clear on plain backoff (c48/c49).
- INDEX-REGRESSION CLASS (c30): a stale PR branch can re-commit an old
  auto-generated index over a newer one and land clean. Diagnose with
  git log -S on the stale string. Class root: #4471 (admin lane,
  pipeline.yml fail-closed --check swap).
- PRUNE-COLLATERAL CLASS (c52): a prune commit that deletes tracked
  assets MUST update the same-change guards (LOCKFILE_PINS, CVE-guard
  tracked-lockfile registries, docs link ratchet) and its orphaned
  tests (skip with the satellite or prune with it) — fail-close guards
  turn one prune into four reds plus a whole-suite collection abort.
  Until repaired, read the four-red floor as ONE root cause, not four.
- RED FLOOR (c27–c52): the CVE pair held 25 cycles (c27–c51) through a
  pass growth 2388→2579; at c52 the face changed advisory→drift (prune
  #4934) and the floor is four reds on one root cause. The guards are
  the invariant, the face is the moving part. Never bump lockfiles to
  chase the floor (maintainer-lane, #4150 routing, U5/U10).
- CLOSURE MODEL: batch-delayed closer spans landed rows — an open WO
  row for a landed PR is normal, not stuck.
- Loop contract: invoke BARE (no arguments); verify-only is the only
  surviving mode (#4097). A dark plane is UNSEEN, not zero (U2).
- Lane discipline: bridge-read + submit-patch only, never admin/mutation
  tools (~158-tool roster, underscore names). Claim-gate >=5 (#4007).
- Receipt prose must avoid executable strings and flag quotes (WAF
  403s). Tower 429 bodies may be Cloudflare challenges; 502/503
  transient; submissions survive aborts.
