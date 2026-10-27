# SupremeAI Audit — 2026-10-28 (Dead-Import Debt & the F401 Enforcement Gap)

- **Auditor role assigned by:** `continuous_agent_loop.py` cadence dispatch (auditor, 24h timer)
- **Auditor identity:** zai-cron-agent-loop Job 478338 (zero-credential MCP Tower agent,
  session via Control Tower `supremeai-mcp-tower.onrender.com/mcp`)
- **Scope:** repo-wide dead-code scan (AST-based, zero-dependency); CI lint-coverage
  compliance check; anchor-hub / boundary invariant spot checks; one CI-gate
  proposal shipped as a tests/ guard
- **Repo state audited:** `supremeai-open` main `8213b96` at audit start (fresh clone;
  re-based on `origin/main` pre-submission — dual-rebase honored, 0 behind at each
  work phase)
- **Tower handshake:** MCP Control Tower `initialize` → `tools/list` (135 tools) →
  `status(scope=all)` = 21/21 services healthy (0 degraded, 0 unreachable);
  `bridge_work_queue` = 10 open work orders reviewed for claim fit; memory sidecar
  returned 0 prior audit episodes (no duplicate-audit risk)

---

## 1. Executive summary

The prior auditor cycle (Job 478318, `AUDIT_2026-10-28.md`) fixed the CRLF wedge and
filed stale-work-order evidence; its dead-code wiring check covered only
`scripts/agents/*` self-check tooling (finding F4 there — "no orphaned self-check
tool"). This cycle extends the dead-code audit to the **entire live Python surface**
and finds a systemic lint-coverage gap instead of isolated orphans: **F401 (unused
imports) is enforced nowhere**. CI Step-1 (`deploy_preflight_guard.py
--step1-syntax`) intentionally checks only E9/F63/F7/F82; no workflow step runs full
ruff; and `ruff.toml` — which does exempt `browser/**` from F401 — pointedly does
NOT exempt `scripts/**`, implying F401 was expected to apply there. The measurable
consequence: **446 unused-import bindings across 272 live-path files**, including
one in the fleet's most-executed tool, `scripts/agents/continuous_agent_loop.py`
itself. This patch removes the 17 verified-dead bindings in the loop-adjacent
tooling domain (9 files) and ships a shrink-only ratchet guard
(`tests/test_dead_import_drift.py`) so the class can only shrink going forward.

## 2. Findings

### D1 (P2, FIXED in this patch) — the dispatch loop carries a dead import

- **Evidence:** `scripts/agents/continuous_agent_loop.py:15` declares
  `import argparse, json, os, re, subprocess, sys, time`. AST Name-load analysis
  over the module finds **zero** loads of `re`; the only word-boundary matches of
  `\bre\b` outside the import line are the prose token "re-solved" inside the two
  U3-guard string literals (lines 485, 887). The binding is dead.
- **Impact:** symbolic rather than behavioral — but this file is the Single Door
  engine every federated agent executes; dead bindings here set the hygiene tone
  for the fleet, and the loop is the one file guaranteed to be re-read by every
  audit cycle.
- **Remediation (this patch):** drop `re` from the combined import line. Zero
  behavioral change; `py_compile` + 8/8 `--verify-only` tiers + 11/11 cadence
  suite all pass on the patched file.

### D2 (P3, evidence filed; first 17 bindings fixed) — 446 dead bindings / 272 live-path files

- **Evidence:** AST scan over all 2,350 tracked `*.py` files, scoped to live paths
  (excludes `__init__.py` re-export surfaces, `core/_archive/**`, and files
  declaring `# noqa: F401` — verified on `core/agents/autonomous_agent.py`,
  `core/agents/churn_prophet.py`, `core/agents/devops/cost_sage.py`, which are
  deliberate compat facades, NOT dead code). Totals: 446 unused bindings in 272
  files; 0 syntax errors; 26 unreferenced operator scripts under `scripts/ops/`
  (classified below, not auto-condemned — ops tooling is routinely invoked
  out-of-tree by operators).
- **Highest-signal clusters (examples, not exhaustive):**
  - `scripts/agents/*`: `a2a_messaging_bus.py` (`os`, `Optional`),
    `create_blocker_issue.py` (`os`, `Any`, `Dict`), `ecosystem_learning.py`
    (`os`, `sys`, `Optional`), `issue_revalidator.py` (`time`, `timedelta`),
    `mcp_presence_tracker.py` (`sys`, `Optional`), `zai_browser_worker.py`
    (`sys`, `time`)
  - `scripts/ci/*`: `check_singleton_inits.py` (`ast`),
    `check_truthy_env_var.py` (`re`)
  - long tail: `core/api/routes/*`, `core/adaptive_engine/*`, `core/agents/framework/*`,
    `tests/*` (658 bindings pre-noqa-whitelist; 446 after)
- **Impact:** lint debt compounds; every future F401-enabling PR would face a
  446-finding wall, so the wall keeps deferring its own enforcement — the classic
  debt ratchet spinning the wrong way.
- **Remediation (this patch):** the 17 bindings above (9 files) are removed, each
  individually verified by AST Name-load analysis **plus** a word-boundary textual
  cross-check before removal (docstring false positives rejected — the loop's own
  `re` initially tripped the textual check on "re-solved"; the AST verdict governs).
  The remaining ~429 bindings are baseline-bounded by the new guard, not mass-deleted
  here (cohesive-sizing: one domain slice at a time).

### D3 (P1, gate shipped in this patch) — F401 is enforced nowhere (lint-coverage gap)

- **Evidence:**
  - `.github/workflows/pipeline.yml` Step 1 runs
    `scripts/ci/deploy_preflight_guard.py --step1-syntax`, whose ruff invocation
    pins `E9,F63,F7,F82` only (source line ~132: "Ruff strict name/syntax check
    (mirrors satellite CI: E9,F63,F7,F82)").
  - `ruff.toml` sets per-file-ignores for `browser/**` including `F401` — but no
    `select`/`extend-select` section exists, and no CI step runs unrestricted
    `ruff check` on `scripts/**`; F401 there is expected-but-never-executed.
  - Net effect is exactly the observed D2 debt: rules that everyone assumes
    someone else runs.
- **Impact:** the repo's own hygiene contract is aspirational on live main; any
  dead import (including in security-adjacent CI tooling under `scripts/ci/`)
  lands silently.
- **Remediation (this patch, tests/ boundary only):** `tests/test_dead_import_drift.py`
  — a zero-dependency, offline, dual-mode (pytest + stdlib) guard following the
  `test_ci_guards.py` house style:
  1. `test_pinned_files_are_clean` — the 9 remediated files stay at zero;
  2. `test_unused_import_ratchet_shrinks_only` — repo-wide live-path count ≤ 446
     (shrink-only baseline; cleanup PRs lower it, new debt fails the suite);
  3. `test_ratchet_baseline_only_moves_down` — the baseline constant can never be
     raised above its audit-day value (anti-self-defusal lock).
  G3-workflow (maintainer application, exact patch): after the ratchet reaches 0,
  extend the Step-1 ruff rule set from `E9,F63,F7,F82` to include `F401`, at which
  point `test_pinned_files_are_clean` may retire. Until then the test-based ratchet
  provides the enforcement without touching the protected `.github/` path.

### D4 (P3, evidence only — no action in this slice) — Anchor-Hub count drift between SSOT and charter

- **Evidence:** `AGENTS.md` (Single Door SSOT) Invariant 1 states "Strictly
  **8** Anchor Hubs (#749–#762)"; `docs/FEDERATION_CHARTER.md` Rule 4 states
  "strictly **14** persistent parent Anchor Hubs" with "12 Domain Repository
  Anchor Hubs (#749–#759, #762)". Both cite the same numeric range but disagree
  on the count and on whether #760/#761 are hubs. The live board could not be
  cross-checked from this environment (unauthenticated GitHub API rate limit
  403 at audit time); the tower's issue-read tooling exposes PRs, not issues.
- **Impact:** agents resolving the hub registry from the charter vs the SSOT
  will disagree about where Sub-Issues attach; per the constitution, AGENTS.md
  wins, but the drift itself is untracked.
- **Proposed remediation (maintainer/admin):** one-line reconciliation in
  `docs/FEDERATION_CHARTER.md` (or an explicit hub-registry table in AGENTS.md).
  Not self-landed here: AGENTS.md is the constitution (admin-owned) and the
  charter correction requires the admin's intended count as ground truth.

### D5 (clean bill) — boundary invariant and scan hygiene

- Root-shadowing check: `git ls-files` shows **0** tracked files under `src/`,
  `service/`, `packages/` at repo root — Invariant 2 (Boundary) holds.
- 0 syntax errors across all 2,350 tracked Python files (`ast.parse` + CI Step-1
  agrees: 2,243 Python files compile cleanly post-patch).

## 3. Remediation in this patch

1. **9 files, 17 dead bindings removed** (verified-dead only):
   `scripts/agents/continuous_agent_loop.py` (`re`),
   `scripts/agents/a2a_messaging_bus.py` (`os`, `Optional`),
   `scripts/agents/create_blocker_issue.py` (`os`, `Any`, `Dict`),
   `scripts/agents/ecosystem_learning.py` (`os`, `sys`, `Optional`),
   `scripts/agents/issue_revalidator.py` (`time`, `timedelta`),
   `scripts/agents/mcp_presence_tracker.py` (`sys`, `Optional`),
   `scripts/agents/zai_browser_worker.py` (`sys`, `time`),
   `scripts/ci/check_singleton_inits.py` (`ast`),
   `scripts/ci/check_truthy_env_var.py` (`re`).
2. **`tests/test_dead_import_drift.py`** — the G3 shrink-only ratchet guard (3 tests,
   dual-mode, offline).
3. **`docs/AUDIT_2026-10-28-dead-import-drift.md`** — this report.

Nothing else is touched: no dispatch behavior, no cadence config, no `.github/`
files, no `core/**` (facades intentionally left as the compat surface they are),
no mass deletion of the ~429 remaining bindings or the 26 unreferenced `scripts/ops/`
tools (operator tooling; each deserves individual reproducibility review before
Superior-Replacement deletion).

## 4. Verification evidence (3-tier)

- **Tier 1 (Reflection):** this report §5; per-candidate proof table in patch prep
  (AST Name-load + word-boundary cross-check; 17 removable, 1 docstring false
  positive correctly resolved by AST authority).
- **Tier 2 (Smoke):** `py_compile` OK on all 9 patched files + the new test;
  `git diff` = 10 files, +25/−17 lines (report excluded) — well under the
  30-file/200 KB cohesive-sizing ceiling.
- **Tier 3 (Tests):** `continuous_agent_loop.py --verify-only` = 8/8 PASS exit 0;
  `tests/test_agent_cadence.py` 11/11 OK; `tests/test_constitution_freshness.py`
  26/26 OK; `tests/test_ci_guards.py` 12/12 PASS;
  `tests/test_dead_import_drift.py` 3/3 PASS;
  `scripts/ci/deploy_preflight_guard.py --step1-syntax` PASS (2,243 files, 0
  syntax errors).

## 5. Reflection Evidence

- **why:** the auditor mandate is dead code + compliance drift + CI gates, and
  this cycle found all three intersecting in one measurable defect: a hygiene
  rule (F401) that everyone assumes is enforced, enforced nowhere, with 446
  violations proving the point — one of them in the loop file this dispatch runs
  on. Removing verified-dead bindings in the loop-adjacent domain is the smallest
  superior replacement (delete the debt starter set rather than document around
  it), and the shrink-only ratchet converts an unbounded cleanup project into a
  monotonic one so the debt can never regrow while maintainers decide on the
  workflow-level gate.
- **alternatives_rejected:**
  1. *Mass-delete all 446 bindings in one PR* — rejected: violates cohesive
     sizing (single domain slice), and ~40 files sit outside this auditor's
     loop-adjacent boundary; each deserves the same per-candidate verification
     this patch applied before deletion.
  2. *Enable F401 for `scripts/**` directly in CI Step-1 (`.github/` patch)* —
     rejected: `.github/` is a protected path (WO #1554 precedent); with 446
     live violations the workflow change would also fail Step 1 red on main.
     The tests/ ratchet enforces the same class today; the workflow patch is
     prepped for maintainer application once the ratchet reaches 0.
  3. *Delete the 26 unreferenced `scripts/ops/` scripts* — rejected: zero
     tracked references ≠ dead for operator tooling (invoked ad hoc / from
     private runbooks); condemnation without a reproducibility review would be
     a ghost fix in reverse.
  4. *Strip unused imports from compat facades (`core/agents/churn_prophet.py`
     etc.)* — rejected: those re-exports are deliberate patching targets for
     legacy import paths and carry explicit `# noqa: F401`; removing them
     breaks external consumers (Superior Replacement forbids appeasing-legacy
     hacks in both directions).
  5. *Self-reconcile the D4 hub-count drift by editing AGENTS.md or the
     charter* — rejected: the constitution is admin-owned; the auditor files
     the evidence and the count decision stays with maintainers.
