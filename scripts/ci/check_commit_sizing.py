#!/usr/bin/env python3
"""Commit sizing gate — reviewability guard (issue #475).

বাংলা: এক কমিটে ৯টি মিশনের ১৭ হাজার লাইন (Wave-4 `2a39b5e9`) রিভিউ-অযোগ্য।
এই গেট প্রতি কমিটের changed-line সংখ্যা রিপোর্ট করে:
  * soft limit (default 2000) ছাড়ালে `::warning` (advisory),
  * hard limit (default 10000) ছাড়ালে ব্যর্থ — বাইসেক্ট/রিভিউ রক্ষার হার্ড ক্যাপ।
Repo variables `COMMIT_SIZE_SOFT_LIMIT` / `COMMIT_SIZE_HARD_LIMIT` দিয়ে টিউনযোগ্য।

English: works in CI (reads GITHUB_EVENT_PATH, push events with `commits[]`)
or locally (`--range BASE..HEAD`). Per-commit stats via git diff-tree.
Skips `[skip ci]`-style bot evidence commits? No — they are also subject to
the cap, but they touch only docs/generated (auto-regen) and stay small by
construction; the throttle from issue #474 keeps them rare.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SOFT_DEFAULT = 2000
HARD_DEFAULT = 10000


def _limit(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


def _stat(rev: str) -> tuple[int, int, str]:
    """Return (insertions+deletions, files, short_id+subject) for one commit."""
    numstat = subprocess.run(
        ["git", "show", "--format=%h %s", "--numstat", rev],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=True,
    ).stdout.splitlines()
    subject = numstat[0] if numstat else rev
    added = removed = 0
    files = 0
    for line in numstat[1:]:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        a, r, path = parts
        # Lockfiles (pnpm-lock.yaml, poetry.lock, package-lock.json) are auto-generated
        # dependency graphs. Counting raw lockfile diff lines distorts commit sizing gates.
        if path.endswith(("pnpm-lock.yaml", "poetry.lock", "package-lock.json", "yarn.lock")):
            added += 100
        elif a == "-" and r == "-":  # binary
            added += 100  # binary diff counts as heavy, not line-countable
        else:
            added += int(a or 0)
            removed += int(r or 0)
        files += 1
    return added + removed, files, subject


def main() -> int:
    soft = _limit("COMMIT_SIZE_SOFT_LIMIT", SOFT_DEFAULT)
    hard = _limit("COMMIT_SIZE_HARD_LIMIT", HARD_DEFAULT)

    revs: list[str] = []
    event_path = os.getenv("GITHUB_EVENT_PATH", "")
    if event_path and Path(event_path).exists():
        event = json.loads(Path(event_path).read_text())
        commits = event.get("commits") or []
        if commits:
            revs = [c["id"] for c in commits if not c.get("message", "").startswith("Merge ")]
        elif event.get("head_commit"):
            revs = [event["head_commit"]["id"]]
    elif len(sys.argv) > 1:
        # local mode: --range BASE..HEAD
        rev_range = sys.argv[sys.argv.index("--range") + 1] if "--range" in sys.argv else ""
        revs = subprocess.run(
            ["git", "rev-list", rev_range],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            check=True,
        ).stdout.split()

    if not revs:
        print("OK: no commits to evaluate (skip).")
        return 0

    failures = 0
    warnings = 0
    for rev in revs:
        changed, files, subject = _stat(rev)
        line = f"{subject[:60]} — {changed} changed lines across {files} file(s)"
        if changed > hard:
            failures += 1
            print(f"❌ HARD OVER CAP ({changed} > {hard}): {line}")
            print("   Split the mission into smaller reviewable commits (issue #475).")
        elif changed > soft:
            warnings += 1
            print(f"⚠️ soft cap exceeded ({changed} > {soft}): {line}")

    summary = f"{len(revs)} commit(s) checked: {failures} over hard cap, {warnings} over soft cap (soft={soft}, hard={hard})."
    print(summary)
    if failures:
        print("::error::Commit sizing hard cap exceeded — split the commit (issue #475).")
        return 1
    if warnings:
        print(
            "::warning::Commit sizing soft cap exceeded — prefer one-mission commits (issue #475)."
        )
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
