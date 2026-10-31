#!/usr/bin/env python3
"""SupremeAI — Lightweight CI Watchdog & In-Place Labeler.

Responsibilities:
1. Handle CI failure events instantly.
2. In-place update: strip 'claimed' and ensure 'ci-failed' + 'status:unclaimed'
   on failing PR and linked issue (Zero Issue Duplication).
3. Post single failure notice comment on domain anchor hub without creating any new issue.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OPEN_REPO = "Supremeai-bd/supremeai-open"
DEFAULT_ANCHOR = 762

ANCHOR_MAP: dict[str, int] = {
    "Supremeai-bd/supremeai-studio": 749,
    "Supremeai-bd/supremeai-api": 750,
    "Supremeai-bd/supremeai-core": 751,
    "Supremeai-bd/supremeai-vscode": 754,
    "Supremeai-bd/supremeai-browser": 756,
    "Supremeai-bd/supremeai": 761,
    "Supremeai-bd/supremeai-open": 762,
}


def get_default_token() -> str:
    return (
        os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or os.environ.get("OPEN_SYNC_PAT")
        or os.environ.get("MERGE_PAT")
        or ""
    )


def gh_api(endpoint: str, token: str | None = None, method: str = "GET", data: Any = None) -> tuple[int, Any]:
    tok = token or get_default_token()
    url = f"https://api.github.com/{endpoint.lstrip('/')}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-CI-Watchdog",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            return resp.status, json.loads(content) if content else {}
    except urllib.error.HTTPError as err:
        try:
            err_content = err.read().decode("utf-8")
            return err.code, json.loads(err_content) if err_content else {}
        except Exception:
            return err.code, {}
    except Exception as exc:
        print(f"[watchdog] API error on {endpoint}: {exc}")
        return 0, {}


def active_anchor_for_repo(repo: str) -> int:
    return ANCHOR_MAP.get(repo, DEFAULT_ANCHOR)


def label_pr_lane_failure(repo: str, pr_num: int, run_id: int | str, html_url: str, token: str | None = None) -> bool:
    """In-place update: remove claimed labels, add ci-failed and status:unclaimed."""
    tok = token or get_default_token()
    code, pr_data = gh_api(f"repos/{repo}/pulls/{pr_num}", token=tok)
    if code != 200 or not isinstance(pr_data, dict):
        print(f"[watchdog] Could not fetch PR #{pr_num} on {repo} (HTTP {code}).")
        return False

    # 1. Update PR labels
    for claimed_lbl in ("status:claimed", "claimed"):
        gh_api(f"repos/{repo}/issues/{pr_num}/labels/{claimed_lbl}", token=tok, method="DELETE")
    gh_api(
        f"repos/{repo}/issues/{pr_num}/labels",
        token=tok,
        method="POST",
        data={"labels": ["ci-failed", "status:unclaimed"]},
    )
    print(f"✅ [watchdog] Marked PR #{pr_num} as 'ci-failed' and 'status:unclaimed' in-place.")

    # 2. Update linked target issue if present via Closes/Fixes/Resolves #N
    pr_body = pr_data.get("body") or ""
    closes_match = re.search(r"(?:closes|fixes|resolves)\s+#(\d+)", pr_body, re.IGNORECASE)
    if closes_match:
        target_issue_num = int(closes_match.group(1))
        for claimed_lbl in ("status:claimed", "claimed"):
            gh_api(f"repos/{OPEN_REPO}/issues/{target_issue_num}/labels/{claimed_lbl}", token=tok, method="DELETE")
        gh_api(
            f"repos/{OPEN_REPO}/issues/{target_issue_num}/labels",
            token=tok,
            method="POST",
            data={"labels": ["ci-failed", "status:unclaimed"]},
        )
        print(f"✅ [watchdog] Marked target issue #{target_issue_num} as 'ci-failed' and 'status:unclaimed' in-place.")
    else:
        # Record comment on anchor if unlinked
        anchor = active_anchor_for_repo(repo)
        gh_api(
            f"repos/{OPEN_REPO}/issues/{anchor}/comments",
            token=tok,
            method="POST",
            data={"body": f"⚠️ **PR #{pr_num} CI Failed** in run [{run_id}]({html_url}). Marked in-place."},
        )
    return True


def mirror_failure(
    repo: str,
    workflow_name: str,
    run_id: int | str,
    html_url: str,
    branch: str = "main",
    commit_sha: str = "",
    error_summary: str = "",
    token: str | None = None,
) -> bool:
    """Instant CI failure handling with Zero Issue Creation."""
    print(f"[watchdog] Handling CI failure: {repo} branch '{branch}' (run #{run_id})")

    # If it's a PR lane (e.g. 123/merge or feature branch)
    merge_pr_match = re.fullmatch(r"(\d+)/merge", (branch or "").strip())
    if merge_pr_match:
        pr_num = int(merge_pr_match.group(1))
        return label_pr_lane_failure(repo, pr_num, run_id, html_url, token=token)

    # If failure is on main, record a single comment on domain anchor (zero new issues created)
    anchor = active_anchor_for_repo(repo)
    gh_api(
        f"repos/{OPEN_REPO}/issues/{anchor}/comments",
        token=token,
        method="POST",
        data={
            "body": (
                f"🚨 **CI Failure** on `{repo}` (`{branch}`):\n"
                f"- Workflow: `{workflow_name}`\n"
                f"- Run: [{run_id}]({html_url})\n"
                f"- Commit: `{commit_sha[:8] if commit_sha else 'n/a'}`\n"
                f"Recorded in-place on Anchor #{anchor}; zero new issues created."
            )
        },
    )
    print(f"✅ [watchdog] Recorded in-place on Domain Anchor #{anchor}. Zero issues created.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Lightweight CI Watchdog")
    parser.add_argument("--payload", help="JSON client_payload from federation_ci_failed dispatch event")
    parser.add_argument("--repo", default=OPEN_REPO, help="Repository name")
    parser.add_argument("--workflow-name", default="CI", help="Workflow name")
    parser.add_argument("--run-id", default=0, help="Run ID")
    parser.add_argument("--html-url", default="", help="Run HTML URL")
    parser.add_argument("--branch", default="main", help="Branch name")
    args = parser.parse_args()

    if args.payload:
        try:
            data = json.loads(args.payload)
            mirror_failure(
                repo=data.get("repo", OPEN_REPO),
                workflow_name=data.get("workflow_name", "CI"),
                run_id=data.get("run_id", 0),
                html_url=data.get("html_url", ""),
                branch=data.get("branch", "main"),
                commit_sha=data.get("commit_sha", ""),
            )
            return 0
        except Exception as exc:
            print(f"[watchdog] Error parsing payload: {exc}")
            return 1

    mirror_failure(
        repo=args.repo,
        workflow_name=args.workflow_name,
        run_id=args.run_id,
        html_url=args.html_url,
        branch=args.branch,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
