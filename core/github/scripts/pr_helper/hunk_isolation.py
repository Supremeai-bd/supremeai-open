#!/usr/bin/env python3
"""
PR Helper — Step 4: Hunk-Level Isolation
========================================
Step 3-এর delta.json (new_failures) থেকে প্রতিটি regression-কে PR-এর
পরিবর্তিত ফাইলের সাথে attribute করার চেষ্টা করে। সিদ্ধান্ত:

  - সব new failure ম্যাপ হয়েছে এবং কিছু ফাইল "clean" থেকে গেছে
      → isolatable = true
      → clean patch (PR diff − attributed files) তৈরি হবে — এই প্যাচটাই
        "Cherry-pick Improvements": ভাঙা হাংক বাদে শুধু ভালো পরিবর্তন।
  - যেকোনো failure attribute করা না গেলে, বা attribution সব changed file
    ঢেকে ফেললে (কিছুই বাদ দেওয়ার থাকে না)
      → isolatable = false (fatal) → উপরের ধাপ auto-issue + block করবে।

Attribution strategy (deterministic, stdlib-only):
  1. Test-file match:  junit classname → backend/<dotted.path>.py, যদি সেই
     টেস্ট ফাইলটি এই PR-এ বদলে থাকে।
  2. Import match:     টেস্ট ফাইলের HEAD content-এর local import
     (api/core/services/models/utils/tools/…) → backend/<module>.py, যদি
     সেই সোর্স ফাইলটি এই PR-এ বদলে থাকে।

Usage:
  python hunk_isolation.py \
    --delta delta.json \
    --base-ref <base-sha> \
    --head-ref <head-sha> \
    --patch-out clean.patch \
    --output-json isolation.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LOCAL_PKG_PREFIXES = ("api", "core", "services", "models", "utils", "tools", "middleware", "schemas")
IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+((?:[A-Za-z_][\w]*\.?)+)", re.MULTILINE
)


def _git(repo: str, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", repo, *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def changed_files(repo: str, base_ref: str, head_ref: str) -> list[str]:
    out = _git(repo, "diff", "--name-only", f"{base_ref}...{head_ref}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def _candidate_test_paths(classname: str) -> list[str]:
    """junit classname ('tests.api.test_x') → সম্ভাব্য ফাইল পাথ, লম্বা থেকে ছোট।"""
    parts = [p for p in classname.split(".") if p]
    candidates = []
    for size in range(len(parts), 0, -1):
        rel = "/".join(parts[:size]) + ".py"
        candidates.append(f"backend/{rel}")
        candidates.append(rel)
    return candidates


def _local_imports(repo: str, head_ref: str, test_file: str) -> list[str]:
    """টেস্ট ফাইলের HEAD কনটেন্ট থেকে local module path বের করা।"""
    try:
        content = _git(repo, "show", f"{head_ref}:{test_file}")
    except RuntimeError:
        return []
    modules = set()
    for match in IMPORT_RE.finditer(content):
        dotted = match.group(1).strip(".")
        parts = [p for p in dotted.split(".") if p]
        # বাংলা মন্তব্য: প্রথম segment আমাদের local package হলেই শুধু তখনই source-file
        # প্রার্থী — 3rd-party/stdlib import attribution-কে বিষ দিত না।
        if not parts or parts[0] not in LOCAL_PKG_PREFIXES:
            continue
        for size in range(len(parts), 0, -1):
            modules.add("backend/" + "/".join(parts[:size]) + ".py")
    return sorted(modules)


def attribute_failures(
    repo: str, base_ref: str, head_ref: str, new_failures: list[dict], changed: list[str]
) -> tuple[dict, list[dict]]:
    """প্রতিটি failure → attributed changed files। Returns (report, attributed_map)."""
    changed_set = set(changed)
    report: dict = {"attributed": {}, "unattributed": []}
    attributed_map: dict[str, set[str]] = {}
    for failure in new_failures:
        classname = failure.get("class") or ""
        hits: set[str] = set()
        # Strategy 1: টেস্ট ফাইল নিজেই changed?
        test_file = None
        for cand in _candidate_test_paths(classname):
            if cand in changed_set:
                test_file = cand
                break
        if test_file:
            hits.add(test_file)
        # Strategy 2: টেস্ট ফাইলের import করা local module changed?
        if not test_file:
            resolved_test = next(
                (c for c in _candidate_test_paths(classname) if Path(repo, c).exists()),
                None,
            )
            if resolved_test:
                for mod in _local_imports(repo, head_ref, resolved_test):
                    if mod in changed_set:
                        hits.add(mod)
        fid = failure.get("id") or "?"
        attributed_map[fid] = hits
        if hits:
            report["attributed"][fid] = sorted(hits)
        else:
            report["unattributed"].append(fid)
    return report, attributed_map


def build_clean_patch(
    repo: str, base_ref: str, head_ref: str, changed: list[str], attributed_map: dict
) -> tuple[str | None, list[str]]:
    """Attributed (ভাঙা) ফাইলগুলো বাদ দিয়ে বাকি changed files-এর unified patch।"""
    broken_files: set[str] = set()
    for hits in attributed_map.values():
        broken_files.update(hits)
    clean_files = [f for f in changed if f not in broken_files]
    if not clean_files:
        return None, sorted(broken_files)
    pathspecs: list[str] = ["--"]
    for f in clean_files:
        pathspecs.append(f)
    diff = _git(repo, "diff", f"{base_ref}...{head_ref}", *pathspecs)
    return diff.strip() or None, sorted(broken_files)


def main() -> int:
    parser = argparse.ArgumentParser(description="PR Helper Step 4: hunk-level isolation")
    parser.add_argument("--delta", required=True, help="delta.json from Step 3")
    parser.add_argument("--base-ref", required=True, help="BASE sha")
    parser.add_argument("--head-ref", required=True, help="HEAD sha")
    parser.add_argument("--repo-root", default=".", help="repository root")
    parser.add_argument("--patch-out", default="clean.patch", help="clean patch output path")
    parser.add_argument("--output-json", default="isolation.json", help="isolation JSON output")
    args = parser.parse_args()

    delta = json.loads(Path(args.delta).read_text(encoding="utf-8"))
    new_failures = delta.get("new_failures", [])

    repo = str(Path(args.repo_root).resolve())
    changed = changed_files(repo, args.base_ref, args.head_ref)

    if not new_failures:
        result = {
            "isolatable": False,
            "reason": "no new failures (nothing to isolate)",
            "changed_files": changed,
            "attribution": {"attributed": {}, "unattributed": []},
            "broken_files": [],
            "clean_patch_files": [],
            "patch_path": None,
        }
    else:
        report, attributed_map = attribute_failures(repo, args.base_ref, args.head_ref, new_failures, changed)
        unattributed = report["unattributed"]
        broken_files: set[str] = set()
        for hits in attributed_map.values():
            broken_files.update(hits)
        clean_count = len([f for f in changed if f not in broken_files])

        if unattributed:
            isolatable = False
            reason = (
                f"{len(unattributed)} new failure(s) could not be attributed to any changed "
                "file — clean cherry-pick would be unsafe (fatal per lifecycle)"
            )
        elif clean_count == 0:
            isolatable = False
            reason = (
                "attribution covers every changed file — nothing left to salvage "
                "in a clean patch"
            )
        else:
            isolatable = True
            reason = (
                f"{len(broken_files)} broken file(s) isolated; {clean_count} clean file(s) "
                "can be cherry-picked"
            )

        patch: str | None = None
        patch_path = None
        if isolatable:
            patch, _ = build_clean_patch(repo, args.base_ref, args.head_ref, changed, attributed_map)
            if patch:
                Path(args.patch_out).write_text(patch + "\n", encoding="utf-8")
                patch_path = args.patch_out
            else:
                isolatable = False
                reason = "clean patch came back empty — treating as fatal"

        result = {
            "isolatable": isolatable,
            "reason": reason,
            "changed_files": changed,
            "attribution": report,
            "broken_files": sorted(broken_files),
            "clean_patch_files": [f for f in changed if f not in broken_files],
            "patch_path": patch_path,
        }

    Path(args.output_json).write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"isolatable={'true' if result['isolatable'] else 'false'}\n")
            f.write(f"broken_files={','.join(result['broken_files'])}\n")
            f.write(f"clean_files={','.join(result['clean_patch_files'])}\n")
            f.write(f"patch_path={result['patch_path'] or ''}\n")

    print(f"PR Helper isolation: isolatable={result['isolatable']} — {result['reason']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
