#!/usr/bin/env python3
"""Discovery-Driven Issue Creator.
================================
Implements SupremeAI Charter Rule #7 (Discovery-Driven Issue Creation):

"Any agent (coder, ci, pr-helper, platform) that discovers a bug, security
vulnerability, or architectural gap while working on their claimed issue —
is authorized and required to create a new GitHub issue for that discovery."

Usage:
    python scripts/agents/create_discovery_issue.py \\
        --parent-issue 1690 \\
        --title "fix(db): vector store leaks across tenants on pagination" \\
        --body "While fixing #1690, discovered pagination doesn't enforce tenant_id..." \\
        --role coder \\
        --severity high

    # Dry-run mode:
    python scripts/agents/create_discovery_issue.py \\
        --parent-issue 1690 \\
        --title "fix(auth): admin bypass when ENV=test" \\
        --body "Discovered that..." \\
        --role ci \\
        --severity critical \\
        --dry-run

Difference from create_blocker_issue.py:
    - Blocker issue: prerequisite that MUST be fixed before current issue can complete
    - Discovery issue: unrelated bug/gap found while working — NOT a prerequisite
    - Discovery issues get `discovered-by:<role>` label + `type:discovery` label
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]

VALID_ROLES = ("planner", "coder", "pr-helper", "ci", "platform")
VALID_SEVERITIES = ("low", "medium", "high", "critical")


@dataclass
class DiscoveryIssueResult:
    new_issue_number: int
    new_issue_url: str
    parent_issue_number: int
    title: str
    role: str
    severity: str
    labels: list[str]
    is_dry_run: bool
    success: bool
    error: str | None = None


def format_discovery_body(
    parent_issue: int,
    description: str,
    role: str,
    severity: str,
) -> str:
    """Format standard markdown body for the discovery issue."""
    return f"""### 🔍 Discovery Issue (Charter Rule #7)

**Discovered while working on:** #{parent_issue}
**Discovering Role:** `{role}`
**Severity:** `{severity}`
**Issue Type:** Discovery (NOT a prerequisite blocker — unrelated to parent scope)

---

### Description
{description.strip()}

---

### 🔗 Links
- **Discovered in:** #{parent_issue}
- **Discovering agent:** `{role}` role
- **Action Required:** This issue is available for any agent in the appropriate role lane to claim. The discovering agent should NOT fix it unless they claim it after their current PR merges.

_Automated by `scripts/agents/create_discovery_issue.py` per Charter Rule #7 (Discovery-Driven Issue Creation)._"""


def create_discovery_issue(
    parent_issue: int,
    title: str,
    body: str,
    role: str = "coder",
    severity: str = "medium",
    extra_labels: list[str] | None = None,
    dry_run: bool = False,
    repo_dir: Path = ROOT_DIR,
) -> DiscoveryIssueResult:
    """Create a new discovery issue and link it to the parent issue."""
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        normalized_role = "coder"

    normalized_severity = severity.strip().lower()
    if normalized_severity not in VALID_SEVERITIES:
        normalized_severity = "medium"

    labels = [
        "type:discovery",
        "status:unclaimed",
        f"discovered-by:{normalized_role}",
        normalized_severity,
    ]
    if extra_labels:
        for lbl in extra_labels:
            clean_lbl = lbl.strip()
            if clean_lbl and clean_lbl not in labels:
                labels.append(clean_lbl)

    formatted_body = format_discovery_body(
        parent_issue=parent_issue,
        description=body,
        role=normalized_role,
        severity=normalized_severity,
    )

    if dry_run:
        return DiscoveryIssueResult(
            new_issue_number=9999,
            new_issue_url="https://github.com/SaifulHaqueNiloy/supremeai/issues/9999",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=True,
            success=True,
        )

    def _execute_create(active_labels: list[str]) -> subprocess.CompletedProcess[str]:
        current_cmd = [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            formatted_body,
        ]
        for lbl in active_labels:
            current_cmd.extend(["--label", lbl])
        return subprocess.run(
            current_cmd,
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
            timeout=30,
        )

    try:
        try:
            res = _execute_create(labels)
        except subprocess.CalledProcessError as exc:
            # If failed due to a label error, fallback to safe standard labels
            err_msg = exc.stderr or str(exc)
            if "label" in err_msg.lower():
                safe_fallback_labels = ["status:unclaimed", normalized_severity]
                res = _execute_create(safe_fallback_labels)
                labels = safe_fallback_labels
            else:
                raise
        url = res.stdout.strip()
        try:
            issue_num = int(url.rsplit("/", 1)[-1])
        except (ValueError, IndexError):
            issue_num = 0
        return DiscoveryIssueResult(
            new_issue_number=issue_num,
            new_issue_url=url,
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=True,
        )
    except subprocess.CalledProcessError as exc:
        return DiscoveryIssueResult(
            new_issue_number=0,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=False,
            error=f"{exc.stderr or str(exc)}",
        )
    except (OSError, RuntimeError) as exc:
        return DiscoveryIssueResult(
            new_issue_number=0,
            new_issue_url="",
            parent_issue_number=parent_issue,
            title=title,
            role=normalized_role,
            severity=normalized_severity,
            labels=labels,
            is_dry_run=False,
            success=False,
            error=str(exc),
        )


def check_duplicates(title: str, repo_dir: Path = ROOT_DIR) -> list[dict]:
    """Check for existing open issues with similar titles (AUDIT-FIX #1997).

    Searches open issues for titles containing key words from the given title.
    Returns a list of potential duplicates.
    """
    import subprocess

    # Extract significant words from title (4+ chars, lowercase)
    words = [w.lower().strip(".,;:()[]{}\"'") for w in title.split() if len(w) >= 4]
    if not words:
        return []

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--state",
                "open",
                "--json",
                "number,title",
                "--limit",
                "100",
            ],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return []
        import json

        issues = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return []

    duplicates = []
    for issue in issues:
        existing_title = (issue.get("title") or "").lower()
        # Check if titles share significant words
        shared = sum(1 for w in words if w in existing_title)
        # If >50% of significant words match, it's a potential duplicate
        if shared >= max(2, len(words) // 2):
            duplicates.append(
                {
                    "number": issue.get("number"),
                    "title": issue.get("title"),
                    "shared_words": shared,
                    "total_words": len(words),
                }
            )
    return duplicates


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a discovery-driven issue (Charter Rule #7)",
    )
    parser.add_argument(
        "--parent-issue",
        type=int,
        required=True,
        help="Parent Issue ID where the discovery was made",
    )
    parser.add_argument(
        "--title", type=str, required=True, help="Title for the discovery issue"
    )
    parser.add_argument(
        "--body",
        type=str,
        required=True,
        help="Detailed description of the discovered issue",
    )
    parser.add_argument(
        "--role",
        choices=VALID_ROLES,
        default="coder",
        help="Role of the discovering agent (default: coder)",
    )
    parser.add_argument(
        "--severity",
        choices=VALID_SEVERITIES,
        default="medium",
        help="Severity level (default: medium)",
    )
    parser.add_argument(
        "--label", action="append", dest="labels", help="Additional labels to attach"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate creation without hitting GitHub API",
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="text", help="Output format"
    )
    # AUDIT-FIX (#1997): dedup flag — check for similar open issues before creating
    parser.add_argument(
        "--check-duplicates",
        action="store_true",
        default=True,
        help="Check for similar open issues before creating (default: on)",
    )
    parser.add_argument(
        "--no-check-duplicates",
        dest="check_duplicates",
        action="store_false",
        help="Skip duplicate check",
    )
    args = parser.parse_args()

    # AUDIT-FIX (#1997): dedup check before creating
    if args.check_duplicates and not args.dry_run:
        dupes = check_duplicates(args.title)
        if dupes:
            print(f"⚠️  Potential duplicate issues found ({len(dupes)}):")
            for d in dupes:
                print(
                    f"  #{d['number']}: {d['title']} ({d['shared_words']}/{d['total_words']} words match)"
                )
            print()
            print("If this is a genuine duplicate, do not create a new issue.")
            print("If this is a distinct issue, re-run with --no-check-duplicates.")
            return 1

    result = create_discovery_issue(
        parent_issue=args.parent_issue,
        title=args.title,
        body=args.body,
        role=args.role,
        severity=args.severity,
        extra_labels=args.labels,
        dry_run=args.dry_run,
    )

    if args.format == "json":
        import json

        print(json.dumps(result.__dict__, indent=2))
    else:
        if result.success:
            print(
                f"✅ Discovery issue {'[DRY-RUN]' if result.is_dry_run else 'created'}:"
            )
            print(f"   #{result.new_issue_number}: {result.title}")
            print(f"   URL: {result.new_issue_url}")
            print(f"   Role: {result.role} | Severity: {result.severity}")
            print(f"   Labels: {', '.join(result.labels)}")
            print(f"   Parent: #{result.parent_issue_number}")
        else:
            print(
                f"❌ Failed to create discovery issue: {result.error}", file=sys.stderr
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
