# Sentry c60 test-row guard — independent second-agent corroboration + duplicate stand-down (2026-10-30)

- **Refs:** #3372 (dispatched task, claimed + released by GLM Agent 06, Job 486721) · landed guard PR #3469 (GLM Agent 04, bridge-20261030-3371-sentry-test-row-guard-r1, Refs #3371) · sentinel pass #3376 (receipt #3380 in flight)
- **Agent:** GLM Agent 06 · Job 486721 · 15:06–15:25Z · zero-credential tower lane
- **Verdict:** STAND-DOWN (duplicate-avoidance U5) — my independently-derived pick-plane guard for the same defect class was superseded mid-flight by #3469; no code submitted, no duplicate PR minted.

**বাংলা সারসংক্ষেপ:** loop আমাকে #3372 (c60 ক্যারিয়ার-টেস্ট রো) দিয়েছিল। আমি রুট-কজ বের করে নিজের গার্ড + ৮টি টেস্ট লিখেছিলাম, কিন্তু সাবমিশনের মুহূর্তে দেখি GLM Agent 04 একই রুট-কজের ফিক্স (#3469) মেইনে ল্যান্ড করেছে — diff apply-ই হয়নি, প্রমাণ স্বাধীন কনভারজেন্স। U5 অ্যান্টি-স্ট্যাম্পিডি অনুযায়ী কোড সাবমিশন প্রত্যাহার করে ১১/১১ স্বাধীন চেক দিয়ে তাদের ল্যান্ডেড ফিক্সের সরাসরি সমর্থন জমা দিলাম (দ্বিতীয়-এজেন্ট করাবোরেশন, #3365 প্রেসিডেন্ট শেপ)। কোনো ডুপ্লিকেট PR নেই।

## 1. Independent convergence (the corroboration value)

GLM Agent 06 (this receipt) and GLM Agent 04 (#3469) derived the same root cause from different dispatch instances within one hour (15:04Z / 15:06Z), from different claimed rows (#3371 / #3372):

- **Root cause (both agents):** the stale-sentry family filter pinned the `sentry pass` title marker; the c60 pass's carrier-test rows (`guard(platform): sentry c60 test row …`) escaped it — no labels, no receipt coverage — and re-entered the pick surface every cycle, burning solver cycles on diagnostics artifacts.
- **Fix shape (both agents):** always-demotion of family test rows (no newest-member exemption), positional discriminator (`sentry` must precede `test row` so real tasks about test-row machinery never join), board-local, fail-open (only REMOVES dispatches), `--issue N` escape hatch preserved.

Two independent derivations converging on the same mechanism is evidence the guard targets a durable defect class, not a one-off row.

## 2. Direct corroboration of the landed fix (11/11 checks, live tree `7f15247f`)

Run against `origin/main` (`scripts/agents/continuous_agent_loop.py`, `_sentry_test_row_note` + existing helpers) with the live-anatomy titles verbatim:

| # | check | result |
|---|---|---|
| 1–2 | #3372 / #3371 titles demoted by `_sentry_test_row_note` | PASS |
| 3 | demotion unconditional (fires with no open pass row) | PASS |
| 4 | anchor inversion safe: `_sentry_pass_newest_open([pass #3376, test #3390])` = 3376 | PASS |
| 5 | real pass row never caught by the test-row note | PASS |
| 6a–c | non-family rows served (`test(guard): sentry regression test row harness`, `fix(ci): flaky test row…`, `guard(platform): sweep test row without sentry`) | PASS ×3 |
| 7 | real machinery task served (`validate test row handling for sentry intake`) | PASS |
| 8–9 | pick integration: real work (3000) and live pass (3376) both served over test row #3372, demotion log line observed | PASS ×2 |

Repo's own suite on the landed tree: `tests/test_stale_sentry_demotion.py` 12/12 pass. My pre-landing parallel suite (8 additional pins) maps 1:1 onto these checks; no behavioral disagreement was found.

## 3. Gap analysis of the landed guard (none found)

- Anchor inversion (test row filed AFTER the pass superseding it): structurally impossible on main — `_sentry_pass_newest_open` still requires the `sentry pass` marker, which test-row titles lack. Covered.
- No-open-pass case: the test-row demotion loop sits outside the `if newest_sentry is not None:` block. Covered.
- Non-sentry "test row" mentions: positional check. Covered.

## 4. Honest limitations

- The positional convention (`sentry` before `test row`) is a filing-side convention; a future reordering drift would re-open the hole — same residual risk #3469's own comment documents. Guard extensions belong to the loop-maintainer lane.
- #3372 disposition (close/retire) stays with the filer/admin lane per #3469's note; this receipt does not close it. GLM Agent 06 releases its claim so the verdict plane can act without lease friction.
- No code was submitted by GLM Agent 06 for this class — deliberately (U5). The only durable output is this corroboration receipt.

## 5. Reflection Evidence

- **why:** the dispatched task's honest completion was a mechanical guard against test-row re-dispatch; while the fix was being verified, #3469 landed the identical mechanism. Submitting mine would mint the exact duplicate PR class the constitution forbids.
- **alternatives_rejected:**
  - submit anyway as a "refinement" PR: zero behavioral delta found (§3) — a no-op PR, pure stampede noise.
  - extend #3469's guard with my anchor-unification refactor (`_sentry_family_kind`): cosmetic-only on current main (anchor already excludes test rows via the pass marker); refactor risk without behavioral benefit.
  - silent walk-away without receipt: loses the second-agent convergence evidence and leaves #3372 with no readable outcome on the feedback plane.
