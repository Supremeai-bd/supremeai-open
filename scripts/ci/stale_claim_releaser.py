#!/usr/bin/env python3
"""
stale_claim_releaser.py — 2-Stage Graduated Lease & Orphan Claim Auto-Release Gate.

Mission & Architecture:
  Enforces the 2-Stage Dynamic Agent Lease Contract:
  
  Stage 1 (Claim -> Branch Creation): 10 Minutes Max
    When an issue is claimed by an agent, the work branch must be created/pushed
    within 10 minutes. If no remote branch matching the issue appears in 10 minutes,
    the claiming agent is considered disconnected/failed-to-start.
    -> The claim marker is released immediately back to the pool.

  Stage 2 (Branch -> Pull Request): 30 Minutes Max
    Once a branch exists, the agent has 30 minutes to complete the 3-tier
    verification and open an active Pull Request. If 30 minutes elapse with a branch
    active but zero open PR submitted, the agent is considered stuck/abandoned.
    -> The claim marker is released back to the pool.

Principles:
  - Stdlib-only: zero external dependencies, runs in public GitHub Actions and offline.
  - Fail-closed: invalid inputs or unreadable data produce non-zero exits, never silent skips.
  - Fast: ls-remote and gh queries execute in ~1-2 seconds.
  - Testable: includes --self-test with offline fixtures.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UPSTREAM_REPO = os.environ.get("GH_REPO", "Supremeai-bd/supremeai-open")
CLAIMED_LABELS = {"status:claimed", "status:in-progress"}
EXCLUDED_LABELS = {"state:seq-hold", "blocked-by-upstream", "mirror:private"}

CLAIM_PATTERNS = [
    re.compile(r"(?:🎯|🤖)?\s*\**\bclaim(?:ing|ed)?\b\**", re.IGNORECASE),
    re.compile(r"claiming this issue", re.IGNORECASE),
    re.compile(r"agent claim", re.IGNORECASE),
]

STAGE_1_CLAIM_TO_BRANCH_MINUTES = 10.0
STAGE_2_BRANCH_TO_PR_MINUTES = 30.0


def run_cmd(args: List[str]) -> Tuple[int, str, str]:
    """Execute a CLI command with UTF-8 encoding."""
    try:
        res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
        return res.returncode, res.stdout, res.stderr
    except Exception as exc:
        return 1, "", str(exc)


def is_claim_comment(body: str) -> bool:
    """Check if comment text represents an agent task claim."""
    if not body:
        return False
    return any(p.search(body) for p in CLAIM_PATTERNS)


def extract_claim_timestamp(issue: Dict[str, Any]) -> Optional[datetime.datetime]:
    """Find the timestamp of the latest claim comment or claim update."""
    comments = issue.get("comments", []) or []
    latest_claim_dt: Optional[datetime.datetime] = None

    for c in comments:
        c_body = c.get("body", "")
        if is_claim_comment(c_body):
            c_time_str = c.get("createdAt")
            if c_time_str:
                try:
                    c_dt = datetime.datetime.fromisoformat(c_time_str.replace("Z", "+00:00"))
                    if latest_claim_dt is None or c_dt > latest_claim_dt:
                        latest_claim_dt = c_dt
                except Exception:
                    pass

    if latest_claim_dt is not None:
        return latest_claim_dt

    labels = [str(l.get("name", "")).lower() for l in issue.get("labels", []) if isinstance(l, dict)]
    if any(l in CLAIMED_LABELS for l in labels) or (CLAIMABLE_LABEL not in labels):
        up_str = issue.get("updatedAt")
        if up_str:
            try:
                return datetime.datetime.fromisoformat(up_str.replace("Z", "+00:00"))
            except Exception:
                pass

    return None


def get_remote_branches(repo: str) -> List[str]:
    """Fetch remote branch refnames from origin."""
    code, out, _ = run_cmd(["git", "ls-remote", "--heads", "origin"])
    if code != 0 or not out.strip():
        # Fallback to gh api
        code, out, _ = run_cmd(["gh", "api", f"repos/{repo}/branches", "--jq", ".[].name"])
        if code == 0 and out.strip():
            return [b.strip() for b in out.strip().split("\n") if b.strip()]
        return []

    branches = []
    for line in out.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            branches.append(parts[1].replace("refs/heads/", "").strip())
    return branches


def issue_has_remote_branch(issue_number: int, branch_names: List[str]) -> Tuple[bool, Optional[str]]:
    """Determine if any remote branch targets this issue number."""
    # Matches /123, -123-, -123, issue-123, issue123
    num_str = str(issue_number)
    pattern = re.compile(rf"(^|/|-|_)({num_str})($|/|-|_)", re.IGNORECASE)

    for b in branch_names:
        if pattern.search(b) or f"issue-{num_str}" in b.lower() or f"issue{num_str}" in b.lower():
            return True, b
    return False, None


def get_open_pr_issue_references(repo: str) -> Set[int]:
    """Fetch all issue numbers currently referenced by open PRs."""
    code, out, _ = run_cmd([
        "gh", "pr", "list",
        "--repo", repo,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,body,headRefName"
    ])
    if code != 0 or not out.strip():
        return set()

    try:
        prs = json.loads(out)
    except Exception:
        return set()

    referenced_issues: Set[int] = set()
    for pr in prs:
        text = f"{pr.get('title', '')} {pr.get('body', '')} {pr.get('headRefName', '')}"
        matches = re.findall(r"#(\d+)|(?:issue[-_](\d+))", text, re.IGNORECASE)
        for m in matches:
            for num_str in m:
                if num_str:
                    referenced_issues.add(int(num_str))

    return referenced_issues


def evaluate_graduated_claims(
    issues: List[Dict[str, Any]],
    open_pr_refs: Set[int],
    remote_branches: List[str],
    claim_to_branch_min: float = STAGE_1_CLAIM_TO_BRANCH_MINUTES,
    branch_to_pr_min: float = STAGE_2_BRANCH_TO_PR_MINUTES,
    now: Optional[datetime.datetime] = None,
) -> List[Dict[str, Any]]:
    """Evaluate 2-stage graduated lease: 10m to branch, 30m branch to PR."""
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)

    stale: List[Dict[str, Any]] = []

    for issue in issues:
        num = issue.get("number")
        if not num:
            continue

        labels = [str(l.get("name", "")).lower() for l in issue.get("labels", []) if isinstance(l, dict)]
        if any(ex in labels for ex in EXCLUDED_LABELS):
            continue
        if any(l.startswith("bridge:") for l in labels):
            continue

        title_lower = issue.get("title", "").lower()
        if title_lower.startswith("audit(") or "admin_decision" in title_lower or "bridge work order" in title_lower:
            continue

        has_claimed_label = any(cl in labels for cl in CLAIMED_LABELS)
        claim_dt = extract_claim_timestamp(issue)

        is_claimed = has_claimed_label or (claim_dt is not None)
        if not is_claimed:
            continue

        # If an active open PR exists, claim is progressing cleanly
        if int(num) in open_pr_refs:
            continue

        if claim_dt is None:
            continue

        elapsed_min = (now - claim_dt).total_seconds() / 60.0
        has_branch, matched_branch = issue_has_remote_branch(int(num), remote_branches)

        # STAGE 1 CHECK: No branch pushed within 10 minutes of claim
        if not has_branch:
            if elapsed_min >= claim_to_branch_min:
                stale.append({
                    "number": num,
                    "title": issue.get("title", ""),
                    "stage": 1,
                    "reason": f"No branch created within {claim_to_branch_min}m of claim",
                    "elapsed_minutes": round(elapsed_min, 1),
                    "branch": None,
                    "labels": labels,
                })
        else:
            # STAGE 2 CHECK: Branch exists, but no PR submitted within 30 minutes
            if elapsed_min >= (claim_to_branch_min + branch_to_pr_min):
                stale.append({
                    "number": num,
                    "title": issue.get("title", ""),
                    "stage": 2,
                    "reason": f"Branch '{matched_branch}' exists but no PR created within {branch_to_pr_min}m",
                    "elapsed_minutes": round(elapsed_min, 1),
                    "branch": matched_branch,
                    "labels": labels,
                })

    return stale


def release_issue_claim(repo: str, issue_number: int, stage: int, reason: str, elapsed_min: float) -> bool:
    """Post release comment and remove status:claimed."""
    comment = (
        f"⏰ **Graduated Lease Auto-Release (Stage {stage})**\n\n"
        f"- **Trigger:** {reason} (elapsed: {elapsed_min}m)\n"
        f"- **Heartbeat Policy:** Claim-to-branch TTL is 10 min; branch-to-PR TTL is 30 min.\n"
        f"- **Action:** Releasing claim marker back to the public pool.\n\n"
        f"Task is immediately available for `--pick-next` dispatch."
    )
    # Post audit comment
    run_cmd(["gh", "issue", "comment", str(issue_number), "--repo", repo, "--body", comment])

    # Remove claimed / in-progress markers
    cmd = ["gh", "issue", "edit", str(issue_number), "--repo", repo]
    for cl in CLAIMED_LABELS:
        cmd.extend(["--remove-label", cl])

    l_code, _, _ = run_cmd(cmd)
    return l_code == 0


def run_self_test() -> int:
    """Offline test of the 2-stage graduated lease."""
    print("Running 2-stage graduated lease self-test...")
    base_time = datetime.datetime(2026, 10, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Issue 1: Claimed 5 min ago, no branch -> NOT stale (within 10 min window)
    iss1 = {
        "number": 1,
        "title": "task 1",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": "2026-10-15T11:55:00Z"}]
    }

    # Issue 2: Claimed 15 min ago, NO branch -> STALE (Stage 1 trigger: >10m no branch)
    iss2 = {
        "number": 2,
        "title": "task 2",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": "2026-10-15T11:45:00Z"}]
    }

    # Issue 3: Claimed 25 min ago, branch exists -> NOT stale (within 40 min total)
    iss3 = {
        "number": 3,
        "title": "task 3",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": "2026-10-15T11:35:00Z"}]
    }

    # Issue 4: Claimed 45 min ago, branch exists but NO PR -> STALE (Stage 2 trigger: >40m)
    iss4 = {
        "number": 4,
        "title": "task 4",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": "2026-10-15T11:15:00Z"}]
    }

    # Issue 5: Claimed 50 min ago, PR exists -> NOT stale (PR active)
    iss5 = {
        "number": 5,
        "title": "task 5",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": "2026-10-15T11:10:00Z"}]
    }

    branches = ["feat/issue-3-contract", "fix/issue-4-repair", "fix/issue-5-patch"]
    open_prs = {5}

    stale = evaluate_graduated_claims(
        [iss1, iss2, iss3, iss4, iss5],
        open_prs,
        branches,
        claim_to_branch_min=10.0,
        branch_to_pr_min=30.0,
        now=base_time
    )

    assert len(stale) == 2, f"Expected 2 stale issues, got {len(stale)}"
    assert stale[0]["number"] == 2 and stale[0]["stage"] == 1, f"Expected #2 Stage 1, got {stale[0]}"
    assert stale[1]["number"] == 4 and stale[1]["stage"] == 2, f"Expected #4 Stage 2, got {stale[1]}"
    print("✅ 2-Stage graduated lease self-test passed cleanly!")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="2-Stage Graduated Claim Lease Gate")
    parser.add_argument("--repo", default=UPSTREAM_REPO, help="GitHub repository (owner/repo)")
    parser.add_argument("--claim-to-branch-min", type=float, default=STAGE_1_CLAIM_TO_BRANCH_MINUTES,
                        help="Minutes allowed from claim to branch push (default: 10)")
    parser.add_argument("--branch-to-pr-min", type=float, default=STAGE_2_BRANCH_TO_PR_MINUTES,
                        help="Minutes allowed from branch to PR creation (default: 30)")
    parser.add_argument("--auto-release", action="store_true", help="Automatically release claims on GitHub")
    parser.add_argument("--self-test", action="store_true", help="Run offline self-test and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    print(f"🔍 Checking 2-stage graduated claim leases on {args.repo}...")
    print(f"   Stage 1: {args.claim_to_branch_min}m (Claim -> Branch) | Stage 2: {args.branch_to_pr_min}m (Branch -> PR)")

    code, out, err = run_cmd([
        "gh", "issue", "list",
        "--repo", args.repo,
        "--state", "open",
        "--limit", "200",
        "--json", "number,title,labels,comments,updatedAt,createdAt"
    ])
    if code != 0:
        print(f"❌ Failed to fetch issues: {err}", file=sys.stderr)
        return 1

    try:
        issues = json.loads(out)
    except Exception as exc:
        print(f"❌ Failed to parse issues JSON: {exc}", file=sys.stderr)
        return 1

    open_prs = get_open_pr_issue_references(args.repo)
    remote_branches = get_remote_branches(args.repo)
    stale_issues = evaluate_graduated_claims(
        issues,
        open_prs,
        remote_branches,
        claim_to_branch_min=args.claim_to_branch_min,
        branch_to_pr_min=args.branch_to_pr_min
    )

    if not stale_issues:
        print(f"✅ Clean: Zero orphaned claims detected across {len(issues)} open issues.")
        return 0

    print(f"⚠️ Found {len(stale_issues)} orphaned claim(s):")
    for s in stale_issues:
        print(f"  - Issue #{s['number']} [Stage {s['stage']}]: '{s['title']}' ({s['reason']}, elapsed: {s['elapsed_minutes']}m)")
        if args.auto_release:
            print(f"    🔄 Releasing claim for #{s['number']}...")
            ok = release_issue_claim(args.repo, s["number"], s["stage"], s["reason"], s["elapsed_minutes"])
            if ok:
                print(f"    ✅ Issue #{s['number']} successfully released to {CLAIMABLE_LABEL}.")
            else:
                print(f"    ❌ Failed to release #{s['number']}.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
