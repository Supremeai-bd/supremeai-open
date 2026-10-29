# AUDIT 2026-10-28 — Claim-lease SSOT drift (the 30-minute lease lives in 3 places)

Role: `auditor` (cadence dispatch, main `fff03f3`). Scope: claim/lease machinery
across `scripts/agents/` and `scripts/ci/`. Method: textual importer scan over
every `*.py/*.ts/*.md/*.yml/*.json` in the repo, then manual verification of
each candidate (dynamic imports, string references, excluded dirs all checked).

## Findings

### F1 — the 30-minute lease is defined three times, none wired together (FIXED here)

| Definition site | Constant | Imported by |
|---|---|---|
| `scripts/agents/claim_thresholds.py` (#57, the declared SSOT) | `ORPHAN_RELEASE_MINUTES = 30` | **nobody** |
| `scripts/agents/continuous_agent_loop.py` | `ISSUE_LEASE_SECONDS = 1800.0` | its own `is_claimable()` |
| `scripts/ci/stale_claim_releaser.py` | `TTL_MINUTES_DEFAULT = 30` | its own `is_stale()` |

`claim_thresholds.py` was landed as the #57 fix for the release↔re-claim
flip-flop war (its docstring: "fleet-কম্পোনেন্টগুলো claim-staleness ভিন্ন উৎস
থেকে মাপত" — fleet components measured claim-staleness from different
sources), with the comment "(আগে continuous_agent_loop.py-তে হার্ডকোড ছিল)" —
"previously hardcoded in continuous_agent_loop.py". But the loop **kept** its
hardcoded copy and the releaser kept a second one. Nothing imports the SSOT:
if any one of the three values is changed, the other two silently diverge and
the #57 war re-opens. This is the same dual-SSOT class the loop's own Bangla
comment (continuous_agent_loop.py ~line 46) already confessed for the label
plane.

### F2 — the 5-minute idempotency floor was landed but never enforced (FIXED here)

`claim_thresholds.MIN_CLAIM_AGE_BEFORE_RELEASE_MINUTES = 5` exists with war
evidence in its docstring ("release হচ্ছিল claim-এর ~১৬s-এর মধ্যেই" — releases
landed within ~16s of claim) — an idempotency guard that no sweep obeys. The
releaser's `release_plan()` would happily release any expired claim, including
one whose typed marker declares a tiny `ttl=` (e.g. `ttl=1m`): the marker TTL
is trusted verbatim, so a malformed or racing marker re-opens the war vector
the floor was built to close.

**Fix applied:** `release_plan()` now keeps (never releases) any claim younger
than the SSOT floor, reason `"fresh_claim_floor"`, before the stale check.
With the default 30-minute TTL the floor is invisible to well-formed markers —
existing tests (test_self_healing_pipeline) stay green unchanged.

### F3 — wiring performed (this PR)

1. `scripts/agents/continuous_agent_loop.py`:
   `ISSUE_LEASE_SECONDS = ORPHAN_RELEASE_MINUTES * 60.0` (SSOT import; Rule 9
   value unchanged at 1800.0).
2. `scripts/ci/stale_claim_releaser.py`:
   `TTL_MINUTES_DEFAULT = ORPHAN_RELEASE_MINUTES` (SSOT import via
   path-bootstrap, mirrors how tests already import this module) + the
   fresh-claim floor in `release_plan()`.
3. `tests/test_claim_lease_ssot.py` (new, 7 pins, offline stdlib): loop lease
   == SSOT ×60 == 1800.0; no hardcoded literal remains in loop source;
   releaser TTL == SSOT == 30; floor blocks a `ttl=1m` release at claim+2min
   (`fresh_claim_floor`) and allows it at claim+6min; default-30m decisions
   untouched; SSOT constants themselves pinned (30 / 5).

**Proof:** new pins RED ×3 on pristine main → GREEN on patched (fail-closed
pattern). Full suite: patched `2 failed, 1068 passed, 3 skipped` vs pristine
identical pre-existing failures (`test_epistemic_router`, `test_stealth_dns_
guards::test_probe_endpoints`) — **zero new failures**. Releaser `--self-test`
OK; loop `--verify-only` 8/8 PASS.

### F4 — flagged, not fixed (need admin/solver decisions)

- **`scripts/ci/update_ci_comments.py` is broken legacy**: it targets
  `.github/workflows/ci.yml`, which no longer exists (only `pipeline.yml`).
  It opens its target **at import time** and would crash with
  `FileNotFoundError`; its anchor strings are from the old workflow's shape.
  Nothing imports or schedules it. Recommendation: delete (Superior
  Replacement) — but it is existence-pinned in
  `scripts/ci/test_parity_baseline.json` (`/scripts[161]`), so deletion must
  update the roster in the same commit; left to a solver cycle to keep this
  diff surgical.
- **`scripts/ci/claim_lease.py` (406 lines) and `scripts/ci/mutation_lease.py`
  (432 lines)**: landed pure cores (#375 drop-in for
  `stale_claim_releaser.py`; #4200 §6/§7 mutation guard) with **zero
  importers and zero tests** — existence-pinned in the parity baseline only.
  Recommendation: either wire them (claim_lease into the releaser family,
  mutation_lease into a dispatch path) or explicitly mark them
  reference/implementations in their docstrings; today they are 838 lines of
  untested dead weight that the parity guard only counts, not runs.
- **G2 still open**: `.github/workflows/pipeline.yml` has **0 pytest steps**
  (47 python steps) — every offline pin test in this repo, including the new
  SSOT pins, is invisible to CI. This audit adds the third independent report
  of G2 (after WO #1572 and the 2026-10-27 audit); it remains admin-owned
  (`.github/`).
- Pre-existing reds untouched: `test_epistemic_router`,
  `test_stealth_dns_guards` (failure-set identical pristine vs patched).
