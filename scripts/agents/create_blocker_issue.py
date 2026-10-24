#!/usr/bin/env python3
"""Prerequisite Blocker Discovery & Autonomous Issue Creator.
=============================================================
Implements SupremeAI Constitution Law:
"When an agent discovers during task execution that resolving its active issue
strictly requires fixing an unrecorded prerequisite bug or dependency, the agent
is authorized and required to create a new GitHub issue for that blocker."

Dedup guard (Issue #1997 — founder-directed fix, 2026-09-27):
Before creating, the script searches OPEN issues for one with the SAME title.
If found, creation is SKIPPED and the existing issue is returned/linked — a
blocker is tracked exactly once. (The 2026-09-27 triage closed ~80 duplicate
auto-created conflict trackers born from a broken search phrase in
auto-update-pr-drift.yml; this guard makes the class impossible.)
Pass --allow-duplicate to force creation (escape hatch, needs a reason).

Usage:
    python scripts/agents/create_blocker_issue.py \
        --parent-issue 1690 \
        --title "fix(db): Missing tenant isolation check in mesh registry" \
        --body "Mesh registry queries fail under multi-tenant isolation..." \
        --role platform

    # Dry-run mode for local validation:
    python scripts/agents/create_blocker_issue.py \
        --parent-issue 1690 \
        --title "fix(core): Missing exponential backoff in swarm worker" \
        --body "Worker crashes without backoff..." \
        --role coder \
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

VALID_ROLES = ("planner", "coder", "pr-helper", "ci", "platform")


@dataclass
class BlockerIssueResult:
    new_issue_number: Optional[int]
    new_issue_url: str
    parent_issue_number: int
    title: str
    role: str
    labels: List[str]
    is_dry_run: bool = False
    success: bool = True
    error_message: str = ""
    duplicate_of: Optional[int] = None  # set when an identical open issue already exists


def _gh_available() -> bool:
    return subprocess.run(["gh", "--version"], capture_output=True).returncode == 0


def find_existing_blocker(title: str, repo_dir: Path = ROOT_DIR) -> Optional[int]:
    """Return the number of an OPEN issue with the exact same title, if any.

    Dedup guard (Issue #1997): the 2026-09-27 flood happened because the old
    caller searched for a phrase ('conflict on PR #N') that never matched the
    created title ('fix(conflict): PR #N (branch) has merge conflict with main').
    This helper searches by the REAL title and verifies an exact match locally,
    so it is safe for titles containing '#', parens, and colons.
    """
    if not _gh_available():
        return None
    try:
        res = subprocess.run(
            [
                "gh", "issue", "list",
                "--state", "open",
                "--limit", "50",
                "--search", f'"{title}" in:title',
                "--json", "number,title",
            ],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if res.returncode != 0:
            return None
        for issue in json.loads(res.stdout or "[]"):
            if str(issue.get("title", "")).strip() == title.strip():
                return int(issue["number"])
    except (subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError):
        return None
    return None


def format_blocker_body(parent_issue: int, description: str, role: str) -> str:
    """Format standard markdown body for the blocker issue with clear audit links."""
    return f"""### 🛑 Prerequisite Blocker

**Discovered while working on:** #{parent_issue}  
**Target Role Lane:** `{role}`  
**Dependency Type:** Upstream Prerequisite Blocker  

---

### Description & Root Cause
{description.strip()}

---

### 🔗 Dependency Links
- **Blocks:** #{parent_issue}
- **Action Required:** Resolve and merge this issue before completing #{parent_issue}.

_Automated by `scripts/agents/create_blocker_issue.py` per AGENTS.md Constitution Invariant 9._"""


def format_parent_comment(new_issue_number: int, title: str, role: str) -> str:
    """Format comment to notify the parent issue that it is blocked."""
    return f"""⚠️ **Blocked by Prerequisite Issue: #{new_issue_number}**

> **Title:** {title}  
> **Assigned Role Lane:** `{role}`  
> **Status:** Unclaimed (`status:unclaimed`)  

Work on this issue is dependent on resolving #{new_issue_number} first to avoid out-of-scope drive-by changes."""


def create_blocker_issue(
    parent_issue: int,
    title: str,
    body: str,
    role: str = "coder",
    extra_labels: Optional[List[str]] = None,
    dry_run: bool = False,
    repo_dir: Path = ROOT_DIR,
    allow_duplicate: bool = False,
) -> BlockerIssueResult:
    """Create a new prerequisite blocker issue and link it to the parent issue."""
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        normalized_role = "coder"

    labels = ["type:blocker", "status:unclaimed", f"handoff:{normalized_role}"]
    if extra_labels:
        for lbl in extra_labels:
            clean_lbl = lbl.strip()
            if clean_lbl and clean_lbl not in labels:
                labels.append(clean_lbl)

    formatted_body = format_blocker_body(
        parent_issue=parent_issue,
        description=body,
        role=normalized_role,
    )

    # --- dedup guard (#1997): one blocker, one tracker -------------------------
    if not dry_run and not allow_duplicate:
        existing = find_existing_blocker(title, repo_dir=repo_dir)
        if existing is not None:
            print(
                f"♻️  Duplicate blocker suppressed: open issue #{existing} already tracks "
                f"'{title}' — linking parent to it instead of creating a new one.",
                file=sys.stderr,
            )
            # Make sure the parent still knows it is blocked (idempotent comment).
            try:
                subprocess.run(
                    ["gh", "issue", "comment", str(parent_issue), "--body",
                     f"⚠️ Blocked by prerequisite issue #{existing} (already tracked — duplicate suppressed, #1997)."],
                    cwd=str(repo_dir), capture_output=True, text=True, check=False, timeout=20,
                )
            except (subprocess.SubprocessError, OSError):
                pass
            return BlockerIssueResult(
                new_issue_number=existing,
                new_issue_url=f"https://github.com/SaifulHaqueNiloy/supremeai/issues/{existing}",
                parent_issue_number=parent_issue,
                title=title,
                role=normalized_role,
                labels=labels,
                is_dry_run=False,
                success=True,
                duplicate_of=existing,
            )

    if dry_run:
        return BlockerIssueResult(
            new_issue_number=9999,
            new_issue_url="https://github.com/SaifulHaqueNiloy/supremeai/issues/9999",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=True,
            success=True,
        )

    # 1. Execute `gh issue create`
    cmd = [
        "gh",
        "issue",
        "create",
        "--title",
        title,
        "--body",
        formatted_body,
    ]
    for lbl in labels:
        cmd.extend(["--label", lbl])

    try:
        res = subprocess.run(
            cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        )
        url = res.stdout.strip()
        # Parse issue number from URL (e.g. https://github.com/.../issues/1786 -> 1786)
        issue_num = None
        if "/issues/" in url:
            try:
                issue_num = int(url.split("/issues/")[-1].strip().split("#")[0])
            except ValueError as err:
                print(f"Warning: could not parse issue number from '{url}': {err}", file=sys.stderr)

        # 2. Post comment to parent issue
        if issue_num is not None:
            comment_body = format_parent_comment(issue_num, title, normalized_role)
            try:
                subprocess.run(
                    ["gh", "issue", "comment", str(parent_issue), "--body", comment_body],
                    cwd=str(repo_dir),
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20,
                )
            except Exception as e:
                print(f"Warning: Failed to comment on parent issue #{parent_issue}: {e}", file=sys.stderr)

        return BlockerIssueResult(
            new_issue_number=issue_num,
            new_issue_url=url,
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=False,
            success=True,
        )
    except (subprocess.SubprocessError, OSError, Exception) as e:
        return BlockerIssueResult(
            new_issue_number=None,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            labels=labels,
            is_dry_run=False,
            success=False,
            error_message=str(e),
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous Prerequisite Blocker Issue Creator per AGENTS.md Constitution"
    )
    parser.add_argument("--parent-issue", type=int, required=True, help="Parent Issue ID that is currently blocked")
    parser.add_argument("--title", type=str, required=True, help="Title for the prerequisite blocker issue")
    parser.add_argument("--body", type=str, required=True, help="Detailed explanation of the blocker defect")
    parser.add_argument("--role", choices=VALID_ROLES, default="coder", help="Responsible role lane")
    parser.add_argument("--label", action="append", dest="labels", help="Additional labels to attach")
    parser.add_argument("--dry-run", action="store_true", help="Simulate creation without hitting GitHub API")
    parser.add_argument("--allow-duplicate", action="store_true",
                        help="Force creation even if an identical open issue exists (escape hatch — state a reason)")
    parser.add_argument("--format", choices=["json", "text"], default="text", help="Output format")

    args = parser.parse_args()

    result = create_blocker_issue(
        parent_issue=args.parent_issue,
        title=args.title,
        body=args.body,
        role=args.role,
        extra_labels=args.labels,
        dry_run=args.dry_run,
        repo_dir=ROOT_DIR,
        allow_duplicate=args.allow_duplicate,
    )

    if not result.success:
        print(f"❌ Failed to create blocker issue: {result.error_message}", file=sys.stderr)
        return 1

    if args.format == "json":
        print(
            json.dumps(
                {
                    "success": result.success,
                    "new_issue_number": result.new_issue_number,
                    "new_issue_url": result.new_issue_url,
                    "parent_issue_number": result.parent_issue_number,
                    "title": result.title,
                    "role": result.role,
                    "labels": result.labels,
                    "is_dry_run": result.is_dry_run,
                    "duplicate_of": result.duplicate_of,
                },
                indent=2,
            )
        )
    else:
        print("✅ Prerequisite Blocker Issue Processed Successfully!")
        if result.duplicate_of:
            print(f"♻️  Existing Issue:  #{result.duplicate_of} (duplicate suppressed — #1997 guard)")
        print(f"🛑 New Issue:       #{result.new_issue_number or 'N/A'}")
        print(f"🔗 URL:             {result.new_issue_url}")
        print(f"📌 Blocks Parent:   #{result.parent_issue_number}")
        print(f"🎭 Target Lane:     {result.role}")
        print(f"🏷️  Labels:          {', '.join(result.labels)}")
        if result.is_dry_run:
            print("🔍 Mode:            Dry Run (No remote GitHub changes made)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
