#!/usr/bin/env python3
"""Run all CI guards in one pass (dispatcher; guards stay as separate modules)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

GUARDS: list[list[str]] = [
    ["python", "scripts/ci/boundary_sanitization_guard.py", "--self-test"],
    ["python", "scripts/ci/cross_platform_invariant_guard.py", "--self-test"],
    ["python", "scripts/ci/admin_sovereignty_guard.py", "--self-test"],
    ["python", "scripts/ci/satellite_board_guard.py", "--self-test"],
    ["python", "scripts/ci/deploy_preflight_guard.py", "--step1-syntax"],
    ["python", "scripts/ci/deploy_preflight_guard.py", "--self-test"],
    ["python", "scripts/ci/issue_template_guard.py", "--self-test"],
    ["python", "scripts/agents/check_loop_contract_parity.py"],
    ["python", "scripts/ci/test_parity_guard.py"],
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
