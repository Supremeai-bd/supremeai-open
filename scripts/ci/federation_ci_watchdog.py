#!/usr/bin/env python3
"""scripts/ci/federation_ci_watchdog.py — Federation-Wide CI Failure Watchdog & Open Queue Mirror.

Automatically mirrors CI failures from all 12 SupremeAI federation repositories
into the public task queue (`Supremeai-bd/supremeai-open`) as actionable agent
task contract issues.

Supports:
  1. Direct event handling: receives `federation_ci_failed` payload and mirrors instantly.
  2. Watchdog polling: audits all 12 federation repositories for recent failed runs.
  3. Strict deduplication: idempotent via `<!-- MIRROR_RUN: {repo}/actions/runs/{run_id} -->`.
  4. Offline self-test: `--self-test` verifies formatting, contract compliance, and dedup.
  5. Lane-honest classification (#1764): a failure on `main` is a production
     P0-critical incident; a failure on any PR lane (`<N>/merge` merge-ref or
     feature branch) is a P2-medium PR-lane incident — the poll previously
     labeled both "P0-critical (Production CI failure / blocker)", which
     misrouted the whole solver fleet onto policy rejections (e.g. the U4
     Anti-Duplicate PR Guard correctly bouncing a duplicate PR) while live
     `main` was green. Priority must describe the lane scope, not amplify it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from scripts.ci.federation_anchors import (
        get_anchor_issue_number,
        list_sub_issue_ids,
        link_sub_issue,
    )
except ImportError:
    try:
        from federation_anchors import (
            get_anchor_issue_number,
            list_sub_issue_ids,
            link_sub_issue,
        )
    except ImportError:
        get_anchor_issue_number = None
        list_sub_issue_ids = None
        link_sub_issue = None

OPEN_REPO = "Supremeai-bd/supremeai-open"

# Lane classification (#1764): production incidents are failures on the
# tracked branch. Everything else — GitHub PR merge-refs (`<N>/merge`, the
# head_branch shape of pull_request runs) and feature branches — is PR-lane
# scope: real signal, but never a production outage on the tracked branch.
PRODUCTION_BRANCH = "main"


def classify_failure_lane(branch: str) -> str:
    """Pure: 'production' only for the tracked branch, else 'pr-lane'.

    Fail-safe direction: an unknown/empty branch is NOT promoted to
    production — crying wolf is the failure mode this gate exists to stop
    (the empty-string default would otherwise classify as `main` upstream
    callers that forgot to pass the branch through).
    """
    return "production" if (branch or "").strip() == PRODUCTION_BRANCH else "pr-lane"


def pr_number_from_merge_ref(branch: str) -> int | None:
    """Pure: extract the PR number from a `<N>/merge` run head_branch, else None."""
    match = re.fullmatch(r"(\d+)/merge", (branch or "").strip())
    return int(match.group(1)) if match else None


FEDERATION_REPOS: tuple[str, ...] = (
    "Supremeai-bd/supremeai-open",
    "Supremeai-bd/supremeai-command",
    "Supremeai-bd/supremeai-skills",
    "Supremeai-bd/supremeai-vscode",
    "Supremeai-bd/supremeai-agents",
    "Supremeai-bd/supremeai-browser",
    "Supremeai-bd/supremeai-api",
    "Supremeai-bd/supremeai-studio",
    "Supremeai-bd/supremeai-infrastructure",
    "Supremeai-bd/supremeai-core",
    "Supremeai-bd/supremeai-sdk",
    "Supremeai-bd/supremeai-mcp-control-plane",
)


def repo_short_name(repo: str) -> str:
    """Extract short name from 'Supremeai-bd/supremeai-<name>' or 'Supremeai-bd/supremeai'."""
    name = repo.split("/")[-1].lower()
    if name.startswith("supremeai-"):
        return name[len("supremeai-") :]
    if name == "supremeai":
        return "monorepo"
    return name


def build_mirror_marker(repo: str, run_id: int | str) -> str:
    return f"<!-- MIRROR_RUN: {repo}/actions/runs/{run_id} -->"


def build_issue_body(
    repo: str,
    workflow_name: str,
    run_id: int | str,
    html_url: str,
    branch: str,
    commit_sha: str,
    error_summary: str = "",
) -> str:
    short_commit = str(commit_sha)[:8] if commit_sha else "unknown"
    error_section = ""
    if error_summary.strip():
        error_section = f"\n- **Error Summary:**\n```\n{error_summary.strip()}\n```\n"

    marker = build_mirror_marker(repo, run_id)

    # Lane-honest contract (#1764): the priority tier must describe the lane
    # scope of the failure, not blindly amplify every red run to P0. A PR-lane
    # failure is real signal for its PR's author / rescue lane, but claiming
    # "Production CI failure / blocker" for it misfires the loop's P0 Drainage
    # Invariant and misroutes solvers onto lanes they cannot push to.
    lane = classify_failure_lane(branch)
    if lane == "production":
        priority_line = "P0-critical (Production CI failure / blocker)"
        lane_note = ""
    else:
        priority_line = (
            "P2-medium (PR-lane CI failure — scoped to this PR lane, "
            "not a tracked-branch production blocker)"
        )
        pr_num = pr_number_from_merge_ref(branch)
        lane_subject = f"PR #{pr_num}" if pr_num is not None else f"branch `{branch}`"
        lane_note = (
            f"\n### Lane Classification (PR-lane)\n"
            f"This failure is confined to {lane_subject} (head ref `{branch}`). "
            "Priority reflects lane scope; it makes no claim about `main` status. "
            "The fix belongs to the PR author lane / bridge rescue path — board "
            "agents cannot push to another agent's bridge branch, so triage "
            "(evidence on the failing check) is the actionable work here, not a "
            "main-side fix.\n"
        )

    return f"""### 🤖 SupremeAI Agent Task Contract
This task is mirrored automatically from a federation CI workflow failure. Open to **all autonomous agents** (Local Antigravity, Claude, ChatGPT, Mistral, external contributors).

### Target Repository
{repo}

### Priority Tier
{priority_line}

### Topological Layer
Layer 2 (Tools / Workers / Sidecars)

### Task Group (VALID_GROUPS registry)
agent-orchestration
{lane_note}
### Summary / Problem Statement
Workflow **{workflow_name}** failed on repository `{repo}` (branch `{branch}`).
- **Workflow Run:** [{run_id}]({html_url})
- **Commit:** `{short_commit}`{error_section}
- **Failure Logs / Check Details:** Inspect the check run logs in the linked run.

### Protected-Path Routing Note (#2512)
The bridge lane rejects `.github/` writes (protected paths — workflow files execute with repo secrets, so intake never accepts them from agents). If this failure's root cause lives in `.github/workflows/` (workflow-internal class: sync clobbers, guard removals, action-version breakage — e.g. the #2511 schedule-lane clobber), NO agent patch can land it: the fix is admin-only. Check the board for a triage report before claiming; if none exists, file triage evidence (report-only) instead of burning a claim+TTL on a structurally blocked patch.

### Acceptance Criteria
1. Inspect the failing check logs in Run #{run_id}.
2. Fix root cause in `{repo}`.
3. Submit fix via zero-credential bridge (`bridge_submit_patch`) or fork PR.

### 3-Tier Verification Contract
1. Reflection: `git diff --stat` matches the fixed CI/code files.
2. Smoke: CI checks compile and pass locally.
3. Tests: relevant tests green.

{marker}
"""


def build_issue_title(
    workflow_name: str, repo: str, branch: str, run_id: int | str
) -> str:
    short_repo = repo_short_name(repo)
    return f"fix(ci): [{short_repo}] {workflow_name} failed on {branch} (Run #{run_id})"


def build_issue_labels(repo: str, branch: str = PRODUCTION_BRANCH) -> list[str]:
    short_repo = repo_short_name(repo)
    # Lane-honest priority (#1764): production lane keeps P0-critical; PR-lane
    # failures file as P2-medium so the loop's priority dispatch (P0→P3 tier
    # sort) and its P0 Drainage Invariant stop treating policy rejections on
    # PR merge-refs as production outages. `status:runway` stays on both —
    # ci-fixer triage is still the right role for PR-lane incidents.
    priority_label = (
        "P0-critical"
        if classify_failure_lane(branch) == "production"
        else "P2-medium"
    )
    return [
        "status:unclaimed",
        priority_label,
        # S09 (#489) label-bridge: `status:runway` is LABEL_PRIORITY[0] in
        # scripts/agents/role_trigger_matrix.py, so the continuous loop's
        # deterministic dispatch routes every mirrored CI failure to the
        # ci-fixer role (the old `handoff:coder` label matched no trigger and
        # silently fell through to the coder fallback).
        "status:runway",
        "handoff:coder",
        "area:ci",
        f"repo:{short_repo}",
    ]


def find_mirror_in_items(
    items: list[dict[str, Any]], repo: str, run_id: int | str
) -> int | None:
    """Pure scan: find the OPEN issue carrying this run's mirror marker.

    The /issues list endpoint mixes pull requests into its items; PRs can
    never carry a mirror marker, and with ~700 mixed items per week the old
    fixed 50-item window missed older mirrors (duplicate issues every poll).
    """
    needle = f"{repo}/actions/runs/{run_id}"
    for item in items or []:
        if item.get("pull_request"):
            continue  # PRs share the issue numbering plane; never a mirror
        if needle in (item.get("body") or ""):
            return int(item["number"])
    return None


def find_mirror_by_commit(
    items: list[dict[str, Any]], repo: str, branch: str, commit_sha: str
) -> int | None:
    """Pure scan: find an OPEN mirror issue for the same repo+branch+commit.

    Complements find_mirror_in_items (which keys on run_id). Re-runs of the
    same commit produce different run_ids but the same root cause; this
    prevents duplicate P0/P2 work orders for one incident (#2705).
    """
    if not commit_sha or len(commit_sha) < 8:
        return None
    short = commit_sha[:12]
    for item in items or []:
        if item.get("pull_request"):
            continue
        body = item.get("body") or ""
        if repo not in body:
            continue
        if short not in body:
            continue
        if branch and branch not in ("unknown",) and f"`{branch}`" not in body and branch not in body:
            continue
        return int(item["number"])
    return None


def is_fresh_run(created_at: str, now_utc: datetime, max_age_hours: int) -> bool:
    """Pure: True only if the failed run is younger than max_age_hours.

    `--poll` used to mirror the 3 most recent failed runs regardless of age,
    so a week-old dead run resurfaced as a fresh P0 issue on every tick.
    Fail-closed: missing or malformed timestamps are never 'fresh'.
    """
    if not created_at or max_age_hours < 0:
        return False
    try:
        ts = datetime.strptime(created_at.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return False
    return (now_utc - ts) <= timedelta(hours=max_age_hours)


def get_default_token() -> str:
    for var in ("OPEN_SYNC_PAT", "GH_TOKEN", "GITHUB_TOKEN"):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()
    try:
        res = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def gh_api(
    endpoint: str,
    token: str | None = None,
    method: str = "GET",
    data: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    """Execute authenticated GitHub REST API request."""
    tok = token or get_default_token()
    url = (
        endpoint
        if endpoint.startswith("http")
        else f"https://api.github.com/{endpoint.lstrip('/')}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-Federation-Watchdog/1.0",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    body_bytes = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return resp.status, json.loads(content) if content.strip() else {}
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_content)
        except (json.JSONDecodeError, ValueError):
            parsed = {"raw": err_content}
        return e.code, parsed
    except (
        urllib.error.URLError,
        OSError,
        TimeoutError,
        ConnectionError,
        ValueError,
    ) as e:
        return 0, {"error": str(e)}


CI_FAILURE_ANCHOR = 761


def check_existing_mirror(
    repo: str, run_id: int | str, token: str | None = None
) -> int | None:
    """Check if this run's marker already exists in CI Failure Hub #761 comments."""
    needle = f"{repo}/actions/runs/{run_id}"
    page = 1
    while True:
        code, comments = gh_api(
            f"repos/{OPEN_REPO}/issues/{CI_FAILURE_ANCHOR}/comments?per_page=100&page={page}",
            token=token,
        )
        if code != 200 or not isinstance(comments, list) or not comments:
            break
        for c in comments:
            if needle in (c.get("body") or ""):
                return int(c.get("id", 0))
        if len(comments) < 100:
            break
        page += 1
    return None


def label_pr_lane_failure(
    repo: str,
    pr_num: int,
    run_id: int | str,
    html_url: str,
    token: str | None = None,
) -> bool:
    """In-place update for PR-lane CI failures: label PR and target issue directly without creating a new issue.
    
    Zero-issue-duplication policy: adds 'ci-failed' and 'status:unclaimed' labels to the PR
    and any target issue cited via 'Closes #N' in the PR body.
    """
    tok = token or get_default_token()
    # 1. Label the PR itself
    code, pr_data = gh_api(f"repos/{repo}/pulls/{pr_num}", token=tok)
    if code != 200 or not isinstance(pr_data, dict):
        print(f"[watchdog] Could not fetch PR #{pr_num} on {repo} (HTTP {code}). Falling back.")
        return False
    
    # Add ci-failed and status:unclaimed to the PR
    gh_api(
        f"repos/{repo}/issues/{pr_num}/labels",
        token=tok,
        method="POST",
        data={"labels": ["ci-failed", "status:unclaimed"]},
    )
    print(f"✅ [watchdog] Marked PR #{pr_num} as 'ci-failed' and 'status:unclaimed' in-place.")

    # 2. Check if the PR links to an issue via Closes/Fixes/Resolves #N
    pr_body = pr_data.get("body") or ""
    closes_match = re.search(r"(?:closes|fixes|resolves)\s+#(\d+)", pr_body, re.IGNORECASE)
    if closes_match:
        target_issue_num = int(closes_match.group(1))
        gh_api(
            f"repos/{OPEN_REPO}/issues/{target_issue_num}/labels",
            token=tok,
            method="POST",
            data={"labels": ["ci-failed", "status:unclaimed"]},
        )
        print(
            f"✅ [watchdog] Marked target issue #{target_issue_num} as 'ci-failed' and 'status:unclaimed' in-place."
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
    """Mirror CI failure.
    
    Policy:
      - PR-lane failures (<N>/merge): in-place label update on PR and target issue (no new duplicate issue created).
      - Production branch (main): mirrored as a tracked sub-issue under CI Failure Hub #761.
    """
    lane = classify_failure_lane(branch)
    if lane != "production":
        pr_num = pr_number_from_merge_ref(branch)
        if pr_num is not None:
            labeled = label_pr_lane_failure(repo, pr_num, run_id, html_url, token=token)
            if labeled:
                print(f"[watchdog] PR-lane CI failure on PR #{pr_num} handled in-place (no duplicate issue created).")
                return True

    # Dedup: scan open issues for this run's marker (paginated).
    page = 1
    while True:
        code, items = gh_api(
            f"repos/{OPEN_REPO}/issues?state=open&per_page=100&page={page}",
            token=token,
        )
        if code != 200 or not isinstance(items, list) or not items:
            break
        existing_num = find_mirror_in_items(items, repo, run_id)
        if existing_num is not None:
            print(
                f"[watchdog] Incident already mirrored as issue #{existing_num}. Skipping."
            )
            return True
        # Enhanced dedup (#2705): same repo+branch+commit => same incident,
        # even if the run_id differs (re-runs / different workflow runs on
        # the same commit). Prevents duplicate P0/P2 WOs for one root cause.
        if commit_sha:
            dup_num = find_mirror_by_commit(items, repo, branch, commit_sha)
            if dup_num is not None:
                print(
                    f"[watchdog] Duplicate incident (same commit {commit_sha[:8]}) "
                    f"already mirrored as issue #{dup_num}. Skipping."
                )
                return True
        if len(items) < 100:
            break
        page += 1

    title = build_issue_title(workflow_name, repo, branch, run_id)
    body = f"## 🚨 CI Failure Incident: {title}\n\n" + build_issue_body(
        repo, workflow_name, run_id, html_url, branch, commit_sha, error_summary
    )
    labels = build_issue_labels(repo, branch=branch)

    code, resp = gh_api(
        f"repos/{OPEN_REPO}/issues",
        token=token,
        method="POST",
        data={"title": title, "body": body, "labels": labels},
    )
    if code == 422:
        core_labels = [l for l in labels if not l.startswith("repo:")]
        code, resp = gh_api(
            f"repos/{OPEN_REPO}/issues",
            token=token,
            method="POST",
            data={"title": title, "body": body, "labels": core_labels},
        )
    if code == 201:
        issue_number = resp.get("number")
        issue_url = resp.get("html_url")
        print(
            f"✅ [watchdog] Mirrored CI failure from {repo} as issue #{issue_number}: {issue_url}"
        )
        # Link as sub-issue directly under the repository's Domain Anchor Hub (zero loose root issues).
        target_anchor = get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR
        if issue_number and link_sub_issue is not None:
            try:
                linked = link_sub_issue(
                    parent_issue_number=target_anchor,
                    child_issue_number=int(issue_number),
                    repo=OPEN_REPO,
                    token=token,
                )
                if linked:
                    print(
                        f"   ↳ linked as sub-issue directly under Domain Anchor #{target_anchor}."
                    )
                else:
                    print(
                        f"   ↳ ❌ sub-issue link FAILED for #{issue_number} -> "
                        f"#{target_anchor}; counting mirror as FAILED so the "
                        f"scheduler surfaces it."
                    )
                    return False
            except Exception as exc:
                print(f"   ↳ ❌ sub-issue link error: {exc}")
                return False
        elif issue_number and link_sub_issue is None:
            print(
                "   ↳ ❌ federation_anchors.link_sub_issue unavailable — cannot "
                "guarantee zero loose incidents; counting mirror as FAILED."
            )
            return False
        return True
    else:
        print(
            f"❌ [watchdog] Failed to mirror incident (HTTP {code}): {resp}"
        )
        return False


def poll_federation_failures(
    token: str | None = None,
    limit_per_repo: int = 3,
    max_age_hours: int = 24,
) -> tuple[int, int]:
    """Audit all 12 federation repositories for RECENT failed runs.

    Returns (mirrored_count, failed_mirror_count) so callers can exit
    non-zero when mirroring itself fails (the old poll always returned 0,
    hiding its own breakage from any scheduler).
    """
    mirrored_count = 0
    failed_count = 0
    now_utc = datetime.now(timezone.utc)
    print(
        f"🔍 [watchdog] Auditing {len(FEDERATION_REPOS)} federation repositories for CI failures..."
    )

    for repo in FEDERATION_REPOS:
        code, resp = gh_api(
            f"repos/{repo}/actions/runs?status=failure&per_page={limit_per_repo}",
            token=token,
        )
        if code != 200 or not isinstance(resp, dict):
            if code in (403, 404):
                print(f"  [skip-inaccessible] {repo}: could not fetch runs (HTTP {code})")
            else:
                print(f"  [skip-error] {repo}: could not fetch runs (HTTP {code})")
                failed_count += 1
            continue

        runs = resp.get("workflow_runs", [])
        if not runs:
            continue

        print(f"  [{repo}] Found {len(runs)} failed workflow runs.")
        for r in runs:
            run_id = r.get("id")
            workflow_name = r.get("name", "CI Pipeline")
            html_url = r.get("html_url", "")
            branch = r.get("head_branch", "unknown")
            commit_sha = r.get("head_sha", "")

            if not run_id:
                continue

            if not is_fresh_run(r.get("created_at", ""), now_utc, max_age_hours):
                print(
                    f"  [skip-stale] {repo} run {run_id}: older than {max_age_hours}h - not a current incident"
                )
                continue

            success = mirror_failure(
                repo=repo,
                workflow_name=workflow_name,
                run_id=run_id,
                html_url=html_url,
                branch=branch,
                commit_sha=commit_sha,
                token=token,
            )
            if success:
                mirrored_count += 1
            else:
                failed_count += 1

    # Auto-close already-resolved incidents so the board drains.
    try:
        auto_resolve_fixed_incidents(token=token)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[watchdog] auto-resolve error: {exc}")

    return mirrored_count, failed_count


def parse_mirror_marker(body: str) -> tuple[str, int] | None:
    """Pure: extract (repo, run_id) from an issue body containing MIRROR_RUN marker."""
    match = re.search(
        r"<!-- MIRROR_RUN:\s*([^/\s]+/[^/\s]+)/actions/runs/(\d+)\s*-->", body or ""
    )
    if match:
        return match.group(1), int(match.group(2))
    return None


def is_run_resolved(
    failed_run_id: int, runs: list[dict[str, Any]], branch: str = "main"
) -> dict[str, Any] | None:
    """Pure: True if any completed run on the specified branch succeeded after failed_run_id."""
    for r in runs:
        if r.get("head_branch") != branch:
            continue
        if r.get("status") == "completed" and r.get("conclusion") == "success":
            run_id = r.get("id")
            if isinstance(run_id, int) and run_id > failed_run_id:
                return r
    return None


def auto_resolve_fixed_incidents(token: str | None = None) -> tuple[int, int]:
    """Audit open mirrored CI failure issues and auto-close ones that succeeded on main.

    Returns (resolved_count, error_count).
    """
    resolved_count = 0
    error_count = 0
    print("🔍 [watchdog] Checking open CI failure incidents for auto-resolution...")

    # 1. Fetch all open issues in supremeai-open
    page = 1
    open_mirrors: list[dict[str, Any]] = []
    while True:
        code, items = gh_api(
            f"repos/{OPEN_REPO}/issues?state=open&per_page=100&page={page}",
            token=token,
        )
        if code != 200 or not isinstance(items, list) or not items:
            break
        for item in items:
            if item.get("pull_request"):
                continue
            parsed = parse_mirror_marker(item.get("body") or "")
            if parsed:
                repo, failed_run_id = parsed
                open_mirrors.append(
                    {
                        "issue_number": item["number"],
                        "repo": repo,
                        "failed_run_id": failed_run_id,
                    }
                )
        if len(items) < 100:
            break
        page += 1

    if not open_mirrors:
        print("✅ [watchdog] No open CI failure incidents requiring resolution.")
        return 0, 0

    print(f"📋 [watchdog] Found {len(open_mirrors)} open CI incident(s) to verify.")

    # Cache latest runs per repo to avoid redundant queries
    repo_runs_cache: dict[str, list[dict[str, Any]]] = {}

    for mirror in open_mirrors:
        repo = mirror["repo"]
        failed_run_id = mirror["failed_run_id"]
        issue_number = mirror["issue_number"]

        if repo not in repo_runs_cache:
            code, resp = gh_api(
                f"repos/{repo}/actions/runs?status=completed&per_page=10",
                token=token,
            )
            if code == 200 and isinstance(resp, dict):
                repo_runs_cache[repo] = resp.get("workflow_runs", [])
            else:
                repo_runs_cache[repo] = []

        resolved_run = is_run_resolved(failed_run_id, repo_runs_cache[repo])
        if resolved_run:
            latest_run_id = resolved_run.get("id")
            run_url = resolved_run.get("html_url", "")
            print(
                f"🎉 [watchdog] Incident #{issue_number} on {repo} resolved by run #{latest_run_id}!"
            )

            # Post resolution comment
            comment_body = (
                f"🎉 **Auto-Resolved:** The latest CI pipeline on `{repo}` is now passing on `main` "
                f"in run [#{latest_run_id}]({run_url}).\n"
                f"Auto-closing this incident issue as completed."
            )
            gh_api(
                f"repos/{OPEN_REPO}/issues/{issue_number}/comments",
                token=token,
                method="POST",
                data={"body": comment_body},
            )

            # Close issue as completed
            code, _ = gh_api(
                f"repos/{OPEN_REPO}/issues/{issue_number}",
                token=token,
                method="PATCH",
                data={"state": "closed", "state_reason": "completed"},
            )
            if code == 200:
                print(
                    f"✅ [watchdog] Successfully auto-closed incident issue #{issue_number}."
                )
                resolved_count += 1
            else:
                print(
                    f"❌ [watchdog] Failed to auto-close incident issue #{issue_number} (HTTP {code})."
                )
                error_count += 1

    return resolved_count, error_count


def find_loose_mirrors(
    items: list[dict[str, Any]] | None,
    linked_ids: set[int] | None = None,
) -> list[int]:
    """Pure: open issues carrying a MIRROR_RUN marker that are NOT sub-issues.

    `items` are /issues list entries (PRs excluded — they share the numbering
    plane and can never be mirrors). `linked_ids` are the parent hub's current
    sub-issue DATABASE ids; each list item carries its own `id` field, so
    linkage is compared db-id to db-id (never issue number to db id). An item
    whose id is missing counts as loose — over-counting is safe because
    link_sub_issue is idempotent, under-counting would leave drift.
    """
    loose: list[int] = []
    linked = linked_ids or set()
    for item in items or []:
        if item.get("pull_request"):
            continue
        body = item.get("body") or ""
        if "MIRROR_RUN:" in body and "/actions/runs/" in body:
            number = item.get("number")
            if isinstance(number, int) and item.get("id") not in linked:
                loose.append(number)
    return loose


def relink_loose_mirrors(
    token: str | None = None,
    parent_issue_number: int = CI_FAILURE_ANCHOR,
) -> tuple[int, int]:
    """Backfill: attach every loose mirrored incident under the CI Failure Hub.

    Self-healing board invariant (8-anchor SSOT): after a merge of the relink
    machinery, the next scheduled `--poll` tick repairs the board without any
    manual step. Idempotent end-to-end: already-linked children are skipped
    via list_sub_issue_ids before any POST.

    Returns (relinked_count, failed_count).
    """
    relinked = 0
    failed = 0
    if link_sub_issue is None or list_sub_issue_ids is None:
        print("❌ [relink] federation_anchors helpers unavailable; cannot relink.")
        return 0, 1

    # Snapshot the hub's current sub-issues once (db ids).
    linked_ids = list_sub_issue_ids(
        parent_issue_number, repo=OPEN_REPO, token=token
    )

    # Scan open issues for mirror markers (paginated).
    loose_numbers: list[int] = []
    page = 1
    while True:
        code, items = gh_api(
            f"repos/{OPEN_REPO}/issues?state=open&per_page=100&page={page}",
            token=token,
        )
        if code != 200 or not isinstance(items, list) or not items:
            if code not in (200,):
                print(f"❌ [relink] could not list open issues (HTTP {code}).")
                return relinked, failed + 1
            break
        loose_numbers.extend(find_loose_mirrors(items, linked_ids))
        if len(items) < 100:
            break
        page += 1

    if not loose_numbers:
        print(
            f"✅ [relink] board clean — every mirrored incident already sits "
            f"under Hub #{parent_issue_number} (0 actions)."
        )
        return 0, 0

    print(
        f"🔧 [relink] {len(loose_numbers)} loose mirrored incident(s) found: "
        f"{', '.join('#' + str(n) for n in loose_numbers)}"
    )
    for number in sorted(loose_numbers):
        ok = link_sub_issue(
            parent_issue_number=parent_issue_number,
            child_issue_number=int(number),
            repo=OPEN_REPO,
            token=token,
        )
        if ok:
            relinked += 1
            print(f"   ↳ #{number} linked under CI Hub #{parent_issue_number}.")
        else:
            failed += 1
            print(f"   ↳ ❌ #{number} link failed (see anchors error above).")
    print(
        f"🏁 [relink] done: {relinked} relinked, {failed} failed "
        f"-> root board now shows only anchor hubs."
    )
    return relinked, failed


def self_test() -> int:
    """Hermetic self-test suite (zero network)."""
    print("[self-test] Running Federation CI Watchdog offline contract test...")

    # 1. Repos registry verification
    assert len(FEDERATION_REPOS) == 12, (
        f"Expected 12 federation repos (including open, excluding supremeai + archive), got {len(FEDERATION_REPOS)}"
    )
    assert "Supremeai-bd/supremeai-open" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-command" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-skills" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-studio" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai" not in FEDERATION_REPOS

    # 2. Short name mapping
    assert repo_short_name("Supremeai-bd/supremeai") == "monorepo"
    assert repo_short_name("Supremeai-bd/supremeai-command") == "command"
    assert repo_short_name("Supremeai-bd/supremeai-skills") == "skills"

    # 3. Marker generation
    marker = build_mirror_marker("Supremeai-bd/supremeai-command", 123456)
    assert (
        marker
        == "<!-- MIRROR_RUN: Supremeai-bd/supremeai-command/actions/runs/123456 -->"
    )

    # 4. Issue formatting
    title = build_issue_title(
        "CI Pipeline", "Supremeai-bd/supremeai-command", "main", 123456
    )
    assert title == "fix(ci): [command] CI Pipeline failed on main (Run #123456)"

    body = build_issue_body(
        repo="Supremeai-bd/supremeai-command",
        workflow_name="CI Pipeline",
        run_id=123456,
        html_url="https://github.com/Supremeai-bd/supremeai-command/actions/runs/123456",
        branch="main",
        commit_sha="abcdef123456",
        error_summary="tests/test_command.py: FAILED",
    )
    assert "Supremeai-bd/supremeai-command" in body
    assert "P0-critical" in body
    assert "agent-orchestration" in body
    assert marker in body
    assert "tests/test_command.py: FAILED" in body
    # #2512: the protected-path routing note ships in every incident body —
    # agents must see the admin-only boundary before burning a claim+TTL on
    # a `.github/`-root-caused lane (the #2511 structural-block class).
    assert "Protected-Path Routing Note" in body
    assert "admin-only" in body

    labels = build_issue_labels("Supremeai-bd/supremeai-command")
    assert "status:unclaimed" in labels
    assert "P0-critical" in labels
    assert "status:runway" in labels  # S09 label-bridge -> ci-fixer dispatch
    assert "area:ci" in labels
    assert "repo:command" in labels

    # 5. Dedup scan: PRs are excluded, real mirror issues are found
    fake_items = [
        {
            "number": 700,
            "pull_request": {"url": "x"},
            "body": f"<!-- MIRROR_RUN: Supremeai-bd/supremeai-command/actions/runs/{123456} -->",
        },
        {
            "number": 701,
            "body": f"prefix <!-- MIRROR_RUN: Supremeai-bd/supremeai-command/actions/runs/{123456} --> suffix",
        },
        {"number": 702, "body": "no marker"},
    ]
    assert (
        find_mirror_in_items(fake_items, "Supremeai-bd/supremeai-command", 123456)
        == 701
    )
    assert (
        find_mirror_in_items(fake_items, "Supremeai-bd/supremeai-command", 111111)
        is None
    )

    # 6. Recency gate: fresh/stale/malformed boundaries
    now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
    assert is_fresh_run("2026-10-18T11:00:00Z", now, 24) is True
    assert is_fresh_run("2026-10-16T11:00:00Z", now, 24) is False
    assert is_fresh_run("", now, 24) is False
    assert is_fresh_run("not-a-date", now, 24) is False

    # 7. Anchor Hub resolution contract
    if get_anchor_issue_number is not None:
        for r in FEDERATION_REPOS:
            anc = get_anchor_issue_number(r)
            assert anc is not None and 749 <= anc <= 762, (
                f"Repo {r} must map to a valid anchor hub, got {anc}"
            )

    # 8. Loose-mirror detection (8-anchor SSOT backfill, #910-#918 class)
    mk = build_mirror_marker("Supremeai-bd/supremeai-api", 424242)
    board = [
        {"number": 910, "id": 9001, "body": f"x {mk} y"},  # loose mirror
        {"number": 911, "id": 9002, "body": "no marker issue"},  # not a mirror
        {
            "number": 912,
            "id": 9003,
            "pull_request": {"url": "p"},
            "body": mk,
        },  # PR: never a mirror
        {"number": 913, "id": 9004, "body": None},  # empty body
    ]
    assert find_loose_mirrors(board, set()) == [910]
    assert find_loose_mirrors(board, None) == [910]
    assert find_loose_mirrors([], set()) == []
    assert find_loose_mirrors(None, set()) == []
    # db-id based exclusion: the linked child (id 9001) is not loose; an
    # item without an id always counts loose (idempotent relink makes the
    # over-count safe, the under-count would leave drift).
    assert find_loose_mirrors(board, {9001}) == []

    # 9. Sub-issue endpoint contract pin (snake_case; hyphen 404s live)
    try:
        from scripts.ci.federation_anchors import SUB_ISSUES_PATH as _ssp
    except ImportError:
        try:
            from federation_anchors import SUB_ISSUES_PATH as _ssp
        except ImportError:
            _ssp = None
    if _ssp is not None:
        assert _ssp == "sub_issues", (
            f"sub-issue endpoint must be snake_case 'sub_issues', got {_ssp!r}"
        )

    # 10. Auto-resolution contract
    marker_text = "prefix <!-- MIRROR_RUN: Supremeai-bd/supremeai-api/actions/runs/555123 --> suffix"
    parsed_info = parse_mirror_marker(marker_text)
    assert parsed_info == ("Supremeai-bd/supremeai-api", 555123)
    assert parse_mirror_marker("no marker present") is None

    sample_runs = [
        {"id": 555120, "head_branch": "main", "status": "completed", "conclusion": "success"},
        {"id": 555124, "head_branch": "fix-branch", "status": "completed", "conclusion": "success"},
        {"id": 555125, "head_branch": "main", "status": "completed", "conclusion": "failure"},
        {"id": 555126, "head_branch": "main", "status": "completed", "conclusion": "success", "html_url": "https://github.com/runs/555126"},
    ]
    # Older run (555120 < 555123) doesn't resolve
    # Other branch (fix-branch) doesn't resolve main
    # Failing run doesn't resolve
    # Newer green run on main (555126 > 555123) resolves!
    resolved = is_run_resolved(555123, sample_runs, branch="main")
    assert resolved is not None and resolved["id"] == 555126
    assert is_run_resolved(999999, sample_runs, branch="main") is None

    # 11. Lane-honest classification (#1764): production vs PR-lane
    assert classify_failure_lane("main") == "production"
    assert classify_failure_lane("  main  ") == "production"
    assert classify_failure_lane("1763/merge") == "pr-lane"
    assert classify_failure_lane("feature/some-work") == "pr-lane"
    assert classify_failure_lane("") == "pr-lane"  # fail-safe: never cry wolf
    assert pr_number_from_merge_ref("1763/merge") == 1763
    assert pr_number_from_merge_ref("feature/x") is None
    assert pr_number_from_merge_ref("main") is None

    # Production lane keeps the legacy P0 contract (default branch param).
    prod_labels = build_issue_labels("Supremeai-bd/supremeai-command")
    assert "P0-critical" in prod_labels
    assert "P2-medium" not in prod_labels
    prod_body = build_issue_body(
        repo="Supremeai-bd/supremeai-command",
        workflow_name="CI Pipeline",
        run_id=123456,
        html_url="https://github.com/Supremeai-bd/supremeai-command/actions/runs/123456",
        branch="main",
        commit_sha="abcdef123456",
    )
    assert "P0-critical (Production CI failure / blocker)" in prod_body
    assert "Lane Classification (PR-lane)" not in prod_body

    # PR-lane files honestly: P2-medium, never P0-critical, lane note present.
    pr_labels = build_issue_labels("Supremeai-bd/supremeai-open", branch="1763/merge")
    assert "P2-medium" in pr_labels
    assert "P0-critical" not in pr_labels
    assert "status:runway" in pr_labels  # ci-fixer triage routing unchanged
    assert "repo:open" in pr_labels
    pr_body = build_issue_body(
        repo="Supremeai-bd/supremeai-open",
        workflow_name="CI — Open Unified Pipeline",
        run_id=40595046266,
        html_url="https://github.com/Supremeai-bd/supremeai-open/actions/runs/40595046266",
        branch="1763/merge",
        commit_sha="554e5015734f",
    )
    assert "P2-medium (PR-lane CI failure" in pr_body
    assert "P0-critical" not in pr_body
    assert "PR #1763" in pr_body  # merge-ref resolves to a human-readable lane
    assert "Lane Classification (PR-lane)" in pr_body
    assert "not a tracked-branch production blocker" in pr_body

    print("✅ [self-test] All 11 contract assertion groups passed!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Federation-wide CI Failure Watchdog")
    parser.add_argument(
        "--self-test", action="store_true", help="Run offline contract assertions"
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Poll all 12 federation repositories for recent failures",
    )
    parser.add_argument(
        "--no-relink",
        action="store_true",
        help="Poll mode: skip the automatic loose-mirror relink pass "
        "(default: poll ends with a self-healing relink under the CI Hub)",
    )
    parser.add_argument(
        "--relink",
        action="store_true",
        help="Standalone backfill: scan open mirrored incidents and attach "
        "every loose one as a sub-issue of the CI Failure Hub (idempotent)",
    )
    parser.add_argument(
        "--auto-resolve",
        action="store_true",
        help="Audit open mirrored CI failure incidents and auto-close resolved ones",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=24,
        help="Ignore failed runs older than this many hours (poll mode)",
    )
    parser.add_argument(
        "--payload",
        type=str,
        help="JSON payload string or path to JSON file for event-driven mirror",
    )
    parser.add_argument(
        "--repo", type=str, help="Repository name (e.g. Supremeai-bd/supremeai-command)"
    )
    parser.add_argument(
        "--workflow", type=str, default="CI Workflow", help="Workflow name"
    )
    parser.add_argument("--run-id", type=int, help="Workflow run ID")
    parser.add_argument("--url", type=str, default="", help="Workflow run HTML URL")
    parser.add_argument("--branch", type=str, default="main", help="Branch name")
    parser.add_argument("--commit", type=str, default="", help="Commit SHA")
    parser.add_argument("--error", type=str, default="", help="Error summary")

    args = parser.parse_args()

    if args.self_test:
        return self_test()

    if args.relink:
        relink_token = (
            os.environ.get("OPEN_SYNC_PAT")
            or os.environ.get("GH_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
            or get_default_token()
        )
        _relinked, _failed = relink_loose_mirrors(token=relink_token)
        return 1 if _failed else 0

    if args.auto_resolve:
        resolve_token = (
            os.environ.get("OPEN_SYNC_PAT")
            or os.environ.get("GH_TOKEN")
            or os.environ.get("GITHUB_TOKEN")
            or get_default_token()
        )
        _resolved, _resolve_failed = auto_resolve_fixed_incidents(token=resolve_token)
        return 1 if _resolve_failed else 0

    token = (
        os.environ.get("OPEN_SYNC_PAT")
        or os.environ.get("GH_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
    )

    if args.payload:
        raw = args.payload
        if os.path.exists(raw):
            with open(raw, encoding="utf-8") as _f:
                raw = _f.read()
        data = json.loads(raw)
        client = data.get("client_payload") or data
        success = mirror_failure(
            repo=client.get("repo", client.get("repository", "")),
            workflow_name=client.get(
                "workflow", client.get("workflow_name", "CI Workflow")
            ),
            run_id=client.get("run_id", 0),
            html_url=client.get("run_url", client.get("html_url", "")),
            branch=client.get("branch", client.get("head_branch", "main")),
            commit_sha=client.get("commit", client.get("head_sha", "")),
            error_summary=client.get("error", client.get("error_summary", "")),
            token=token,
        )
        return 0 if success else 1

    if args.repo and args.run_id:
        success = mirror_failure(
            repo=args.repo,
            workflow_name=args.workflow,
            run_id=args.run_id,
            html_url=args.url
            or f"https://github.com/{args.repo}/actions/runs/{args.run_id}",
            branch=args.branch,
            commit_sha=args.commit,
            error_summary=args.error,
            token=token,
        )
        return 0 if success else 1

    if args.poll:
        _mirrored, _failed = poll_federation_failures(
            token=token, max_age_hours=args.max_age_hours
        )
        # Check and auto-resolve any incidents where subsequent runs are green
        _resolved, _resolve_failed = auto_resolve_fixed_incidents(token=token)
        # Self-healing board invariant: every poll tick ends with a relink
        # pass so mirrored incidents can never drift loose on the root board
        # again (the #910-#918 failure mode). Fail the tick if either half
        # fails so the scheduled workflow surfaces breakage loudly.
        _relinked, _relink_failed = (0, 0)
        if not args.no_relink:
            _relinked, _relink_failed = relink_loose_mirrors(token=token)
        return 1 if (_failed or _resolve_failed or _relink_failed) else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
