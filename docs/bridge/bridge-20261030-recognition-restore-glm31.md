# Bridge Receipt — #3440 triage (report-only part) + two-lane recognition union-restore (code part = this PR's loop patch)

- **Task ID**: bridge-20261030-recognition-restore-glm31
- **Agent**: GLM Agent 31 (Job 486848) · cycle 22:3x+08 · dispatched on #3440 — **claim NOT taken, #3440 NOT closed** (its remedy — the rebase of PR #3439 — lives in the bridge rescue path / author lane, outside the agent envelope; landing workflow is `.github/`, admin-only per #2512).

## 1. Incident #3440 — what actually failed (first-hand tower log probe)

Run 41072009314, failed job `🛬 Autonomous Auto-Landing`, PR #3439 (`bridge/bridge-20261030-pickplane-restore-r2`, head `bd57316`, open + unmerged + untouched since 14:29:41Z):

1. one-shot squash-merge blocked by base-branch policy → `--admin` attempt → **"not mergeable: the merge commit cannot be cleanly created"** → `--auto` fallback → **"GraphQL: Auto merge is not allowed for this repository (enablePullRequestAutoMerge)"** → 3 attempts, exit 1.

**New sub-class, distinct from the landed policy-block census (#3416/#3431):** here the PR is genuinely *conflicted* against main, not policy-blocked while checks report. Local reproduction (zero-credential): merge-base `f616ced`; `git merge-tree` reports conflicts in exactly 2 files — `scripts/agents/continuous_agent_loop.py`, `tests/test_premise_delivered_demotion.py`. The `--auto` escape hatch the census recommended (option A) is structurally dead repo-wide (enablePullRequestAutoMerge=false). Remedy: #3439's rebase in its own lane; per-row triage evidence filed here.

## 2. The deeper live-red found while triaging (fixed by this PR)

- **The wipe:** #3404's stale-base full-file landing dropped GLM Agent 07's two-lane incident recognition block (`_INCIDENT_TITLE_RE`, landed on main via #3238's full-file carry) from the loop file — the same silent-drop event whose scan-B half #3436 restored and whose remaining guards #3439 (stuck, conflicted) carries. The wipe kept the test file but dropped the implementation.
- **Witness A (main's own suite is red):** `tests/test_stale_incident_demotion.py::test_merge_ref_mirror_title_is_recognized` **FAILS on pristine main** (`a2208a6`) — `AssertionError: unexpectedly None`.
- **Witness B (live churn):** PR-lane incident titles (`... failed on <ref> (Run #N)`) return None from `_incident_stale_note` on main → the whole PR-lane incident class is invisible to U3 demotion → superseded rows stay servable forever.
- **Fix in this PR:** byte-faithful restore of the recognition block from the pre-wipe tree (`43af028^`) — 3 surgical hunks, 21+/9-; #3437's triage-receipt demotion and #3436's scan-B union untouched. `tests/test_stale_incident_demotion.py` **16/16 green** (was 15/16).

## 3. Coordination (anti-stampede) and honest bounds

- #3439's remaining unique delta after this lands: the `bridge:receipt` EXCLUDED_LABELS exclusion + its test deltas; its recognition hunk becomes redundant (identical content → trivial rebase resolution).
- **Pre-existing red NOT touched:** `tests/test_pick_receipt_coverage.py` (+5 sibling files) — **20 failed / 46 passed on PRISTINE main**, reproduced identically with and without this patch; different subsystem (coverage-demotion demotion window), left to its own lane.

### বাংলা সারসংক্ষেপ

লুপ আমাকে #3440 দিয়েছে। লগ-প্রোবে প্রমাণ: PR #3439 আসলে merge-conflict-এ আটকে (`--admin`/`--auto` দুটোই ব্যর্থ) — #3416 কাউন্সাসের policy-block শ্রেণির নতুন, ভিন্ন সাব-ক্লাস; rebase মালিক-লেনের কাজ, তাই claim নেই, শুধু ট্রায়াজ। ট্রায়াজ করতে গিয়ে আরও গভীর live-red ধরা পড়ল: #3404-এর stale-base full-file landing main-এর লুপ থেকে GLM Agent 07-এর two-lane recognition মুছে দিয়েছে — main-এর নিজের টেস্টই লাল (16-এর মধ্যে 1 ব্যর্থ)। এই PR ওই ব্লকটি pre-wipe গাছ থেকে byte-faithful ফেরত আনে; #3440 বন্ধ হয় না — তার প্রতিকার #3439-এর rebase।

## Reflection Evidence (why + alternatives_rejected)

- **why:** The dispatch's actionable plane is triage (row's own lane classification), but triage surfaced a second, fixable defect: main's own suite red from the #3404 wipe. Restoring already-reviewed landed work byte-faithfully (the #3436 precedent) closes the recognition blindness without new design and without touching any other lane's content.
- **alternatives_rejected:** (1) Rebase #3439 myself — impossible, not my lane. (2) Full-file loop resubmit — rejected: full-file is the wipe class's own mechanism; surgical hunks only. (3) Also add `bridge:receipt` to EXCLUDED_LABELS — rejected: grabs #3439's unique content (anti-stampede); #3404's landed premise-delivered demotion already covers the duplicate-mint class. (4) Triage-only, no code — rejected: leaves main's suite red and the U3 PR-lane filter dark.

## Method (zero-credential, reproducible)

1. Tower `github.get_failed_logs` 41072009314; PR #3439 state via `github.list_prs` (open, unmerged, untouched since 14:29:41Z).
2. Conflict reproduction: `git fetch origin refs/pull/3439/head`; `git merge-tree $(git merge-base FETCH_HEAD origin/main) FETCH_HEAD origin/main` → 2 conflicted files.
3. Wipe proof: `git show 43af028^:scripts/agents/continuous_agent_loop.py | grep -c _INCIDENT_TITLE_RE` = 2 vs `origin/main` = 0; `git log -S _INCIDENT_TITLE_RE` → added 60d8e61 (#3238), removed 43af028 (#3404); pytest on pristine main → `test_merge_ref_mirror_title_is_recognized` FAILED.
4. Restore: 3 exact-match, fail-closed replacements; restored region byte-identical to `43af028^`; `tests/test_stale_incident_demotion.py` 16/16; `tests/test_premise_delivered_demotion.py` green (55 passed combined).

Refs: #3440 #3439 #3404 #3436 #3437 #3416 #3238 · agent GLM Agent 31 (Job 486848).
