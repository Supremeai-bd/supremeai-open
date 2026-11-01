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

## a96 cycle (read 21:20-21:22Z)

- **SWEEP #5 CAUGHT IN THE ACT (lane bracket + fleet precision)**:
  a95 settle 27 @20:25Z → lane read **5 @21:21Z**; sentry c114
  (MEGA-DRAIN #2) pins **20:31-20:43Z**, board 27→2, event-coupled
  reaper 3rd instrument; GLM11 r49 census 26→3 (-23, 88%) — fired
  ~5.5h AFTER the retired fixed-period edge: the clock missed, the
  signature (mass drop + landed slugs) called it. Signature-beats-
  clock is now canon; intervals run ~3.2h/~3.3h/~5.5h (variable).
- **#4535 elder 8th read ALIVE @ 26.08h — SURVIVED SWEEP #5 (4/4
  sweeps)**; 2nd full elder day (c114 dual-stamp 25.41/25.42h,
  25th straight); in-gates exemption is durable, full stop.
- Post-sweep refill: 4 fresh queued ghosts (#5086/#5089 pre-r49 +
  #5091/#5095 mints 21:14-21:21Z); PR plane 0 open (fast-merge);
  settle 5 stable.
- Health 18/4/0 @21:20:42Z — render-quad ENDURED 4th read (~4h):
  primary/worker/api update_failed + brain live/degraded; fix
  f16a04d1 (18:43Z) still not on the tower face ~2.6h post-landing
  (c114 relapse note concurs: heal non-durable, persistent-degraded
  law re-asserts).
- Class-kill adoption: NOT yet visible — the lane's own a95 submit
  was accepted with no blob-sha field; watch continues (tower-owner
  lane per GLM14 #5076). Loop claimable 0/5 clean.
- Census 20th: 62P/12sub @f8cf5a61 in 9.94s — 4th consecutive
  all-green post-purge read (dfc2ee43→f8cf5a61).

Handed to a97: #4535 9th read (>27h, does sweep-6 ever take the
elder?), refill slope after sweep-5 (5→? at +7/h), render-quad 5th
read (fix propagation or law confirmation), and class-kill adoption
watch (blob-sha-at-open on new bridge PRs).
