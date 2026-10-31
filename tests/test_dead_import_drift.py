#!/usr/bin/env python3
"""tests/test_dead_import_drift.py — shrink-only ratchet for unused-import debt (F401 class).

Auditor finding (docs/AUDIT_2026-10-28-dead-import-drift.md): CI Step-1 lint
(``scripts/ci/deploy_preflight_guard.py --step1-syntax``) enforces E9/F63/F7/F82
only; F401 (unused imports) is never run anywhere — ruff.toml does not even
exempt ``scripts/**`` from F401, yet hundreds of live-path bindings violate it.
Result: 446 unused-import bindings had accumulated across live-path files,
including in the fleet's most-executed tool (``scripts/agents/continuous_agent_loop.py``).

This guard makes the class self-healing without touching the protected
``.github/`` path (WO #1554 precedent — gates land as tests, admin applies
workflow patches):

  1. ``test_pinned_files_are_clean``  — the 9 files remediated in the audit
     patch stay at zero unused top-level imports (regression lock).
  2. ``test_unused_import_ratchet_shrinks_only`` — repo-wide live-path
     unused-import count must stay <= BASELINE. Cleanup PRs lower the
     baseline (shrink-only); any NEW dead import fails the suite.

Scan scope (mirrors the audit methodology):
  - tracked ``*.py`` from ``git ls-files``
  - excludes ``__init__.py`` (intentional re-export API surface)
  - excludes ``core/_archive/`` (archived legacy kept by design)
  - excludes files declaring ``# noqa: F401`` (deliberate compat facades:
    autonomous_agent.py / churn_prophet.py / cost_sage.py pattern)
  - excludes the compiler-directive binding ``annotations``

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_dead_import_drift.py
  - stdlib:  python3 tests/test_dead_import_drift.py   (plain runner)

Every test is offline and deterministic (pure AST over the worktree).

Contract note: a ratchet baseline is NOT a license to add dead imports —
new violations fail immediately; the baseline only bounds pre-existing debt
so the suite is green on pristine main while the debt can only shrink.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Auditor baseline at patch time: 446 unused bindings across 272 live-path
# files (AST scan, scope below). Shrink-only: lower this number when a
# cleanup PR removes more; never raise it.
#
# Re-armed 2026-10-28 at 40ac0bf: re-measured with this file's own
# _scan_live_scope (deterministic AST, same scope) -> 388 unused bindings
# across 233 files. The 446 baseline had gone stale-high by 58 slots: debt
# only ever leaves via cleanup (the ratchet forbids net growth, and the
# suite was green at 446 both at patch time and now), so a stale-high
# baseline could silently absorb up to 58 NEW dead imports before failing.
# The ratchet now binds at the measured floor. Causality note: the drop is
# consistent with the #1887-era −851-line prune wave plus the docs cuts
# removing import-carrying files entirely; per-commit scan determinism is
# what makes the number trustworthy, not the attribution.
#
# Re-armed 2026-10-30 at 932753b: the 388 baseline went stale-low when peer
# landings introduced 4 NEW dead-binding files (browser/action_cascade.py,
# core/adaptive_engine/{approval_workflow,capability_registry,correlation,
# mcp_skeleton}.py — first fleet RED 392>388). Remediation PR removed all 8
# dead bindings (CONFIDENCE_EXECUTE incl. its __all__ entry, hashlib,
# ensure_columns, get_conn/jdump/jload, ActionRisk/jdump; each verified
# dead by AST Name-load + zero consumer imports incl. _archive delegates)
# and re-measured with this file's own _scan_live_scope -> 384 across a
# smaller file set. Shrink-only preserved: 384 < 388 < 446.
# Re-armed 2026-10-30 r5 heal (post-#3016/#3017 window): slice-r1 landings added 5 dead
# bindings (core/marketplace_registry_sync.py: re/sys/dataclass/asdict;
# tests/test_hollow_read_guard.py: json). All 5 removed (AST + word-boundary verified
# dead, zero string-annotation uses); re-measured with this scanner -> 363.
# Re-armed 2026-10-30 r6 heal (standing-suite red sweep, #3665): 11 dead bindings
# landed since c547d1e in 7 files (gateway/service/app.py Response;
# scripts/agents/pr_lifecycle_guard.py datetime/timedelta/timezone;
# scripts/ci/pr_archive_indexer.py Optional/os; scripts/ops/migrate_docs_to_archive.py
# re/subprocess; tests/test_agent_identity_cli_model_forward.py subprocess;
# tests/test_search_ssot.py json; tests/test_zizmor_profile_guard.py sys). Each
# verified dead (zero non-import whole-word refs; string refs are comments, dict
# keys, a local method name, or patch.object on another module's attribute);
# re-measured with this scanner -> 361. Shrink-only preserved: 361 < 363 < 446.
# Re-armed 2026-10-31 r7 heal (GLM Agent 12, Job 486773; #4151 triage red #3,
# agent-lane): 13 dead stdlib bindings in 12 files of the core/api/routes(+server)
# block (UTC x3, datetime, timezone x5, uuid, json, urljoin, time x2). Each
# verified dead four ways: AST Name-load zero (this scanner), zero non-import
# whole-word refs (the single textual hit is a strftime literal "%S UTC", not a
# name), zero consumers beyond the gateway/routes star-facade pair
# (`from core.api.routes.X import *  # noqa: F401, F403`), and zero gateway-side
# uses of the forwarded name (word-boundary scan over all 11 facades). FastAPI/
# pydantic/project-name leftovers in the same block (Query, PolicyRule,
# DecisionResult, AgentRegistry, Depends, Response, ...) deliberately NOT touched
# here — higher re-export/string-annotation risk, separate slice.
# Re-measured with this scanner -> 355 after the core/api heal, -> 354 after the
# sibling-loop heal (loop_v1.py `os`, same order). Shrink-only preserved:
# 354 < 355 < 361 < 363 < 446.
BASELINE_UNUSED_IMPORTS = 354

# Files remediated by the audit patch (docs/AUDIT_2026-10-28-dead-import-drift.md).
# Each binding below was verified dead by AST Name-load analysis + word-boundary
# textual cross-check before removal; this list locks them at zero.
PINNED_CLEAN_FILES = (
    "scripts/agents/continuous_agent_loop.py",
    "scripts/agents/a2a_messaging_bus.py",
    "scripts/agents/create_blocker_issue.py",
    "scripts/agents/ecosystem_learning.py",
    "scripts/agents/issue_revalidator.py",
    "scripts/agents/mcp_presence_tracker.py",
    "scripts/agents/zai_browser_worker.py",
    "scripts/ci/check_singleton_inits.py",
    "scripts/ci/check_truthy_env_var.py",
)

_COMPILER_DIRECTIVE_BINDINGS = {"annotations"}  # `from __future__ import annotations`


class _Skip(Exception):
    """Honest skip signal (dual-mode; mirrors test_ci_guards.py)."""


def _tracked_py_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=True,
    )
    return [REPO_ROOT / f for f in out.stdout.splitlines() if f.strip()]


def _in_live_scope(path: Path) -> bool:
    name = path.name
    parts = path.parts
    if name == "__init__.py":
        return False  # re-export API surface — unused imports are the point
    if "_archive" in parts:
        return False  # archived legacy kept by design
    return True


def _module_unused_imports(path: Path) -> list[str]:
    """Top-level import bindings never Name-loaded in the module (F401-lite)."""
    src = path.read_text(encoding="utf-8", errors="replace")
    if "noqa: F401" in src or "noqa:F401" in src:
        return []  # deliberate compat facade / explicit suppression
    tree = ast.parse(src, filename=str(path))
    imported: dict[str, int] = {}  # binding -> lineno of import stmt
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                imported[a.asname or a.name.split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != "*":
                    imported[a.asname or a.name] = node.lineno
    loads = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loads.add(node.id)
    return sorted(
        b for b, _lineno in imported.items()
        if b not in loads and b not in _COMPILER_DIRECTIVE_BINDINGS
    )


def _scan_live_scope() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in _tracked_py_files():
        if not _in_live_scope(path):
            continue
        try:
            unused = _module_unused_imports(path)
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue  # unparseable files are other guards' jurisdiction
        if unused:
            result[str(path.relative_to(REPO_ROOT))] = unused
    return result


# --------------------------------------------------------------------------- #
# Guards                                                                       #
# --------------------------------------------------------------------------- #

def test_pinned_files_are_clean():
    scan = _scan_live_scope()
    dirty = {f: scan[f] for f in PINNED_CLEAN_FILES if f in scan}
    assert not dirty, (
        "pinned-clean files regressed to carrying unused imports "
        f"(audit patch files must stay at zero): {dirty}"
    )


def test_unused_import_ratchet_shrinks_only():
    scan = _scan_live_scope()
    total = sum(len(v) for v in scan.values())
    assert total <= BASELINE_UNUSED_IMPORTS, (
        f"unused-import debt grew: {total} > ratchet baseline {BASELINE_UNUSED_IMPORTS}. "
        # Honesty note (post-#4153 lesson): the sample below is the
        # alphabetically-first scan entries, NOT a growth diff — pre-existing
        # baseline debt appears here too (a healer that trusts it will
        # remediate the wrong files; the #4153-era triage misattributed new
        # growth this exact way). Find the true growth by diffing this map
        # against the scan at the commit that armed BASELINE_UNUSED_IMPORTS.
        f"Offender sample (first {min(5, len(scan))} of {len(scan)} files; NOT a growth diff): "
        f"{dict(list(scan.items())[:5])}. "
        "Remove the dead bindings (or mark deliberate re-exports with `# noqa: F401`), "
        "then lower the baseline — it is shrink-only."
    )


def test_ratchet_baseline_only_moves_down():
    """Constitutional honesty: the BASELINE constant must never be raised above
    the audit-day value. Guards the guard against silent self-defusal."""
    audit_day_value = 446
    assert BASELINE_UNUSED_IMPORTS <= audit_day_value, (
        f"BASELINE_UNUSED_IMPORTS ({BASELINE_UNUSED_IMPORTS}) exceeds the audit-day "
        f"ceiling ({audit_day_value}) — raising the ratchet is forbidden; remove "
        "dead imports instead."
    )


# --------------------------------------------------------------------------- #
# Dual-mode runner (stdlib path; pytest discovers test_* above directly)      #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = skipped = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"  SKIP | {fn.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except (
            RuntimeError, ValueError, TypeError, OSError, TimeoutError,
            ConnectionError, AttributeError, KeyError, ImportError,
            ModuleNotFoundError,
        ) as exc:
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed - skipped
    if skipped:
        print(f"{passed}/{len(fns)} tests passed ({skipped} skipped)")
    else:
        print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
