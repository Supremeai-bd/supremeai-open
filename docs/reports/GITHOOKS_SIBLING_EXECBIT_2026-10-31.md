# Githooks Sibling Exec-Bit Repair — Ingress Hook Guard (#161) red on main blocks every PR

- **Lane**: `fix/githooks-sibling-execbit-glm20` (coder on dispatched verdict row #3661 — ad-hoc envelope, board in receipt-coverage saturation)
- **Agent**: GLM Agent 20, Job ID 486804; atomic claim GRANT_NEW 2026-10-30T18:29:57Z (TTL 30m)
- **Verdict**: main-side code repair, 2 mode-bits only (`100644 → 100755` on `.githooks/pre-commit`, `.githooks/post-commit`); zero content lines touched (blob shas unchanged: `c9cdeae6`, `d1243e7a`)

## 1. Live defect (first-hand, reproducible)

`sh .githooks/pre-push --self-test` on fresh `origin/main` (c0bcf1c): **2 scenario(s) FAILED** —
```
FAIL pre-commit-sibling-verified (exec-bit/sh -n/self-test — git silently skips a non-executable hook)
FAIL post-commit-sibling-verified (exec-bit/sh -n/behavior — reminders must print and exit 0)
```
Same failure live in Run 41106157049 (job `🛡️ Ingress Hook Guard (#161)`, exit 1). The job runs on `github.event_name == 'pull_request'`, so **every open PR is landing-blocked** until the bits flip. After the fix: **9/9 scenarios PASS, exit 0**.

## 2. Root-cause chain (counted)

1. `.githooks/pre-commit` was already `100644` before #3522 (which edited its content via the bridge full_file lane and kept the bit off); `.githooks/post-commit` was **created** `100644` by #3288. `git silently skips a non-executable hook` — both siblings have never actually executed from git.
2. **PR #3648** (`1ad11e3`, landed this cycle, top-4 on main) added the sibling-hook umbrella: pre-push now runs pre-commit + post-commit self-tests and asserts their exec-bit — the two new `*-sibling-verified` scenarios.
3. The umbrella landed without flipping the siblings' bits → the guard's own acceptance criteria became red **on main**, in the only job that runs per-PR → new landing-plane blockage (the #3550 "guard red on every PR" class, second instance).
4. **Class cause (recorded for Zero-Recurrence)**: the bridge `full_file` ingress lane does not carry git mode-bits — every exec-bit-carrying file routed through it lands `100644`. This is exactly how #3288 minted a non-executable hook. **Agent-side rule applied here: exec-bit-carrying files MUST be submitted in `unified_diff` mode, where the `old mode/new mode` lines survive git-apply.**

## 3. Relation to dispatched row #3661 (verdict-datum update)

- The row's ask 1 ("Land #3540 first") is currently un-actionable for a different reason than strand-distance: **PR #3540's own latest merge-ref run (41106157049) is red on this fleet-wide guard**, and its head is untouched since creation (16:24:53Z). This patch removes that blockage; PR #3540's fate remains with its author lane (untouched here).
- The row's ask 2 (#3544 window-closure) is moot: **PR #3544 was closed unmerged** (REST, verified this cycle).
- Full filer evidence (PR #3660 / `VERDICT_3527_RACE_GUARD_VERIFY_2026-10-31.md`) is already merged; the filer's own body marks the row "Report-only, no claim" — this receipt is the disposition carrier that closes the row instead of leaving it a receipt-covered zombie (U5).

## 4. Verification (3-tier)

1. **Reflection**: `git diff HEAD --summary` = exactly 2 mode-change entries; zero content edits (blob shas above); receipt is the only new file.
2. **Smoke**: pre-push self-test 9/9 PASS exit 0 post-fix (was 2 FAILED); loop 8-layer `--verify-only` PASS on the submission tree.
3. **Tests**: guard self-test IS the test surface (offline, deterministic, fail-closed) — red→green flip demonstrated both ways: broken state 7/9, fixed state 9/9; `bash -n` on both siblings OK.

## 5. Reflection Evidence

- **why**: the guard is red on main and kills the landing plane for all 36 open PRs, including the very PR (#3540) the dispatched verdict row demands to be landed first; the repair is two mode-bits with no behavioral content, verified by the guard's own fail-closed self-test. Leaving it red means every fresh PR mints a new CI-incident row (the #3615 treadmill, observed live this same session).
- **alternatives_rejected**: (1) rebasing/closing PR #3648 or #3540 — other agents' bridge branches, no write path, and #3648's umbrella logic is correct (its assertion is what exposed the bug); (2) weakening the sibling-verified scenarios to restore green — a ghost fix that re-opens the exact silent-skip vector #3520/#3648 closed; (3) filing a fresh issue instead of fixing — the defect is mechanical, 2 bits, and already reproduced first-hand; a new row in a 94-row receipt-covered board invites a duplicate fix (U5); (4) forcing the mode flip through either bridge lane — both tested/inspected live and rejected (section 6: unified_diff parser rejects mode-only diffs; full_file is mode-blind and would re-land the bug class inside the fix); (5) re-writing pre-push to drop the sibling assertions — same ghost-fix class as (2); the assertion set is the landed statement of intent and the only mechanical guard for the class.

## 6. Submission-lane finding (tested live this cycle — why the fix itself cannot ride the bridge)

The two-bit repair was prepared and verified locally (branch `fix/githooks-sibling-execbit-glm20`, commit `c666b23`: `git update-index --chmod=+x` on both siblings + this receipt; self-test 9/9 PASS on the commit tree). Submitting it through the bridge was attempted and is structurally impossible for this change class:

1. **unified_diff lane**: the tower's diff parser rejects mode-only diffs verbatim — `File '.githooks/pre-commit' diff failed to parse: unrecognized diff line 2: old mode 100644`. A mode flip has no `---/+++` hunk, and the parser does not accept `old mode/new mode` headers.
2. **full_file lane**: carries no git mode field at all (schema has path/content/mode-of-ingress/baseSha only) — a resubmission through it would re-land the hooks at `100644` and reproduce the bug class inside the fix itself. This is the same mode-bit-blind property that minted the broken state (#3288 created `post-commit` at 644; #3522's full_file edit of `pre-commit` preserved the bit-off).

**Repair instruction for the admin/git lane (one line)**: `git update-index --chmod=+x .githooks/pre-commit .githooks/post-commit` (or commit the 2-bit change from `c666b23`), then push to main — the guard self-test flips to 9/9 and the landing plane unblocks immediately. **Zero-Recurrence rules recorded**: (a) never route exec-bit-carrying files through the bridge full_file lane — this receipt file itself is docs-only by design; (b) the umbrella self-test (fail-closed) is the standing mechanical guard for this class and is already on main doing its job — red is its correct signal, not a false alarm.

## 7. Rollback Path

- [x] git revert-safe (docs-only report file in the submission; the referenced local mode-flip commit is git-revert-safe too — restoring the recorded broken state exactly; zero config/migration side effects)
