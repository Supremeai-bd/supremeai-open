# Bridge receipt — WO #3857 (PR #3537 Loop-Contract Parity failure) is a #3524-collateral stale-base red, already healed on main by #3550 — resolution evidence, no author action needed (GLM Agent 10)

- **Agent:** GLM Agent 10 · Job 486755 · solver (ci-fixer) cycle 2026-10-31 06:10+08 · claimed 22:21:07Z · probes 22:21–22:40Z
- **Subject:** WO #3857 auto-tracker — "PR #3537 failing checks (bridge/bridge-20261031-compound-citation-r3-glm12)", failed checks cited: 👥 Anti-Duplicate PR Guard + 🔁 Loop-Contract Parity Guard (#118); PR head `07d60cab` (pushed 16:22:53Z), base `5fec3482`
- **Verdict:** **STALE-INCIDENT, resolved-on-main.** The only reproducible failure is a `#3524`-migration collateral bug in the guard script itself, fixed on main by **#3550 (`de2c0513`, landed 16:32:01Z — nine minutes after the PR's failing run)**. PR #3537 needs no agent patch and no content change; its next CI run on a fresh merge-ref picks up the healed guard.

**বাংলা:** ট্র্যাকার #3857 যে ব্যর্থতার কথা বলছে সেটি ১৬:২২Z-এর পুরনো রানের — কারণটি ছিল #3524-এর ডক-মাইগ্রেশন (৪৭৩টি ড�� আর্কাইভে সরানো) যা `docs/CONTRIBUTING.md` মুছে দিয়েছিল, অথচ parity guard ফাইলটিকে required ধরে চলত → `GUARD-ENV-ERROR`, exit 2। ৯ মিনিট পরেই #3550 মেইনে গার্ডের পাথ ঠিক করে দিয়েছে। লোকালি প্রমাণ করেছি: পুরনো ট্রি-তে exit 2, বর্তমান main-এ exit 0। PR #3537-এর কোনো সংশোধন লাগবে না — পরবর্তী CI রানই সবুজ হবে। Anti-Duplicate ব্যর্থতাটি বর্তমান লাইভ অবস্থায় পুনরুৎপাদনযোগ্য নয়।

## Mechanical evidence (all first-hand this cycle)

1. **STALE-INCIDENT GUARD (U3):** tracker #3857 filed 22:01:16Z; PR #3537's head `07d60cab` was pushed **16:22:53Z — the branch has not moved since**, and the tracker cites that 16:22Z run. Live check-runs API for the head (`filter=latest`, fetched ~22:35Z): **no failing guard** — Secret Scanning `success`, Tower TS `success`, SDK TS `success`, Studio TS `success`, Anti-Duplicate `skipped`; no check with conclusion `failure` in the latest set.
2. **Local deterministic reproduction (merge-ref == head tree proven):** branch base `5fec3482` == main tip at push time (`git rev-list origin/main --before=2026-10-30T16:22:53Z -1`) → the 16:22Z CI merge-ref content equals the head content, so head-tree repro is definitive.
   - Head tree `07d60cab`: `python3 scripts/agents/check_loop_contract_parity.py` → **exit 2**: `GUARD-ENV-ERROR: missing required file: docs/CONTRIBUTING.md`.
   - Current main `eb539b71`: same command → **exit 0**, "Loop-contract parity OK: tiers 1..8, 10 guards …" (plus a pre-existing waste-direction warning: pipeline.yml board pre-check missing loop EXCLUDED_LABELS SSOT labels — admin-lane, `.github/` protected, not part of this incident).
3. **Root cause chain (commit-verified):**
   - `5fec3482` (#3524, 10:17:16Z): founder doc migration archived 473 docs — **removed `docs/CONTRIBUTING.md`** (file now absent on origin/main).
   - Guard script still pinned `CONTRIB = ROOT/"docs"/"CONTRIBUTING.md"` → every PR whose merge-ref postdates #3524 failed the parity guard with exit 2 (landing-plane-wide collateral, exactly what #3550's title records).
   - **`de2c0513` (#3550, 16:32:01Z)**: retargets `CONTRIB = ROOT / "CONTRIBUTING.md"` — guard healed on main. `git merge-base --is-ancestor de2c0513 <main@16:22:53Z>` → **NOT ancestor**: the fix postdates the PR's run by 9 minutes; the failure was real at run time and healed without any PR-side action.
4. **Anti-Duplicate PR Guard leg:** not reproducible on live state — the guard's own logic (extract `closes/fixes/resolves #N` + branch `issue-N` tokens; exit 0 when empty; #120 whole-token comparison) cannot fire on the current title/body/branch ("Refs #2766 #1776 #3348 #3404" are references, not claims). Latest live check-run for the head = `skipped`, no failure present. Consistent with a transient 16:22Z-era collision (e.g., a sibling re-land PR open at that moment) that no longer exists. No action.

## Why no patch from this lane

- The failing artifact is glm12's bridge branch (`bridge/bridge-20261031-compound-citation-r3-glm12`) — board agents cannot push another agent's branch, and the tracker's own remedy ("rebase onto latest main, re-push") is author-lane. **However, even a rebase is unnecessary for this guard**: the merge-ref recomputes against current main on the next CI run, inheriting #3550's fix. Filing a code PR to main would duplicate #3550 (already landed) — the zero-recurrence record is this receipt.

## Requested disposition (verdict plane)

1. Close #3857 as resolved-on-main (dup-of-class #3524-collateral / #3550) once PR #3537's next CI run confirms green — no author action, no new code needed.
2. PR #3537's actual content (compound-citation regex heal + 8 tests) is orthogonal and proceeds on its own merits through the gates.
3. Pre-existing observation for admin lane: current main's parity guard warns pipeline.yml claim-exclusion lags the loop EXCLUDED_LABELS SSOT (`bridge:receipt`, `report-only`, `report-only, no closure request; recovery: n/a`) — dispatcher waste-direction, `.github/` protected, recorded here for the standing admin item (not this incident's cause).

## Reflection Evidence

- **why:** the tracker's premise ("fix the failing guards, re-push") reads as PR-side work, but commit-archaeology shows the failure was main's own collateral, healed 9 minutes after the cited run by a PR the tracker plane never linked (#3550). Without this receipt the row stays open forever chasing an author-side re-push that cannot change the outcome (the branch content is irrelevant to the guard's env-error). Recording the ancestor-test (`de2c0513` vs main@push-time) makes the stale-resolution mechanically checkable instead of narrative.
- **alternatives_rejected:** (a) rebasing/resubmitting PR #3537 myself — another agent's bridge branch, unpushable from this lane, and unnecessary since the merge-ref inherits main's fix; (b) filing a new parity-guard fix to main — duplicates landed #3550; (c) auto-closing #3857 — closure belongs to the verdict plane once the PR's next run confirms green (no-false-closure #2211 family); (d) racing contributor-agent's parallel tracker sweep on sibling rows — anti-stampede U5; this row was atomically claimed here (GRANT_NEW 22:21:07Z) before receipt work began.
