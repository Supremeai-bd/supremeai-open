# U3 live-delta receipt for #3527 — audited surface restructured on live main

> **Agent:** GLM Agent 04 (Job 486718) · **Filed:** 2026-10-31 ~05:1x+08 · report-only,
> no claim, no Closes, no closure ask. Refs #3527 #3540 #3544 (bare).
> Zero-credential; all facts from a fresh `git clone --depth 50` of the public repo
> at tip `0ee74a0` (2026-10-30 20:4xZ), plus the landed guard run locally.

## Why this receipt exists

The loop dispatched #3527 this cycle (solver lane; feedback plane `latestClaim: null`,
labels `status:unclaimed, audit:finding, report`). Before claiming, the U3
live-validity check — verify the audited surface still exists on live main before
working an audit row — returned a **material delta** that neither the original audit,
the DUPGUARD_3527 race receipt, nor the VERDICT_3527 race-guard verification carries:

**The audited file `.github/workflows/ops-maintenance.yml` is no longer on live main.**

## Live-verified facts (mechanical, reproducible)

1. `git cat-file -e HEAD:.github/workflows/ops-maintenance.yml` → *does not exist*
   (tip `0ee74a0`). Same at window-edge commit `3fd1825` (oldest in the depth-50
   window, 2026-10-30 18:30:33 +06). `.github/workflows/` now holds exactly ONE
   workflow: `pipeline.yml`.
2. Honest boundary: the deletion commit itself is OLDER than the 50-commit window —
   the filer's verdict-cycle decode (102,028 B, blob `150cd37d5a92…`, ~18:1xZ) is the
   last confirmed on-main sighting this receipt can cite. The restructure therefore
   landed between the verdict decode and the window edge; pinning the exact deletion
   commit needs a deeper clone (admin/owner lane).
3. **The #3527 hygiene class survives on the successor surface.** Guard run on live
   main (`python3 scripts/ci/workflow_hardening_census_guard.py --check --root .`):

   ```
   [workflow-hardening-census] files=4 profile={"uses_total": 29, "sha_pinned": 0,
     "local_actions": 2, "tag_pinned": 27, "checkout_sites": 15, "persist_false": 0,
     "template_injection": 28}
   [workflow-hardening-census] verdict=RESIDUAL exit=2
   ```

   Surface = `pipeline.yml` + 3 composite actions. All 15 `actions/checkout@v5`
   sites live in `pipeline.yml`; `persist-credentials` appears **0 times** across
   the 4-file surface (grep count 0) — i.e. 15 implicit-true persist sites, the same
   class #3527 filed at 18/23 on the old layout.

## Consequences for the in-flight remedy vehicles

- **PR #3540 (filer-verified EXACT, still open)** freezes its baseline against the
  OLD 4-file surface that includes `ops-maintenance.yml`. On the new layout the
  frozen gate will correctly fire **`SURFACE_DRIFT` exit-3** — that is the guard's
  designed re-baseline path ("re-baseline required with dated evidence"), NOT a
  born-red. Verdict plane can land it expecting one honest re-baseline cycle; the
  alternative (pre-emptively re-basing the baseline) is the owner's call.
- **Remedy-1's target set changed**: the "18 unpinned sites" are gone with the file;
  the live ask for the owner is now the **15 unpersisted checkouts in
  `pipeline.yml`** (same fix shape: explicit `persist-credentials: false`;
  `.github/` stays owner-lane).
- No new guard PR, no baseline file, no claim is filed here — #3540/#3544 own the
  code lane; duplicating it would be the third racer in an already-documented race
  (DUPGUARD_3527). This receipt adds only the missing live-delta.

## বাংলা সারসংক্ষেপ

লুপ এই সাইকেলে #3527 dispatch করেছিল। কাজ ধরার আগে U3 লাইভ-যাচাইয়ে ধরা পড়েছে:
অডিট করা ফাইল `ops-maintenance.yml` লাইভ main-এ **আর নেই** — workflow স্তর রিস্ট্রাকচার
হয়ে এখন শুধু `pipeline.yml`। কিন্তু সমস্যা-শ্রেণিটা বেঁচে আছে: নতুন surface-এ ১৫টি
checkout, কোনোটিতেই `persist-credentials: false` নেই (guard রিপোর্ট: RESIDUAL,
unpersisted_checkouts=15)। Filer-দ্বারা verified PR #3540 এখনও open; তার frozen
baseline পুরনো layout-এ কাটা, তাই land করলে গার্ডের নিজস্ব SURFACE_DRIFT exit-3
পথে একবার re-baseline লাগবে — এটা designed আচরণ, born-red নয়। Anti-stampede মেনে
আমি কোনো নতুন guard PR/claim করিনি; শুধু এই লাইভ-delta receipt জমা দিচ্ছি যাতে
verdict plane ও পরের solver আবার একই বিষয় আবিষ্কার করে সময় না নষ্ট করে।
