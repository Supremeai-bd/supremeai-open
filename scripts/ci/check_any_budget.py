#!/usr/bin/env python3
"""': any' burn-down ratchet gate (frontend).

বাংলা মন্তব্য: এটি একটি ratchet (র‍্যাচেট) গেট — frontend/src-এ `: any` টাইপ
অ্যানোটেশনের সংখ্যা baseline (frontend/any_budget.json) থেকে বাড়লেই fail করবে।
কমার দিকে গেলে pass; কমার পর baseline ম্যানুয়ালি কমিয়ে নিতে হয় (ডেটা ফাইল,
কোনো hardcoded সংখ্যা স্ক্রিপ্টে নেই)। এভাবে পুরনো টেকনিক্যাল ডেট ধীরে ধীরে
শূন্যে নামবে, নতুন কোনো `any` ঢুকতে পারবে না — এবং কিছুই হঠাৎ ভাঙবে না।
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# বাংলা: স্ক্যান প্যাটার্ন — `: any` (colon পরে any), টেস্ট/ডিক্লারেশন ফাইল বাদ
ANY_PATTERN = re.compile(r":\s*any\b")
EXCLUDED_SUFFIXES = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".d.ts")
EXCLUDED_DIRS = {"node_modules", "coverage", "dist", "__tests__"}


def count_any(src_dir: Path) -> tuple[int, list[str]]:
    total = 0
    offenders: list[str] = []
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file() or path.suffix not in (".ts", ".tsx"):
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if str(path).endswith(EXCLUDED_SUFFIXES):
            continue
        try:
            hits = len(
                ANY_PATTERN.findall(path.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError as exc:  # বাংলা: ফাইল পড়া গেল না — সৎ ব্যর্থতা, নীরব স্কিপ নয়
            print(
                f"[any-budget] unreadable file skipped with warning: {path} ({exc})",
                file=sys.stderr,
            )
            continue
        if hits:
            total += hits
            offenders.append(f"{path.relative_to(src_dir.parent)}: {hits}")
    return total, offenders


def main() -> int:
    parser = argparse.ArgumentParser(description="': any' burn-down ratchet gate")
    parser.add_argument(
        "--src", required=True, help="frontend source dir (e.g. frontend/src)"
    )
    parser.add_argument("--baseline", required=True, help="baseline JSON file path")
    args = parser.parse_args()

    src_dir = Path(args.src)
    baseline_path = Path(args.baseline)
    if not src_dir.is_dir():
        print(f"[any-budget] src dir not found: {src_dir}", file=sys.stderr)
        return 1
    if not baseline_path.is_file():
        # বাংলা: baseline নেই = প্রথম রান — বর্তমান সংখ্যা দিয়ে baseline লিখে দিই
        total, _ = count_any(src_dir)
        baseline_path.write_text(
            json.dumps(
                {
                    "max_any_count": total,
                    "note": "ratchet baseline — কমানো যাবে, বাড়ানো যাবে না",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"[any-budget] baseline created at {baseline_path} with max_any_count={total}"
        )
        return 0

    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        max_allowed = int(baseline["max_any_count"])
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"[any-budget] baseline unreadable/invalid: {exc}", file=sys.stderr)
        return 1

    total, offenders = count_any(src_dir)
    if total > max_allowed:
        print(
            f"[any-budget] ❌ FAIL: ': any' count {total} > baseline {max_allowed} (+{total - max_allowed})"
        )
        for line in offenders[:15]:
            print(f"  - {line}")
        print(
            "[any-budget] নতুন `any` যোগ হয়েছে — সঠিক টাইপ লিখুন, বা baseline সত্যিই বাড়াতে হলে justification সহ আপডেট করুন"
        )
        return 1
    if total < max_allowed:
        print(
            f"[any-budget] ✅ PASS: {total} < baseline {max_allowed} — baseline কমিয়ে {total} করুন (ratchet tighten)"
        )
        return 0
    print(f"[any-budget] ✅ PASS: count {total} == baseline {max_allowed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
