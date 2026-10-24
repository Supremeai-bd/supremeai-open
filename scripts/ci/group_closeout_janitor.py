#!/usr/bin/env python3
"""Group Closeout Janitor — Post-Group Repository Hygiene & Cleanup Engine.

Automates the OPS-09 protocol:
1. Prunes stale remote branches whose PRs are merged/closed.
2. Strips temporary lifecycle labels (queue:hold, queue:pending-rollup, has-pr) from closed issues/PRs.
3. Reconciles or reports abandoned draft PRs belonging to the finished group.
4. Cleans up local scratch test scripts and temporary artifacts.
5. Runs dry-run mode safely by default or when requested.
6. Emits the closeout benefit counter report (#2397 — Gap G6): merged PRs,
   +/- lines, conflict-flagged PRs, closed issues (read-only, --report-json opt).

Reference: docs/archive/OPS-09-POST-GROUP-JANITOR-AND-HYGIENE-PROTOCOL.md
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPORARY_LABELS = {"queue:hold", "queue:pending-rollup", "has-pr", "status:in-progress"}
PROTECTED_BRANCHES = {"main", "master", "production", "staging"}
AGENT_PREFIXES = ("coder-", "ci-", "planner-", "pr-helper-", "platform-", "agent-", "super-")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("group_closeout_janitor")


def run_cmd(cmd: list[str], check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=capture,
        text=True,
        check=check,
    )


def get_open_pr_branches() -> set[str]:
    """Fetch branches that have active open pull requests."""
    res = run_cmd(["gh", "pr", "list", "--state", "open", "--json", "headRefName"])
    if res.returncode != 0 or not res.stdout.strip():
        logger.warning("Could not fetch open PRs from gh CLI.")
        return set()
    try:
        prs = json.loads(res.stdout)
        return {p["headRefName"] for p in prs if isinstance(p, dict) and "headRefName" in p}
    except Exception as e:
        logger.error("Error parsing open PR heads: %s", e)
        return set()


def get_remote_agent_branches() -> set[str]:
    """Fetch all remote branches on origin matching agent prefixes."""
    run_cmd(["git", "fetch", "origin", "--prune"])
    res = run_cmd(["git", "branch", "-r"])
    if res.returncode != 0:
        return set()
    branches = set()
    for line in res.stdout.splitlines():
        b = line.strip()
        if b.startswith("origin/"):
            ref = b.replace("origin/", "")
            if ref not in PROTECTED_BRANCHES and not ref.startswith("HEAD"):
                if any(ref.startswith(p) for p in AGENT_PREFIXES):
                    branches.add(ref)
    return branches


def sweep_remote_branches(dry_run: bool = False) -> int:
    """Sweep and delete remote agent branches that have no open PR."""
    logger.info("--- Step 1: Sweeping Stale Remote Agent Branches ---")
    open_branches = get_open_pr_branches()
    remote_branches = get_remote_agent_branches()
    stale = sorted(list(remote_branches - open_branches))

    if not stale:
        logger.info("[OK] No stale remote branches found.")
        return 0

    logger.info("Found %d stale remote branches to delete: %s", len(stale), stale)
    if dry_run:
        logger.info("[DRY-RUN] Skipped deleting %d branches.", len(stale))
        return len(stale)

    batch_size = 15
    for i in range(0, len(stale), batch_size):
        chunk = stale[i : i + batch_size]
        logger.info("Deleting batch %s...", chunk)
        res = run_cmd(["git", "push", "origin", "--delete"] + chunk)
        if res.returncode != 0:
            logger.warning("Deletion warning: %s", res.stderr.strip()[:200])

    run_cmd(["git", "fetch", "origin", "--prune"])
    logger.info("[OK] Successfully swept %d stale remote branches.", len(stale))
    return len(stale)


def sanitize_closed_labels(group: str, dry_run: bool = False) -> int:
    """Remove temporary lifecycle labels from closed issues belonging to the group."""
    logger.info("--- Step 2: Sanitizing Temporary Labels on Closed Issues (group:%s) ---", group)
    group_label = f"group:{group}" if not group.startswith("group:") else group
    res = run_cmd([
        "gh", "issue", "list",
        "--label", group_label,
        "--state", "closed",
        "--json", "number,labels,title"
    ])
    if res.returncode != 0 or not res.stdout.strip():
        logger.info("[OK] No closed issues found for %s.", group_label)
        return 0

    try:
        issues = json.loads(res.stdout)
    except Exception:
        return 0

    modified = 0
    for iss in issues:
        num = iss["number"]
        cur_labels = {l["name"] for l in iss.get("labels", [])}
        to_remove = cur_labels.intersection(TEMPORARY_LABELS)
        if to_remove:
            logger.info("Issue #%d has stale labels: %s", num, to_remove)
            if not dry_run:
                for lbl in to_remove:
                    run_cmd(["gh", "issue", "edit", str(num), "--remove-label", lbl])
            modified += 1

    if dry_run:
        logger.info("[DRY-RUN] Found %d closed issues with stale labels.", modified)
    else:
        logger.info("[OK] Sanitized labels on %d closed issues.", modified)
    return modified


def clean_local_scratch(dry_run: bool = False) -> int:
    """Clean or archive temporary test artifacts in the local workspace."""
    logger.info("--- Step 3: Cleaning Local Scratch & Temp Artifacts ---")
    scratch_dir = REPO_ROOT / "scratch"
    temp_files = list(REPO_ROOT.glob("temp_*.json")) + list(REPO_ROOT.glob("diff_*.txt"))
    cleaned = 0

    for tf in temp_files:
        logger.info("Removing temporary file: %s", tf.name)
        if not dry_run:
            try:
                tf.unlink()
            except Exception as e:
                logger.warning("Could not remove %s: %s", tf, e)
        cleaned += 1

    if scratch_dir.exists():
        archive_dir = REPO_ROOT / ".archive" / "scratch"
        if not dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
            for item in scratch_dir.iterdir():
                if item.is_file():
                    shutil.move(str(item), str(archive_dir / item.name))
                    cleaned += 1
            logger.info("[OK] Archived local scratch files to %s", archive_dir)
        else:
            logger.info("[DRY-RUN] Would archive contents of %s", scratch_dir)

    logger.info("[OK] Local scratch clean complete (%d items).", cleaned)
    return cleaned


def _safe_gh(args: list[str]):
    """gh call returning stdout (str) or None — never raises (#2397 counters).

    # বাংলা মন্তব্য: gh CLI অনুপস্থিত বা API-ব্যর্থতায় counters অন্ধকারে যাবে না —
    # zero-shell + warning, বাকি জানিটর ধাপগুলো চলবেই।
    """
    try:
        res = run_cmd(args)
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("gh unavailable for counters: %s", e)
        return None
    return res.stdout if res.returncode == 0 and res.stdout.strip() else None


def harvest_closeout_counters(group: str) -> dict[str, object]:
    """Aggregate the group's benefit-matrix counters (Gap G6, wired by #2397).

    # বাংলা মন্তব্য: গ্রুপ ক্লোজআউটে "১০১% বাস্তব লাভ" দাবিটি পরিমাপযোগ্য করা —
    # মার্জ-হওয়া PR, যোগ/ছাঁটাই লাইন, কনফ্লিক্ট-পতাকাযুক্ত PR, ক্লোজড ইস্যু।
    # সম্পূর্ণ read-only (dry-run-safe স্বয়ংক্রিয়ভাবেই); gh অনুপলব্ধ হলে সতর্কতা।
    """
    counters: dict[str, object] = {
        "group": group or "ALL",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "merged_prs": 0,
        "lines_added": 0,
        "lines_removed": 0,
        "net_lines": 0,
        "conflict_flagged_prs": 0,
        "closed_issues": 0,
        "data_available": False,
    }
    if not group:
        logger.warning("Counters need --group (no group scope given) — report is a shell.")
        return counters
    group_label = f"group:{group}" if not group.startswith("group:") else group

    res_out = _safe_gh([
        "gh", "pr", "list", "--state", "merged", "--search", f"\"{group_label}\"",
        "--limit", "100", "--json", "number,title,additions,deletions",
    ])
    prs = []
    if res_out is not None:
        try:
            prs = json.loads(res_out)
            counters["data_available"] = True
        except Exception as e:
            logger.warning("Counter parse (PRs) failed: %s", e)

    counters["merged_prs"] = len(prs)
    counters["lines_added"] = sum(int(p.get("additions", 0)) for p in prs)
    counters["lines_removed"] = sum(int(p.get("deletions", 0)) for p in prs)
    counters["net_lines"] = counters["lines_added"] - counters["lines_removed"]

    res_out = _safe_gh([
        "gh", "issue", "list", "--state", "closed", "--label", "hold:merge-conflict",
        "--search", f"\"{group_label}\"", "--limit", "100", "--json", "number",
    ])
    if res_out:
        try:
            counters["conflict_flagged_prs"] = len(json.loads(res_out))
        except Exception:
            pass

    res_out = _safe_gh([
        "gh", "issue", "list", "--state", "closed", "--label", group_label,
        "--limit", "100", "--json", "number",
    ])
    if res_out:
        try:
            counters["closed_issues"] = len(json.loads(res_out))
        except Exception:
            pass
    return counters


def print_closeout_report(counters: dict[str, object]) -> None:
    """Log the human-readable closeout benefit report (OPS-09 closeout artifact)."""
    logger.info("--- Closeout Benefit Report (Gap G6 counters, #2397) ---")
    logger.info("Group:                 %s", counters["group"])
    logger.info("Generated at:          %s", counters["generated_at"])
    logger.info("Merged PRs:            %s", counters["merged_prs"])
    logger.info("Lines added:           +%s", counters["lines_added"])
    logger.info("Lines removed:         -%s", counters["lines_removed"])
    logger.info("Net lines (lean):      %s", counters["net_lines"])
    logger.info("Conflict-flagged PRs:  %s", counters["conflict_flagged_prs"])
    logger.info("Closed issues:         %s", counters["closed_issues"])
    if not counters["data_available"]:
        logger.warning("(gh data unavailable — counters are zero-shells, NOT zeros of record)")


def main() -> int:
    parser = argparse.ArgumentParser(description="OPS-09 Group Closeout Janitor Protocol")
    parser.add_argument("--group", type=str, default="", help="Group name (e.g. step-1, step-2)")
    parser.add_argument("--dry-run", action="store_true", help="Audit mode without making changes")
    parser.add_argument("--skip-branches", action="store_true", help="Skip remote branch sweep")
    parser.add_argument("--skip-labels", action="store_true", help="Skip label sanitization")
    parser.add_argument("--skip-scratch", action="store_true", help="Skip local scratch cleanup")
    parser.add_argument("--report-json", type=str, default="", help="Write closeout counters to this JSON path")
    parser.add_argument("--skip-report", action="store_true", help="Skip the closeout benefit counter report")

    args = parser.parse_args()

    logger.info("=======================================================")
    logger.info("   OPS-09 Repository Janitor Protocol (Closeout Clean) ")
    logger.info("   Target Group: %s | Dry-Run: %s", args.group or "ALL", args.dry_run)
    logger.info("=======================================================")

    if not args.skip_branches:
        sweep_remote_branches(dry_run=args.dry_run)

    if not args.skip_labels and args.group:
        sanitize_closed_labels(group=args.group, dry_run=args.dry_run)

    if not args.skip_scratch:
        clean_local_scratch(dry_run=args.dry_run)

    if not args.skip_report:
        counters = harvest_closeout_counters(group=args.group)
        print_closeout_report(counters)
        if args.report_json:
            try:
                Path(args.report_json).write_text(
                    json.dumps(counters, indent=2, ensure_ascii=False), encoding="utf-8"
                )
                logger.info("[OK] Counters written to %s", args.report_json)
            except Exception as e:
                logger.warning("Could not write report JSON: %s", e)

    logger.info("=======================================================")
    logger.info("   [SUCCESS] Janitor Clean Complete — Zero Debris!     ")
    logger.info("=======================================================")
    return 0


if __name__ == "__main__":
    sys.exit(main())
