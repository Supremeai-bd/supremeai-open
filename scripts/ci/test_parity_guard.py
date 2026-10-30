#!/usr/bin/env python3
"""Test parity guard (plan §7 / §10.4).

Ensures every script under scripts/agents and scripts/ci that is part of the
autonomous loop has a corresponding test file (or an explicit allowlist entry).
Fail-closed: a missing test for a non-allowlisted script -> exit 1.

Parity baseline (shrink-only ratchet, drift repair audited on pristine main):
the sweep surface (200+ scripts) long outgrew the guard's original
loop-critical scope, so the allowlist lagged and the guard — plus its own
suite — sat permanently red on main. The baseline records the known-debt
missing-test set so the guard is honest again while staying anti-regressive:

  - a NEW script without a test still FAILS the guard (never auto-baselined);
  - the only ways in are an ALLOWLIST entry (with a reason) or a deliberate,
    reviewable ``--freeze`` re-baseline committed by a maintainer;
  - the ratchet only shrinks: adding tests or allowlist entries removes lines.

Stdlib-only. Offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = Path(__file__).resolve().parent / "test_parity_baseline.json"

# Scripts that are reference-only / not unit-testable by design (fail-closed
# allowlist; each entry must carry a reason).
ALLOWLIST: dict[str, str] = {
    "scripts/agents/continuous_agent_loop.py": "covered by test_constitution_freshness, test_s09, test_s12, test_agent_cadence",
    "scripts/agents/role_trigger_matrix.py": "covered by test_s09_role_trigger_matrix",
    "scripts/agents/check_loop_contract_parity.py": "parity checker, exercised by CI",
    "scripts/agents/ecosystem_scout_reference.py": "reference implementation, exercised via repository-auditor skill",
    "scripts/agents/scout_extractor.py": "reference implementation, exercised via repository-auditor skill",
    "scripts/agents/self_healing_reporter.py": "covered by test_self_healing_reporter",
    "scripts/agents/context_graph_resolver.py": "covered by test_s08_mistake_immunity",
    "scripts/agents/role_registry.py": "covered by test_s09_role_trigger_matrix",
    "scripts/agents/loop_cadence.py": "deprecated tombstone (#3573) — docstring-only stub, rotation API lives in continuous_agent_loop.py (covered by test_agent_cadence)",
    "scripts/agents/loop_common.py": "covered by test_constitution_freshness, test_ci_guards",
    "scripts/agents/agent_cadence.json": "config, not code",
    "scripts/agents/controller_evidence_verify.py": "covered by test_controller_evidence",
    "scripts/agents/execution_executor.py": "covered by test_execution_executor",
    "scripts/agents/learning_feedback.py": "covered by test_learning_feedback",
    "scripts/ci/federation_dispatch.py": "covered by test_federation_dispatch, test_federation_transit",
    "scripts/ci/staggered_rolling_train.py": "covered by test_s12_nightly_train",
    "scripts/ci/probe_live_status.py": "live probe, manual/CI-only",
    "scripts/ci/validate_md_links.py": "covered by test_validate_schemas",
    "scripts/ci/admin_sovereignty_guard.py": "covered by test_admin_sovereignty",
    "scripts/ci/auto_bridge_pr_opener.py": "bridge opener, exercised by CI",
    "scripts/ci/boundary_sanitization_guard.py": "covered by test_ci_guards",
    "scripts/ci/bridge_opener_hardening_reference.py": "reference implementation",
    "scripts/ci/controller_evidence_verify.py": "covered by test_controller_evidence",
    "scripts/ci/cross_platform_invariant_guard.py": "covered by test_cross_platform_guard",
    "scripts/ci/deploy_preflight_guard.py": "covered by test_ci_guards",
    "scripts/ci/hourly_satellite_batcher.py": "covered by test_s12_nightly_train",
    "scripts/ci/issue_template_guard.py": "covered by test_ci_guards",
    "scripts/ci/pr_improvement_regression_guard.py": "covered by test_ci_guards",
    "scripts/ci/render_build_quota_guard.py": "covered by test_ci_guards",
    "scripts/ci/satellite_board_guard.py": "covered by test_satellite_board_guard",
    "scripts/ci/self_healing_reporter.py": "covered by test_self_healing_pipeline",
    "scripts/ci/stale_claim_releaser.py": "covered by test_ci_guards",
    "scripts/ci/run_all_guards.py": "guard dispatcher, meta",
    "scripts/ci/vendored_tree_guard.py": "covered by test_ci_guards",
    "scripts/ci/federation_ci_watchdog.py": "covered by test_ci_guards",
    "scripts/ci/contract_parity_guard.py": "covered by --self-test and contract guards",
}


def discover_scripts(root: Path) -> list[Path]:
    out: list[Path] = []
    for sub in ("scripts/agents", "scripts/ci"):
        d = root / sub
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.py")):
            if p.name.startswith("_"):
                continue
            out.append(p)
    return out


def expected_test_name(script: Path) -> str:
    stem = script.stem
    # normalize: foo_bar -> test_foo_bar
    return f"test_{stem}.py"


def find_test(root: Path, script: Path) -> Path | None:
    rel = script.relative_to(root).as_posix()
    if rel in ALLOWLIST:
        return None  # explicitly allowed without a dedicated test
    # search tests/ and skills/tests/
    candidates = [
        root / "tests" / expected_test_name(script),
        root / "skills" / "tests" / expected_test_name(script),
    ]
    for c in candidates:
        if c.is_file():
            return c
    # also allow test_<stem with dashes normalized>
    alt = "test_" + script.stem.replace("-", "_") + ".py"
    for d in (root / "tests", root / "skills" / "tests"):
        if (d / alt).is_file():
            return d / alt
    return None


def load_baseline(path: Path | None = None) -> frozenset[str]:
    """Load the recorded parity debt (scripts knowingly without tests).

    Unreadable/absent baseline -> empty set -> the guard enforces EVERYTHING
    (fail-closed): a corrupt ledger can never excuse a missing test.
    """
    target = path or BASELINE_PATH
    if not target.is_file():
        return frozenset()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return frozenset()
    items = data.get("scripts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return frozenset()
    return frozenset(str(x) for x in items)


def run_guard(root: Path) -> tuple[bool, list[str]]:
    missing: list[str] = []
    baseline = load_baseline()
    for script in discover_scripts(root):
        rel = script.relative_to(root).as_posix()
        if rel in ALLOWLIST or rel in baseline:
            continue
        if find_test(root, script) is None:
            missing.append(rel)
    return (len(missing) == 0, missing)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test parity guard")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="record the current missing set as the parity baseline (deliberate, reviewable re-baseline)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    ok, missing = run_guard(root)
    if args.freeze:
        payload = {
            "_comment": (
                "Parity baseline (shrink-only ratchet), recorded by "
                "`scripts/ci/test_parity_guard.py --freeze`. Known debt: scripts "
                "without a dedicated test and without an ALLOWLIST entry. The "
                "baseline never grows automatically — new untested scripts still "
                "FAIL the guard. Shrink it by adding tests or allowlist entries "
                "(each with a reason)."
            ),
            "scripts": sorted(missing),
        }
        BASELINE_PATH.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"Froze parity baseline: {len(missing)} scripts -> {BASELINE_PATH}")
        return 0
    if args.json:
        print(json.dumps({"passed": ok, "missing": missing}, sort_keys=True))
    else:
        if ok:
            print("OK: Test parity passed - every non-allowlisted script has a test.")
        else:
            print("FAIL: Test parity FAILED - scripts without tests:")
            for m in missing:
                print(f"   - {m}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
