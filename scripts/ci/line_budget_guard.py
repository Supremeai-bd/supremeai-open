#!/usr/bin/env python3
"""line_budget_guard.py — Mechanical Anti-Bloat Guard for SupremeAI Core Scripts.

Enforces strict line budget limits on core entry scripts to prevent
uncontrolled monolith expansion and multi-agent accretion.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# File budget allocations (relative to REPO_ROOT)
# Maximum line counts permitted before CI rejection
BUDGETS: dict[str, int] = {
    "scripts/agents/loop_v1.py": 350,
    "scripts/ci/pr_preflight_guard.py": 250,
}

def check_budgets() -> list[str]:
    violations = []
    for rel_path, max_lines in BUDGETS.items():
        file_path = REPO_ROOT / rel_path
        if not file_path.is_file():
            continue
        try:
            lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            count = len(lines)
            if count > max_lines:
                violations.append(
                    f"LINE_BUDGET_EXCEEDED: '{rel_path}' is {count} lines (budget limit: {max_lines} lines). "
                    f"Modularize your logic into helper libraries instead of bloating this core file."
                )
        except Exception as e:
            violations.append(f"ERROR reading '{rel_path}': {e}")
    return violations

def self_test() -> int:
    # Test checking logic against current budgets
    violations = check_budgets()
    if violations:
        print("line_budget_guard self-test: FAIL (budget currently exceeded)")
        for v in violations:
            print(" -", v)
        return 1
    print("line_budget_guard self-test: PASS (all budgeted files within limits)")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Check line budgets of core scripts.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test assertions")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    violations = check_budgets()
    if violations:
        print("line_budget_guard: FAIL")
        for v in violations:
            print(" -", v)
        return 1

    print("line_budget_guard: PASS")
    return 0

if __name__ == "__main__":
    sys.exit(main())

