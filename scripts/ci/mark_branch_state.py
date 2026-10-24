#!/usr/bin/env python3
"""Branch State Manager — lightweight label transitions (#4200).

বাংলা সারসংক্ষেপ:
------------------
#4200 §2: lightweight branch-state signaling via issue labels।
Labels are coordination hints, NOT the source of truth। Git branch existence,
commit history, and issue linkage remain authoritative।

State transitions:
  (none) →→→ active    [claim: agent starts work]
  active →→→ paused    [graceful exit: agent session ends, work resumable]
  active →→→ orphaned  [stale detect: agent session lost unexpectedly]
  paused →→→ active    [resume: replacement agent takes over]
  orphaned →→→ active  [resume: replacement agent takes over]
  active →→→ ready     [work complete + verified — ready for PR]
  ready  →→→ (PR)      [PR created, branch enters integration phase]

Usage:
  python scripts/ci/mark_branch_state.py <issue_number> <state> [--branch-name <name>]
  python scripts/ci/mark_branch_state.py 4200 active --branch-name agent/4200-persistent-branch
  python scripts/ci/mark_branch_state.py 4200 paused
  python scripts/ci/mark_branch_state.py 4200 ready
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")

VALID_STATES = {"active", "paused", "orphaned", "ready"}

STATE_LABELS = {
    "active": "branch:active",
    "paused": "branch:paused",
    "orphaned": "branch:orphaned",
    "ready": "branch:ready",
}

ALL_BRANCH_LABELS = set(STATE_LABELS.values())


def get_gh_token() -> str:
    """Get GitHub token from env (GH_TOKEN preferred, fallback to gh auth)."""
    token = os.environ.get("GH_TOKEN", "").strip()
    if not token:
        try:
            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
            )
            token = result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            pass
    if not token:
        print("ERROR: GH_TOKEN not set and gh auth token unavailable", file=sys.stderr)
        sys.exit(1)
    return token


def api_call(method: str, path: str, token: str, data: dict | None = None) -> dict:
    """Make a GitHub API call."""
    url = f"https://api.github.com/repos/{REPO}/{path}"
    payload = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API error {e.code}: {body[:200]}", file=sys.stderr)
        return {"error": e.code, "message": body[:200]}
    except Exception as e:
        print(f"API call failed: {e}", file=sys.stderr)
        return {"error": str(e)}


def get_current_labels(issue_number: int, token: str) -> set[str]:
    """Get current labels on an issue."""
    result = api_call("GET", f"issues/{issue_number}", token)
    return {l["name"] for l in result.get("labels", [])}


def remove_labels(issue_number: int, labels: set[str], token: str) -> None:
    """Remove branch:* labels from an issue."""
    for label in labels:
        if label in ALL_BRANCH_LABELS:
            api_call("DELETE", f"issues/{issue_number}/labels/{label}", token)


def add_label(issue_number: int, label: str, token: str) -> None:
    """Add a label to an issue."""
    api_call("POST", f"issues/{issue_number}/labels", token, {"labels": [label]})


def mark_branch_state(issue_number: int, state: str, branch_name: str | None = None, token: str | None = None) -> bool:
    """Transition an issue's branch state to a new state.

    বাংলা: issue-র branch state transition করে — আগের branch:* labels remove,
    নতুন label add।

    Returns:
        True if transition succeeded, False otherwise.
    """
    if state not in VALID_STATES:
        print(f"ERROR: invalid state '{state}'. Valid: {sorted(VALID_STATES)}", file=sys.stderr)
        return False

    if token is None:
        token = get_gh_token()

    new_label = STATE_LABELS[state]
    current_labels = get_current_labels(issue_number, token)
    current_branch_labels = current_labels & ALL_BRANCH_LABELS

    # Remove existing branch:* labels (except the target)
    labels_to_remove = current_branch_labels - {new_label}
    if labels_to_remove:
        remove_labels(issue_number, labels_to_remove, token)

    # Add the new label
    if new_label not in current_labels:
        add_label(issue_number, new_label, token)

    # Post a comment with branch info
    comment_body = f"<!-- branch-state:{state} -->\n## Branch State: {state}\n"
    if branch_name:
        comment_body += f"- **Branch:** `{branch_name}`\n"
    comment_body += f"- **State:** `{state}`\n"
    comment_body += f"- **Issue:** #{issue_number}\n"
    if state == "paused":
        comment_body += "\n> Branch work paused — next agent can resume from existing commits.\n"
    elif state == "orphaned":
        comment_body += "\n> Branch orphaned — agent session lost. Next agent may resume.\n"
    elif state == "ready":
        comment_body += "\n> Branch ready for PR creation — work complete, verified.\n"

    api_call("POST", f"issues/{issue_number}/comments", token, {"body": comment_body})

    print(f"✅ Issue #{issue_number} branch state → {state} (label: {new_label})")
    if branch_name:
        print(f"   Branch: {branch_name}")

    return True


def discover_branch(issue_number: int, token: str | None = None) -> str | None:
    """Discover an existing issue-deterministic branch.

    বাংলা (#4200 §3): `git ls-remote --heads origin agent/<issue>-*` দিয়ে
    existing branch খোঁজে। থাকলে branch name return, নাহলে None।

    Returns:
        Branch name if found, None otherwise.
    """
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--heads", "origin", f"agent/{issue_number}-*"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Return the first matching branch
            lines = result.stdout.strip().split("\n")
            if lines:
                # Format: "<sha>\trefs/heads/agent/<issue>-<slug>"
                branch_ref = lines[0].split("\t")[1] if "\t" in lines[0] else ""
                return branch_ref.replace("refs/heads/", "")
    except Exception:
        pass
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Branch State Manager (#4200)")
    parser.add_argument("issue_number", type=int, help="Issue number")
    parser.add_argument("state", choices=sorted(VALID_STATES), help="New branch state")
    parser.add_argument("--branch-name", help="Branch name (optional, for audit trail)")
    parser.add_argument("--discover", action="store_true", help="Discover existing branch for issue")
    args = parser.parse_args()

    if args.discover:
        token = get_gh_token()
        branch = discover_branch(args.issue_number, token)
        if branch:
            print(branch)
            return 0
        else:
            print(f"No branch found for issue #{args.issue_number}", file=sys.stderr)
            return 1

    success = mark_branch_state(args.issue_number, args.state, args.branch_name)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
