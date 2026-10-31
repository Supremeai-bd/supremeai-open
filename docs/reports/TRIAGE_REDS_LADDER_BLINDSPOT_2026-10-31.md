# TRIAGE — 12 red faces on main invisible to the 9-tier ladder (2026-10-31)

Agent: GLM Agent 19 (Job ID 486803) · Repro tree: origin/main 35a72f6 · Zero-credential lane.

## Headline

At 35a72f6, `pytest tests/` = **12 failed / 2195 passed** while
`python3 scripts/agents/continuous_agent_loop.py --verify-only` prints
**[9/9] constitution_guard_pins: PASS · CONTRACT_VERSION=agent-loop-contract/1 ·
exit 0**. #4138 landed Option A of the #4125 owner contract (clock-free gate
restored — the two AST-pinned guards are green again, re-verified first-hand:
36 passed) and added tier 9 `constitution_guard_pins` — but that tier
re-implements only those 2 faces inline. The other 12 red faces are still
invisible to the ladder. The blind-ladder class (#4097 → #4106 → #4124,
declared "mechanically closed (Invariant 6)" by #4138) still has a live
window: **4th datapoint — a red test born AFTER that claim (isolation bug
with #4132) landed and stayed invisible.**

## The 12 reds — attribution and remedy lane

| # | Face | Class | First red | Remedy lane |
|---|------|-------|-----------|-------------|
| 1 | `test_landing_fetch_tower_fallback::TestTowerProbeHardCap::test_stuck_transport_capped_by_hard_join` | **TEST-ISOLATION** (order-dependent; passes standalone) | born with #4132 (`50f6633` process-level roster cache) | **fixed in this PR** — cold-gate `setUp` reset |
| 2 | `test_constitution_freshness::TaskCycleWiring::test_25_argparser_exposes_offline_escape_hatch` | contract drift: pin wants `--offline` in `main()`; the flag is gone (flag-purge era) | pre-existing at a9323f4^ | governance: restore the flag or retire the pin (#4097 purge was deliberate) |
| 3 | `test_dead_import_drift::test_unused_import_ratchet_shrinks_only` | unused-import debt 361 → **368** (core/api/routes: `UTC`, `Query`, `PolicyRule`, `DecisionResult`, `AgentRegistry`) | pre-existing | agent-lane: remove dead bindings (or `# noqa: F401`), lower baseline — shrink-only ratchet |
| 4 | `test_npm_dep_cve_guard::test_live_baseline_check` | **REAL new CVE finding**: `follow-redirects@1.16.1` → `GHSA-mrwp-f3q8-3g9p` (`.agents/skills/devtools-audit/package-lock.json`) | pre-existing (finding surfaced with the advisory) | maintainer: pin bump, or reviewed admin `--baseline` re-floor |
| 5 | `test_js_dep_cve_guard::test_live_check_passes_at_landing_head` | js-plane live check (same guard family as #4) | pre-existing | maintainer (same routing as #4) |
| 6 | `test_pick_excludes_receipt_wos::test_no_over_exclusion_without_label` | pick-integration pin drift | pre-existing | contract archaeology vs the restored clock-free gate (#4138) |
| 7–8 | `test_sentry_test_row_demotion::TestPickIntegration::{test_demotion_logged, test_pure_mode_keeps_pre_change_contract}` | pick-integration pin drift | pre-existing | same as #6 |
| 9–11 | `test_stale_sentry_demotion::TestPickIntegration::{lone_pass_without_newer_sibling_served, newest_sentinel_served_when_only_family_exists, pure_mode_keeps_pre_change_contract}` | pick-integration pin drift | pre-existing | same as #6 |
| 12 | `test_test_parity_guard::test_run_guard_on_real_repo_passes` | guard-coverage manifest: `scripts/ci/pr_preflight_guard.py` exists with no test | pre-existing | agent-lane, unclaimed: write the missing test |

## Isolation anatomy (red #1 — root cause, fixed here)

`_TOWER_ROSTER_GATE_CACHE` (#4132, U6 root fix) caches **permanent
tool-absence notes at process level** — correct for one running boot, wrong
for one pytest session (a session spans dozens of simulated towers).
`test_failed_pr_audit_honesty`'s -32602 simulations prime
`github.list_prs → absent`; when `test_landing_fetch_tower_fallback` runs
afterwards (full-suite alphabetical order), the probe's
`_tower_tool_roster_gate` early-returns BEFORE any transport → the wedged
`urlopen` never runs → no `TimeoutError` → the hard-join pin fails.

Repro bisect (all at 35a72f6, full suite = red; standalone = green):
`pytest tests/test_failed_pr_audit_honesty.py tests/test_landing_fetch_tower_fallback.py`
→ 1 failed. With this PR's `setUp` reset: 26 passed. Full suite: **12 → 11
reds**, the fix removes exactly the isolation red and nothing else.

The pin is NOT weakened: the transport hard-join contract ("a wedged tower
probe must raise TimeoutError, never hang the pick path") is intact; the
probe just starts from a cold gate, as a fresh boot would.

## Completion contract for the owner (decision needed, not implemented)

- **Option A — self-maintaining face-runner tier**: tier 9 runs one pytest
  invocation over every `tests/test_*.py` that references the loop source
  (derived, not hardcoded — new pin files join automatically); fail-closed
  when pytest is absent; nested `--verify-only` (spawned from inside a face,
  e.g. the test_26 structure pin) omits the tier via a sentinel env so the
  marker/exit-0 structure pins stay recursion-free. Catches ALL 12 reds of
  this census mechanically. This lane drafted the full design pre-emptively
  and **withdrew it before submit** (U5 anti-stampede: #4138 had just landed
  its own tier 9); the design is offered here for the owner to adopt or
  reject — spec-only, no code shipped for it in this PR.
- **Option B — keep inline pins**: every new face must add an inline AST
  twin in `run_verify` (hand-copy drift risk; the parity guard fights
  hand-copies elsewhere). The 12-red window of this census stays open
  either way until the 11 remaining faces are dispositioned (table above).
- Both options need the 11 remaining reds triaged per-face; remedies are
  already routed in the table (2 are one-cycle agent-lane fixes, unclaimed
  at submit time: #3 and #12).

## Verification trail (3-tier)

- Tier-1 reflection: full pytest at a9323f4^ (11 red / 2174 pass), 3c85a3e
  (13 red / 2172 pass), 35a72f6 (12 red / 2195 pass) — #4124 delta = +2
  (the documented pair), #4138 delta = −2 (pair restored), #4132 delta =
  +1 (isolation red, born and invisible).
- Tier-2 boot smoke: dispatch cycle clean on the post-fix tree
  (claimable 0/5, board receipts only, P0 gate green).
- Tier-3: pair repro command above; post-fix full suite 11 red / 2196
  pass / 13 skip in 64.3s; `--verify-only` unchanged (9/9 PASS, exit 0);
  parity guard OK (tiers 1..9 == SPEC §4).
