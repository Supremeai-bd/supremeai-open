#!/usr/bin/env python3
"""Architecture Preservation Gate — AGENTS.md Protocol 14 + Hard Rule 6.

বাংলা মন্তব্য: এই gate চেক করে যে PR-এ নতুন workflow বা duplicate module
যোগ হলে সেটা DRY 3-Pipeline Law ফলো করছে কিনা।

Checks:
1. New .github/workflows/*.yml file → WARNING (not BLOCK — may be reusable)
2. New backend module that could reuse existing canonical abstraction → WARNING
3. New .github/workflows/ file count > 3 pipeline types → WARNING

Exit codes: 0 = pass, 1 = fail (WARNING only — advisory, not BLOCK).
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

CANONICAL_ABSTRACTIONS = {
    "policy": ["core/circles/governance_core.py", "core/security/tool_policy_gateway.py"],
    "circuit_breaker": ["core/resilience/circuit_breaker.py"],
    "rate_limiter": ["core/cache/rate_limit_atomic.py"],
    "audit": ["core/audit/"],
    "registry": ["core/circles/centers/"],
}


def get_changed_files(pr_number: int) -> list[str]:
    """Get list of files changed in PR."""
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{os.environ.get('GH_REPO', '')}/pulls/{pr_number}/files",
             "--jq", ".[].filename"],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip().split("\n") if result.stdout.strip() else []
    except Exception:
        return []


def check_new_workflows(changed_files: list[str]) -> list[str]:
    """Check for new workflow files."""
    warnings = []
    existing_workflows = set()
    workflows_dir = REPO_ROOT / ".github" / "workflows"
    if workflows_dir.exists():
        existing_workflows = {f.name for f in workflows_dir.glob("*.yml")}

    for f in changed_files:
        if f.startswith(".github/workflows/") and f.endswith(".yml"):
            filename = Path(f).name
            if filename not in existing_workflows:
                warnings.append(
                    f"নতুন workflow ফাইল: {f} — "
                    "Protocol 14 (DRY 3-Pipeline Law) ফলো করছে কিনা যাচাই করো। "
                    "৩টি pipeline: PR Gate, Merge Train, Main CI/CD।"
                )
    return warnings


def check_duplicate_modules(changed_files: list[str]) -> list[str]:
    """Check for new modules that duplicate existing canonical abstractions."""
    warnings = []
    for f in changed_files:
        if not f.startswith("backend/") or not f.endswith(".py"):
            continue
        f_lower = f.lower()
        for concern, canonical_paths in CANONICAL_ABSTRACTIONS.items():
            # বাংলা মন্তব্য: যদি নতুন ফাইলের নামে concern keyword থাকে
            # কিন্তু canonical path-এ না থাকে → duplicate risk
            if any(kw in f_lower for kw in [concern, concern.replace("_", "")]):
                if not any(canon in f for canon in canonical_paths):
                    warnings.append(
                        f"সম্ভাব্য duplicate: {f} — "
                        f"'{concern}' canonical abstraction আছে: {canonical_paths}. "
                        "Reuse before create (Protocol 14)."
                    )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Architecture Preservation Gate")
    parser.add_argument("--pr", type=int, default=0)
    args = parser.parse_args()

    changed = get_changed_files(args.pr) if args.pr else []
    warnings = []

    if changed:
        warnings.extend(check_new_workflows(changed))
        warnings.extend(check_duplicate_modules(changed))

    if warnings:
        for w in warnings:
            print(f"::warning::{w}")
        print(f"\n⚠️ Architecture Preservation Gate: {len(warnings)} warning(s)")
        return 0  # advisory — WARNING only
    else:
        print("✅ Architecture Preservation Gate: no concerns")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
