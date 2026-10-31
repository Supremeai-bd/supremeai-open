# #4471 remedy — apply-ready verified one-line patch for the protected lane (fast-lint fail-closed index `--check`, recurring #1630 stale-index landing hole)

> **Agent:** GLM Agent 08 (Job ID 486735) · **Cycle:** 2026-11-01 00:08+08 · **Dispatch:** `continuous_agent_loop.py` → #4471 (solver, classified ci-fixer)
> **Lane:** report-only evidence for the admin/HITL lane — the bridge client gate rejects automatic writes to protected paths (first-hand error, this cycle: *"Path '.github/workflows/pipeline.yml' is protected (.github/). Bridge lane does not accept automatic writes to protected paths."*). Same lane pattern as `3527_REMEDY1_PROTECTED_PATCH_2026-10-31.md`. Refs #4471 #1630 (bare).

## What is ready (verified first-hand, apply as-is)

A **one-line** change in `.github/workflows/pipeline.yml` fast-lint step (blob `0fa2f6210b6a` at base `ec71682` — re-verify CAS before apply):

```diff
--- a/.github/workflows/pipeline.yml
+++ b/.github/workflows/pipeline.yml
@@ -568,7 +568,7 @@ jobs:
         run: |
           set -euo pipefail
           # Self-healing for script index freshness if scripts/ changed
-          python3 scripts/ops/generate_script_index.py || true
+          python3 scripts/ops/generate_script_index.py --check
           python3 scripts/ci/deploy_preflight_guard.py --step1-syntax
       - name: Run import-contract guard
         run: |
```

`|| true` swallowed the generator's exit code, so the step silently **regenerated** a stale `_INDEX.md` on every run instead of enforcing freshness — the exact recurring #1630 stale-index landing hole #4471 re-flags. `--check` is the generator's own documented CI contract ("exits 1 when stale", `scripts/ops/generate_script_index.py:380`), so zero new code is needed: the minimal swap is the whole fix (invariant #7, simplest solution).

## Verification at authoring time (3-tier)

1. **Reflection:** live-main pre-patch census — hole present at `pipeline.yml:571` (`|| true`), `--check` flag declared at `generate_script_index.py:380`; issue not claimed (`latestClaim: null`) before work; 1-file diff, 1 ins/1 del, nothing else touched.
2. **Boot smoke:** patched-file YAML parse OK (`yaml.safe_load`); fresh-main `python3 scripts/ops/generate_script_index.py --check` → `OK: ... up to date (559 scripts, 6 hand sections)`, exit 0 — so main CI stays green immediately after the swap.
3. **Tests (negative test, fail-closed proven):** appended a probe line to `scripts/ops/_INDEX.md` → `--check` printed `STALE: ... differs from the regenerated index (559 live scripts found)` and **exited 1**; `git checkout` restore → exit 0 again. The swapped line therefore fails the job exactly when the index is stale — the enforcement #4471 demands.

## Why this lane ends at the admin

The remedy is mechanically complete and verified, but the target file lives under `.github/` — a protected path (AGENTS.md boundary rules; bridge contract `protectedPathsToAdminReview`; bridge intake hard-rejects automatic writes, first-hand error quoted above). Fork-PR is unavailable to zero-credential agents. The patch is apply-ready above; an admin apply turns fast-lint into a real freshness gate. Residual watch: if the admin prefers a separate check step over the in-place swap, `--check` must still gate the job — any variant that keeps `|| true` on the regen path re-opens the hole.

## Never-do

- No claim of closure: the issue stays open until the admin applies the patch (false-closure #2211/#2225 family — this receipt is Refs-only, no `Closes` line anywhere).
- No forcing the diff through other lanes (`full_file` on the protected path would be rejected identically; satellite lanes are out of scope for a board-side workflow fix).
- No local commit of the working-tree edit: the scratch branch was reverted to `origin/main` (`ec71682`) after the bridge rejection — the only durable artifact is this evidence file.

---

**বাংলা (GLM Agent 08):** #4471-এর সম্পূর্ণ সমাধান এক লাইনের পরিবর্তন — fast-lint-এ `|| true` নীরবে ইনডেক্স পুনর্জন্ম দিয়ে #1630 পরিবারের stale-index ল্যান্ডিং-হোল খোলা রাখত; সেটিকে জেনারেটরের নথিভুক্ত CI চুক্তি `--check`-এ বদলে fail-closed করা হয়েছে। প্রমাণ: প্যাচ-পূর্ব main-এ হোল বর্তমান (:571), `--check` ফ্ল্যাগ বিদ্যমান (:380), fresh main-এ exit 0 (৫৫৯ script, ৬ hand section — অর্থাৎ সোয়াপের পরও CI সবুজ), এবং নেগেটিভ টেস্টে কৃত্রিম স্টেইল ইনডেক্সে **exit 1** (enforcement প্রমাণিত), পুনরুদ্ধারে exit 0। কিন্তু `.github/` protected path — bridge lane স্বয়ংক্রিয় রাইট নেয় না (প্রথম-হাতে ত্রুটি উদ্ধৃত), তাই প্যাচটি apply-ready অবস্থায় admin lane-এ জমা হলো (আগের #3527 remedy-1 প্রেসিডেন্টের একই লেন)। ইস্যুটি খোলা থাকবে যতক্ষণ না admin প্রয়োগ করেন — মিথ্যা closure নয়।
