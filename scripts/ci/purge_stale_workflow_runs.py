#!/usr/bin/env python3
"""
scripts/ci/purge_stale_workflow_runs.py
=======================================
Nightly retention & stale workflow run cleanup engine.

# বাংলা মন্তব্য:
# এই স্ক্রিপ্টটি গিটহাব অ্যাকশনের পুরানো ও অপ্রয়োজনীয় সম্পন্ন হওয়া রান (Completed Runs)
# স্বয়ংক্রিয়ভাবে মুছে ফেলে Actions ট্যাব নিট-অ্যান্ড-ক্লিন রাখে।
# 
# কঠোর নিরাপত্তা নীতি (Safety Invariants):
# ১. Protected Branch: 'main', 'master', 'production', 'staging' ব্রাঞ্চের কোনো রান কখনো ডিলিট হবে না।
# ২. Protected Workflows: প্রোডাকশন ডিপ্লয়মেন্ট ও প্রিফ্লাইট অডিট রান সবসময় সংরক্ষিত থাকবে।
# ৩. Active Runs: শুধুমাত্র 'completed' স্ট্যাটাসের রান মূল্যায়ন করা হবে; queued/in_progress কখনো নয়।
# ৪. Open PR Failure Preservation: ওপেন PR-এর ফেইলড রান মোছা হবে না যাতে ডিবাগ করা যায়।
# ৫. Rate-limit Protection: প্রতি রানে সর্বোচ্চ --max-deletions (ডিফল্ট ১০০) রান ডিলিট করা হবে।
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def get_github_token() -> str:
    """পরিবেশ বা gh CLI থেকে অ্যাক্সেস টোকেন উদ্ধার করে।"""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return ""

DEFAULT_PROTECTED_BRANCHES: Set[str] = {
    "main",
    "master",
    "production",
    "staging",
}

DEFAULT_PROTECTED_WORKFLOWS: Set[str] = {
    "08-production-preflight.yml",
    "09-post-deploy-smoke.yml",
    "ci-deploy-production.yml",
    "audit-release.yml",
    "Production Preflight",
    "Post-Deploy Smoke Check",
    "CI Deploy Production",
    "Audit & Release Engine",
}


def parse_iso_datetime(dt_str: str) -> datetime:
    """ISO 8601 টাইমস্ট্যাম্প পার্স করে UTC datetime অবজেক্টে রূপান্তর করে।"""
    clean_str = dt_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_str).astimezone(timezone.utc)


def is_run_stale(
    run: Dict[str, Any],
    now: datetime,
    min_age_days: int = 2,
    protected_branches: Optional[Set[str]] = None,
    protected_workflows: Optional[Set[str]] = None,
) -> Tuple[bool, str]:
    """
    যাচাই করে একটি নির্দিষ্ট workflow run ডিলিট করার যোগ্য কিনা।
    Returns (is_stale, reason_string).
    """
    if protected_branches is None:
        protected_branches = DEFAULT_PROTECTED_BRANCHES
    if protected_workflows is None:
        protected_workflows = DEFAULT_PROTECTED_WORKFLOWS

    status = run.get("status")
    if status != "completed":
        return False, f"status '{status}' is not completed"

    head_branch = run.get("head_branch") or ""
    if head_branch in protected_branches:
        return False, f"head_branch '{head_branch}' is protected"

    # Workflow name ও path ফিল্টার
    workflow_name = run.get("name") or ""
    workflow_path = run.get("path") or ""
    workflow_file = workflow_path.split("/")[-1] if workflow_path else ""

    if workflow_name in protected_workflows or workflow_file in protected_workflows:
        return False, f"workflow '{workflow_name or workflow_file}' is protected"

    # বয়স গণনা (Age calculation)
    created_at_raw = run.get("created_at") or run.get("run_started_at")
    if not created_at_raw:
        return False, "missing created_at timestamp"

    try:
        created_dt = parse_iso_datetime(created_at_raw)
    except Exception as e:
        return False, f"invalid created_at timestamp: {e}"

    age = now - created_dt
    min_age = timedelta(days=min_age_days)

    if age < min_age:
        return False, f"age {age.total_seconds() / 3600:.1f}h is below threshold {min_age_days}d"

    event = run.get("event") or ""
    conclusion = run.get("conclusion") or ""

    # ১. শিডিউলড রুটিন রান (যেমন: issue-ops, merge-train, smart-merge-queue, drift checks)
    if event == "schedule":
        if conclusion in ("success", "cancelled", "skipped", "neutral"):
            return True, f"scheduled routine run (conclusion={conclusion}, age={age.days}d)"
        elif conclusion == "failure" and age >= timedelta(days=max(3, min_age_days)):
            return True, f"stale failed schedule tick (age={age.days}d >= 3d)"

    # ২. বাতিল হওয়া রান (Cancelled / Superseded runs)
    if conclusion in ("cancelled", "skipped"):
        return True, f"cancelled/skipped run on non-protected branch '{head_branch}'"

    # ৩. ফিচার ব্রাঞ্চ বা PR-এর সফল সমাপ্ত রান
    if conclusion == "success" and event in ("pull_request", "pull_request_target", "push"):
        return True, f"completed {event} run on branch '{head_branch}' (age={age.days}d)"

    return False, f"run kept (event={event}, conclusion={conclusion}, branch={head_branch})"


def fetch_completed_runs(
    repo: str,
    token: str,
    max_pages: int = 3,
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    """GitHub API থেকে সম্পন্ন হওয়া রানগুলোর তালিকা নিয়ে আসে।"""
    all_runs: List[Dict[str, Any]] = []

    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{repo}/actions/runs?status=completed&per_page={per_page}&page={page}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "SupremeAI-Nightly-Janitor",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                runs = data.get("workflow_runs", [])
                if not runs:
                    break
                all_runs.extend(runs)
                if len(runs) < per_page:
                    break
        except urllib.error.HTTPError as e:
            print(f"⚠️ GitHub API error on page {page}: {e.code} {e.reason}", file=sys.stderr)
            break
        except Exception as e:
            print(f"⚠️ Unexpected error on page {page}: {e}", file=sys.stderr)
            break

    return all_runs


def delete_single_run(repo: str, run_id: int, token: str) -> bool:
    """একটি একক রান পার্মানেন্টলি ডিলিট করার API কল।"""
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}"
    req = urllib.request.Request(
        url,
        method="DELETE",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "SupremeAI-Nightly-Janitor",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status in (204, 200)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return True  # Already deleted
        print(f"⚠️ Failed to delete run {run_id}: HTTP {e.code}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"⚠️ Failed to delete run {run_id}: {e}", file=sys.stderr)
        return False


def purge_workflow_runs(
    repo: str,
    token: str,
    min_age_days: int = 2,
    max_deletions: int = 100,
    dry_run: bool = False,
    protected_branches: Optional[Set[str]] = None,
    protected_workflows: Optional[Set[str]] = None,
    runs_override: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    মেইন পার্জ এক্সিকিউটর — ফিল্টার করে স্টেল রানগুলো ডিলিট করে।
    """
    now = datetime.now(timezone.utc)
    scanned_runs = runs_override if runs_override is not None else fetch_completed_runs(repo, token)

    eligible_runs: List[Tuple[Dict[str, Any], str]] = []
    skipped_count = 0

    for run in scanned_runs:
        stale, reason = is_run_stale(
            run=run,
            now=now,
            min_age_days=min_age_days,
            protected_branches=protected_branches,
            protected_workflows=protected_workflows,
        )
        if stale:
            eligible_runs.append((run, reason))
        else:
            skipped_count += 1

    deleted_count = 0
    errors_count = 0

    print(f"🔍 Scanned: {len(scanned_runs)} runs | Eligible: {len(eligible_runs)} | Skipped/Protected: {skipped_count}")

    for run, reason in eligible_runs:
        if deleted_count >= max_deletions:
            print(f"🛑 Reached maximum deletions limit ({max_deletions}). Stopping.")
            break

        run_id = run["id"]
        run_name = run.get("name", "Unknown")
        run_branch = run.get("head_branch", "unknown")

        if dry_run:
            print(f"[DRY-RUN] Would delete #{run_id} ({run_name} @ {run_branch}) — Reason: {reason}")
            deleted_count += 1
        else:
            success = delete_single_run(repo, run_id, token)
            if success:
                print(f"🗑️ Deleted #{run_id} ({run_name} @ {run_branch}) — Reason: {reason}")
                deleted_count += 1
            else:
                errors_count += 1

    summary = {
        "scanned": len(scanned_runs),
        "eligible": len(eligible_runs),
        "deleted": deleted_count,
        "skipped": skipped_count,
        "errors": errors_count,
        "dry_run": dry_run,
    }
    return summary


def write_step_summary(summary: Dict[str, Any], summary_file: Optional[str] = None) -> None:
    """GitHub Action Step Summary-তে সুন্দর মার্কডাউন রিপোর্ট লেখে।"""
    target = summary_file or os.environ.get("GITHUB_STEP_SUMMARY")
    if not target:
        return

    mode = "DRY-RUN (Simulated)" if summary["dry_run"] else "LIVE PURGE"
    md = f"""### 🧹 Nightly Workflow Runs Retention Report

| Metric | Value |
| :--- | :--- |
| **Execution Mode** | `{mode}` |
| **Total Runs Scanned** | `{summary['scanned']}` |
| **Eligible for Purge** | `{summary['eligible']}` |
| **Runs Deleted** | `{summary['deleted']}` |
| **Protected / Active Runs Skipped** | `{summary['skipped']}` |
| **Deletion Errors** | `{summary['errors']}` |

> 🛡️ *All runs on protected branches (`main`, `master`, `production`) and release workflows were safely preserved.*
"""
    try:
        with open(target, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    except Exception as e:
        print(f"⚠️ Could not write GITHUB_STEP_SUMMARY: {e}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly Workflow Runs Purge & Retention Engine")
    parser.add_argument("--repo", default=os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY", "SaifulHaqueNiloy/supremeai"))
    parser.add_argument("--token", default=get_github_token(), help="GitHub API Token (default: GH_TOKEN, GITHUB_TOKEN, or gh auth token)")
    parser.add_argument("--min-age-days", type=int, default=2, help="Minimum age in days for runs to be purged (default: 2)")
    parser.add_argument("--max-deletions", type=int, default=100, help="Maximum number of runs to delete in a single invocation")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without actually deleting anything")
    parser.add_argument("--summary-file", default=None, help="Path to write GitHub step summary")

    args = parser.parse_args()

    if not args.dry_run and not args.token:
        print("[ERROR] GH_TOKEN or GITHUB_TOKEN environment variable (or gh auth login) is required for live purge.", file=sys.stderr)
        return 1

    summary = purge_workflow_runs(
        repo=args.repo,
        token=args.token,
        min_age_days=args.min_age_days,
        max_deletions=args.max_deletions,
        dry_run=args.dry_run,
    )

    write_step_summary(summary, args.summary_file)
    print("\n✅ Nightly Workflow Runs Retention Sweep Completed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
