#!/usr/bin/env python3
"""SupremeAI Multi-Agent Cross-PR & Branch Collision Detector.
=============================================================
Identifies direct file and module collisions across active agent branches
and open pull requests to prevent merge conflicts, overwritten work,
and silent semantic regressions.

Usage:
    # Run locally against current branch:
    python scripts/git/cross_pr_collision_detector.py

    # Run in CI for a specific PR:
    python scripts/git/cross_pr_collision_detector.py --pr 1626 --format markdown

    # Strict mode (fails with exit code 1 if direct collision found):
    python scripts/git/cross_pr_collision_detector.py --strict
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class CollisionItem:
    file_path: str
    target_pr: Optional[int]
    target_branch: str
    colliding_pr: Optional[int]
    colliding_branch: str
    colliding_author: str


@dataclass
class CollisionReport:
    target_branch: str
    target_pr: Optional[int]
    target_files: List[str] = field(default_factory=list)
    direct_collisions: List[CollisionItem] = field(default_factory=list)
    module_collisions: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def has_direct_collision(self) -> bool:
        return len(self.direct_collisions) > 0


def get_current_branch() -> str:
    """Get the current checked-out branch name."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return "main"


def get_changed_files_for_branch(branch: str, base: str = "origin/main") -> List[str]:
    """Get list of files modified in a branch relative to base."""
    try:
        # Ensure base exists
        res = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...{branch}"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except Exception:
        pass
    return []


def fetch_open_prs() -> List[dict]:
    """Fetch active open pull requests from GitHub via gh CLI."""
    try:
        res = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--json",
                "number,title,headRefName,author,files,isDraft",
            ],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            # Exclude drafts and non-dict entries
            return [pr for pr in data if isinstance(pr, dict) and not pr.get("isDraft", False)]
    except Exception:
        pass
    return []


def fetch_remote_agent_branches() -> List[str]:
    """Fallback when gh is not available: find remote agent-* branches."""
    try:
        res = subprocess.run(
            ["git", "branch", "-r", "--list", "origin/agent-*"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            branches = []
            for line in res.stdout.splitlines():
                b = line.strip().replace("origin/", "")
                if b and not b.startswith("HEAD"):
                    branches.append(b)
            return branches
    except Exception:
        pass
    return []


def detect_collisions(
    target_branch: str,
    target_pr_num: Optional[int] = None,
    target_files: Optional[List[str]] = None,
) -> CollisionReport:
    """Analyze overlap between target files/branch and other open PRs/branches."""
    if target_files is None:
        target_files = get_changed_files_for_branch(target_branch)

    report = CollisionReport(
        target_branch=target_branch,
        target_pr=target_pr_num,
        target_files=target_files,
    )

    if not target_files:
        return report

    target_file_set: Set[str] = set(target_files)
    open_prs = fetch_open_prs()

    if open_prs:
        for pr in open_prs:
            pr_num = pr.get("number")
            pr_branch = pr.get("headRefName", "")
            author_info = pr.get("author", {})
            pr_author = author_info.get("login", "unknown") if isinstance(author_info, dict) else "unknown"

            # Skip self
            if target_pr_num and pr_num == target_pr_num:
                continue
            if pr_branch == target_branch:
                continue

            pr_files = [f.get("path") for f in pr.get("files", []) if isinstance(f, dict) and "path" in f]
            if not pr_files:
                # If files array was empty, fetch via git diff if branch exists locally
                pr_files = get_changed_files_for_branch(f"origin/{pr_branch}")

            overlapping_files = target_file_set.intersection(set(pr_files))
            for file_path in sorted(overlapping_files):
                report.direct_collisions.append(
                    CollisionItem(
                        file_path=file_path,
                        target_pr=target_pr_num,
                        target_branch=target_branch,
                        colliding_pr=pr_num,
                        colliding_branch=pr_branch,
                        colliding_author=pr_author,
                    )
                )
    else:
        # Fallback to local git inspection of remote agent branches
        remote_branches = fetch_remote_agent_branches()
        for rb in remote_branches:
            if rb == target_branch:
                continue
            rb_files = get_changed_files_for_branch(f"origin/{rb}")
            overlapping_files = target_file_set.intersection(set(rb_files))
            for file_path in sorted(overlapping_files):
                report.direct_collisions.append(
                    CollisionItem(
                        file_path=file_path,
                        target_pr=None,
                        target_branch=target_branch,
                        colliding_pr=None,
                        colliding_branch=rb,
                        colliding_author="agent",
                    )
                )

    return report


def format_text_report(report: CollisionReport) -> str:
    """Format collision report for CLI / terminal display."""
    lines = []
    lines.append(f"Branch: {report.target_branch} (Files modified: {len(report.target_files)})")

    if not report.has_direct_collision:
        lines.append("  [OK] No file collisions detected with other active agent branches or open PRs.")
        return "\n".join(lines)

    lines.append("\n⚠️  [CROSS-AGENT COLLISION DETECTED]")
    lines.append("The following files are also being modified in peer branches / open PRs:")
    for col in report.direct_collisions:
        pr_str = f"PR #{col.colliding_pr}" if col.colliding_pr else "Remote branch"
        lines.append(f"  • {col.file_path}")
        lines.append(f"    --> Collides with {pr_str} ('{col.colliding_branch}' by @{col.colliding_author})")

    lines.append("\n👉 Recommendation: Coordinate with the owner or sequence your PR after theirs to avoid conflicts.")
    return "\n".join(lines)


def format_markdown_report(report: CollisionReport) -> str:
    """Format collision report as GitHub Flavored Markdown for PR comments."""
    if not report.has_direct_collision:
        return (
            "### ✅ Cross-PR Collision Check: Clean\n\n"
            "No file overlaps detected with any other active pull requests or agent branches."
        )

    lines = [
        "### ⚠️ Multi-Agent Cross-PR Collision Warning",
        "",
        "The following files in this branch are **concurrently modified** by other active pull requests:",
        "",
        "| Overlapping File | Current Branch | Colliding PR | Colliding Branch | Author |",
        "|---|---|---|---|---|",
    ]
    for col in report.direct_collisions:
        pr_link = f"[#{col.colliding_pr}](https://github.com/{os.getenv('GITHUB_REPOSITORY', 'SaifulHaqueNiloy/supremeai')}/pull/{col.colliding_pr})" if col.colliding_pr else "N/A"
        lines.append(
            f"| `{col.file_path}` | `{col.target_branch}` | {pr_link} | `{col.colliding_branch}` | @{col.colliding_author} |"
        )

    lines.extend([
        "",
        "> [!IMPORTANT]",
        "> **Action Required**: Please coordinate with the colliding PR owner before merging. "
        "Merging one PR before resolving overlapping diffs will trigger automatic merge conflicts in the other.",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-Agent Cross-PR Collision Detector")
    parser.add_argument("--branch", type=str, default=None, help="Target branch to inspect (default: current HEAD)")
    parser.add_argument("--pr", type=int, default=None, help="Target PR number to evaluate")
    parser.add_argument("--format", choices=["text", "markdown", "json"], default="text", help="Output format")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if direct collision is found")
    args = parser.parse_args()

    branch = args.branch or get_current_branch()
    report = detect_collisions(target_branch=branch, target_pr_num=args.pr)

    if args.format == "json":
        output = {
            "target_branch": report.target_branch,
            "target_pr": report.target_pr,
            "has_collision": report.has_direct_collision,
            "collisions": [
                {
                    "file": c.file_path,
                    "colliding_pr": c.colliding_pr,
                    "colliding_branch": c.colliding_branch,
                    "colliding_author": c.colliding_author,
                }
                for c in report.direct_collisions
            ],
        }
        print(json.dumps(output, indent=2))
    elif args.format == "markdown":
        print(format_markdown_report(report))
    else:
        print(format_text_report(report))

    if args.strict and report.has_direct_collision:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
