#!/usr/bin/env python3
"""LESSONS_LEARNED Enforcement Gate — AGENTS.md Hard Rule 1.

বাংলা মন্তব্য: যদি কোনো PR-এ CI fail হয়ে পরে fix করতে হয়েছে (force-push
বা একাধিক commit), তাহলে সেই issue-তে LESSONS_LEARNED entry আছে কিনা
চেক করে। Advisory mode (WARNING, not BLOCK).

Exit codes: 0 = pass, 1 = fail (advisory).
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


def check_pr_force_pushed(pr_number: int) -> bool:
    """Check if PR was force-pushed (indicates CI failure + fix cycle)."""
    try:
        repo = os.environ.get("GH_REPO", "")
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/commits",
             "--jq", "length"],
            capture_output=True, text=True, timeout=30
        )
        # বাংলা মন্তব্য: যদি ৩+ commit থাকে, সম্ভবত fail-then-fix cycle
        commit_count = int(result.stdout.strip()) if result.stdout.strip() else 0
        return commit_count >= 3
    except Exception:
        return False


def check_lessons_entry(pr_number: int) -> bool:
    """Check if LESSONS_LEARNED.md was updated in this PR."""
    try:
        repo = os.environ.get("GH_REPO", "")
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/pulls/{pr_number}/files",
             "--jq", ".[].filename"],
            capture_output=True, text=True, timeout=30
        )
        files = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return any("LESSONS_LEARNED" in f for f in files)
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="LESSONS_LEARNED Enforcement Gate")
    parser.add_argument("--pr", type=int, default=0)
    args = parser.parse_args()

    if not args.pr:
        print("✅ LESSONS_LEARNED Gate: no PR to check")
        return 0

    force_pushed = check_pr_force_pushed(args.pr)
    has_lessons = check_lessons_entry(args.pr)

    if force_pushed and not has_lessons:
        print("::warning::⚠️ PR-এ একাধিক commit (সম্ভবত fail-then-fix) কিন্তু LESSONS_LEARNED.md update নেই। Hard Rule 1 অনুযায়ী ভুল থেকে শিখতে হবে।")
        return 0  # advisory
    elif has_lessons:
        print("✅ LESSONS_LEARNED Gate: LESSONS_LEARNED.md updated in PR ✅")
        return 0
    else:
        print("✅ LESSONS_LEARNED Gate: no force-push detected, no LESSONS_LEARNED needed")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
