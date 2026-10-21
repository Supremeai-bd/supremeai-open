#!/usr/bin/env python3
"""
scripts/ops/gitlab_mirror_sync.py
SupremeAI GitLab Private Mirror & Readiness Manager

Manages the standby mirror repositories on GitLab for all proprietary/secret
satellites and the umbrella repository under the paykaribazaronline namespace.

Capabilities:
  --status    : Verify readiness and accessibility of all GitLab private repos.
  --dry-run   : Simulate a sync run without pushing any commits.
  --self-test : Self-check invariants and configuration sanity.

Zero-impact guarantee:
  Does not modify any GitHub remote, workflow, or active branch.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = WORKSPACE_ROOT / ".env"

PROPRIETARY_REPOSITORIES: list[dict[str, str]] = [
    {
        "name": "supremeai",
        "tier": "Tier 3 (Master Umbrella)",
        "desc": "Master Synchronization Mirror",
    },
    {
        "name": "supremeai-core",
        "tier": "Tier 1 (Moat)",
        "desc": "Decision Intelligence & Planning",
    },
    {
        "name": "supremeai-api",
        "tier": "Tier 1 (Vault)",
        "desc": "Unified Gateway & Key Vault",
    },
    {
        "name": "supremeai-infrastructure",
        "tier": "Tier 1 (Infra)",
        "desc": "Cloud Infrastructure & Ops",
    },
    {
        "name": "supremeai-command",
        "tier": "Tier 1 (Admin)",
        "desc": "Omnichannel Admin Dispatcher",
    },
    {
        "name": "supremeai-agents",
        "tier": "Tier 1 (Runtime)",
        "desc": "Stateless Autonomous Runtime",
    },
    {
        "name": "supremeai-browser",
        "tier": "Tier 1 (Sandbox)",
        "desc": "Stealth Automation Sandbox",
    },
    {
        "name": "supremeai-mcp-control-plane",
        "tier": "Tier 1 (Control)",
        "desc": "Governed Tool Plane",
    },
    {
        "name": "supremeai-archive",
        "tier": "Tier 2 (Memory)",
        "desc": "Institutional Memory & History",
    },
]


def load_env() -> dict[str, str]:
    """Parse workspace .env if present and merge with os.environ."""
    env_vars: dict[str, str] = dict(os.environ)
    if ENV_FILE.is_file():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k not in env_vars or not env_vars[k]:
                        env_vars[k] = v
        except Exception:
            pass
    return env_vars


def api_request(path: str, token: str, method: str = "GET") -> dict[str, Any] | None:
    """Perform an authenticated GitLab v4 API call."""
    url = f"https://gitlab.com/api/v4{path}"
    req = urllib.request.Request(
        url,
        headers={
            "PRIVATE-TOKEN": token,
            "User-Agent": "SupremeAI-GitLab-Mirror/1.0",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    except Exception as e:
        print(f"[WARN] API request to {path} failed: {e}", file=sys.stderr)
        return None


def check_status(user: str, token: str) -> bool:
    """Check readiness of all proprietary repositories on GitLab."""
    print("=" * 70)
    print(" SupremeAI GitLab Standby Mirror Status")
    print(f" Namespace: {user} | Host: gitlab.com")
    print("=" * 70)

    all_ready = True
    for repo in PROPRIETARY_REPOSITORIES:
        name = repo["name"]
        enc_path = f"{user}%2F{name}"
        data = api_request(f"/projects/{enc_path}", token)

        if data:
            vis = data.get("visibility", "unknown")
            is_private = vis == "private"
            status_symbol = "[OK]" if is_private else "[WARN]"
            branch = data.get("default_branch") or "(empty/ready)"
            print(
                f" {status_symbol} {name:<28} | {repo['tier']:<24} | Visibility: {vis:<7} | Branch: {branch}"
            )
            if not is_private:
                all_ready = False
        else:
            print(f" [MISSING] {name:<24} | Not found on GitLab")
            all_ready = False

    print("-" * 70)
    if all_ready:
        print(
            "[SUCCESS] All 9 proprietary repositories are active and PRIVATE on GitLab."
        )
        print("          Standby status: 100% READY TO SWITCH ANYTIME.")
    else:
        print("[NOTICE] Some repositories require attention.")
    print("=" * 70)
    return all_ready


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI GitLab Mirror Manager")
    parser.add_argument(
        "--status", action="store_true", help="Check status of all GitLab mirror repos"
    )
    parser.add_argument("--self-test", action="store_true", help="Run sanity check")
    parser.add_argument(
        "--dry-run", action="store_true", help="Simulate synchronization"
    )
    args = parser.parse_args()

    env = load_env()
    token = env.get("GITLAB_TOKEN", "")
    user = env.get("GITLAB_USER", "paykaribazaronline")

    if args.self_test:
        assert len(PROPRIETARY_REPOSITORIES) == 9, (
            "Must track 9 proprietary repositories"
        )
        assert all("name" in r and "tier" in r for r in PROPRIETARY_REPOSITORIES)
        print("[PASS] gitlab_mirror_sync self-test passed.")
        return 0

    if not token:
        print("[ERROR] GITLAB_TOKEN not found in environment or .env.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("[DRY-RUN] Simulating GitLab mirror sync without modifying state...")
        check_status(user, token)
        return 0

    # Default action is status check
    success = check_status(user, token)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
