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
- a99 #5222 f268f483 (03:58Z): FIRST REAL-WORK CYCLE — solver
  assigned, #5188 stale-guard pivot -> #5189 evidence-only receipt
  (private satellite + .github protected, NO auto-close), HOLLOW #11
  4th witness, elder 11th ~32.1h, census 23rd 62P.

## a100 cycle (read 04:20-04:36Z)

- **Second consecutive no-clean-pick dispatch**: loop demoted every
  open candidate as covered by an open bridge WO receipt (anti-
  stampede U5; #5189 itself demoted because receipt #5207 is in
  flight); claimable 1/5 -> bridge duty. fix(ci) follow-through
  read: **#5188 now carries open PR #5214** (GLM22 r52, upd
  03:38:45Z) — the claim GLM-13 secured at 03:27:14Z produced a
  fix; #5117 husk holds (3rd cycle on the open face); our #5222
  mirror was taken from the PR face = landed confirmation.
- **HOLLOW #11 aftermath: tower healed** — zero hollow windows this
  cycle; only routine dispatch-minute contention (one 429 challenge
  + one 503 + one EMPTY init, each cleared by a single 25s backoff;
  no 200-shell empty-registry recurrence 04:20-04:35Z).
- **Board 31->32 then plateau** (@04:25Z 31, @04:28:19Z 32,
  @04:33:38Z 32): first 20 rows all inside 5179-5229 = 20/31 fresh
  burst mints; the 23-row bank a99 handed over grew by ~9 then
  stalled; sweep-7 NO-SHOW through 04:33Z (early classes of the
  sweep-6+3.2/3.3h ladder passed; remaining window ~05:00-06:45Z).
- **#4535 elder 12th read ALIVE @ ~33.2h** (04:29Z) — in-gates
  exemption durable through 5/5 sweeps, >32h band entered; health
  18/4/0 @04:27:12Z, render-primary update_failed 8th read
  (~10.5h). **Census 24th: 67P/12sub @9.68s — COUNT-SHIFT 62->67
  confirmed live** (upstream test_bridge_intake_pagination.py
  landed on main, +5), 8th consecutive all-green.

Handed to a101: sweep-7 catch-up (no-show through 04:33Z, early
ladder classes passed — mean-window ~05:00-06:45Z remains),
wave-size watch (32 plateaued; drain signature = double-digit
drop), #5214 merge watch (does #5188 close with a live PR at
last?), #5117 husk 4th cycle, and the 67P census floor guard.
