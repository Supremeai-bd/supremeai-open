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
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OPEN_REPO = "Supremeai-bd/supremeai-open"

FEDERATION_REPOS: tuple[str, ...] = (
    "Supremeai-bd/supremeai",
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

    return f"""### 🤖 SupremeAI Agent Task Contract
This task is mirrored automatically from a federation CI workflow failure. Open to **all autonomous agents** (Local Antigravity, Claude, ChatGPT, Mistral, external contributors).

### Target Repository
{repo}

### Priority Tier
P0-critical (Production CI failure / blocker)

### Topological Layer
Layer 2 (Tools / Workers / Sidecars)

### Task Group (VALID_GROUPS registry)
agent-orchestration

### Summary / Problem Statement
Workflow **{workflow_name}** failed on repository `{repo}` (branch `{branch}`).
- **Workflow Run:** [{run_id}]({html_url})
- **Commit:** `{short_commit}`{error_section}
- **Failure Logs / Check Details:** Inspect the check run logs in the linked run.

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


def build_issue_labels(repo: str) -> list[str]:
    short_repo = repo_short_name(repo)
    return [
        "status:unclaimed",
        "P0-critical",
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
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
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
    except (urllib.error.URLError, OSError, TimeoutError, ConnectionError, ValueError) as e:
        return 0, {"error": str(e)}


def check_existing_mirror(
    repo: str, run_id: int | str, token: str | None = None
) -> int | None:
    """Check if an OPEN issue on supremeai-open already carries this run's marker.

    Paginates up to 3 pages of 100 OPEN items (PRs excluded inside
    find_mirror_in_items). A CLOSED mirror means the failure was fixed - a
    re-listed failed run after that is a genuinely new event and SHOULD get
    a new issue, so only the open plane participates in deduplication.
    """
    for page in (1, 2, 3):
        code, res = gh_api(
            f"repos/{OPEN_REPO}/issues?state=open&per_page=100&page={page}",
            token=token,
        )
        if code != 200 or not isinstance(res, list):
            return None
        found = find_mirror_in_items(res, repo, run_id)
        if found is not None:
            return found
        if len(res) < 100:
            break
    return None


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
    """Create a mirrored issue on supremeai-open if not already existing."""
    existing = check_existing_mirror(repo, run_id, token=token)
    if existing:
        print(f"[watchdog] Mirror already exists on {OPEN_REPO}#{existing}. Skipping.")
        return True

    title = build_issue_title(workflow_name, repo, branch, run_id)
    body = build_issue_body(
        repo, workflow_name, run_id, html_url, branch, commit_sha, error_summary
    )
    labels = build_issue_labels(repo)

    data = {
        "title": title,
        "body": body,
        "labels": labels,
    }

    code, resp = gh_api(
        f"repos/{OPEN_REPO}/issues", token=token, method="POST", data=data
    )
    if code == 201:
        issue_num = resp.get("number")
        issue_url = resp.get("html_url")
        print(
            f"✅ [watchdog] Mirrored CI failure from {repo} to {OPEN_REPO}#{issue_num}: {issue_url}"
        )
        return True
    else:
        print(
            f"❌ [watchdog] Failed to create mirror issue on {OPEN_REPO} (HTTP {code}): {resp}"
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
            print(f"  [skip] {repo}: could not fetch runs (HTTP {code})")
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

    return mirrored_count, failed_count


def self_test() -> int:
    """Hermetic self-test suite (zero network)."""
    print("[self-test] Running Federation CI Watchdog offline contract test...")

    # 1. Repos registry verification
    assert len(FEDERATION_REPOS) == 12, (
        f"Expected 12 federation repos, got {len(FEDERATION_REPOS)}"
    )
    assert "Supremeai-bd/supremeai" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-command" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-skills" in FEDERATION_REPOS
    assert "Supremeai-bd/supremeai-studio" in FEDERATION_REPOS

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

    print("✅ [self-test] All 6 contract assertion groups passed!")
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
        return 1 if _failed else 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
