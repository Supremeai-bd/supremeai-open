#!/usr/bin/env python3
"""Auto-Bridge PR Opener — Zero-Admin Autonomous PR Submission (#155).

Purpose:
  External autonomous agents (Z.ai, Claude, ChatGPT, community contributors)
  submitting work via Bridge Lane (AGENTS.md §8) push patch branches (bridge/<task-id>)
  and file Bridge Work Order issues with label 'bridge:queued'.

  Without this opener, a human admin would have to manually open the Pull Request
  from the bridge branch to main — which violates the Zero-Admin Doctrine
  (admin manual effort budget <= 0.01%).

  This script automatically scans open Bridge Work Orders ('bridge:queued'),
  checks if their patch branch exists on remote, verifies whether an open PR
  already exists, and autonomously creates the Pull Request so CI and
  Merge Gate (landing.yml) can evaluate and auto-merge the patch.

Usage:
  python scripts/ci/auto_bridge_pr_opener.py              # Dry-run audit mode
  python scripts/ci/auto_bridge_pr_opener.py --auto-open  # Autonomous PR creation
  python scripts/ci/auto_bridge_pr_opener.py --self-test   # Run unit tests
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

UPSTREAM_REPO = "Supremeai-bd/supremeai-open"


def extract_patch_branch(body: str) -> str | None:
    """Extract patch branch from Bridge Work Order body."""
    # Look for ### Patch Branch section or explicit bridge/ pattern
    lines = body.splitlines()
    for idx, line in enumerate(lines):
        if "Patch Branch" in line:
            # Check following lines for bridge/ branch name
            for next_line in lines[idx + 1:idx + 5]:
                match = re.search(r"bridge/[a-zA-Z0-9._-]+", next_line)
                if match:
                    return match.group(0).strip("`*()[]:,")
    # Fallback: scan whole body
    match = re.search(r"\bbridge/[a-zA-Z0-9._-]+\b", body)
    if match:
        return match.group(0).strip("`*()[]:,")
    return None


def extract_task_issue_reference(title: str, body: str) -> str | None:
    """Extract referenced task issue (#N) from title or body."""
    match = re.search(r"\(#(\d+)\)", title)
    if match:
        return f"#{match.group(1)}"
    match = re.search(r"#(\d+)", title)
    if match:
        return f"#{match.group(1)}"
    match = re.search(r"issue\s+#?(\d+)", body, re.IGNORECASE)
    if match:
        return f"#{match.group(1)}"
    return None


# --- Knowledge Sharing / Claim Gate support (#392) ----------------------------
# AGENTS.md §2/§5 mandate Reflection Evidence on every contribution; #392's
# knowledge-sharing-guard enforces it on PR bodies. The opener therefore builds
# the section from the work order's own content — why = the WO's Summary (what
# + why) section, alternatives_rejected = an explicit alternatives_rejected
# entry when the WO carries one, else an honest pointer to the agent's
# decision ledger (never fabricated rationale).

def extract_summary_section(body: str) -> str | None:
    """Extract the '### Summary' section text from a Bridge Work Order body."""
    match = re.search(r"###\s*Summary[^\n]*\n(.*?)(?=\n###\s|\Z)", body, re.DOTALL)
    if not match:
        return None
    text = match.group(1).strip()
    return text or None


def extract_alternatives(body: str) -> str | None:
    """Extract an alternatives_rejected entry from the WO body, if present.

    Handles both inline text on the label line and a markdown sub-list on the
    following lines. The label's own bold '**' suffix is skipped — capturing it
    was a real defect the self-test caught (alt == '**').
    """
    match = re.search(r"alternatives_rejected:?[ \t]*\**[ \t]*(.*)", body, re.IGNORECASE)
    if not match:
        return None
    inline = (match.group(1) or "").strip()
    if inline:
        return inline
    for line in body[match.end():].splitlines():
        text = line.strip().lstrip("-").strip()
        if text:
            return text
    return None


def build_reflection_section(body: str, wo_num: int) -> str:
    """Build the guard-compliant Reflection Evidence section from WO content.

    Honesty contract: quotes the work order; never invents rationale. When the
    WO lacks an alternatives_rejected entry the fallback SAYS so and points at
    the submitting agent's decision ledger instead of fabricating one.
    """
    why = extract_summary_section(body) or f"Work order #{wo_num} summary (what + why)."
    why = why[:400]
    alt = extract_alternatives(body)
    if alt is None:
        alt = (
            f"Not recorded in work order #{wo_num} body — rejected alternatives "
            "live in the submitting agent's decision ledger (AGENTS.md §2/§5)."
        )
    alt = alt[:400]
    return (
        "## Reflection Evidence (why + alternatives_rejected)\n"
        f"- **why:** {why}\n"
        f"- **alternatives_rejected:**\n"
        f"  - {alt}\n"
    )


def issue_has_active_claim(issue_number: int, repo: str = UPSTREAM_REPO) -> bool:
    """Claim Gate SSOT predicate (#392) — mirrors pipeline.yml claim-guard.

    Active claim = status:claimed / status:in-progress label, an open bridge:*
    label (a filed Bridge Work Order IS the zero-credential claim vehicle), or
    an <!-- atomic-claim --> comment vetoed by the released marker
    (status:unclaimed, per stale_claim_releaser vocabulary). Fail-closed: an
    unreadable issue or any error counts as NO verifiable claim.
    """
    cmd = ["gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "labels,comments"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode != 0:
            return False
        data = json.loads(res.stdout)
        labels = [str(lbl.get("name", "")) for lbl in data.get("labels", []) or []]
        if "status:claimed" in labels or "status:in-progress" in labels:
            return True
        if any(lbl.startswith("bridge:") for lbl in labels):
            return True
        if "status:unclaimed" in labels:
            return False
        for comment in data.get("comments", []) or []:
            if "<!-- atomic-claim -->" in str(comment.get("body", "")):
                return True
        return False
    except Exception:
        return False


def branch_exists_on_remote(branch: str, repo: str = UPSTREAM_REPO) -> bool:
    """Check if the branch exists on remote repository."""
    cmd = ["git", "ls-remote", "--heads", f"https://github.com/{repo}.git", branch]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return False


def get_existing_pr_for_branch(branch: str, repo: str = UPSTREAM_REPO) -> int | None:
    """Check if an open or merged PR already exists for the branch."""
    cmd = ["gh", "pr", "list", "--repo", repo, "--head", branch, "--state", "all", "--json", "number", "--limit", "1"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            if data and isinstance(data, list) and len(data) > 0:
                return int(data[0]["number"])
    except Exception:
        pass
    return None


def build_pr_body(issue: dict[str, Any], branch: str, repo: str = UPSTREAM_REPO) -> str:
    """Build the PR body for a Bridge Work Order (pure; guard-compliant)."""
    wo_num = issue.get("number")
    title = issue.get("title", f"Bridge Work Order #{wo_num}")
    body = issue.get("body", "")

    # Clean up title for PR: strip leading emojis/Bridge Work Order prefix if present
    pr_title = re.sub(r"^🌉\s*Bridge Work Order\s*—\s*", "", title).strip()
    if not pr_title:
        pr_title = f"feat(bridge): deliver work order #{wo_num}"

    task_ref = extract_task_issue_reference(title, body)
    closes_line = f"Closes {task_ref}" if task_ref else ""

    reflection = build_reflection_section(body, wo_num)

    return f"""## Claim & Work Order
Submitted via [Bridge Work Order #{wo_num}](https://github.com/{repo}/issues/{wo_num}) on branch `{branch}`.

## Summary & Purpose
{pr_title}

{closes_line}
Refs #{wo_num}

{reflection}"""


def create_pr_for_work_order(issue: dict[str, Any], branch: str, repo: str = UPSTREAM_REPO) -> tuple[bool, str]:
    """Create a Pull Request for a Bridge Work Order."""
    wo_num = issue.get("number")
    title = issue.get("title", f"Bridge Work Order #{wo_num}")
    body = issue.get("body", "")

    # Clean up title for PR: strip leading emojis/Bridge Work Order prefix if present
    pr_title = re.sub(r"^🌉\s*Bridge Work Order\s*—\s*", "", title).strip()
    if not pr_title:
        pr_title = f"feat(bridge): deliver work order #{wo_num}"

    pr_body = build_pr_body(issue, branch, repo)

    cmd = [
        "gh", "pr", "create",
        "--repo", repo,
        "--base", "main",
        "--head", branch,
        "--title", pr_title,
        "--body", pr_body,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            pr_url = res.stdout.strip()
            return True, pr_url
        return False, res.stderr.strip()
    except Exception as exc:
        return False, str(exc)


def run_auto_bridge_pr_opener(auto_open: bool = False, repo: str = UPSTREAM_REPO) -> list[dict[str, Any]]:
    """Scan open bridge:queued issues and autonomously open PRs."""
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open", "--label", "bridge:queued", "--json", "number,title,body"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            print(f"Failed to query issues: {res.stderr.strip()}")
            return []
        issues = json.loads(res.stdout)
    except Exception as exc:
        print(f"Error querying issues: {exc}")
        return []

    actions = []
    print(f"Auto-Bridge PR Opener: Found {len(issues)} open 'bridge:queued' issues.")

    for iss in issues:
        wo_num = iss["number"]
        title = iss["title"]
        # Skip sync backfills (Auto-Bridge: Sync PR...)
        if "Auto-Bridge: Sync PR" in title:
            continue

        branch = extract_patch_branch(iss.get("body", ""))
        if not branch:
            print(f"  [WO #{wo_num}] No patch branch found in body. Skipping.")
            continue

        exists = branch_exists_on_remote(branch, repo)
        if not exists:
            print(f"  [WO #{wo_num}] Branch '{branch}' does NOT exist on remote. Skipping.")
            continue

        existing_pr = get_existing_pr_for_branch(branch, repo)
        if existing_pr:
            print(f"  [WO #{wo_num}] Branch '{branch}' already has PR #{existing_pr}. Skipping.")
            continue

        # Claim Gate precheck (#392 deliverable 4): verify an active claim on the
        # referenced target issue (or the WO itself) BEFORE opening. Fail-honest
        # skip — one unverifiable WO must not kill the whole scan.
        task_ref = extract_task_issue_reference(title, iss.get("body", ""))
        claim_check_num = int(task_ref.lstrip("#")) if task_ref else wo_num
        if not issue_has_active_claim(claim_check_num, repo):
            print(f"  [WO #{wo_num}] No active claim on issue {task_ref or f'#{wo_num}'} (fail-closed). "
                  f"Per AGENTS.md Step 4 (no claim, no work) — skipping PR creation.")
            actions.append({"wo": wo_num, "branch": branch, "status": "unclaimed-skip"})
            continue

        print(f"  [WO #{wo_num}] Eligible for autonomous PR creation: branch='{branch}'")
        if auto_open:
            success, detail = create_pr_for_work_order(iss, branch, repo)
            if success:
                print(f"    🚀 Autonomously created PR: {detail}")
                actions.append({"wo": wo_num, "branch": branch, "pr": detail, "status": "created"})
            else:
                print(f"    ❌ Failed to create PR: {detail}")
                actions.append({"wo": wo_num, "branch": branch, "error": detail, "status": "failed"})
        else:
            print("    [DRY-RUN] Would execute 'gh pr create'. Use --auto-open to execute.")
            actions.append({"wo": wo_num, "branch": branch, "status": "eligible"})

    return actions


def run_self_test() -> None:
    """Run unit tests for extractor logic."""
    print("Running auto_bridge_pr_opener self-test...")
    sample_body = """### Task ID
bridge-20261015-issue-51-webhook-dispatch-contract

### Patch Branch
bridge/bridge-20261015-issue-51-webhook-dispatch-contract

### Target Repo
Supremeai-bd/supremeai
"""
    b = extract_patch_branch(sample_body)
    assert b == "bridge/bridge-20261015-issue-51-webhook-dispatch-contract", f"Unexpected branch: {b}"

    t = extract_task_issue_reference("Bridge Work Order — feat(schemas): external Webhook (#51)", sample_body)
    assert t == "#51", f"Unexpected task ref: {t}"

    # Reflection Evidence builders (#392)
    summary = extract_summary_section(
        sample_body + "\n### Summary (what + why)\nfixes the webhook dispatch contract.\n"
    )
    assert summary is not None and "webhook dispatch contract" in summary, f"Unexpected summary: {summary}"
    assert extract_summary_section("no sections here") is None, "missing section must be None"
    alt = extract_alternatives("- **alternatives_rejected:**\n  - dropped approach X because Y")
    assert alt is not None and "approach X" in alt, f"Unexpected alternatives: {alt}"
    assert extract_alternatives("nothing here") is None, "missing alternatives must be None"
    refl = build_reflection_section(sample_body, 51)
    assert "## Reflection Evidence" in refl, "reflection section header missing"
    assert "- **why:**" in refl and "- **alternatives_rejected:**" in refl, "reflection fields missing"
    assert "decision ledger" in refl, "honest fallback for missing alternatives missing"
    refl2 = build_reflection_section(
        sample_body + "\n### Summary (what + why)\nfixes X.\n- **alternatives_rejected:**\n  - Y because Z",
        51,
    )
    assert "fixes X." in refl2 and "Y because Z" in refl2, "WO-provided why/alternatives not carried"

    print("✅ Auto-Bridge PR Opener self-test passed cleanly!")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-Bridge PR Opener for SupremeAI Federation")
    parser.add_argument("--auto-open", action="store_true", help="Autonomously open PRs for eligible bridge branches")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests and exit")
    parser.add_argument("--repo", type=str, default=UPSTREAM_REPO, help=f"Target GitHub repo (default: {UPSTREAM_REPO})")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0

    run_auto_bridge_pr_opener(auto_open=args.auto_open, repo=args.repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
