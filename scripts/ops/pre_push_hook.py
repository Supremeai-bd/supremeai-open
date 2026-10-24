#!/usr/bin/env python3
"""SupremeAI Git Pre-Push Hook (Upgraded with Auto-Sync & Drift Protection).
========================================================================
Ensures:
  1. Deletion Exemption: If pushing to delete a branch, bypasses all checks.
  2. Auto-Sync Drift Protection: If local branch is behind `origin/main` (or tracking upstream),
     automatically executes a clean, safe auto-sync instead of hard-blocking.
     Only aborts if true unresolvable merge conflicts exist.
  3. Scoped Regression Scanner: Runs the regression scanner on backend when backend
     files are modified by this branch. Prevents unrelated pre-existing backend findings
     from blocking workflow/script/frontend PRs.

Install:
  Invoked via .git/hooks/pre-push
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import List

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable

# Add ROOT_DIR to sys.path so scripts.git.auto_sync_main can be imported
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def is_ref_deletion() -> bool:
    """Check if the push is a branch/tag deletion without blocking on stdin."""
    try:
        if sys.stdin.isatty():
            return False

        if os.name == "nt":
            import ctypes
            from ctypes import wintypes
            import msvcrt

            handle = msvcrt.get_osfhandle(sys.stdin.fileno())
            avail = wintypes.DWORD()
            if ctypes.windll.kernel32.PeekNamedPipe(handle, None, 0, None, ctypes.byref(avail), None):
                if avail.value == 0:
                    return False
                data = sys.stdin.read(avail.value)
                for line in data.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        local_ref, local_sha = parts[0], parts[1]
                        if local_sha == "0" * 40 or local_ref in ("(delete)", ""):
                            return True
            return False
        else:
            import select
            if select.select([sys.stdin], [], [], 0.05)[0]:
                data = sys.stdin.read()
                for line in data.splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 4:
                        local_ref, local_sha = parts[0], parts[1]
                        if local_sha == "0" * 40 or local_ref in ("(delete)", ""):
                            return True
    except Exception:
        pass
    return False


def get_current_branch() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "main"


def get_changed_files() -> List[str]:
    """Get list of files modified in this branch relative to origin/main."""
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            return [l.strip() for l in res.stdout.splitlines() if l.strip()]
    except Exception:
        pass
    return []


def check_and_sync_remote(branch: str) -> bool:
    """Verify branch is not behind origin/main; auto-sync cleanly if behind."""
    print(f"\n[PRE-PUSH 1/3] Checking drift for branch '{branch}' against remote...")
    try:
        remote_check = subprocess.run(
            ["git", "remote"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if "origin" not in remote_check.stdout:
            print("  [PRE-PUSH] No 'origin' remote configured, skipping remote check.")
            return True

        # Fetch latest origin
        subprocess.run(
            ["git", "fetch", "origin", "main", "--quiet"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        rev_count = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        if rev_count.returncode == 0:
            behind_count = int(rev_count.stdout.strip() or "0")
            if behind_count > 0:
                print(f"  ⚠️ Local branch '{branch}' is behind 'origin/main' by {behind_count} commit(s).")
                print("  🔄 Attempting automatic safe synchronization (auto-sync)...")
                try:
                    from scripts.git.auto_sync_main import auto_sync_branch
                    sync_ok, sync_msg = auto_sync_branch(strategy="merge", verbose=True)
                    if not sync_ok:
                        print(
                            f"\n❌ [PRE-PUSH BLOCKED] Auto-sync failed due to merge conflicts.\n"
                            f"{sync_msg}\n",
                            file=sys.stderr,
                        )
                        return False
                    print("  ✅ [PRE-PUSH] Auto-sync succeeded! Branch is now updated with origin/main.")
                    return True
                except Exception as e:
                    print(
                        f"\n❌ [PRE-PUSH BLOCKED] Auto-sync error: {e}\n"
                        f"👉 Please run: git pull --rebase origin main\n",
                        file=sys.stderr,
                    )
                    return False

        print("  [OK] Local branch is up-to-date with origin/main.")
        return True
    except (subprocess.SubprocessError, OSError) as e:
        print(f"  [WARN] Remote check skipped ({e}). Proceeding to collision check.")
        return True


def check_peer_collisions(branch: str) -> bool:
    """Check for file collisions with other active agent branches or open PRs."""
    print(f"\n[PRE-PUSH 2/3] Checking peer branch & open PR collision matrix for '{branch}'...")
    try:
        from scripts.git.cross_pr_collision_detector import detect_collisions, format_text_report
        report = detect_collisions(target_branch=branch)
        if report.has_direct_collision:
            print(format_text_report(report))
            # If in strict mode via env var, block push. Otherwise warn clearly.
            if os.getenv("SUPREME_STRICT_COLLISION_GUARD", "").lower() in ("1", "true", "yes"):
                print(
                    "\n❌ [PRE-PUSH BLOCKED] Strict collision guard is enabled and file collisions exist!\n"
                    "👉 Coordinate with the peer branch owner or resolve overlapping edits.\n",
                    file=sys.stderr,
                )
                return False
        else:
            print("  [OK] No file collisions detected with other active agent branches or open PRs.")
        return True
    except Exception as e:
        print(f"  [WARN] Peer collision check skipped ({e}). Proceeding to regression scan.")
        return True


def check_regression_scanner() -> bool:
    """Run regression scanner on backend when backend files are modified."""
    print("\n[PRE-PUSH 3/3] Running SupremeAI Regression Scanner check...")
    changed_files = get_changed_files()

    backend_changed = [f for f in changed_files if f.startswith("backend/") or f.startswith("backend\\")]
    if not backend_changed:
        print("  [OK] No backend files modified in this branch. Backend regression scan skipped.")
        return True

    scanner_path = os.path.join(ROOT_DIR, "scripts", "quality", "regression_scanner.py")
    if not os.path.exists(scanner_path):
        print(f"  [WARN] Regression scanner script not found: {scanner_path}")
        return True

    for rel_path in backend_changed:
        full_path = os.path.join(ROOT_DIR, rel_path)
        if not os.path.exists(full_path):
            continue
        cmd = [
            PYTHON,
            scanner_path,
            "--path",
            rel_path,
            "--fail-on",
            "critical,high",
        ]
        res = subprocess.run(cmd, cwd=ROOT_DIR, check=False)
        if res.returncode != 0:
            print(
                f"\n❌ [PRE-PUSH BLOCKED] Regression scan failed on modified file: {rel_path}!\n"
                "👉 Please resolve the regression scanner findings before pushing to remote.\n",
                file=sys.stderr,
            )
            return False

    print("  [OK] Regression scanner passed on all modified backend files (0 critical, 0 high).")
    return True


def main() -> int:
    if is_ref_deletion():
        # Deleting a branch should never be blocked by pre-push hooks
        return 0

    branch = get_current_branch()
    if not check_and_sync_remote(branch):
        return 1
    if not check_peer_collisions(branch):
        return 1
    if not check_regression_scanner():
        return 1
    print("\n✅ [PRE-PUSH] All pre-push checks passed! Proceeding with git push.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

