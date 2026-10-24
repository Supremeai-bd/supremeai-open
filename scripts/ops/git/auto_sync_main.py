#!/usr/bin/env python3
"""SupremeAI Auto-Sync Engine (Branch Drift Prevention).
======================================================
Solves the multi-agent branch-behind / main-ahead drift problem.

When parallel agents or developers merge PRs into `main`, active task branches
fall behind `origin/main`. This tool automatically synchronizes the current branch
with latest `origin/main` cleanly without destructive operations.

Features:
  1. Safe Stash-Sync-Pop: preserves unstaged / uncommitted working files.
  2. Conflict Detection: aborts safely (`git merge --abort`) if conflicts arise,
     leaving zero half-merged mess.
  3. Pre-Push & Hook Integration: can be called by pre-push hooks or CI scripts.

Usage:
  python scripts/git/auto_sync_main.py [--check-only] [--strategy merge|rebase]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass


def run_git(args: List[str], check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in repository root."""
    return subprocess.run(
        ["git"] + args,
        cwd=ROOT_DIR,
        capture_output=capture,
        text=True,
        check=check,
        encoding="utf-8",
        errors="replace",
    )


def get_current_branch() -> str:
    """Get the active git branch name."""
    res = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return res.stdout.strip() if res.returncode == 0 else "main"


def fetch_origin_main() -> bool:
    """Fetch the latest origin/main safely."""
    res = run_git(["fetch", "origin", "main", "--quiet"])
    return res.returncode == 0


def get_drift_status(branch: str = "HEAD", base: str = "origin/main") -> Tuple[int, int]:
    """Return (behind_count, ahead_count) relative to base branch."""
    behind_res = run_git(["rev-list", "--count", f"{branch}..{base}"])
    ahead_res = run_git(["rev-list", "--count", f"{base}..{branch}"])
    
    behind = int(behind_res.stdout.strip() or "0") if behind_res.returncode == 0 else 0
    ahead = int(ahead_res.stdout.strip() or "0") if ahead_res.returncode == 0 else 0
    return behind, ahead


def is_working_tree_dirty() -> bool:
    """Check if the working tree has tracked or untracked changes."""
    res = run_git(["status", "--porcelain"])
    # Ignore LFS pointer smudges for touch icons if benign
    lines = [l for l in res.stdout.splitlines() if not l.endswith("apple-touch-icon.png") and not l.endswith("icon-192.png")]
    return len(lines) > 0


def auto_sync_branch(strategy: str = "merge", verbose: bool = True) -> Tuple[bool, str]:
    """Safely synchronize current branch with origin/main."""
    branch = get_current_branch()
    if branch == "main":
        # On main branch: simply pull fast-forward
        fetch_origin_main()
        behind, _ = get_drift_status("main", "origin/main")
        if behind == 0:
            return True, "Main branch is already up-to-date with origin/main."
        res = run_git(["pull", "--ff-only", "origin", "main"])
        if res.returncode == 0:
            return True, f"Main branch successfully fast-forwarded ({behind} commits)."
        return False, f"Failed to fast-forward main: {res.stderr.strip()}"

    if verbose:
        print(f"🔄 [AUTO-SYNC] Checking drift for branch '{branch}' against origin/main...")

    if not fetch_origin_main():
        return False, "Failed to fetch origin/main from remote."

    behind, ahead = get_drift_status("HEAD", "origin/main")
    if behind == 0:
        msg = f"Branch '{branch}' is up-to-date with origin/main (Ahead: {ahead}, Behind: 0)."
        if verbose:
            print(f"  ✅ {msg}")
        return True, msg

    if verbose:
        print(f"  ⚠️ Branch '{branch}' is behind origin/main by {behind} commit(s) (Ahead: {ahead}).")
        print("  Attempting zero-conflict clean synchronization...")

    stashed = False
    if is_working_tree_dirty():
        if verbose:
            print("  📦 Working tree is dirty. Temporarily stashing uncommitted changes...")
        stash_res = run_git(["stash", "save", "-u", "auto-sync temporary stash"])
        stashed = "Saved working directory" in stash_res.stdout

    sync_success = False
    error_detail = ""

    try:
        if strategy == "merge":
            merge_msg = f"ci(sync): auto-sync '{branch}' with origin/main ({behind} commits behind)"
            merge_res = run_git(["merge", "origin/main", "--no-edit", "-m", merge_msg])
            if merge_res.returncode == 0:
                sync_success = True
            else:
                error_detail = merge_res.stderr.strip() or merge_res.stdout.strip()
                # Conflict occurred, abort cleanly
                run_git(["merge", "--abort"])
        elif strategy == "rebase":
            rebase_res = run_git(["rebase", "origin/main"])
            if rebase_res.returncode == 0:
                sync_success = True
            else:
                error_detail = rebase_res.stderr.strip() or rebase_res.stdout.strip()
                run_git(["rebase", "--abort"])
        else:
            return False, f"Unknown synchronization strategy: {strategy}"
    finally:
        if stashed:
            if verbose:
                print("  📦 Restoring stashed uncommitted changes...")
            run_git(["stash", "pop"])

    if sync_success:
        new_behind, new_ahead = get_drift_status("HEAD", "origin/main")
        msg = (
            f"✅ [AUTO-SYNC] Successfully synced '{branch}' with origin/main!\n"
            f"   Applied {behind} incoming commits. Current status: Ahead: {new_ahead}, Behind: {new_behind}."
        )
        if verbose:
            print(msg)
        return True, msg
    else:
        msg = (
            f"❌ [AUTO-SYNC CONFLICT] Automatic {strategy} failed due to conflicts:\n"
            f"   {error_detail}\n"
            f"👉 Safe abort executed: your working branch remains unchanged.\n"
            f"👉 Please resolve the conflicting files manually with:\n"
            f"   git merge origin/main\n"
        )
        if verbose:
            print(msg, file=sys.stderr)
        return False, msg


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Branch Auto-Sync Engine")
    parser.add_argument("--check-only", action="store_true", help="Only check drift status without modifying git state")
    parser.add_argument("--strategy", choices=["merge", "rebase"], default="merge", help="Sync strategy (default: merge)")
    parser.add_argument("--quiet", action="store_true", help="Suppress output except errors")

    args = parser.parse_args()

    if args.check_only:
        fetch_origin_main()
        branch = get_current_branch()
        behind, ahead = get_drift_status("HEAD", "origin/main")
        print(f"Branch: {branch} | Behind origin/main: {behind} | Ahead of origin/main: {ahead}")
        return 0 if behind == 0 else 1

    success, msg = auto_sync_branch(strategy=args.strategy, verbose=not args.quiet)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
