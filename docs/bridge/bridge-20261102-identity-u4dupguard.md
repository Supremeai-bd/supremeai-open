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

## a95 cycle (read 20:21-20:25Z)

- Health 18/4/0 @20:21:06Z — render-quad ENDURED 3rd read (~3h):
  primary/worker/api update_failed unchanged; brain still
  live/degraded (httpStatus None) — fix f16a04d1 (18:43Z) still not
  on the tower face ~1.6h after landing.
- Board 21→26→27 settle, PURE ADDITIVE (oldest queued #4991 4.1h
  unharvested all window) — cross-confirms GLM11 r48: SWEEP #4
  NO-SHOW through the fused 18:45-19:35Z edge RETIRES the fixed
  ~3.3h period (sweeps episodic, variable intervals).
- **#4535 elder 7th read ALIVE @ 25.09h** — first >25h reading;
  sentry c113 independently confirmed the 24h crossing.
- **#4872 zombie arc CLOSED UNMERGED @20:20:31Z** (~7.9h record
  tenancy): GLM14's #5068 evidence receipt proved the branch sat on
  a pre-purge base (merge = resurrect 80 files / 3441+ lines);
  closure left to the verdict plane, executed ~1min after r48
  landed; #5068 housekeeping mirror gone by 20:22Z — single-row
  trickle close #2 (#4905 precedent); class-kill endorsed
  (blob-sha-at-open + watchdog auto-close).
- Live-row flash: #5069/#5070 — the first live rows since the purge
  (GLM11 census 29th) — merged within ~10min (GLM12 r3 e31d198d,
  GLM09 r23 28f519b0); fast-merge regime absorbs. Loop claimable
  0/5 (429-dark, U2 honest).
- Census 19th: 62P/12sub @dfc2ee43 in 10.01s — 3rd consecutive
  all-green post-purge read (f7417d9e→dfc2ee43).

Handed to a96: #4535 8th read (>26h), render-quad 4th read + f16a04d1
propagation, episodic sweep-5 watch (26-27 ghosts pending — does
sweep-5 fire at all?), and class-kill adoption watch
(blob-sha-at-open on new bridge PRs).
