#!/usr/bin/env python3
"""Group Branch Cleanup Utility (#2573).

Cleans up merged/closed group branches and syncs have-branch labels.

Usage:
    python scripts/ci/cleanup_group_branches.py --group <group_name>
    python scripts/ci/cleanup_group_branches.py --all
    python scripts/ci/cleanup_group_branches.py --pr <pr_number>
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

GROUP_BRANCH_PREFIX = "group/"
HAVE_BRANCH_LABEL_PREFIX = "have-branch:"
REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def fetch_group_branches() -> list[str]:
    res = run(["git", "ls-remote", "--heads", "origin"])
    branches = []
    if res.returncode == 0:
        for line in res.stdout.splitlines():
            if not line.strip():
                continue
            head = line.split("/")[-1]
            if head.startswith(GROUP_BRANCH_PREFIX):
                branches.append(head)
    return branches


def fetch_open_prs() -> list[dict[str, Any]]:
    res = run(["gh", "pr", "list", "--repo", REPO, "--state", "open", "--json", "number,title,headRefName,labels"])
    if res.returncode == 0 and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            pass
    return []


def fetch_closed_prs() -> list[dict[str, Any]]:
    res = run(["gh", "pr", "list", "--repo", REPO, "--state", "closed", "--json", "number,title,headRefName,mergedAt,labels"])
    if res.returncode == 0 and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            pass
    return []


def fetch_issues_for_group(group_name: str) -> list[dict[str, Any]]:
    label = f"group:{group_name}"
    res = run(["gh", "issue", "list", "--repo", REPO, "--label", label, "--state", "open", "--json", "number,labels"])
    if res.returncode == 0 and res.stdout.strip():
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            pass
    return []


def remove_have_branch_label(issue_number: int, label: str) -> None:
    run(["gh", "issue", "edit", str(issue_number), "--remove-label", label])


def add_have_branch_label(issue_number: int, label: str) -> None:
    run(["gh", "issue", "edit", str(issue_number), "--add-label", label])


def delete_remote_branch(branch_name: str) -> bool:
    res = run(["git", "push", "origin", "--delete", branch_name])
    return res.returncode == 0


def cleanup_group(group_name: str) -> dict[str, Any]:
    branch = f"{GROUP_BRANCH_PREFIX}{group_name}"
    report: dict[str, Any] = {"group": group_name, "branch": branch, "deleted": False, "labels_updated": 0}
    branches = fetch_group_branches()
    if branch not in branches:
        report["status"] = "branch_not_found"
        return report
    prs = fetch_open_prs() + fetch_closed_prs()
    branch_prs = [p for p in prs if p.get("headRefName") == branch]
    active_prs = [p for p in branch_prs if p.get("labels") and "queue:hold" not in [l.get("name", "") for l in p.get("labels", [])]]
    if active_prs:
        report["status"] = "active_pr_exists"
        report["prs"] = [p["number"] for p in active_prs]
        return report
    if delete_remote_branch(branch):
        report["deleted"] = True
        report["status"] = "deleted"
    else:
        report["status"] = "delete_failed"
        return report
    label = f"{HAVE_BRANCH_LABEL_PREFIX}{group_name}"
    for issue in fetch_issues_for_group(group_name):
        num = issue.get("number")
        if num:
            remove_have_branch_label(num, label)
            report["labels_updated"] += 1
    return report


def cleanup_all() -> list[dict[str, Any]]:
    branches = fetch_group_branches()
    prs = fetch_open_prs() + fetch_closed_prs()
    reports = []
    for branch in branches:
        group_name = branch[len(GROUP_BRANCH_PREFIX):]
        branch_prs = [p for p in prs if p.get("headRefName") == branch]
        active_prs = [p for p in branch_prs if p.get("labels") and "queue:hold" not in [l.get("name", "") for l in p.get("labels", [])]]
        if active_prs:
            reports.append({
                "group": group_name,
                "branch": branch,
                "status": "active_pr_exists",
                "prs": [p["number"] for p in active_prs],
            })
            continue
        if delete_remote_branch(branch):
            label = f"{HAVE_BRANCH_LABEL_PREFIX}{group_name}"
            count = 0
            for issue in fetch_issues_for_group(group_name):
                num = issue.get("number")
                if num:
                    remove_have_branch_label(num, label)
                    count += 1
            reports.append({
                "group": group_name,
                "branch": branch,
                "status": "deleted",
                "deleted": True,
                "labels_updated": count,
            })
        else:
            reports.append({
                "group": group_name,
                "branch": branch,
                "status": "delete_failed",
                "deleted": False,
            })
    return reports


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Group Branch Cleanup Utility (#2573)")
    parser.add_argument("--group", help="Specific group name to clean up")
    parser.add_argument("--all", action="store_true", help="Clean up all eligible group branches")
    parser.add_argument("--pr", type=int, help="PR number whose head branch to delete if it is a group branch")
    parser.add_argument("--format", choices=["json", "text"], default="text")
    args = parser.parse_args()
    if args.pr:
        prs = fetch_open_prs() + fetch_closed_prs()
        target = next((p for p in prs if p.get("number") == args.pr), None)
        if not target:
            print(f"PR #{args.pr} not found.", file=sys.stderr)
            return 1
        branch = target.get("headRefName", "")
        if not branch.startswith(GROUP_BRANCH_PREFIX):
            print(f"PR #{args.pr} head branch '{branch}' is not a group branch.", file=sys.stderr)
            return 1
        group_name = branch[len(GROUP_BRANCH_PREFIX):]
        report = cleanup_group(group_name)
    elif args.all:
        reports = cleanup_all()
        if args.format == "json":
            print(json.dumps(reports, indent=2))
        else:
            for r in reports:
                print(f"📁 {r['group']}: {r.get('status', 'unknown')}")
        return 0
    elif args.group:
        report = cleanup_group(args.group)
    else:
        parser.print_help()
        return 2
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"📁 {report['group']}: {report.get('status', 'unknown')}")
        if report.get("deleted"):
            print(f"   ✅ Deleted branch {report['branch']}")
        if report.get("labels_updated"):
            print(f"   🏷️ Updated have-branch labels on {report['labels_updated']} issues")
    return 0


if __name__ == "__main__":
    sys.exit(main())
