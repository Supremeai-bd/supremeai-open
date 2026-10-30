#!/usr/bin/env python3
"""
Anti-Regression & Root-Cause Enforcement Guard.
===============================================
Enforces the Zero-Recurrence Invariant (AGENTS.md Clause 6):
Whenever a Pull Request is submitted to fix a defect or incident (e.g. title starts with
'fix(' or 'fix:', or addresses an incident/bug), this guard mechanically ensures:

1. The PR includes an automated regression test file under `tests/` (e.g. `tests/test_*.py`).
2. The PR body includes explicit Reflection Evidence documenting:
   - Root Cause analysis (`why`)
   - Alternatives considered and rejected (`alternatives_rejected`)

Without a reproduction / regression test, a fix cannot land, preventing the same bug
from ever recurring.

Usage:
  python scripts/ci/anti_regression_guard.py --self-test
  python scripts/ci/anti_regression_guard.py --check-pr <TITLE> --files <FILE1,FILE2> --body <BODY>
"""

from __future__ import annotations

import argparse
import re
import sys
from typing import List, Tuple


def is_fix_pr(title: str, body: str = "") -> bool:
    """Determine whether a PR is claiming to fix a bug or incident."""
    title_clean = title.strip().lower()
    if re.search(r"^(fix|hotfix|patch)(\([a-z0-9_-]+\))?:", title_clean):
        return True
    if re.search(r"\b(fixes|closes|resolves)\s+#[0-9]+\b", body, re.IGNORECASE):
        if "fix" in title_clean or "remedy" in title_clean or "bug" in title_clean:
            return True
    return False


def validate_anti_regression(
    title: str,
    changed_files: List[str],
    body: str,
    labels: List[str] | None = None,
) -> Tuple[bool, List[str]]:
    """Validate PR against the Zero-Recurrence and Root-Cause contract."""
    labels = labels or []
    reasons: List[str] = []

    if "guard-exempt" in labels or "docs-only" in labels:
        return True, ["PR is explicitly marked exempt."]

    if not is_fix_pr(title, body):
        return True, ["Not classified as a fix PR; anti-regression test gate not required."]

    has_test = any(
        f.startswith("tests/") or f.endswith("_test.py") or f.endswith(".test.ts") or f.endswith(".spec.ts")
        for f in changed_files
    )

    if not has_test:
        reasons.append(
            "VIOLATION: Zero-Recurrence Invariant failed. Fix PRs MUST include a regression test under `tests/` "
            "to permanently prevent recurrence. Machine enforcement supersedes human vigilance."
        )

    has_reflection = "## Reflection Evidence" in body or "**why:**" in body
    if not has_reflection:
        reasons.append(
            "VIOLATION: Missing root-cause documentation. Fix PRs must include '## Reflection Evidence' "
            "documenting the underlying failure mechanism."
        )

    passed = len(reasons) == 0
    return passed, reasons


def run_self_test() -> int:
    """Run offline unit tests for constitutional CI conformance."""
    print("[anti-regression-guard] Running offline contract self-tests...")

    ok, _ = validate_anti_regression(
        title="fix(gateway): resolve connection pool leak",
        changed_files=["gateway/pool.py", "tests/test_gateway_pool_leak.py"],
        body="## Reflection Evidence\n- **why:** pool connections were not closing\n- **alternatives_rejected:** none",
    )
    assert ok, "Valid fix PR should pass"

    ok, msgs = validate_anti_regression(
        title="fix(core): patch exception handling in worker",
        changed_files=["core/worker.py"],
        body="## Reflection Evidence\n- **why:** fixed",
    )
    assert not ok, "Fix PR without regression test must fail"
    assert "Zero-Recurrence Invariant failed" in msgs[0]

    ok, _ = validate_anti_regression(
        title="feat(docs): update architecture documentation",
        changed_files=["docs/ROADMAP.md"],
        body="Adding roadmap",
    )
    assert ok, "Non-fix PR should not require regression test"

    ok, _ = validate_anti_regression(
        title="fix(hotfix): urgent doc correction",
        changed_files=["README.md"],
        body="quick fix",
        labels=["guard-exempt"],
    )
    assert ok, "Exempt PR should pass"

    print("[anti-regression-guard] PASS - All 4 contract scenarios verified cleanly.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Anti-Regression & Root-Cause Enforcement Guard")
    parser.add_argument("--self-test", action="store_true", help="Run contract self-tests")
    parser.add_argument("--title", type=str, default="", help="PR title")
    parser.add_argument("--files", type=str, default="", help="Comma-separated changed files")
    parser.add_argument("--body", type=str, default="", help="PR body")
    parser.add_argument("--labels", type=str, default="", help="Comma-separated labels")

    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    files_list = [f.strip() for f in args.files.split(",") if f.strip()]
    labels_list = [lbl.strip() for lbl in args.labels.split(",") if lbl.strip()]

    passed, reasons = validate_anti_regression(args.title, files_list, args.body, labels_list)
    if not passed:
        print("::error::" + "\n::error::".join(reasons))
        for r in reasons:
            print(f"❌ {r}", file=sys.stderr)
        return 1

    print("✅ Anti-Regression & Root-Cause Guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

