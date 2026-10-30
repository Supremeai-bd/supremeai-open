#!/usr/bin/env python3
"""Run all CI guards in one pass (dispatcher; guards stay as separate modules)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

GUARDS: list[list[str]] = [
    # Wiring integrity FIRST (#3316): every later roster entry is asserted to
    # reference a script that actually exists in the tree — wiring must not
    # outrun implementation (live instance 2026-10-30: #3268 wiring merged
    # while carrying PR #3257 still waited in the gate).
    ["python", "scripts/ci/wiring_integrity_guard.py", "--self-test"],
    ["python", "scripts/ci/wiring_integrity_guard.py", "--check"],
    ["python", "scripts/ci/boundary_sanitization_guard.py", "--self-test"],
    ["python", "scripts/ci/cross_platform_invariant_guard.py", "--self-test"],
    ["python", "scripts/ci/admin_sovereignty_guard.py", "--self-test"],
    ["python", "scripts/ci/satellite_board_guard.py", "--self-test"],
    ["python", "scripts/ci/deploy_preflight_guard.py", "--step1-syntax"],
    ["python", "scripts/ci/deploy_preflight_guard.py", "--self-test"],
    ["python", "scripts/ci/issue_template_guard.py", "--self-test"],
    ["python", "scripts/ci/constitution_pointer_guard.py", "--self-test"],
    ["python", "scripts/ci/constitution_pointer_guard.py"],
    ["python", "scripts/ci/openapi_breaking_guard.py", "--check"],
    ["python", "scripts/ci/security_gate.py", "--self-test"],
    ["python", "scripts/ci/mcp_access_policy_guard.py", "--check"],
    ["python", "scripts/ci/contract_fuzz_guard.py", "--self-test"],
    ["python", "scripts/ci/boundary_contract_sentinel.py", "--self-test"],
    ["python", "scripts/ci/fleet_contract_probe.py", "--self-test"],
    ["python", "scripts/ci/bridge_landing_watchdog.py", "--self-test"],
    ["python", "scripts/ci/bridge_intake_gate_watchdog.py", "--self-test"],
    # open→core sync staleness guard (#2756): self-test only in the roster —
    # the live check reads two external commit planes and belongs to the
    # cadence lane, not the per-PR roster.
    ["python", "scripts/ci/open_core_sync_staleness_watchdog.py", "--self-test"],
    # PR-lane strand tripwire (post-#3418 landing family): self-test only in
    # the roster — the live check reads the tower PR plane and belongs to the
    # cadence lane, same doctrine as the watchdogs above.
    ["python", "scripts/ci/pr_landing_age_guard.py", "--self-test"],
    # Radar pointer⇄pin co-obligation guard (#3624 class): self-test only in
    # the roster — --check/--check-ref read the git/index planes and belong
    # to the registration-PR author's pre-push step (#3483 literal rule).
    ["python", "scripts/ci/radar_pointer_pin_guard.py", "--self-test"],
    ["python", "scripts/ci/closure_live_state_gate.py", "--self-test"],
    ["python", "scripts/ci/license_ssot_guard.py", "--check"],
    ["python", "scripts/ci/contract_codegen_guard.py", "--check"],
    ["python", "scripts/ci/bandit_sast_guard.py", "--check"],
    ["python", "scripts/ci/js_dep_cve_guard.py", "--check"],
    ["python", "scripts/ci/py_dep_cve_guard.py", "--check"],
    ["python", "scripts/ci/check_dockerfile_security.py", "--from-strict"],
    ["python", "scripts/ci/npm_dep_cve_guard.py", "--self-test"],
    ["python", "scripts/ci/npm_dep_cve_guard.py", "--check"],
    ["python", "scripts/ci/bump_candidate_probe.py", "--self-test"],
    ["python", "scripts/ci/mcp_registry_catalog.py", "--self-test"],
    ["python", "scripts/ci/docs_link_integrity_guard.py", "--self-test"],
    ["python", "scripts/ci/docs_link_integrity_guard.py"],
    ["python", "scripts/ci/radar_index_freshness_guard.py", "--check"],
    ["python", "scripts/ci/verdict_plane_age_guard.py", "--self-test"],
    ["python", "scripts/agents/check_loop_contract_parity.py"],
    ["python", "scripts/ci/test_parity_guard.py"],
    ["python", "scripts/ops/generate_script_index.py", "--check"],
    ["python", "scripts/ci/skill_conformance_guard.py", "--self-test"],
    ["python", "scripts/ci/skill_conformance_guard.py", "--check"],
    ["python", "scripts/ci/ghost_host_guard.py", "--self-test"],
    ["python", "scripts/ci/ghost_host_guard.py", "--check"],
]


def main() -> int:
    failed = 0
    for cmd in GUARDS:
        print(f"=== {' '.join(cmd)} ===")
        r = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
        if r.returncode != 0:
            failed += 1
            print(f"FAIL (exit {r.returncode})")
        else:
            print("OK")
    print(f"\n{len(GUARDS) - failed}/{len(GUARDS)} guards passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
