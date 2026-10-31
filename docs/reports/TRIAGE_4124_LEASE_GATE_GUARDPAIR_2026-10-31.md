# TRIAGE — #4124 re-introduced the #3573 dispatch time-gate: two AST-pinned guards went red on main, spec §4c now contradicts the shipped loop, and the "smart cooldown" cadence half is dead config

- **Lane**: `bridge-20261031-4124-leasegate-guardpair-glm04` — self-initiated triage, P1-high (constitution-facing reds on main, unowned, guard pair broken by the same landing that claims "8/8 PASS")
- **Agent**: GLM Agent 04 (Job ID 486718, slot agent-3) · worktree verified at `a9323f45` (0-behind) · zero-credential throughout
- **Trigger**: this cycle's loop dispatch ran clean, but the shipped `agent_cadence.json` notes changed regime; routine verification of the pick plane surfaced the contradiction. Related: glm28's pytest-redpair triage (#4122) — same root cause, DIFFERENT red pair (disjointness below).

## বাংলা সারসংক্ষেপ

প্রতিষ্ঠাতার `#4124` কমিট (09:02+06) দুটি কাজ করেছে: (১) `pick_next_issue`-এ ৩০-মিনিট lease-store কুলডাউন ফিরিয়ে এনেছে, (২) `agent_cadence.json`-এ `#3573`-এর event-driven notes মুছে `cadences_hours` (4/6/8/12 ঘণ্টা) ফিরিয়ে এনেছে। কিন্তু `#3573`-এর founder mandate-ই ছিল "zero artificial timer locks" — এই ৩০-মিনিট gate ছিল সেই "fixed guess" যা সরানো হয়েছিল। ফল: **দুটি AST-pinned guard টেস্ট এখন main-এ লাল** (`test_claim_lease_ssot.py::test_02`, `test_agent_cadence.py::test_pick_has_no_dispatch_time_gate`), **AGENT_LOOP_SPEC.md §4c এখন শিপড কোডের সরাসরি বিরোধে**, এবং `cadences_hours`-এর ঘণ্টা-মানগুলো লুপ আদৌ পড়ে না (keys-only) — অর্থাৎ "smart cooldown"-এর cadence অর্ধটি মৃত কনফিগ। সাধারণ মূল কারণ glm28-এর থিসিসেরই তৃতীয় প্রমাণ: ৮-টিয়ার verify ladder-এ pytest নেই — `#4097`, `#4106`, এখন `#4124` তিনটিই "8/8 PASS" দাবি করে লাল গার্ড নিয়ে জমেছে। মালিকের সিদ্ধান্ত চুক্তি এই রিপোর্টে (Option A: mandate অপরিবর্তিত, gate সরাও; Option B: সত্যিকারের নতুন mandate, তবে governance PR-এ spec+tests+dead config সব একসাথে)।

## Ground truth (reproduced this cycle, worktree `a9323f45`, 0-behind)

`python3 -m pytest tests/test_claim_lease_ssot.py tests/test_agent_cadence.py -q`:

| # | Test | Result | First-red landing |
|---|------|--------|-------------------|
| R1 | `tests/test_claim_lease_ssot.py::ClaimLeaseSSOTPins::test_02_loop_source_has_no_time_gate_and_keeps_ssot_lineage` | FAILED — `AssertionError: 'LEASE' unexpectedly found in 'LOAD_ISSUE_LEASE_STORE'` | PR #4124 (`a9323f45`) |
| R2 | `tests/test_agent_cadence.py::TestEventDrivenContract::test_pick_has_no_dispatch_time_gate` | FAILED — same AST scan, same token | PR #4124 (`a9323f45`) |

34 sibling tests in the two files pass; both failures are deterministic and non-flaky (AST source scan, comment-immune by design). Both guards pin the SAME contract: **the dispatch pick plane (`pick_next_issue`) must stay clock-free** — the lease/journal names may appear only as the twin-demote in-flight input (#3738), never inside the gate. That is the mechanical form of the #3573 founder mandate ("no artificial waiting"; the old 30-minute window was documented in the SPEC itself as "a fixed guess, not lease renewal").

## Anatomy — what #4124 changed, plane by plane

1. **The pick gate (behavior, live):** `pick_next_issue` now reads `load_issue_lease_store()` and returns `False` for any issue dispatched by this runner within 1800 s. The #3573 Bangla rationale comment (dispatched-but-unclaimed work must be re-pickable immediately; the live claim probe and atomic `work_claim` are the only arbiters) was **deleted and replaced** by the gate. This is the exact exclusion the SPEC says is removed — a dispatched-but-unclaimed actionable issue is now invisible to the pick for 30 minutes (founder mandate 1 violated in code, on main).
2. **The spec (document, unchanged, now false):** `docs/AGENT_LOOP_SPEC.md` §4c still states the 30-minute time-window exclusion "is REMOVED", "founder mandate 1: no artificial waiting", and "(the claimability gate `is_claimable` is clock-free; AST-pinned)". Every clause is now contradicted by the shipped source. No spec edit rode the commit (`git show --stat a9323f45`: spec absent).
3. **The cadence config (half-dead):** `agent_cadence.json` re-gains `cadences_hours` (4/6/8/12) — but `load_cadence_config()` reads legacy `cadences_hours` KEYS as role order and **ignores the hour values by documented design** ("Legacy `cadences_hours` configs are accepted for one regime: their KEYS become the role order and the hour values are IGNORED (zero artificial timer locks)"). So the "smart 30-min cooldown" cadence half of the commit message is **dead config**: no code path reads those numbers. The new `notes` string ("Scheduled roles rotate on cadence when claimable issues <= 5") describes a rotation mechanism that does not exist in the loop (event-driven episode rotation per #3573 is intact); the config now documents a regime the code does not implement.
4. **merged_roles shrink (silent contract change):** `federation-auditor`, `task-auditor`, `ci-fixer`, `fixer` were dropped from `merged_roles` (4 of 6 mappings removed). `canonical_role()` now passes those names through unmerged. Any journal/state artifact or board row still citing the old names resolves differently than before the commit. AGENTS.md's cadence notes were likewise rewritten (the `#3573` reference is gone).
5. **The commit message vs the landed diff:** the message claims "Parity Guard passed" and "Verification Ladder: --verify-only passed all 8 tiers". Both may be literally true — the 8-tier ladder demonstrably does not run these two pytest surfaces (glm28's thesis, third datapoint below). The message also contains escaped-literal artifacts (`\scripts/agents/…\`, `\^Guditor`) consistent with an assembled-not-executed verification pass.

## Common root cause — the landing ladder's pytest blind spot (third datapoint)

`#4097` landed "8/8 PASS" over `test_25` red (glm28 R2); `#4106` landed "8/8 PASS" over the index gate red (glm28 R1); `#4124` landed "8/8 PASS" over THIS guard pair red. Three consecutive landings, three red pytest surfaces, zero ladder trips. The 8-tier ladder is real but pytest-blind; every constitution-facing pin (`test_constitution_freshness`, `test_claim_lease_ssot`, `test_agent_cadence`, `test_script_index_freshness`) is sub-second, pure-local, and deterministic. This report adds nothing new to glm28's recommendation — it corroborates it as a **recurring class (3/3 in one day)**: until the ladder runs the pinned pytest faces, "8/8 PASS" in a commit message certifies only the ladder's own surface.

## Fix contract (owner decision; the filer ships zero code edits)

- **Option A — the #3573 mandate stands (smaller diff):** remove the 1800 s lease check + `load_issue_lease_store` import from `pick_next_issue` (restore the deleted #3573 rationale comment), revert `agent_cadence.json` to v2 shape (`"version": 2`, event-driven notes, full 6-entry `merged_roles`), keep the version-tag purge. Both guards return green; spec §4c stays true. If a dispatch-cooldown is genuinely wanted, it must arrive as a NEW mandate (Option B), not as a silent re-land of the removed mechanism.
- **Option B — a genuine new regime (governance lane):** if the founder now WANTS the 30-minute cooldown, the change must land whole: (1) amend AGENT_LOOP_SPEC.md §4c (the "REMOVED/no artificial waiting/AST-pinned" clauses), (2) rewrite both guards to pin the NEW contract (and keep the twin-demote-only boundary pinned), (3) either implement the `cadences_hours` reading in the loop or delete the dead keys, (4) fix the `notes` string to describe real behavior, (5) decide `merged_roles` fate explicitly. A partial state where code, spec, config notes, and guards tell four different stories is the failure mode the Full-Scope Completeness invariant (9) exists to prevent.
- **Paired with either option (the actual root cause):** add the deterministic pytest faces to the landing ladder (or a pre-bridge intake step) — minimum: `tests/test_constitution_freshness.py`, `tests/test_claim_lease_ssot.py`, `tests/test_agent_cadence.py`, `tests/test_script_index_freshness.py`. Sub-second total; kills the 3/3 recurrence class mechanically (Zero-Recurrence invariant 6).

## Adjacency / disjointness (per the #2392 predicate)

- **glm28 redpair (#4122):** same root-cause thesis, different reds (R1 script-index — already healed by #4120; R2 `test_25` offline-escape-hatch — #4097's half-purge). This lane's pair is #4124-born, one hour later. The two reports are complementary halves of one recurrence class; neither supersedes the other.
- **CI_4617's six older picker reds:** different tests entirely (dead_import ratchet, federation_satellite_sync, license_ssot, script_index_freshness, parity_guard, tower_tool_name_drift). Not this pair.
- **#3573 lineage:** this lane does not re-litigate #3573; it reports a mechanical contract break of the regime #3573 landed. Cited as lineage, not adopted.
- **R96 branch-death rows, PR-plane dark (glm22 #3959), render-primary (glm10):** different planes; untouched here.

## Verification (3-tier)

- Tier 1 (reflection): commit-vs-diff-vs-spec three-way read at `a9323f45`; guard pair's AST scan reproduced; `load_cadence_config()` legacy path re-read to prove the hour-values-ignored design before calling the config dead.
- Tier 2 (boot smoke): `continuous_agent_loop.py` dispatch cycle ran this cycle: clean, claimable 0/5, board 3 rows, 0 behind origin/main.
- Tier 3 (tests): `pytest tests/test_claim_lease_ssot.py tests/test_agent_cadence.py -q` → **2 failed, 34 passed** (deterministic, rerun-stable); docs-only payload = one new report file (absent on main, no baseSha required); no claim taken, no closure claimed — the lane stays open until the owner contract lands.
