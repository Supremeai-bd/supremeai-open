#!/usr/bin/env python3
"""
PR Helper — Auto-Fix Engine (Phase 4 of Intelligent Decision Engine)
=====================================================================
fixability_scorer.py থেকে "auto_fix" verdict পাওয়া failures-এর জন্য
স্বয়ংক্রিয় fix patch তৈরি করে।

Safety:
  - শুধু test files (backend/tests/**) modify করে
  - Source code কখনো touch করে না
  - প্রতিটি fix-এর জন্য confidence + rationale লগ করে

Usage:
  python auto_fix_engine.py --recommendations recommendations.json \\
    --delta delta.json --repo /path/to/repo --head-sha <sha> \\
    --output-json auto_fix.json

GitHub Actions outputs (GITHUB_OUTPUT):
  fixes_generated = N
  fixes_applied = M
  fix_branch = pr-helper/auto-fix-pr-XXX (if any fixes)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True, text=True, check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def _find_test_file(repo: str, head_sha: str, classname: str) -> str:
    """Find the test file path from junit classname."""
    parts = [p for p in classname.split(".") if p]
    for size in range(len(parts), 0, -1):
        rel = "/".join(parts[:size]) + ".py"
        for prefix in ["backend/tests/", "tests/"]:
            path = f"{prefix}{rel}"
            if _git(repo, "cat-file", "-e", f"{head_sha}:{path}"):
                return path
    return ""


def _fix_import_error(
    repo: str, head_sha: str, test_file: str, failure: dict, changed_files: list[str]
) -> dict | None:
    """Fix: update import path when module moved/renamed.

    Strategy: find the old import in the test file, find the new location
    in changed files, generate a sed replacement.
    """
    snippet = failure.get("snippet", "") + failure.get("message", "")

    # Extract the missing module name
    m = re.search(r"No module named ['\"]?([\w.]+)", snippet)
    if not m:
        m = re.search(r"cannot import name ['\"]?(\w+)['\"]? from ['\"]?([\w.]+)", snippet)
        if m:
            old_name, old_path = m.group(1), m.group(2)
        else:
            return None
    else:
        old_path = m.group(1)

    # Try to find new path in changed files
    # e.g., if old_path is "core.llm.llm_gateway_with_learning"
    # and changed files contain "core/llm/llm_gateway/__init__.py"
    # → new path is "core.llm.llm_gateway"
    old_path_parts = old_path.replace(".", "/")
    for cf in changed_files:
        if old_path_parts in cf and cf.endswith(".py"):
            # Derive new module path
            new_path = cf.replace("/", ".").replace(".py", "").replace(".__init__", "")
            if new_path != old_path:
                return {
                    "file": test_file,
                    "old_import": old_path,
                    "new_import": new_path,
                    "fix_type": "replace_import",
                    "sed_command": f"sed -i 's|{old_path}|{new_path}|g' {test_file}",
                    "confidence": 0.95,
                    "rationale": f"Module moved: {old_path} → {new_path}",
                }
    return None


def _fix_assertion_mismatch(
    repo: str, head_sha: str, test_file: str, failure: dict, recommendation: dict
) -> dict | None:
    """Fix: update assertion when PR intentionally changed behavior.

    Strategy: if expected=X and actual=Y, and PR intention matches,
    update the assertion from X to Y.
    """
    expected = recommendation.get("expected", "")
    actual = recommendation.get("actual", "")

    if not expected or not actual or expected == actual:
        return None

    # Only auto-fix if intention_match is True (PR intentionally changed this)
    if not recommendation.get("intention_match", False):
        return None

    # Generate sed to replace expected with actual in the assertion
    # Be careful: only replace within assert statements
    return {
        "file": test_file,
        "old_value": expected,
        "new_value": actual,
        "fix_type": "update_assertion",
        "sed_command": f"sed -i 's|assert.*{re.escape(expected)}.*|assert result == {actual}|' {test_file}",
        "confidence": 0.85,
        "rationale": f"PR intentionally changed behavior: {expected} → {actual}",
    }


def _fix_type_error(
    repo: str, head_sha: str, test_file: str, failure: dict, changed_files: list[str]
) -> dict | None:
    """Fix: update function call signature when API changed."""
    snippet = failure.get("snippet", "") + failure.get("message", "")

    # Extract: "got an unexpected keyword argument 'X'"
    m = re.search(r"unexpected keyword argument ['\"](\w+)['\"]", snippet)
    if m:
        kwarg = m.group(1)
        return {
            "file": test_file,
            "fix_type": "remove_keyword_arg",
            "sed_command": f"sed -i 's/{kwarg}=[^,)]*[,)]*//' {test_file}",
            "confidence": 0.80,
            "rationale": f"Remove unexpected keyword argument '{kwarg}' from test call",
        }

    # Extract: "missing 1 required positional argument: 'X'"
    m = re.search(r"missing.*required.*argument.*['\"](\w+)['\"]", snippet)
    if m:
        arg = m.group(1)
        return {
            "file": test_file,
            "fix_type": "add_positional_arg",
            "sed_command": f"# Manual fix needed: add '{arg}' argument",
            "confidence": 0.60,
            "rationale": f"Test needs to pass '{arg}' argument — manual review recommended",
        }

    return None


def generate_fix(
    repo: str,
    head_sha: str,
    failure: dict,
    recommendation: dict,
    changed_files: list[str],
) -> dict | None:
    """Generate a fix for a single failure based on its type + recommendation."""
    if recommendation["verdict"] != "auto_fix":
        return None

    ftype = failure.get("failure_type", "unknown")
    classname = failure.get("class", "")
    test_file = _find_test_file(repo, head_sha, classname)

    if not test_file:
        return {
            "test_id": failure.get("id", ""),
            "fix_type": "skip",
            "reason": "Test file not found in repo",
            "confidence": 0.0,
        }

    if ftype == "import_error":
        return _fix_import_error(repo, head_sha, test_file, failure, changed_files)
    elif ftype == "assertion_mismatch":
        return _fix_assertion_mismatch(repo, head_sha, test_file, failure, recommendation)
    elif ftype == "type_error":
        return _fix_type_error(repo, head_sha, test_file, failure, changed_files)
    elif ftype == "connection_error":
        return {
            "test_id": failure.get("id", ""),
            "fix_type": "skip_env_issue",
            "confidence": 0.95,
            "rationale": "Connection error — not code-related, skip test",
        }
    else:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper: Auto-Fix Engine")
    parser.add_argument("--recommendations", required=True, help="recommendations.json from fixability_scorer")
    parser.add_argument("--delta", required=True, help="delta.json from Step 3")
    parser.add_argument("--repo", default=".", help="Repo path")
    parser.add_argument("--head-sha", default="HEAD", help="HEAD SHA for file lookup")
    parser.add_argument("--changed-files", default="", help="Comma-separated changed files")
    parser.add_argument("--output-json", default="", help="Output JSON path")
    args = parser.parse_args()

    recs = json.loads(Path(args.recommendations).read_text(encoding="utf-8"))
    delta = json.loads(Path(args.delta).read_text(encoding="utf-8"))
    new_failures = {f["id"]: f for f in delta.get("new_failures", [])}
    changed_files = [f.strip() for f in args.changed_files.split(",") if f.strip()]

    fixes = []
    for rec in recs.get("recommendations", []):
        test_id = rec.get("test_id", "")
        failure = new_failures.get(test_id, {})
        if not failure:
            continue
        fix = generate_fix(args.repo, args.head_sha, failure, rec, changed_files)
        if fix:
            fix["test_id"] = test_id
            fix["failure_type"] = failure.get("failure_type", "unknown")
            fixes.append(fix)

    result = {
        "fixes_generated": len(fixes),
        "fixes": fixes,
        "has_fixes": len(fixes) > 0,
    }

    if args.output_json:
        Path(args.output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Auto-fix: {len(fixes)} fixes generated")
    for fix in fixes:
        print(f"  [{fix.get('fix_type','?'):20s}] {fix.get('test_id','')[:50]}")
        if fix.get("rationale"):
            print(f"    → {fix['rationale'][:80]}")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"fixes_generated={len(fixes)}\n")
            f.write(f"has_fixes={str(len(fixes) > 0).lower()}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
