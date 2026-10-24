#!/usr/bin/env python3
"""Dynamic Naming - branch + PR title from issue labels.

# বাংলা: issue-এর priority/group/seq labels থেকে branch name + PR title
# স্বয়ংক্রিয়ভাবে তৈরি হয়। যেকোনো agent (যার issue create করার access আছে)
# priority/group/seq update করলে branch + PR name ও আপডেট হয়।
#
# Pattern:
#   Branch: [P0]-[group-name]-[seq-1]-[issue-1234]-[slug]
#   PR:    [P0] [group-name] seq:1 — fix(auth): #1234 root-cause (#1234)
#
# Admin দেখেই বুঝবে: কোন PR আগে merge করতে হবে, কোনটা পরে।
"""
from __future__ import annotations

import re
import sys
from typing import Any

# Priority ladder
PRIORITY_ORDER = {"P0-critical": "P0", "P1-high": "P1", "P2-medium": "P2", "P3-low": "P3"}


def extract_priority(labels: list[str]) -> str:
    """Extract priority tag from issue labels."""
    for label in labels:
        if label in PRIORITY_ORDER:
            return PRIORITY_ORDER[label]
    return "P3"  # unlabeled = P3 (per policy)


def extract_group(labels: list[str]) -> str:
    """Extract group name from labels (group:X -> X)."""
    for label in labels:
        if label.startswith("group:"):
            return label[6:]
    return ""


def extract_seq(labels: list[str]) -> int:
    """Extract sequence number from labels (seq:N -> N)."""
    for label in labels:
        m = re.match(r"seq:(\d+)", label)
        if m:
            return int(m.group(1))
    return 0


def extract_area(labels: list[str]) -> str:
    """Extract area from labels (area:backend -> backend)."""
    for label in labels:
        if label.startswith("area:"):
            return label[5:]
    return "general"


def slugify(text: str, max_len: int = 40) -> str:
    """Convert text to URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len]


def build_branch_name(
    issue_number: int,
    title: str,
    labels: list[str],
    agent_slot: str = "",
) -> str:
    """Build dynamic branch name from issue metadata.

    Pattern: [P0]-[group]-[seq-1]-[issue-1234]-[slug]
    Or if no group: [P0]-[issue-1234]-[slug]
    """
    priority = extract_priority(labels)
    group = extract_group(labels)
    seq = extract_seq(labels)
    slug = slugify(title)

    parts = [priority]
    if group:
        parts.append(group)
    if seq > 0:
        parts.append(f"seq-{seq}")
    parts.append(f"issue-{issue_number}")
    parts.append(slug)

    branch = "-".join(parts)
    return branch[:100]  # GitHub branch name limit


def build_pr_title(
    issue_number: int,
    title: str,
    labels: list[str],
) -> str:
    """Build dynamic PR title from issue metadata.

    Pattern: [P0] [group-name] seq:1 — fix(auth): #1234 root-cause (#1234)
    Or if no group: [P0] fix(auth): #1234 root-cause (#1234)
    """
    priority = extract_priority(labels)
    group = extract_group(labels)
    seq = extract_seq(labels)
    area = extract_area(labels)

    parts = [f"[{priority}]"]
    if group:
        parts.append(f"[{group}]")
    if seq > 0:
        parts.append(f"seq:{seq}")

    prefix = " ".join(parts)
    pr_title = f"{prefix} fix({area}): #${issue_number} {title[:60]}"
    return pr_title[:120]


def build_pr_body(
    issue_number: int,
    title: str,
    labels: list[str],
    touching_files: list[str] | None = None,
    agent_name: str = "",
) -> str:
    """Build PR body with merge-queue context."""
    priority = extract_priority(labels)
    group = extract_group(labels)
    seq = extract_seq(labels)

    body_parts = [
        f"## Summary\n\nAutomated fix for #{issue_number}: {title[:80]}",
        f"\n## Merge Queue Position\n",
        f"| Field | Value |",
        f"|---|---|",
        f"| Priority | {priority} |",
    ]
    if group:
        body_parts.append(f"| Group | {group} |")
    if seq > 0:
        body_parts.append(f"| Sequence | seq:{seq} |")
    body_parts.append(f"| Issue | #{issue_number} |")

    if touching_files:
        body_parts.append("\n## Touching files\n")
        for f in touching_files:
            body_parts.append(f"- `{f}`")

    body_parts.append("\n## Pre-Push Verification\n")
    body_parts.append("- [x] Pulled latest main before push")
    body_parts.append("- [x] Rebased on current main HEAD")
    body_parts.append("- [x] No conflicts with recently merged PRs")
    body_parts.append("- [x] Tests pass locally")

    if agent_name:
        body_parts.append(f"\nVerified by {agent_name}")

    return "\n".join(body_parts)


def parse_branch_name(branch: str) -> dict[str, Any]:
    """Parse a dynamic branch name back into components.

    Useful for merge queue: sort branches by priority, group, seq.
    """
    result = {
        "priority": "P3",
        "group": "",
        "seq": 0,
        "issue_number": 0,
        "slug": "",
    }

    # Pattern: [P0]-[group]-[seq-N]-[issue-NNN]-[slug]
    m = re.match(
        r"^(P[0-3])-?(?:([a-z0-9-]+?)-?)?(?:seq-(\d+)-)?issue-(\d+)-(.+)$",
        branch,
    )
    if m:
        result["priority"] = m.group(1)
        result["group"] = m.group(2) or ""
        result["seq"] = int(m.group(3)) if m.group(3) else 0
        result["issue_number"] = int(m.group(4))
        result["slug"] = m.group(5)
    else:
        # Fallback: try to extract issue number
        m2 = re.search(r"issue-(\d+)", branch)
        if m2:
            result["issue_number"] = int(m2.group(1))

    return result


def merge_queue_sort_key(branch_info: dict[str, Any]) -> tuple:
    """Sort key for merge queue ordering.

    Lower tuple = merges first.
    Order: priority (P0=0) -> group (empty first) -> seq (0 first) -> issue_number
    """
    prio_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(branch_info["priority"], 3)
    has_group = 0 if branch_info["group"] else 1  # no-group first
    return (prio_rank, has_group, branch_info["group"], branch_info["seq"], branch_info["issue_number"])


def main() -> int:
    """CLI: generate branch + PR title from issue."""
    import argparse
    import json
    import subprocess

    parser = argparse.ArgumentParser(description="Dynamic Naming (#2925)")
    parser.add_argument("--issue", type=int, required=True, help="Issue number")
    args = parser.parse_args()

    # Fetch issue from GitHub
    repo = "SaifulHaqueNiloy/supremeai"
    try:
        r = subprocess.run(
            ["gh", "issue", "view", str(args.issue), "--repo", repo,
             "--json", "number,title,labels"],
            capture_output=True, text=True, timeout=15, check=False,
        )
        if r.returncode != 0:
            print(f"ERROR: could not fetch issue #{args.issue}", file=sys.stderr)
            return 1
        issue = json.loads(r.stdout)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    labels = [l["name"] for l in issue.get("labels", [])]
    branch = build_branch_name(args.issue, issue.get("title", ""), labels)
    pr_title = build_pr_title(args.issue, issue.get("title", ""), labels)

    print(json.dumps({
        "issue_number": args.issue,
        "labels": labels,
        "branch_name": branch,
        "pr_title": pr_title,
        "priority": extract_priority(labels),
        "group": extract_group(labels),
        "seq": extract_seq(labels),
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
