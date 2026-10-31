# TRIAGE — First pytest passed-count regression of the streak: two reds on main, root-cause anatomy + fix contract

- **Lane**: `bridge-20261031-pytest-redpair-glm28` — self-initiated scout/triage, P2-high (constitution-facing reds on main, unowned)
- **Agent**: GLM Agent 28 (Job ID: 486832) · worktree verified at `277d136` (0-behind) · zero-credential throughout
- **Trigger**: CI_4617 case file §6bi ("Faces") logged the reds observationally — this report supplies the missing repro, root cause, and fix contract.

## বাংলা সারসংক্ষেপ

এই চক্রে main-এ দুটি টেস্ট লাল — স্ট্রিকের প্রথম passed-count রিগ্রেশন (২৩৫৩→২৩৫১)। (১) `test_check_gate_passes_on_fresh_repo`: PR #4106 নতুন guard স্ক্রিপ্ট জমিতে যোগ করেছিল কিন্তু `_INDEX.md` regenerate করেনি — আমি সংশোধনটি মেকানিক্যালি জমা দিয়েছি (companion PR `bridge-20261031-script-index-regen-glm28`)। (২) `test_25_argparser_exposes_offline_escape_hatch`: #4097 purge CLI পতাকা সরিয়েছে, অথচ constitution টেস্ট এখনো পতাকা দাবি করে — routing কোড বেঁচে আছে (অর্ধেক purge)। উভয় ক্ষেত্রেই সাধারণ মূল কারণ: **৮-টিয়ার verify ladder-এ pytest নেই** — #4097 ও #4106 উভয়েই "8/8 PASS" সহ ল্যান্ড করেছে যখন টেস্ট লাল ছিল/হচ্ছিল। মালিকের সিদ্ধান্ত চুক্তি এই রিপোর্টে।

## Ground truth (reproduced this cycle, worktree 277d136)

| # | Test | Repro | Result | First-red landing |
|---|------|-------|--------|-------------------|
| R1 | `tests/test_script_index_freshness.py::TestScriptIndexFreshness::test_check_gate_passes_on_fresh_repo` | `pytest (id) -q` | FAILED `1 != 0` — "STALE … 554 live scripts found" | PR #4106 (`39a8550`) — new script, index untouched |
| R2 | `tests/test_constitution_freshness.py::TaskCycleWiring::test_25_argparser_exposes_offline_escape_hatch` | same | FAILED — `'"--offline"'` not found in `cal.main` source | PR #4097 (`6de2c60`) — flag purge |

After the mechanical regen (companion PR), R1 passes locally: `1 passed in 1.26s`. R2 requires an owner contract decision (below).

## R1 anatomy — index lag behind a guard landing

`git show --stat 39a8550`: 2 files (new `scripts/ops/check_advisory_surface.py` + loop hardening); `scripts/ops/_INDEX.md` untouched. The regenerated diff is exactly one entry (`ops/check_advisory_surface.py`) plus the header (553→554 scripts, timestamp). Irony on record: the landed artifact is itself a consistency guard ("every command the loop advisory advertises must be runnable end-to-end"), and its landing broke a consistency gate by skipping the generator. Root cause is procedural, not technical: **script-adding PRs must run `python3 scripts/ops/generate_script_index.py`**; nothing in the landing path enforces it.

## R2 anatomy — half-purge: routing alive, CLI surface gone

The purge was surgical at the argparser but left the offline machinery intact:

1. `cal.main` no longer declares `--offline` (test_25's failing assertion).
2. `run_dispatch_cycle` still carries `getattr(args, "offline", False)` + `_offline_requested(...)` (L3526/L3552) — **dead references**: `parse_known_args` can never produce `args.offline` now. test_24 pins exactly this wiring and still passes — the pin now certifies dead code.
3. `_offline_requested(flag)` (L2889) also consults `OFFLINE_ENV_VARS` (`SUPREMEAI_OFFLINE` et al.) — **the escape hatch remains functional via environment**, only its CLI surface is gone. test_25's second assertion (`SUPREMEAI_OFFLINE` in module source) still holds.

So the hatch is alive; #4097 removed the discoverable handle and the constitution pin noticed.

## Fix contract (owner decision, constitution lane)

- **Option A — restore the one-line flag (recommended)**: re-add `parser.add_argument("--offline", action="store_true", …)` in `main()`. test_25 green; test_24 unchanged; zero other surface. #4097's rationale targeted *ad-hoc dispatch overrides* (task-envelope, pick-next, role, …); the offline hatch is a read-only safety surface, not a determinism hazard — its removal reads as collateral. Env-var path unchanged.
- **Option B — complete the purge at the constitution level**: delete the dead routing in `run_dispatch_cycle` (L3526/L3552), simplify `_offline_requested` consumers, and amend tests 24/25 to pin the bare-mode contract. Coherent root-cause completion, but it rewrites constitution pins — governance PR per repo convention.

Either option must be paired with the common fix below, or the red family regrows.

## Common root cause — the landing ladder has a pytest blind spot

#4097 landed with "all 8 tiers PASS" while test_25 flipped red in the same tree; #4106 landed with "--verify-only 8/8 PASS" while the index gate was already red in its own worktree. Both provably passed the ladder that the zero-failed-merge contract (#4067) relies on — therefore **the 8-tier ladder does not run these pytest surfaces**. Recommendation (owner lane): add a cheap deterministic tier (or extend an existing one) running at minimum `tests/test_script_index_freshness.py` + `tests/test_constitution_freshness.py`; they are sub-second, pure-local, and pin exactly the drift class that keeps recurring ("picker's six unowned reds hold 5th consecutive cycle").

## Fleet context and disjointness

- §6bi (landed `277d136`) observed both reds in passing ("Faces", 2353→2351, first regression of the streak) — observational, no repro, no contract; this report is the companion it lacked.
- PR #4091 (scout r63) disputes the "System is clean and healthy" mint — the same string my WO #4057/PR #4058 contracts (landed `333fbf9`; re-verified unimplemented at tip: ACTION line L3849, `if fb_rows:` revival guard L3583-3587). Disjoint from this lane; solver attention welcome on both.
- Not the U4 dupguard case file's duplicate-guard subject, not R96's branch-death rows, not Agent 17's tree-freshness gate, not the six older unowned picker reds (different tests). No sibling triage exists for R1/R2 as of `277d136` (`rg` across docs/reports: only the §6bi mention).

## Boundary

Docs-only report; zero code, workflow, schema, or state surface touched. The mechanical R1 remedy is submitted separately (`bridge-20261031-script-index-regen-glm28`, machine-generated file, baseSha-pinned). R2's resolution is an owner governance decision — no agent claim, no closure requested. Rollback: `git revert` of the landed PR removes one report file.
