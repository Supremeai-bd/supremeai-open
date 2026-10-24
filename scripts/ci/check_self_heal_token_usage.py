#!/usr/bin/env python3
"""Audit GitHub Actions workflow files for self-heal token anti-patterns.

Rules:
1. Workflows performing 'git push', 'gh pr create', or 'update-branch' MUST use
   secrets.SELF_HEAL_PAT (or secrets.SELF_HEAL_PAT || github.token).
2. Using bare 'github.token' or 'secrets.GITHUB_TOKEN' for branch push/update
   triggers GitHub anti-recursion rules and results in silent CI stalls or 'action_required' locks.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


WORKFLOWS_DIR = Path(".github/workflows")

# Patterns indicating mutations that trigger downstream CI
MUTATION_PATTERNS = [
    re.compile(r"\bgit\s+push\b"),
    re.compile(r"\bgh\s+pr\s+create\b"),
    re.compile(r"/update-branch\b"),
]

# Pattern indicating safe token usage
SAFE_TOKEN_PATTERN = re.compile(r"SELF_HEAL_PAT")

# Pattern indicating dangerous bare token usage
BARE_TOKEN_PATTERNS = [
    re.compile(r"\bsecrets\.GITHUB_TOKEN\b"),
    re.compile(r"\bgithub\.token\b"),
]


def audit_workflows() -> list[str]:
    violations: list[str] = []

    if not WORKFLOWS_DIR.exists():
        print(f"Error: {WORKFLOWS_DIR} not found.", file=sys.stderr)
        return [f"Missing directory: {WORKFLOWS_DIR}"]

    for yml_file in sorted(WORKFLOWS_DIR.glob("*.yml")):
        content = yml_file.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        # Check if workflow contains any mutation patterns
        has_mutation = any(p.search(content) for p in MUTATION_PATTERNS)
        if not has_mutation:
            continue

        # If it has a mutation, check each step or script block
        # For simplicity, if file contains mutation and bare token without SELF_HEAL_PAT in that context
        for i, line in enumerate(lines, 1):
            for mut_pat in MUTATION_PATTERNS:
                if mut_pat.search(line):
                    # Look backwards and forwards in a window of 30 lines for GH_TOKEN or auth
                    window_start = max(0, i - 25)
                    window_end = min(len(lines), i + 25)
                    window_text = "\n".join(lines[window_start:window_end])

                    # Check if token is configured in this window
                    has_bare_token = any(bp.search(window_text) for bp in BARE_TOKEN_PATTERNS)
                    has_safe_token = bool(SAFE_TOKEN_PATTERN.search(window_text))

                    if has_bare_token and not has_safe_token:
                        violations.append(
                            f"{yml_file}:{i}: Mutation '{line.strip()}' uses bare GITHUB_TOKEN without SELF_HEAL_PAT."
                        )

    return violations


def main() -> int:
    # Set utf-8 stdout encoding if possible
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    print("[INFO] Auditing GitHub Actions workflows for self-heal token safety...")
    violations = audit_workflows()

    if violations:
        print("\n❌ Found token usage violations:")
        for v in violations:
            print(f"  - {v}")
        print("\nFix: Use 'secrets.SELF_HEAL_PAT || github.token' (or 'secrets.SELF_HEAL_PAT || secrets.GITHUB_TOKEN').")
        return 1

    print("✅ All mutation workflows properly use SELF_HEAL_PAT. Zero anti-recursion hazards found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
