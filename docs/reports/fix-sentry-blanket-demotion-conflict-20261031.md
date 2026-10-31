# fix(pick): sentry blanket-exclusion vs demotion-family — one root cause, six reds

**Lane**: modify-existing-file ×2 (`scripts/agents/continuous_agent_loop.py`,
`tests/test_pick_excludes_receipt_wos.py`) + this report. Agent: GLM Agent 28
(Job ID: 486832). Cycle 13, 2026-10-31 12:28+08 dispatch.

## বাংলা সারসংক্ষেপ

মূল লুপের dispatch pick-এ দুটি পরস্পরবিরোধী sentry নিয়ন্ত্রণ একসাথে বসে ছিল:
(ক) `is_claimable`-এর ভেতরের ব্ল্যাঙ্কেট টাইটেল-বাদ ("sentry" শব্দ থাকলেই বাতিল)
এবং (খ) একই ফাংশনের নিচের board-local demotion পরিবার (stale-sentry →
sentry-test-row → twin → receipt-coverage), যার pinned চুক্তি: superseded fossil
বাদ, কিন্তু lone/newest sentinel কাজ হিসেবে serve হবে। ব্ল্যাঙ্কেট-বাদ আগেই
প্রতিটি sentry রোকে সরিয়ে দেয় — ফলে পরিবারটি dead code হয়ে যায় এবং ৫টি pinned
টেস্ট লাল থাকে। এ ছাড়া receipt-গার্ড টেস্টের একটি fixture নিজের docstring-ই
ভাঙত ("report-only" vs plain "report" label)। এক কারণ, ছয় লাল।

## Ground truth (HEAD 33db313, 0 behind)

| Red face | Failure | First-red landing |
| --- | --- | --- |
| test_stale_sentry_demotion: lone pass served | got '3000', expected '2237' | 1e28af1 (#3860) |
| test_stale_sentry_demotion: newest sentinel served | expected '3111', got None | 1e28af1 (#3860) |
| test_stale_sentry_demotion: pure mode contract | expected '2237', got '3000' | 1e28af1 (#3860) |
| test_sentry_test_row_demotion: demotion logged | log line never emitted | 1e28af1 (#3860) |
| test_sentry_test_row_demotion: pure mode contract | expected '3371', got '3401' | 1e28af1 (#3860) |
| test_pick_excludes_receipt_wos: no over-exclusion | expected '2538', got None | 1e28af1 (#3860) |

Pre-fix full census: 10 failed / 2222 passed / 13 skipped (71s).
Post-fix full census: 4 failed / 2228 passed / 13 skipped. Verify ladder 9/9
PASS; script index check OK.

## Root cause

1. **2026-10-30**: the board-local demotion family lands with an extensive
   pinned suite (stale-sentry #3050-family; test-row guard #3469; twin guard
   #3738). Contract: the family is the sole sentry arbiter on the live path;
   pure mode keeps the pre-change label-only contract byte-identical.
2. **2026-10-30 22:08Z**: #3860 (1e28af1, "respect lane declarations in the
   dispatch pick") re-adds `if "sentry" in title.lower(): return False` inside
   `is_claimable` — a blanket, mode-agnostic exclusion. The PR's own tests pin
   only the label plane; nothing pins the blanket sentry check.
3. The blanket runs BEFORE the family, so every sentry row (including the lone
   pass, the newest sentinel, pure-mode picks) never reaches the family. Five
   pins of the family break; the receipt guard's over-exclusion test breaks for
   a second, independent reason (fixture used the now-excluded "report-only"
   label, contradicting its own docstring "carrying only `report`").
4. #3860 landed with the suite red — the blind-ladder class documented in
   bridge-20261031-pytest-redpair-glm28 (#4122). Same class, third instance.

## Fix

1. Remove the blanket sentry title check from `is_claimable` (anchor-hub check
   stays — no pinned contract conflicts with it). The demotion family resumes
   as the sole sentry arbiter: fossils and test rows still never burn dispatch
   cycles in live mode; the sentinel duty survives.
2. Amend the receipt-guard fixture to plain "report" per its own docstring.
   #3860's label-plane SSOT stays fully honored.

`loop_v1.py` is deliberately untouched: its own test file pins its own
`is_claimable` (blanket included) — the lightweight variant is internally
consistent and has no demotion family to contradict.

## Remaining reds (documented, not this lane)

- test_25 (--offline): Option A/B owner contract filed in #4122 — pending.
- test_dead_import_drift: unused-import debt 361→368 — mechanical cleanup lane.
- test_js_dep_cve_guard + test_npm_dep_cve_guard: NEW-DRIFT advisories
  (follow-redirects, glob, minimatch) — pin bumps are a studio-owner decision
  per the guard's own fail-closed contract.

## Boundary

Code + test fixture only. No board row closure claimed; labels speak.
