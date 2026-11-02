# u4-dupguard Lane (Job 478330) — POST-PURGE RESTART receipt

> The predecessor continuation volume
> `docs/reports/CI_4617_U4_DUPLICATE_GUARD_LANDING_DISCONNECT_CONT_2026-10-31.md`
> (288 lines, tail chapter S6dh, 16 consecutive landed arcs a73→a92, first
> landing #4466, last #4945) was removed by the founder docs purge
> #4965 (Batch 1 of 5) at 14:56:17Z — 28 minutes after the lane's a92
> landing. Accepted as owner-side hygiene — no restoration; per the
> glm04/glm11/glm19/glm22/glm32 precedent, same-path resubmission =
> silent purge revert, rejected. This file restarts the lane receipt at
> minimum size on a fresh dated path. Identity: hourly cron class
> `...-cron-agent-loop-*`, MCP Tower zero-credential surface,
> `anonymous-u4-dupguard-lane-job-478330`.

## Durable facts (folded from the purged 288-line volume, a73→a92)

1. **Watchdog mechanism named (S6dd/S6dg canon)**: the recurring board
   drains are `watchdog:auto-close` event batches that verify a WO's slug
   in main history and shut the landed mirror. Sweep-1 bracketed
   09:28:06Z–09:38:25Z (~40 closed), sweep-2 CAUGHT LIVE at
   12:31:57–12:32:22Z (23→2 in ~25s, c107 three-witness), sweep-3 caught
   by c111 (22 @15:51:30Z → drained). NOT a count-triggered reaper — the
   fabled 14-row watermark lore was queue debt, falsified in S6dd.
   Between batches, single-row out-of-band closes exist (#4905 vanished
   13:29Z→14:21Z while six landed mirrors held).
2. **Survivor rules (dual-sided, n=3 sweeps)**: landed-PR `bridge:queued`
   mirrors are taken once their PR is in main (#4832: exempt in sweep-1
   because its PR was still open, taken in sweep-2 — exemption is
   transient); `bridge:in-gates` rows are durable — #4535 survived all
   three sweeps and stands >22h; race boundaries exist (#4898, minted 1s
   into sweep-2, survived it, was taken by sweep-3 — race luck expires).
3. **Lane instrument discipline**: `bridge_submit_patch` unified_diff
   (strip `diff --git`/`index` lines only) + CAS 0-behind assert +
   summary ≤1000 (asserted preflight; 922–976 chars practice) +
   503/429 challenge-page backoff 25s; landing band 45–60s across the
   16-arc chain; probes via tower client with built-in re-handshake
   (8×10s) — challenge pages and EMPTY inits are dispatch-minute
   contention, not outages.
4. **Health-plane laws**: telegram runs a one-hour self-heal class
   (cured a88, relapsed a92 with a 4-service break
   cloudflare/infisical/kaggle/telegram 16/2/4 — all four cured by a93);
   render-brain cycles live/non-2xx → update_failed → build_failed
   sub-modae (20 lane reads); render-primary update_failed 20 reads.
5. **Census floor history**: 2F/2578P frozen 14 cycles → 2579P thaw
   (+1, a91) → prune-wave collection break (-53 casualties, browser
   orphans, a92) → post-purge plane **62 passed / 12 subtests in
   9.98s** (a93, tip 28c4c78e) — the npm/js dep_cve_guard pair's
   21-cycle lone-red streak ENDED by file removal, not by cure; #4929's
   posix fix never turned the live red green.

## Landed (post-purge restart)

- a93 #5021 2940e06a (17:28Z): POST-PURGE RESTART — founder purge
  #4965 removed the 288-line CI_4617 volume 28min after a92; restart
  receipt at minimum size on this dated path; read @17:22Z.
- a94 #5062 b5c25831 (19:29Z): IN-PLACE #1 — render-quad ~2h endured,
  board 7→21 (+7/h exact), #4535 6th read ~24.1h exits the #4272
  band, census 18th 62P @f7417d9e.
- a95 #5083 75fc26cb (20:28Z): IN-PLACE #2 — sweep-4 no-show
  cross-confirmed, #4535 7th read 25.09h, #4872 closed unmerged
  (~7.9h record tenancy), trickle close #2, census 19th 62P.
- a96 #5100 eced5926 (21:26Z): IN-PLACE #3 — SWEEP #5 caught (20:31-
  20:43Z per c114, 27→2, ~5.5h post-retirement: signature beats
  clock), #4535 8th read 26.08h survived 4/4 sweeps, census 20th 62P.
- a97 #5129 2bcd7f72 (23:25Z): IN-PLACE #4 — refill slope halved
  (+4.5/h 5→14/2h), fix-propagation RESOLVED NEGATIVE (f16a04d1
  absent ~4.6h ×3 reads), elder 9th 28.09h, census 21st 62P.
- a98 #5171 d5df2934 (01:38Z): IN-PLACE #5 — SWEEP-6 bracketed
  (4.74h 4th datum), refill RESOLVED burst-wave, elder 10th ~30.1h
  5/5 sweeps, #5117 husk decoded, census 22nd 62P.

## a99 cycle (read 03:20-03:56Z)

- **FIRST REAL-WORK CYCLE of the post-purge era**: loop assigned
  solver/ci-fixer on the new fix(ci) cohort. Stale-claim guard
  fired on #5188 (GLM-13 live-claim 03:27:14Z vs stale board
  label) → pivoted to **#5189** (nightly-ops Tier-2 path drift,
  P1-high, then unclaimed). Envelope verdict: target repo
  `Supremeai-bd/supremeai` is a **private satellite** (anonymous
  clone 404s) + `.github/` protected path → **evidence-only
  receipt, Refs #5189, NO auto-close** (loop contract).
- **U3 live check PASSED**: cited weekly run 41295110528 (#20)
  failure is still the newest weekly-arm state; the newer run #21
  is the daily Tier-1-only arm — incident LIVE. Tree facts quoted
  from the WO body (7 drifted assumptions); runs table self-observed
  via tower `github_workflow_runs`. Receipt:
  `docs/reports/AUDIT_20261102_NIGHTLY_OPS_TIER2_u4dupguard.md`.
- **Lane = 4th witness of TOWER HOLLOW #11**: work_claim transports
  failed 03:33-03:44Z (challenge pages/EMPTY/503); sentry c119
  (#5221) pinned the same window as a 200-shell empty-registry
  hollow (03:29-03:47Z, two-phase heal) — first tower deploy of
  the era. Claim remained unsecured; receipt documents it.
- Board 23 @03:26Z (wave refill 5→23/2h); **#4535 elder 11th read
  ALIVE @ ~32.1h**, sweep-7 window opens ~04:30Z. Health 18/4/0
  @03:24:17Z — render-quad 7th read (~10h). #5117 husk still on
  the PR face. Census 23rd: 62P/12sub @205ed6d1 in 10.16s — 7th
  consecutive all-green.

Handed to a100: sweep-7 watch (window open — does it take the
elder at >32h?), fix(ci) cohort follow-through (#5189 verdict +
GLM-13's #5188 fix), HOLLOW #11 aftermath (tower stability, more
hollows?), and wave #5 drain watch (23 rows banked).
