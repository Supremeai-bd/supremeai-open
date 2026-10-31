# Triage: #4310 census-blind collection error — bare pytest aborts at HEAD 48ad193

- Reporter: GLM Agent 14 (Job 486785) · Cycle 22 (2026-10-31 17:14+08)
- Lane: **report-only triage, no claim** (U7/U10: loop said clean 0/5; U8: surface with dedup —
  board 0 rows, issue search `meta_cognitive OR sqlalchemy` = 0 hits, first to file)
- Subject commit: 8cf8ebc / PR #4310 ("add heuristic meta-cognitive intent router"),
  test file `tests/test_meta_cognitive_intent.py` (created there; also present: #4307's
  `tests/test_no_core_browser_duplicate.py`, which collects fine).

## First-hand evidence (all commands run this cycle)

1. Bare pytest at 48ad193: `Interrupted: 1 error during collection` (1 skipped, 1 error,
   6.31 s) — the whole census aborts; suite state UNCERTIFIABLE (vs 2F/2413P/14S at
   e442099 one cycle earlier). Census SSOT blinded.
2. Isolated rerun: `pytest tests/test_meta_cognitive_intent.py` → same error, 1.67 s.
3. Import chain (verbatim from traceback):
   `tests/test_meta_cognitive_intent.py:8` → `core.adaptive_engine.intent_parser`
   → `core/brain/model_router.py:33` → `core.performance_enhancer` → `core/brain/model_registry.py:4`
   → `core/services/config_service.py:5` → `from sqlalchemy import select` →
   **ModuleNotFoundError: No module named 'sqlalchemy'**.
4. The test file itself (L4-6) does `sys.path.insert(0, REPO_ROOT / "core")` — that hack is
   why `from brain.model_registry` / `from services.config_service` resolve at all; it drags
   the whole core runtime config stack into the test import graph.
5. The paradox: CI run 41187864743 on 48ad193 = **success** — pipeline.yml has **zero pytest
   jobs** (guards + Tower/SDK TS only). Green CI, blind census: nothing mechanical catches
   this today.
6. `sqlalchemy` is declared nowhere in this repo (only manifest: requirements-dev.txt,
   dev tooling only; its header says runtime deps belong to domain mirrors).

## Root cause (why this class of breakage)

`core/` is a Layer-2 domain mirror with its own runtime deps. #4310 added the first test
that imports the core runtime stack **without an optional-dependency guard**, and pytest's
default behavior on any collection error is a full-session abort. One new edge blinded the
SSOT that the #4151 lesson established as the only honest census.

## Fix contract (root-cause, minimal-first)

- **Option A (recommended, 1 line):** at the top of `tests/test_meta_cognitive_intent.py`,
  before the core import: `pytest.importorskip("sqlalchemy")`. Envs without runtime deps
  show a visible skip instead of aborting the other ~2,400 tests. No core-mirror touch
  (Invariant 8), no new deps (Invariant 7).
- **Option B (rejected):** install sqlalchemy into the census env / requirements-dev —
  wrong layer; runtime deps belong to the core domain mirror; heavy install for one file.
- **Option C (rejected here):** lazy-import sqlalchemy inside
  `core/services/config_service.py` — touches core mirror runtime code; belongs to the
  supremeai-core lane if pursued.

## Zero-recurrence recipe (U6; admin lane — .github/ is protected)

Add one cheap CI step: `python3 -m pytest --collect-only -q` (fail on any collection
error). It would have caught this in seconds. Cannot be agent-landed (#2512 pattern) —
admin recipe only.

## Verification recipe for the fixing agent

Bare pytest must return to the pre-#4310 census shape (errors=0; 2F CVE-guard pair
expected to remain, maintainer lane #4204). This reporter will first-hand verify heal
next cycle (established pattern: #4163→#4200).
