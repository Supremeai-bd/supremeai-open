# GLM Agent 20 — Job 486804 · compact worklog (in-place replace; old detail pruned, receipts hold the evidence)

Durable one-liners; full evidence lives in the linked receipts/PRs (git log --grep 486804). Replaced in place each cycle — this file stays small.

## Landed chain (2026-10-30 → 31, +08)
- #3615 stranded-duplicate triage (report-only): Run 41099207571 = U4 duplicate death, not a main defect → #3633.
- #3399 landing-race corroboration: second policy-block PR #3392 97s after instance 1 → #3411.
- #3661 Ingress Hook Guard red-on-main triage → #3689-class exec-bit mode-drift (class later cited by landed #3941 bootstrap fix).
- scout R82: #3386 runner-cost gap (4/22 jobs missing timeout-minutes) → #3392.
- #3354 re-dispatch ROOT CAUSE: closure-integrity class in `incident_triage_receipts.json` + test pin → #3774 **merged** (aa5c2f4), 17/17 tests.
- referenced-PR-landed CI-row pick demotion → #3913 **merged** (204d1c9).
- 07:20+08: worklog r1 established, landed → #3952/#3953; 10:20 r2: bare-mode transition + board 52→4 noted.

## Cycles
- 11:20+08 (r3): board-plane clean (bare loop "clean and healthy, observation idle"; 6 queued rows, 0 unclaimed, 0 P0) but TEST-PLANE RED PAIR live: `test_claim_lease_ssot::test_02` + `test_agent_cadence::test_pick_has_no_dispatch_time_gate`, my repro 2F/34P at 3c85a3e = third independent after Agent 04 (#4125, a9323f45) and Agent 16 (#4128, 915f470). Cause: #4124 re-introduced the #3573 dispatch time-gate (30-min lease cooldown in pick_next_issue). FIX OWNER-CONTRACTED (Option A restore #3573 / Option B governance flip, paired with pytest faces in the landing ladder) — no agent code-fix by contract; also third datapoint for the glm28 pytest-blind-ladder thesis (#4097/#4106/#4124: ladder 8/8 PASS while pytest red). PR-plane tool-absence U6 fix in-flight by another agent (#4131, queued 03:20Z). My guards green: verify 8/8 PASS, test_triage_receipt_demotion 17/17 PASS.
