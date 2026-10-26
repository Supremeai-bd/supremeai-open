# 🌉 Bridge Work Order — [P0] Core CI green: guard optional platform submodule imports in core/__init__.py (fixes the red Core Pytest & Lint lane)

Addresses the `handoff:coder` CI-failure orders on `Supremeai-bd/supremeai-core` main
(#1418 and the sibling orders for runs 40388762313 / 40388071488 / 40387495325 / 40383561892 /
40380388569 / 40379732594 / 40378104481 — one shared root cause).

## Root cause (reproduced locally, not guessed)
1. The satellite `Supremeai-bd/supremeai-core` ships **without** `core/accessibility/`,
   `core/deployment/` and `core/optimization/` (removed by the duplicate-cleanup PRs:
   "eliminate duplicate core/browser files", "resolve gap_finder package shadowing", …).
2. Its `core/__init__.py` still carries the OLD triple-fallback import ladder:
   `.optimization.*` → bare `optimization.*` / `accessibility.*` / `deployment.*` →
   `core.optimization.*` / `core.accessibility.*` / `core.deployment.*`. **All three rungs fail**
   → `import core` raises `ModuleNotFoundError: No module named 'core.accessibility'`.
3. `decision_engine.py` does `from core.logging_config import logger` → the `core` package init
   executes → crash. `tests/test_core_planner.py`'s top-level import branch fails, its
   `from core.context_synthesizer import …` fallback also triggers the same broken package init
   → **pytest collection error** → the "Core Pytest & Lint" job fails on every sync.
4. Note the scheduled-run failures (e.g. run on SHA cf11b9cc08, which passed as a push) are the
   separate PyErrorFix job — same repo, different job, not addressed here.

## The fix (smallest safe change, public + monorepo compatible)
The current public/monorepo `core/__init__.py` (the #1347-hygiene version, canonical relative
imports) is kept **byte-identical except** the three platform-submodule import blocks, which
become guarded — the exact pattern already used in this file for `testing.qa_suite` (aiohttp) and
the evolution block (torch): one canonical path, an availability flag
(`ACCESSIBILITY_AVAILABLE` / `DEPLOYMENT_AVAILABLE` / `OPTIMIZATION_AVAILABLE`), and a PEP 562
lazy re-export (`_PLATFORM_LAZY_EXPORTS`) so `from core import PerformanceOptimizer` still
resolves where the submodule exists and yields the conditional-None contract where it does not.

## Verification evidence (real, local, reproducible)
- **Reproduction**: satellite-layout sandbox (root planner modules + `core/` without
  accessibility/deployment/optimization + top-level `monitoring/`) → current file:
  collection error `ModuleNotFoundError: No module named 'core.accessibility'` (matches CI).
- **After patch, same sandbox**: `import core` OK (v2.0.0); root `decision_engine` imports OK;
  `pytest tests/ -v` → **11 passed**; `ruff check . --select=E9,F63,F7,F82` → **All checks passed**.
- The guarded file is a strict superset where the submodules exist (monorepo has all three) —
  behavior there is unchanged.

## Sync note for operators
The satellite's `core/__init__.py` has diverged from the public mirror (it still carries the
pre-hygiene ladder). If the open→core sync skips locally-modified files, this fix needs a
one-time `git checkout <public-sha> -- core/__init__.py` in the satellite, otherwise the sync
may keep the broken local variant.

## Labels
`bridge:queued` `P0-critical` `area:ci` `repo:core` `handoff:coder`
