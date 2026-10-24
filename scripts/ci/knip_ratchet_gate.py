#!/usr/bin/env python3
"""knip ratchet gate — #2736: dead-code CI assertion (no NEW findings)।

বাংলা মন্তব্য: knip.json-এ files/exports rule এখন "error" (PR #2827) — কিন্তু
কোনো workflow-ই knip চালায় না ছিল, তাই নিয়মটি মৃত-কনফিগ ছিল। main-এ এখন
১৮টি unused file + ১৫৭টি symbol-issue জমে আছে — এক রাতে সব পরিশোধ P3-স্কোপের
বাইরে। তাই **ratchet** নীতি: বেসলাইনের চেয়ে বেশি হলেই CI লাল; কমলে সবুজ
(এবং নতুন বেসলাইন commit করার পরামর্শ দেয়)। নতুন dead-file/export যোগ করা
PR আর নীরবে মার্জ হতে পারবে না।

Usage:
  knip_ratchet_gate.py <knip-report.json> [--baseline <path>] [--update-baseline]

- knip চালানো হয়: `pnpm exec knip --reporter json --no-exit-code` (exit-code
  নীতি এই গেটের, knip-এর নয়)।
- বেসলাইন: JSON, {"files": N, "issues": {"exports": N, ...}, "total": N}।
- Schema-defensive (knip_summarize.py-র দর্শন): অপ্রত্যাশিত structure-এ সৎ
  ত্রুটি + non-zero exit — নীরব পাস নয় (gate হিসেবে fail-closed)।
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ISSUE_KEYS = (
    "dependencies",
    "devDependencies",
    "optionalPeerDependencies",
    "unlisted",
    "binaries",
    "unresolved",
    "exports",
    "types",
    "enumMembers",
    "duplicates",
    "catalog",
)


def parse_report(data: object) -> tuple[int, Counter]:
    """knip JSON → (unused-file count, per-category issue counts)।"""
    if not isinstance(data, dict):
        raise ValueError(f"unexpected knip report root: {type(data).__name__}")
    files = data.get("files")
    if files is None:
        files = []
    if not isinstance(files, list):
        raise ValueError(f"unexpected 'files' shape: {type(files).__name__}")
    issues = data.get("issues")
    if issues is None:
        issues = []
    if not isinstance(issues, list):
        raise ValueError(f"unexpected 'issues' shape: {type(issues).__name__}")
    totals: Counter = Counter()
    for item in issues:
        if not isinstance(item, dict):
            continue
        for key in ISSUE_KEYS:
            value = item.get(key)
            if isinstance(value, list):
                totals[key] += len(value)
    return len(files), totals


def load_baseline(path: Path) -> tuple[int, Counter]:
    data = json.loads(path.read_text(encoding="utf-8"))
    files = int(data.get("files", 0))
    issues_raw = data.get("issues", {})
    if not isinstance(issues_raw, dict):
        raise ValueError("baseline 'issues' must be an object")
    totals = Counter({k: int(v) for k, v in issues_raw.items()})
    return files, totals


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", help="knip JSON report path")
    ap.add_argument("--baseline", default="knip-baseline.json", help="baseline JSON path")
    ap.add_argument(
        "--update-baseline",
        action="store_true",
        help="বর্তমান রিপোর্ট থেকে বেসলাইন ফাইল লিখে দাও (উন্নতি commit করার সময়)",
    )
    args = ap.parse_args()

    report_path = Path(args.report)
    baseline_path = Path(args.baseline)

    try:
        current_files, current_issues = parse_report(
            json.loads(report_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"::error::knip ratchet: report unreadable ({exc}) — fail-closed")
        return 1

    if args.update_baseline:
        payload = {
            "files": current_files,
            "issues": dict(sorted(current_issues.items())),
            "total": current_files + sum(current_issues.values()),
        }
        baseline_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"[knip-ratchet] baseline updated: {baseline_path}")
        return 0

    if not baseline_path.exists():
        print(
            f"::error::knip ratchet: baseline missing ({baseline_path}) — "
            "generate via --update-baseline and commit it"
        )
        return 1

    try:
        base_files, base_issues = load_baseline(baseline_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"::error::knip ratchet: baseline unreadable ({exc}) — fail-closed")
        return 1

    regressions: list[tuple[str, int, int]] = []
    improvements: list[tuple[str, int, int]] = []
    all_keys = sorted(set(base_issues) | set(current_issues))
    if current_files > base_files:
        regressions.append(("files", base_files, current_files))
    elif current_files < base_files:
        improvements.append(("files", base_files, current_files))
    for key in all_keys:
        base_n, cur_n = base_issues.get(key, 0), current_issues.get(key, 0)
        if cur_n > base_n:
            regressions.append((key, base_n, cur_n))
        elif cur_n < base_n:
            improvements.append((key, base_n, cur_n))

    base_total = base_files + sum(base_issues.values())
    cur_total = current_files + sum(current_issues.values())

    print(f"[knip-ratchet] baseline: files={base_files}, issues={base_total}")
    print(f"[knip-ratchet] current: files={current_files}, issues={cur_total}")

    if improvements:
        print("[knip-ratchet] উন্নতি (বেসলাইন ছোট করার সুযোগ):")
        for key, old, new in improvements:
            print(f"  ✓ {key}: {old} → {new}")
        print(
            "[knip-ratchet] ইঙ্গিত: --update-baseline দিয়ে নতুন বেসলাইন রেখে "
            "commit করলে লাভ স্থায়ী হবে।"
        )

    if regressions:
        print("::error::knip ratchet: নতুন dead-code যোগ হয়েছে — PR Gate ব্লক!")
        for key, old, new in regressions:
            print(f"  ✗ {key}: {old} → {new} (+{new - old})")
        print(
            "[knip-ratchet] সমাধান: unused export/file সরাও, বা wire-or-delete "
            "doctrine অনুযায়ী wire করো (deletion-এ admin approval লাগে)।"
        )
        return 1

    print("[knip-ratchet] PASS — নতুন কোনো dead-code যোগ হয়নি।")
    return 0


if __name__ == "__main__":
    sys.exit(main())
