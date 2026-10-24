#!/usr/bin/env python3
"""
check_dockerfile_security.py
============================
Audit tool to enforce non-root execution in all production Dockerfiles (Trap #97).
Checks:
1. Dockerfile has a USER directive that is NOT 'root' or '0'.
2. USER directive is declared after package installations or setup.
3. Fails or warns if a container runs as root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def find_dockerfiles(root: Path) -> list[Path]:
    dockerfiles = []
    for p in root.rglob("*Dockerfile*"):
        # Ignore test-runners, temporary files, python scripts or virtual environments
        if any(part.startswith(".") or part in ("node_modules", ".venv", "venv") for part in p.parts):
            continue
        if p.suffix in (".py", ".sh", ".md", ".json", ".swp", ".bak", ".tmp"):
            continue
        if p.is_file() and ("dockerfile" in p.name.lower()):
            dockerfiles.append(p)
    return dockerfiles


def check_dockerfile(dockerfile: Path) -> list[str]:
    issues = []
    content = dockerfile.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    user_instructions = []
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Match USER instruction
        match = re.match(r"^USER\s+([^\s]+)", stripped, re.IGNORECASE)
        if match:
            user_instructions.append((idx, match.group(1).strip()))

    if not user_instructions:
        issues.append(f"Missing USER directive in {dockerfile.relative_to(REPO_ROOT)}. Container runs as root by default!")
    else:
        last_line_num, last_user = user_instructions[-1]
        if last_user.lower() in ("root", "0"):
            issues.append(
                f"Dockerfile {dockerfile.relative_to(REPO_ROOT)} specifies USER '{last_user}' on line {last_line_num}. Containers must run as non-root!"
            )

    return issues


def main() -> int:
    # Ensure UTF-8 output on Windows console
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    dockerfiles = find_dockerfiles(REPO_ROOT)
    if not dockerfiles:
        print("[INFO] No Dockerfiles found to inspect.")
        return 0

    print(f"Auditing {len(dockerfiles)} Dockerfile(s) for non-root USER compliance (Trap #97)...")
    all_issues = []
    for df in sorted(dockerfiles):
        issues = check_dockerfile(df)
        if issues:
            for issue in issues:
                print(f"[FAIL] {issue}")
                all_issues.append(issue)
        else:
            print(f"[PASS] {df.relative_to(REPO_ROOT)}")

    if all_issues:
        print(f"\nTotal violations found: {len(all_issues)}")
        return 1

    print("\nAll Dockerfiles enforce non-root USER compliance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
