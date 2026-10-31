# #4471 tip-refresh: premise re-verified on live main `2f1268c` + first incident-faithful negative proof (the real #4450 regressed blob, not a synthetic probe)

> **Agent:** GLM Agent 05 (Job ID 486719) · **Cycle:** 2026-11-01 03:05+08 · **Dispatch:** `continuous_agent_loop.py` bare run -> ASSIGNED ROLE solver, highest-priority unclaimed issue = 4471, with an explicit order: the landing cross-scan ran DARK (both transports), so "re-verify the row's premise on live main before claiming".
> **Lane:** report-only evidence for the admin/HITL lane — the remedy lives in `.github/` (protected; bridge lane hard-rejects automatic writes, per GLM 08's first-hand error). Refs #4471 #1630 (bare, no `Closes` line — closure stays with the admin apply).

## What is new here (unique delta, not a re-statement)

Fifth independent confirmation on 4471 (GLM 09 discovery -> GLM 08 apply-ready patch -> GLM 13 ordering upgrade -> GLM 25 sequence proof -> this one), and it carries two things nobody had produced:

1. **Loop-mandated premise re-verification on the current tip.** GLM 25's sequence ran on `889da7c`; two landing waves later (CORS fix 4527, sentry c89 wave), the loop re-dispatched the row but its own cross-scan was dark, so a fresh human-independent check was ordered. Result at tip `2f1268c`, ff-only fresh, first-hand: the flawed verb is still live — `.github/workflows/pipeline.yml:571` reads `python3 scripts/ops/generate_script_index.py || true` (job fast-lint-syntax-preflight); the guard step (`deploy_preflight_guard.py --step1-syntax`) still runs immediately after it at line 572, so the GLM 13 ordering defect is also still in place; the generator's CI contract is present (`generate_script_index.py:380` `--check`, "exit 1 if the output file is out of date"). **Freshness datum for the admin lane: as of 03:05+08 Nov 1 the one-line swap remains unapplied on main.**
2. **First incident-faithful negative proof.** Prior negative tests simulated staleness with a synthetic appended probe line. This receipt replays the actual failure artifact instead: the #4450-regressed `_INDEX.md` (the real blob that burned the fleet-wide census red), fetched with `git show 7c731bf:scripts/ops/_INDEX.md` (66,533 bytes), dropped into a throwaway worktree at `2f1268c` as the only mutation, then `--check`:

```
STALE: /tmp/wt4471/scripts/ops/_INDEX.md differs from the regenerated index (559 live scripts found). Run: python3 scripts/ops/generate_script_index.py
exit 1
```

   Worktree removed afterwards; main tree untouched (worktree verified clean). Reading: with the one-line swap in place, fast-lint fails exactly on the artifact class that actually landed in the #4450 wave — the gate would have blocked that regression at CI, before review, with zero synthetic setup.

## Healthy-path control (same tip)

Fresh ff-only checkout, no mutation: `--check` prints `OK: ... is up to date (559 scripts, 6 hand sections)` and exits 0 — the fixed gate stays green on healthy PRs, so the swap costs nothing on the happy path.

## Claim lifecycle (first on this row)

All four prior evidence authors deliberately took no claim. This cycle the loop dispatched the row as solver, the feedback plane showed `latestClaim: null` immediately before work (stale-claim guard), and the claim went through atomically: `GRANT_NEW`, agentId `GLM-Agent-05--Job-486719-`, TTL 30m, planes `label:status:claimed` + `comment:atomic-claim`. This receipt completes the solver turn; the lease is released after landing so the row returns to the board with its evidence trail — the issue itself stays open until an admin applies the swap (no false closure, #2211/#2225 family respected).

## Remedy (unchanged, minimal, apply-ready per GLM 08)

One line in the fast-lint step: replace the regen `|| true` with `python3 scripts/ops/generate_script_index.py --check`; `set -euo pipefail` in the same step propagates the exit. Nothing else is needed — GLM 25 proved `--check` is memory-only, so no regen can pre-empt the gate, and this receipt proves the gate fires on the real incident blob at the current tip.

## Never-do

- No `Closes`/`Fixes` anywhere: the hole closes only at an admin apply.
- No `full_file` attempt against `.github/` (protected write, hard-rejected lane), no fork-PR (zero-credential agents), no re-run of the instance regen wave (#4463/#4468 already raced; the class ends at CI).
- No weakening of anyone's tests or receipts; this file adds one docs artifact under the non-protected `docs/reports/` lane only.

---

**বাংলা (GLM Agent 05):** লুপ এই সাইকেলে 4471 সলভার-রোলে পাঠিয়েছিল, কিন্তু তার নিজের cross-scan অন্ধ ছিল — তাই claim-এর আগে বর্তমান টিপে (2f1268c) premise নিজ হাতে যাচাই করেছি: `|| true` এখনও pipeline.yml:571-এ জীবিত, ordering ত্রুটিও বহাল, অর্থাৎ এক-লাইন সোয়াপ এখনও প্রয়োগ হয়নি (admin lane-এর জন্য freshness datum)। নতুন প্রমাণ: কৃত্রিম probe নয়, #4450 তরঙ্গের প্রকৃত regressed blob (7c731bf) বর্তমান টিপের কর্ম-গাছে বসিয়ে `--check` চালালে exit 1 — অর্থাৎ সোয়াপ থাকলে সেই প্রকৃত regression CI-তেই আটকাত। সুস্থ গাছে exit 0 (happy path অক্ষত)। প্রথম solver-claim (GRANT_NEW) নিয়ে প্রমাণ-রিসিট জমা দিলাম; ইস্যু খোলা থাকবে — বন্ধ করার সিদ্ধান্ত admin-এর।
