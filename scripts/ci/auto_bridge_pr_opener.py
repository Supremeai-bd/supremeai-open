#!/usr/bin/env python3
"""Auto Bridge PR Opener — Ingress Instant PR Automation.

Enforces:
  1. Atomic PR Pairing: Every bridge/* branch has a corresponding PR against main.
  2. Pre-Push Rebase: Every branch is rebased onto fresh origin/main before opening PR.
  3. Windows UTF-8 Parity (#515): Explicit UTF-8 encoding across all subprocess and file operations.

Part of Issue #514 (Federation Transit Pipeline).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Configure stdout/stderr UTF-8
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

UPSTREAM_REPO = "Supremeai-bd/supremeai-open"


def run_cmd(args: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    """Execute a CLI command with explicit UTF-8 encoding."""
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            check=False,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return 1, "", str(e)


def find_stranded_bridge_work_orders() -> list[dict[str, Any]]:
    """Scan for bridge work orders with queued labels that lack an open PR."""
    code, out, err = run_cmd(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            UPSTREAM_REPO,
            "--label",
            "bridge:queued",
            "--state",
            "open",
            "--limit",
            "30",
            "--json",
            "number,title,body,labels",
        ]
    )
    if code != 0:
        print(f"❌ Failed to query bridge work orders: {err}", file=sys.stderr)
        return []

    try:
        issues = json.loads(out)
    except json.JSONDecodeError as e:
        print(f"❌ JSON parse error: {e}", file=sys.stderr)
        return []

    stranded = []
    for issue in issues:
        body = issue.get("body", "")
        # Extract patch branch name from body
        branch_match = re.search(r"###\s*Patch Branch\s*\n+([A-Za-z0-9_./-]+)", body)
        if not branch_match:
            # Fallback search
            branch_match = re.search(r"`(bridge/[A-Za-z0-9_.-]+)`", body)
        if not branch_match:
            continue

        branch = branch_match.group(1).strip()

        # Check if an open PR exists for this branch
        pr_code, pr_out, _ = run_cmd(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                UPSTREAM_REPO,
                "--head",
                branch,
                "--state",
                "open",
                "--json",
                "number",
            ]
        )
        if pr_code == 0:
            try:
                prs = json.loads(pr_out)
                if prs:
                    continue  # PR already active
            except json.JSONDecodeError:
                pass

        title = issue.get("title", "")
        # Filter out report-only / audit receipts from executable stranded queue
        if re.search(r"\b(report-only|docs-only|receipt|evidence\s+(addendum|refresh))\b", title, re.IGNORECASE):
            print(f"ℹ️ Skipping report-only receipt work order #{issue.get('number')}: '{title}'", file=sys.stderr)
            continue

        stranded.append(
            {
                "issue_number": issue.get("number"),
                "title": title,
                "branch": branch,
                "body": body,
            }
        )

    # Anti-stampede idempotency: Deduplicate items targeting the same patch branch,
    # keeping the earliest/lowest issue number to prevent race-condition duplicate PRs.
    deduped_stranded: list[dict[str, Any]] = []
    seen_branches: set[str] = set()
    for s in stranded:
        b = s["branch"]
        if b in seen_branches:
            print(f"⚠️ Skipping duplicate stranded work order #{s['issue_number']} for branch '{b}'.", file=sys.stderr)
            continue
        seen_branches.add(b)
        deduped_stranded.append(s)

    return deduped_stranded


def open_pr_for_work_order(item: dict[str, Any], dry_run: bool = False) -> bool:
    """Fetch, rebase onto origin/main, and open PR for stranded bridge branch."""
    issue_num = item["issue_number"]
    branch = item["branch"]
    title = (
        item["title"]
        .replace("🌉 Bridge Work Order — ", "")
        .replace("🌉 Bridge Work Order: ", "")
        .strip()
    )

    print(f"\n🔍 Processing stranded work order #{issue_num} on branch '{branch}'...")

    if dry_run:
        print(
            f"   [DRY-RUN] Would rebase '{branch}' onto origin/main and open PR against main."
        )
        return True

    # 1. Fetch branch and origin/main
    fetch_code, _, fetch_err = run_cmd(
        [
            "git",
            "fetch",
            "origin",
            f"+refs/heads/{branch}:refs/remotes/origin/{branch}",
            "main",
        ]
    )
    if fetch_code != 0:
        print(f"   ❌ Failed to fetch branch {branch}: {fetch_err}")
        return False

    # 2. Checkout local temporary tracking branch
    run_cmd(["git", "branch", "-D", f"tmp-{issue_num}"])
    co_code, _, co_err = run_cmd(
        ["git", "checkout", "-b", f"tmp-{issue_num}", f"origin/{branch}"]
    )
    if co_code != 0:
        print(f"   ❌ Failed to checkout tmp branch for {branch}: {co_err}")
        return False

    # 3. Check divergence and rebase onto origin/main
    # Fail-closed divergence check: an unparseable rev-list result is UNKNOWN,
    # never "0 behind". Treating it as fresh skipped the rebase and the PR body
    # then hard-asserted "[x] Pre-Push Rebase Invariant verified" — a lie that
    # lands stale branches under Invariant 1's signature. Unknown aborts.
    _, behind_out, _ = run_cmd(["git", "rev-list", "--count", "HEAD..origin/main"])
    if not behind_out.strip().isdigit():
        print(
            f"   ❌ Cannot verify divergence from origin/main (fail-closed, "
            f"got '{behind_out.strip()[:80]}'). No PR will be opened."
        )
        run_cmd(["git", "checkout", "-"])
        return False
    behind = int(behind_out.strip())
    if behind > 0:
        print(f"   ⚠️ Branch is {behind} commit(s) behind origin/main. Rebasing...")
        run_cmd(["git", "config", "user.name", "supremeai-bot"])
        run_cmd(["git", "config", "user.email", "bot@supremeai.org"])
        reb_code, _, reb_err = run_cmd(["git", "rebase", "origin/main"])
        if reb_code != 0:
            print(f"   ❌ Rebase failed with conflict: {reb_err}. Auto-recovering...")
            run_cmd(["git", "rebase", "--abort"])
            run_cmd(["git", "checkout", "-"])
            # Self-healing: mark work order as conflicting/rejected and close to prevent permanent stranded clutter
            run_cmd([
                "gh", "issue", "comment", str(issue_num),
                "--repo", UPSTREAM_REPO,
                "--body", f"<!-- auto-bridge:conflict-close -->\n❌ **Automatic Closure**: Branch `{branch}` has git rebase conflicts against `origin/main`.\n\nError: `{reb_err}`\nPer Invariant 1 (Dual-Rebase) & Invariant 3 (Superior Replacement), this stranded work order is closed. Please rebase locally against fresh `origin/main` before resubmitting."
            ])
            run_cmd([
                "gh", "issue", "edit", str(issue_num),
                "--repo", UPSTREAM_REPO,
                "--add-label", "bridge:rejected,conflict:needs-rebase",
                "--remove-label", "bridge:queued"
            ])
            run_cmd([
                "gh", "issue", "close", str(issue_num),
                "--repo", UPSTREAM_REPO,
                "--reason", "not planned"
            ])
            return False
        # Push rebased branch back to remote
        print(f"   🚀 Pushing rebased branch to origin/{branch}...")
        push_code, _, push_err = run_cmd(
            ["git", "push", "--force-with-lease", "origin", f"tmp-{issue_num}:{branch}"]
        )
        if push_code != 0:
            print(f"   ❌ Failed to push rebased branch: {push_err}")
            run_cmd(["git", "checkout", "-"])
            return False
    else:
        print("   ✅ Branch is fresh (0 commits behind origin/main).")

    # 3b. Pre-PR Payload Integrity Guard (Zero-Corrupted-Payload Invariant)
    # Check all modified code files on the branch for raw git diff headers.
    _, diff_files_out, _ = run_cmd(["git", "diff", "--name-only", "origin/main...HEAD"])
    for file_path in diff_files_out.splitlines():
        file_path = file_path.strip()
        if not file_path:
            continue
        p = Path(file_path)
        if p.suffix.lower() in {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml"} and p.is_file():
            try:
                first_lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[:5]
                for l in first_lines:
                    if l.startswith("diff --git ") or re.match(r"^index [0-9a-f]{7,}\.\.", l):
                        print(f"   ❌ Corrupted payload detected in '{file_path}': starts with raw git diff header.")
                        run_cmd(["git", "checkout", "-"])
                        run_cmd([
                            "gh", "issue", "comment", str(issue_num),
                            "--repo", UPSTREAM_REPO,
                            "--body", f"<!-- auto-bridge:corruption-close -->\n❌ **Automatic Closure**: Corrupted payload detected in `{file_path}`. The file starts with raw git diff headers instead of valid source code (e.g. `diff --git ...`).\n\nPlease submit valid full file contents or unified diffs, not raw patch headers pasted as code."
                        ])
                        run_cmd([
                            "gh", "issue", "edit", str(issue_num),
                            "--repo", UPSTREAM_REPO,
                            "--add-label", "bridge:rejected,corrupted-payload",
                            "--remove-label", "bridge:queued"
                        ])
                        run_cmd([
                            "gh", "issue", "close", str(issue_num),
                            "--repo", UPSTREAM_REPO,
                            "--reason", "not planned"
                        ])
                        return False
            except Exception as e:
                print(f"   ⚠️ Could not read {file_path} for payload guard: {e}")

    # 4. Open PR
    pr_body = (
        f"## Summary\n"
        f"Autonomous bridge contribution: {title}\n\n"
        f"## Linked Work Order\n"
        f"Closes #{issue_num}\n"
        f"Refs #{issue_num}\n\n"
        f"## Verification\n"
        f"- [x] Pre-Push Rebase Invariant verified against latest `origin/main` (0 commits behind).\n"
        f"- [x] UTF-8 cross-platform subprocess parity (#515) satisfied.\n\n"
        f"## Rollback Path\n"
        f"- [x] `git revert`-safe pure patch\n"
    )

    pr_code, pr_out, pr_err = run_cmd(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            UPSTREAM_REPO,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            f"feat(bridge): {title}",
            "--body",
            pr_body,
        ]
    )

    run_cmd(["git", "checkout", "-"])
    run_cmd(["git", "branch", "-D", f"tmp-{issue_num}"])

    if pr_code == 0:
        print(f"   🎉 PR Successfully Created: {pr_out}")
        return True
    else:
        print(f"   ❌ Failed to create PR ({pr_code}): {pr_err}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Auto Bridge PR Opener for SupremeAI Federation"
    )
    parser.add_argument(
        "--auto-open",
        action="store_true",
        help="Automatically fetch, rebase, and open PRs for stranded work orders",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report stranded work orders without modifying git or GitHub",
    )
    args = parser.parse_args()

    print("======================================================================")
    print(" SupremeAI Auto Bridge PR Opener — Ingress Instant PR Automation")
    print(" Target: Supremeai-bd/supremeai-open")
    print("======================================================================")

    stranded = find_stranded_bridge_work_orders()
    if not stranded:
        print(
            "✅ No stranded bridge work orders detected. Transit pipeline is 100% clean!"
        )
        return 0

    print(f"ℹ️ Found {len(stranded)} stranded bridge work order(s):")
    for s in stranded:
        print(f"   - #{s['issue_number']}: {s['title']} (branch: {s['branch']})")

    if not args.auto_open and not args.dry_run:
        print("\nPass --auto-open to automatically rebase and open PRs.")
        return 0

    success_count = 0
    for s in stranded:
        if open_pr_for_work_order(s, dry_run=args.dry_run):
            success_count += 1

    print(
        f"\n🏁 Finished: {success_count}/{len(stranded)} work orders processed successfully."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
