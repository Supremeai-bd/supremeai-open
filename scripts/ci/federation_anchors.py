#!/usr/bin/env python3
"""scripts/ci/federation_anchors.py — SSOT Registry for Federation Anchor Hubs.

Defines the permanent Anchor Hub parent issues hosted on Supremeai-bd/supremeai-open.
All automated CI failure reports, bridge sync work orders, rejections, and agent tasks
attach strictly as Sub-Issues under their respective repository's Anchor Hub.

Topology Architecture (Golden 6-Domain Architecture):
  - Strictly 6 Active Primary Domain Anchor Hubs (#749 Studio, #750 API, #751 Core, #754 VSCode,
    #756 Browser, #762 Open Embassy).
  - 8 Historical / Consolidated / Infrastructure Hubs:
    * 6 Historical Transit Hubs (#752 Command, #753 Skills, #755 Agents, #757 SDK, #758 Infra, #759 MCP)
      permanently consolidated into API (#750) and VSCode (#754).
    * 2 Operational / Cold Storage Desks (#760 Archive/Bridge, #761 Monorepo/CI Desk) retired
      in favor of in-place failure tracking and direct repository sync.
  - Root board query `gh issue list --search "no:parent is:open"` returns strictly the active domain anchor hubs.
  - All granular tasks are child sub-issues.
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OPEN_REPO = "Supremeai-bd/supremeai-open"

# Canonical 14 Anchor Hub Issue Numbers on Supremeai-bd/supremeai-open
ANCHOR_HUBS: dict[str, int] = {
    # 12 Satellites
    "Supremeai-bd/supremeai-studio": 749,
    "Supremeai-bd/supremeai-api": 750,
    "Supremeai-bd/supremeai-core": 751,
    "Supremeai-bd/supremeai-command": 752,
    "Supremeai-bd/supremeai-skills": 753,
    "Supremeai-bd/supremeai-vscode": 754,
    "Supremeai-bd/supremeai-agents": 755,
    "Supremeai-bd/supremeai-browser": 756,
    "Supremeai-bd/supremeai-sdk": 757,
    "Supremeai-bd/supremeai-infrastructure": 758,
    "Supremeai-bd/supremeai-mcp-control-plane": 759,
    "Supremeai-bd/supremeai-archive": 760,
    # 1 Central Monorepo
    "Supremeai-bd/supremeai": 761,
    # 1 Open Embassy / Task Board SSOT
    "Supremeai-bd/supremeai-open": 762,
}

# Active 6 Primary Domain Anchor Hubs (Core Live Repositories with Active Domain Mirrors)
ACTIVE_ANCHOR_HUBS: dict[str, int] = {
    "Supremeai-bd/supremeai-studio": 749,
    "Supremeai-bd/supremeai-api": 750,
    "Supremeai-bd/supremeai-core": 751,
    "Supremeai-bd/supremeai-vscode": 754,
    "Supremeai-bd/supremeai-browser": 756,
    "Supremeai-bd/supremeai-open": 762,
}

# Consolidated / Retired Anchor Hubs (Merged domains + Retired operational desks)
RETIRED_ANCHOR_HUBS: dict[str, int] = {
    "Supremeai-bd/supremeai-command": 752,
    "Supremeai-bd/supremeai-skills": 753,
    "Supremeai-bd/supremeai-agents": 755,
    "Supremeai-bd/supremeai-sdk": 757,
    "Supremeai-bd/supremeai-infrastructure": 758,
    "Supremeai-bd/supremeai-mcp-control-plane": 759,
    "Supremeai-bd/supremeai-archive": 760,
    "Supremeai-bd/supremeai": 761,
}

# Specialized Hubs
BRIDGE_ORDER_ANCHOR: int = 760  # [Federation Hub] Bridge Transit, Orders & Rejections
CI_FAILURE_ANCHOR: int = 761  # [Federation Hub] CI Pipeline Failures & Incident Desk

# Short aliases for CLI/script convenience
ANCHOR_ALIASES: dict[str, int] = {
    "studio": 749,
    "api": 750,
    "core": 751,
    "command": 752,
    "skills": 753,
    "vscode": 754,
    "agents": 755,
    "browser": 756,
    "sdk": 757,
    "infra": 758,
    "infrastructure": 758,
    "mcp": 759,
    "mcp-control-plane": 759,
    "archive": 760,
    "bridge": 760,
    "monorepo": 761,
    "supremeai": 761,
    "ci": 761,
    "pipeline": 761,
    "open": 762,
    "supremeai-open": 762,
}


def normalize_repo_key(identifier: str) -> str:
    """Normalize full repo path, URL, or short key into canonical lookup key."""
    raw = (identifier or "").strip().rstrip("/")
    if "github.com/" in raw:
        raw = raw.split("github.com/")[-1]
    raw = raw.replace(".git", "")
    parts = raw.split("/")
    repo_name = parts[-1].lower()

    if raw in ANCHOR_HUBS:
        return raw

    # Match against full repo names (case-insensitive)
    for full_repo in ANCHOR_HUBS:
        if full_repo.lower() == raw.lower():
            return full_repo

    # Check aliases
    if repo_name in ANCHOR_ALIASES:
        target_num = ANCHOR_ALIASES[repo_name]
        for full_repo, num in ANCHOR_HUBS.items():
            if num == target_num:
                return full_repo

    # Strip supremeai- prefix if present
    if repo_name.startswith("supremeai-"):
        short = repo_name[len("supremeai-") :]
        if short in ANCHOR_ALIASES:
            target_num = ANCHOR_ALIASES[short]
            for full_repo, num in ANCHOR_HUBS.items():
                if num == target_num:
                    return full_repo

    return raw


def get_anchor_issue_number(identifier: str) -> int | None:
    """Resolve repository identifier or alias to its 14-Anchor Hub issue number."""
    key = normalize_repo_key(identifier)
    if key in ANCHOR_HUBS:
        return ANCHOR_HUBS[key]

    clean = identifier.strip().lower()
    if clean in ANCHOR_ALIASES:
        return ANCHOR_ALIASES[clean]
    if clean.startswith("supremeai-") and clean[len("supremeai-") :] in ANCHOR_ALIASES:
        return ANCHOR_ALIASES[clean[len("supremeai-") :]]

    return None


def get_default_token() -> str:
    for var in ("OPEN_SYNC_PAT", "GH_TOKEN", "GITHUB_TOKEN", "MERGE_PAT"):
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


# GitHub REST sub-issue endpoints use SNAKE_CASE `sub_issues` (verified live:
# GET /repos/{o}/{r}/issues/761/sub_issues -> 200; the hyphenated /sub-issues
# variant returns 404 "Not Found", which silently killed every REST link
# attempt and left mirrored CI incidents floating loose on the board).
SUB_ISSUES_PATH: str = "sub_issues"


def _gh_headers(tok: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "SupremeAI-Federation-Anchors/1.0",
    }


def list_sub_issue_ids(
    parent_issue_number: int,
    repo: str = OPEN_REPO,
    token: str | None = None,
    max_pages: int = 10,
) -> set[int]:
    """Return the database IDs of every current sub-issue under a parent issue.

    Paginated GET /repos/{owner}/{repo}/issues/{parent}/sub_issues.
    Fail-honest: network/API problems return whatever was collected so far
    (possibly empty) after printing the error — callers treat an empty set
    combined with a link failure as 'board state unknown', never as success.
    """
    tok = token or get_default_token()
    ids: set[int] = set()
    if not parent_issue_number:
        return ids
    for page in range(1, max(1, max_pages) + 1):
        url = (
            f"https://api.github.com/repos/{repo}/issues/{parent_issue_number}/"
            f"{SUB_ISSUES_PATH}?per_page=100&page={page}"
        )
        req = urllib.request.Request(url, headers=_gh_headers(tok or ""))
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                items = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            print(f"[anchors] list_sub_issue_ids HTTP {exc.code} for parent #{parent_issue_number}")
            return ids
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            print(f"[anchors] list_sub_issue_ids failed for parent #{parent_issue_number}: {exc}")
            return ids
        if not isinstance(items, list):
            return ids
        for item in items:
            item_id = item.get("id")
            if isinstance(item_id, int):
                ids.add(item_id)
        if len(items) < 100:
            break
    return ids


def link_sub_issue(
    parent_issue_number: int,
    child_issue_number: int,
    repo: str = OPEN_REPO,
    token: str | None = None,
) -> bool:
    """Link an existing issue as a native sub-issue under a parent anchor issue.

    Idempotent: if the child is already linked the call returns True without
    re-posting (makes backfill/relink passes safe to re-run).
    """
    tok = token or get_default_token()

    # 0. Idempotency pre-check: already linked? (GET is cheaper than a
    # duplicate POST and avoids 422 'already a sub-issue' noise.)
    try:
        if child_issue_number in list_sub_issue_ids(
            parent_issue_number, repo=repo, token=tok
        ):
            return True
    except Exception as exc:  # noqa: BLE001 - pre-check must never block linking
        print(f"[anchors] sub-issue pre-check skipped: {exc}")

    # 1. Try gh issue edit --parent
    cmd = [
        "gh",
        "issue",
        "edit",
        str(child_issue_number),
        "--repo",
        repo,
        "--parent",
        str(parent_issue_number),
    ]
    tok = token or get_default_token()
    env = {**os.environ}
    if tok:
        env["GH_TOKEN"] = tok

    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            return True
    except (OSError, subprocess.SubprocessError):
        pass

    # 2. REST fallback: POST /repos/{owner}/{repo}/issues/{parent}/sub_issues
    # (snake_case segment; the hyphenated form 404s — see SUB_ISSUES_PATH).
    if tok:
        try:
            # First fetch child issue database id
            url_child = (
                f"https://api.github.com/repos/{repo}/issues/{child_issue_number}"
            )
            req_c = urllib.request.Request(url_child, headers=_gh_headers(tok))
            with urllib.request.urlopen(req_c, timeout=10) as resp_c:
                c_data = json.loads(resp_c.read().decode("utf-8"))
                child_id = c_data.get("id")

            if child_id:
                url_link = (
                    f"https://api.github.com/repos/{repo}/issues/"
                    f"{parent_issue_number}/{SUB_ISSUES_PATH}"
                )
                data_bytes = json.dumps({"sub_issue_id": child_id}).encode("utf-8")
                req_l = urllib.request.Request(
                    url_link,
                    data=data_bytes,
                    headers=_gh_headers(tok),
                    method="POST",
                )
                with urllib.request.urlopen(req_l, timeout=10) as resp_l:
                    if resp_l.status in (200, 201):
                        return True
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
            except OSError:
                detail = ""
            print(
                f"[anchors] link_sub_issue REST failed: HTTP {exc.code} "
                f"for child #{child_issue_number} -> parent #{parent_issue_number}: {detail}"
            )
            # Self-healing: if parent reached GitHub's 100 sub-issue hard limit, auto-prune closed sub-issues and retry once
            if exc.code == 422 and "Parent cannot have more than 100 sub-issues" in detail:
                print(f"[anchors] Parent #{parent_issue_number} reached 100 sub-issues limit. Auto-pruning closed sub-issues...")
                try:
                    list_url = f"https://api.github.com/repos/{repo}/issues/{parent_issue_number}/sub_issues?per_page=100"
                    r_sub = urllib.request.Request(list_url, headers=_gh_headers(tok))
                    with urllib.request.urlopen(r_sub, timeout=10) as s_resp:
                        sub_items = json.loads(s_resp.read().decode("utf-8"))
                    closed_subs = [i for i in sub_items if i.get("state") == "closed"]
                    pruned = 0
                    for c_sub in closed_subs[:10]:
                        del_url = f"https://api.github.com/repos/{repo}/issues/{parent_issue_number}/sub_issue"
                        d_bytes = json.dumps({"sub_issue_id": c_sub["id"]}).encode("utf-8")
                        del_req = urllib.request.Request(del_url, data=d_bytes, headers=_gh_headers(tok), method="DELETE")
                        try:
                            with urllib.request.urlopen(del_req, timeout=8):
                                pruned += 1
                        except Exception:
                            pass
                    if pruned > 0:
                        print(f"[anchors] Auto-pruned {pruned} closed sub-issues from #{parent_issue_number}. Retrying link...")
                        # Retry link
                        with urllib.request.urlopen(req_l, timeout=10) as retry_resp:
                            if retry_resp.status in (200, 201):
                                return True
                except Exception as prune_err:
                    print(f"[anchors] Auto-prune retry failed: {prune_err}")
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            print(f"[anchors] link_sub_issue REST failed: {exc}")

    return False


def create_sub_issue(
    repo_or_key: str,
    title: str,
    body: str,
    labels: list[str] | None = None,
    open_repo: str = OPEN_REPO,
    token: str | None = None,
) -> tuple[int | None, str]:
    """Create a new issue directly attached as a sub-issue to the target repo's anchor hub.

    Returns (issue_number, issue_url).
    """
    parent_num = get_anchor_issue_number(repo_or_key)
    tok = token or get_default_token()
    env = {**os.environ}
    if tok:
        env["GH_TOKEN"] = tok

    # Build gh issue create command
    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        open_repo,
        "--title",
        title,
        "--body",
        body,
    ]
    if labels:
        for lbl in labels:
            cmd.extend(["--label", lbl])

    # If parent anchor resolved, pass --parent
    if parent_num:
        cmd.extend(["--parent", str(parent_num)])

    try:
        res = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
        out = (res.stdout or "").strip()
        if res.returncode == 0 and out:
            url = out.splitlines()[-1]
            m = re.search(r"/issues/(\d+)", url)
            if m:
                num = int(m.group(1))
                return num, url
    except (OSError, subprocess.SubprocessError):
        pass

    # Fallback: create without --parent, then link via REST
    if parent_num:
        cmd_fallback = [
            "gh",
            "issue",
            "create",
            "--repo",
            open_repo,
            "--title",
            title,
            "--body",
            body,
        ]
        if labels:
            for lbl in labels:
                cmd_fallback.extend(["--label", lbl])
        try:
            res_fb = subprocess.run(
                cmd_fallback, env=env, capture_output=True, text=True, check=False
            )
            out_fb = (res_fb.stdout or "").strip()
            if res_fb.returncode == 0 and out_fb:
                url = out_fb.splitlines()[-1]
                m = re.search(r"/issues/(\d+)", url)
                if m:
                    num = int(m.group(1))
                    link_sub_issue(parent_num, num, repo=open_repo, token=tok)
                    return num, url
        except (OSError, subprocess.SubprocessError):
            pass

    return None, ""


def self_test() -> int:
    """Hermetic contract test verifying the Federation Anchor Hub architecture (zero network)."""
    print("[self-test] Validating Federation Anchor Hub SSOT contract...")

    # 1. Exact count check
    assert len(ANCHOR_HUBS) == 14, (
        f"Must have 14 total historical anchor hubs in lookup, found {len(ANCHOR_HUBS)}"
    )
    assert len(ACTIVE_ANCHOR_HUBS) == 6, (
        f"Must have strictly 6 active domain anchor hubs, found {len(ACTIVE_ANCHOR_HUBS)}"
    )
    assert len(RETIRED_ANCHOR_HUBS) == 8, (
        f"Must have strictly 8 consolidated/retired anchor hubs, found {len(RETIRED_ANCHOR_HUBS)}"
    )

    # 2. Unique issue numbers
    numbers = list(ANCHOR_HUBS.values())
    assert len(set(numbers)) == 14, "Anchor issue numbers must all be distinct"
    assert len(set(ACTIVE_ANCHOR_HUBS.values())) == 6, "Active anchor issue numbers must all be distinct"
    assert len(set(RETIRED_ANCHOR_HUBS.values())) == 8, "Retired anchor issue numbers must all be distinct"

    # 3. Sequential 749-762 range
    expected_range = set(range(749, 763))
    assert set(numbers) == expected_range, (
        f"Anchor numbers must match {expected_range}, got {set(numbers)}"
    )

    # 4. Satellite resolution
    assert get_anchor_issue_number("Supremeai-bd/supremeai-studio") == 749
    assert get_anchor_issue_number("studio") == 749
    assert get_anchor_issue_number("supremeai-studio") == 749
    assert get_anchor_issue_number("api") == 750
    assert get_anchor_issue_number("core") == 751
    assert get_anchor_issue_number("command") == 752
    assert get_anchor_issue_number("skills") == 753
    assert get_anchor_issue_number("vscode") == 754
    assert get_anchor_issue_number("agents") == 755
    assert get_anchor_issue_number("browser") == 756
    assert get_anchor_issue_number("sdk") == 757
    assert get_anchor_issue_number("infra") == 758
    assert get_anchor_issue_number("infrastructure") == 758
    assert get_anchor_issue_number("mcp") == 759
    assert get_anchor_issue_number("archive") == 760
    assert get_anchor_issue_number("monorepo") == 761
    assert get_anchor_issue_number("Supremeai-bd/supremeai") == 761
    assert get_anchor_issue_number("open") == 762
    assert get_anchor_issue_number("Supremeai-bd/supremeai-open") == 762

    # 5. Unknown repo returns None (fail-honest)
    assert get_anchor_issue_number("nonexistent-repo") is None

    # 6. Sub-issue REST endpoint contract: snake_case `sub_issues` only.
    # The hyphenated variant is a live-verified 404; pinning the constant
    # here makes a regression to it fail this self-test immediately.
    assert SUB_ISSUES_PATH == "sub_issues", (
        "GitHub sub-issue endpoints are snake_case /sub_issues; "
        "hyphenated /sub-issues returns 404"
    )
    assert "sub-issues" not in SUB_ISSUES_PATH

    print("✅ [self-test] All 14 Anchor Hub contracts verified successfully!")
    return 0


def verify_live(token: str | None = None) -> int:
    """Verify against live GitHub API that active Anchor Hubs are open and retired anchors are closed."""
    tok = token or get_default_token()
    print(
        "🔍 [verify-live] Verifying active and retired Anchor Hubs on Supremeai-bd/supremeai-open..."
    )
    errors = 0

    print("--- Active 6 Primary Domain Anchor Hubs ---")
    for repo_name, issue_num in sorted(ACTIVE_ANCHOR_HUBS.items(), key=lambda x: x[1]):
        url = f"https://api.github.com/repos/{OPEN_REPO}/issues/{issue_num}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SupremeAI-Federation-Anchors/1.0",
        }
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                state = data.get("state")
                title = data.get("title")
                if state != "open":
                    print(
                        f"❌ Active Anchor #{issue_num} ({repo_name}) is {state}! (Must be OPEN)"
                    )
                    errors += 1
                else:
                    print(f"✅ Active Anchor #{issue_num}: {title} [state: {state}]")
        except Exception as exc:
            print(f"❌ Failed to query Anchor #{issue_num} ({repo_name}): {exc}")
            errors += 1

    print("--- Retired / Consolidated Anchor Hubs ---")
    for repo_name, issue_num in sorted(RETIRED_ANCHOR_HUBS.items(), key=lambda x: x[1]):
        url = f"https://api.github.com/repos/{OPEN_REPO}/issues/{issue_num}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "SupremeAI-Federation-Anchors/1.0",
        }
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                state = data.get("state")
                title = data.get("title")
                if state != "closed":
                    print(
                        f"❌ Retired Anchor #{issue_num} ({repo_name}) is {state}! (Must be CLOSED)"
                    )
                    errors += 1
                else:
                    print(f"✅ Retired Anchor #{issue_num}: {title} [state: {state} (consolidated)]")
        except Exception as exc:
            print(f"❌ Failed to query Anchor #{issue_num} ({repo_name}): {exc}")
            errors += 1

    if errors == 0:
        print("🎉 All Active Anchor Hubs are OPEN and all Retired Hubs are CLOSED as consolidated!")
        return 0
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="14 Anchor Hub SSOT Registry")
    parser.add_argument(
        "--self-test", action="store_true", help="Run offline contract assertions"
    )
    parser.add_argument(
        "--verify-live",
        action="store_true",
        help="Query live board to check all 14 anchors",
    )
    parser.add_argument(
        "--resolve", type=str, help="Resolve repository identifier to anchor number"
    )
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.verify_live:
        return verify_live()
    if args.resolve:
        num = get_anchor_issue_number(args.resolve)
        if num is not None:
            print(f"{args.resolve} -> Anchor #{num}")
            return 0
        print(f"Could not resolve '{args.resolve}' to any Anchor Hub.", file=sys.stderr)
        return 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
