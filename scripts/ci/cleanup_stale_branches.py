#!/usr/bin/env python3
"""Prune stale agent and orphan work branches from origin.

Branches created by agents, bridge runners, or completed PRs that have no open PRs
are pruned from origin, ensuring that remote branch existence reflects ONLY active
in-progress work and never clutters the remote repository.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Set

REPO_ROOT = Path(__file__).resolve().parents[2]

# Standard prefixes for transient agent, bridge, and development branches
AGENT_PREFIXES = (
    "bridge/",
    "coder-",
    "ci-",
    "planner-",
    "pr-helper-",
    "platform-",
    "agent-",
    "super-",
    "fix/",
    "feat/",
    "chore/",
    "refactor/",
    "docs/",
    "test/",
    "perf/",
    "revert/",
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("cleanup_stale_branches")


def get_open_pr_head_branches() -> Set[str]:
    try:
        res = subprocess.run(
            ["gh", "pr", "list", "--state", "open", "--limit", "300", "--json", "headRefName"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(res.stdout)
        return {pr["headRefName"] for pr in data if isinstance(pr, dict) and "headRefName" in pr}
    except Exception as e:
        logger.error("Failed to fetch open PR heads: %s", e)
        return set()


def get_remote_branches() -> Set[str]:
    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=str(REPO_ROOT), check=False)
    res = subprocess.run(
        ["git", "branch", "-r"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    branches = set()
    for line in res.stdout.splitlines():
        b = line.strip()
        if b.startswith("origin/"):
            ref = b.replace("origin/", "")
            if ref not in ("HEAD", "main", "master") and not ref.startswith("HEAD ->"):
                branches.add(ref)
    return branches


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune stale remote branches without open PRs.")
    parser.add_argument("--dry-run", action="store_true", help="List stale branches without deleting.")
    args = parser.parse_args()

    open_heads = get_open_pr_head_branches()
    logger.info("Protected open PR branches (%d): %s", len(open_heads), open_heads)

    remote_branches = get_remote_branches()
    to_delete = []

    for branch in sorted(remote_branches):
        # Never touch main, master, or currently open PR branches
        if branch in open_heads or branch in ("main", "master"):
            continue
        if any(branch.startswith(prefix) for prefix in AGENT_PREFIXES):
            to_delete.append(branch)

    logger.info("Found %d stale/orphan branches to delete from origin.", len(to_delete))
    if not to_delete:
        logger.info("No stale branches to clean.")
        return 0

    if args.dry_run:
        logger.info("Dry-run mode: Would delete the following %d branches:", len(to_delete))
        for b in to_delete:
            logger.info("  - %s", b)
        return 0

    batch_size = 20
    for i in range(0, len(to_delete), batch_size):
        chunk = to_delete[i:i + batch_size]
        logger.info("Deleting batch %d-%d of %d...", i + 1, min(i + batch_size, len(to_delete)), len(to_delete))
        cmd = ["git", "push", "origin", "--delete"] + chunk
        res = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if res.returncode != 0:
            logger.warning("Batch deletion warning: %s", res.stderr.strip()[:200])

    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=str(REPO_ROOT), check=False)
    logger.info("Stale branch cleanup complete. Remote tracking branches pruned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
