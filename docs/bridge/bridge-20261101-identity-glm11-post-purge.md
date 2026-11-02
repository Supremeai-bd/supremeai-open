# GLM Agent 11 — Worklog (post-purge restart, Job ID 486770)

> Continuation of `bridge-20261031-identity-glm11.md` (slot chain r2→r44,
> 38 merged landings, first worklog landing r2 = #3230, last r44 =
> 023e016/PR #4937), removed by the owner-side docs purge (#4965 + the
> 58-file lean-SSOT prune #4995, refs #762).
> This file restarts the slot receipt (r45 = 1c8f736/#4994 → r49 =
> bbc6b71/#5093, r50 = orphaned PR #5117, r51-r53 = 1fa84c8/#5160,
> b02910f/#5176, df4e6b5/#5197). Compressed durable facts:

- **Landing chain**: 38 merged landings r2→r44 + r45-r49, r51-r53
  post-purge; fourteen of the last fifteen (r39→r49, r51-r53) landed
  first-pass via the fail-closed CAS gate + SUMMARY≤1000 preflight. r50 = orphaned exception
  (PR #5117, opened 6 min before the ~22:19Z tower reboot, never
  merged despite 27 later landings) — recovered at r51 via
  pre-declared supersede; landed ~5 min: job lost, not slowed.
- **Sweep law (n=5, signature-based, multi-agent)**: EPISODIC,
  variable intervals — #1 ~09:20Z (45→7), #2 ~12:31Z (22→5), #3
  ~15:50Z± (11→1), #4 ~21:0xZ (26→3), #5 in 00:15→01:13Z (18→2).
  Detector: mass drop (>50%) + departed slugs landed. Cross-slot
  witnesses converge (sentry c117/c118, d5df293); no new machinery.
  Ghost pile hit 23 at c60 — largest since #4; sweep #6 signature
  building, no point prediction.
- **Refill law (arcs 10/10, sweep-coupled)**: refill followed EVERY
  sweep — ratchet 45→7→…→18→2→10→21→29. Additive bursts without a
  sweep: n=2 (10→21 c59, 21→29 c60); tracked, no law change.
- **#4535 (bridge:in-gates) longevity record**: survived 5/5 sweeps,
  the daily audit, both purge windows, ~32h. Durable-until-closer.
- **#4250 (loop CI verdict)**: run #49 (schedule, 2026-11-01T09:48:49Z)
  failure — streak 4 straight. Run #50 absent ~18.4h: past the ETA and
  the ~15h longest-gap baseline. Falsifiable threshold: ~20h crosses
  in the 06:11+08 window → scheduler-stuck becomes primary hypothesis.
- **Disciplines pinned**: 2-window persistence; receipts sporadically
  invisible — never resubmit; zero cross-agent collateral; protected
  paths evidence-only; the loop is the permission (U10); one-
  outstanding-PR per slot — supersede, never stack (r50→r51 precedent).

## Cycle 60 (2026-11-02 12:11+08) — first loop dispatch; claim-race lost honestly; no-slug class solved

- **Census (36th, full board): totalOpen 21→29 (+8), truncated=
  false — second additive burst, no sweep.** 23 ghosts (#5154-#5220),
  #4535, #5213 (new legit), 4 no-slug (#5189-#5192). 0 misclassified
  — 36th clean census.
- **NO-SLUG CLASS SOLVED**: queue JSON shows those rows are issue-
  plane GitHub issues (area:ci, repo:core, handoff:coder, ci-failed)
  — real work items, not receipt slugs. #1304 departed unlanded
  between c35-c36 — honest UNCLASSIFIED departure (as #5069/#5070).
- **FIRST LOOP DISPATCH this session → #5192** ([core] SARIF upload
  when GHAS unavailable, ci-fixer). STALE-CLAIM GUARD caught the
  label lag: live label status:claimed, updatedAt ~1 min before my
  read — race lost. Guard held: no work_claim, no same-row retry;
  loop rerun DARK (tower 429) → no sibling hand-claims (U10). The
  dispatch→guard→race→dark chain ran as designed.
- **PR #5117 zombie watch: NEGATIVE ~6h** — trailer-pattern grep
  empty (prior grep self-matched our r53 evidence; probe improved).
- **#4535 still open** (~32h, 5/5 sweeps) — no touch (evidence-only).
- Heartbeat primary, tree fresh vs origin/main at f268f48. This file
  survived its 9th in-place window.

## Notes for next agent (first probes)

1. Verify r54 landed; #5117 zombie watch via trailer-pattern grep.
2. Census 37: sweep #6 watch (23-ghost pile pending); #5213 —
   loop-dispatch only (U10).
3. #4535: 6th sweep survival? (~32h+; record live.)
4. #4250 run #50 — ~20h threshold crosses in the 06:11+08 window;
   scheduler-stuck goes primary after that.
5. This file: verify in-place survival before editing (purge class
   risk).

## Reflection Evidence

- **why:** the first loop dispatch exercised the full guard chain —
  dispatch, live re-verify, race lost, no-retry — proving the
  anti-stampede design under real contention; solving the no-slug
  class turns two UNCLASSIFIED buckets into one understood plane.
- **alternatives_rejected:** claiming #5192 anyway (live label:
  claimed — stampede risk); hand-claiming #5191/#5213 after the dark
  rerun (U10); calling #1304's departure "completed" (no evidence);
  promoting additive bursts (n=2); touching #4535 (evidence-only).

## Rollback

Single docs-only in-place file update (baseSha CAS pinned to the landed
blob) — revert this one PR; no code paths touched this cycle.
