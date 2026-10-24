#!/usr/bin/env python3
"""#2893 — Cross-tier full-suite ratchet gate (PR Gate-এর full-backend-suite job-এর সিদ্ধান্ত-মস্তিষ্ক)।

চুক্তি (knip-baseline র্যাচেট-মতবাদ অনুসরণ — pr.yml-এর Frontend dead-code ratchet প্যাটার্ন):
- backend/full-suite-baseline.txt = main-এর known-red স্ন্যাপশট (২০২৬-১০-০২, HEAD 2fe47d42
  বেসলাইন রানে প্রমাণিত: ১৭ failed + ২ collection-error, ~৮,৪০০ টেস্ট অন্যথায় সবুজ)।
- baseline-এর ভেতরে ফেইল → PASS (স্বীকৃত ঋণ; আলাদা ইস্যুতে নামবে)
- baseline-এর বাইরে নতুন ফেইল → BLOCK — নতুন stale assertion লাল main-এ যাবে না
  (issue #2893-এর মূল উদ্দেশ্য: "merge → red → fix" চক্র বন্ধ)।
- baseline-ভুক্ত অথচ আর ফেইল করছে না → advisory WARNING (র্যাচেট-নামার সুযোগ; ব্লক নয় —
  কারণ এটি অগ্রগতি, শাস্তি নয়)।

fail-closed নীতি (কোনো silent-swallow নয়):
- pytest rc {0,1}-এর বাইরে (2=usage, 3=internal, 4=file-not-found, 5=no-collected) → BLOCK
- rc=1 অথচ শূন্য ফেইল-লাইন (পার্স-অসঙ্গতি) → BLOCK
- rc=0 অথচ FAILED লাইন উপস্থিত (out/RC বিচ্ছিন্নতা) → BLOCK
- output ফাইল অনুপস্থিত/অপাঠযোগ্য → BLOCK

পার্সিং চুক্তি: কেবল pytest short-summary লাইন — `FAILED <node-id>[ - msg]` /
`ERROR <node-id>` (ঠিক একটি স্পেস + node-id `tests/` প্রিফিক্সড)। caplog-এর
`ERROR    logger:...` স্টাইল নয়েজ-লাইন (multi-space / non-tests টোকেন) বাদ —
false-positive র্যাচেট-ব্লক আটকায়।

I/O subprocess (pytest) এই গেটের ভেতরে চলে না — job নিজে pytest চালিয়ে output ফাইল +
rc এখানে দেয়; তাই স্যান্ডবক্সে pytest ছাড়াই চুক্তি টেস্টযোগ্য (main(argv)-injectable)।
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# short-summary লাইন: `FAILED tests/... - msg` বা `ERROR tests/...` (ঠিক ১ স্পেস)।
_SUMMARY_LINE_RE = re.compile(r"^(?:FAILED|ERROR) (tests/\S+)(?: - .*)?$")

_ANALYZABLE_RCS = {0, 1}


def parse_failure_node_ids(text: str) -> set[str]:
    """pytest আউটপুট টেক্সট থেকে short-summary ফেইল/এরর node-id সেট বের করে।"""
    failures: set[str] = set()
    for raw in text.splitlines():
        m = _SUMMARY_LINE_RE.match(raw.strip())
        if m:
            failures.add(m.group(1))
    return failures


def load_baseline(path: Path) -> set[str]:
    """baseline JSON পড়ে ("known_red" অ্যারে) — ফাইল না থাকলে শূন্য সেট (ঋণহীন ভবিষ্যৎ);
    ভাঙা JSON / ফরম্যাট-অসঙ্গতিতে ValueError — main() এটাকে fail-closed BLOCK-এ নেবে।"""
    if not path.is_file():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("known_red"), list):
        raise ValueError("baseline-এ {known_red: [...]} অবজেক্ট প্রত্যাশিত")
    entries: set[str] = set()
    for entry in data["known_red"]:
        line = str(entry).strip()
        if not line or line.startswith("#"):
            continue
        entries.add(line)
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="#2893 full-suite ratchet gate — baseline-এর বাইরে নতুন ফেইলে PR block।"
    )
    parser.add_argument("output_file", help="pytest-এর পূর্ণ stdout/stderr ক্যাপচার ফাইল")
    parser.add_argument(
        "--pytest-rc",
        type=int,
        required=True,
        help="pytest প্রসেসের exit code (job থেকে সরাসরি)",
    )
    parser.add_argument(
        "--baseline",
        default="full-suite-baseline.json",
        help="known-red স্ন্যাপশট (ডিফল্ট: backend/full-suite-baseline.json, backend cwd থেকে)",
    )
    args = parser.parse_args(argv)

    out_path = Path(args.output_file)
    if not out_path.is_file():
        print("❌ র্যাচেট গেট: output ফাইল অনুপস্থিত — fail-closed (infra অসঙ্গতি)।")
        print(f"   প্রত্যাশিত ফাইল: {out_path}")
        return 1

    if args.pytest_rc not in _ANALYZABLE_RCS:
        print("❌ র্যাচেট গেট: pytest rc=" + str(args.pytest_rc) + " — suite চলেইনি/infra ব্যর্থতা, fail-closed।")
        print("   (rc 2=usage, 3=internal, 4=file-not-found, 5=no-collected — কোনোটাই ফেইল-সেট বিশ্লেষণযোগ্য নয়।)")
        return 1

    output_text = out_path.read_text(encoding="utf-8", errors="replace")
    failures = parse_failure_node_ids(output_text)

    if args.pytest_rc == 1 and not failures:
        print("❌ র্যাচেট গেট: rc=1 অথচ শূন্য ফেইল-লাইন — পার্স-অসঙ্গতি, fail-closed।")
        return 1
    if args.pytest_rc == 0 and failures:
        print("❌ র্যাচেট গেট: rc=0 অথচ FAILED লাইন উপস্থিত — out/RC অসঙ্গতি, fail-closed।")
        for node in sorted(failures):
            print(f"   {node}")
        return 1

    try:
        baseline = load_baseline(Path(args.baseline))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("❌ র্যাচেট গেট: baseline অপাঠযোগ্য/ভাঙা — fail-closed (অসঙ্গতিতে ব্লক নীতি)।")
        print(f"   কারণ: {exc}")
        return 1
    known = failures & baseline
    new = failures - baseline
    stale = baseline - failures

    if new:
        print(
            f"❌ র্যাচেট গেট (#2893): baseline-এর বাইরে {len(new)}টি নতুন ফেইল — PR BLOCK।"
        )
        print("   নতুন stale assertion লাল main-এ merge হবে না — এই PR-এই ঠিক করুন:")
        for node in sorted(new):
            print(f"   {node}")
        return 1

    if stale:
        print(
            f"⚠️ WARNING: baseline-ভুক্ত {len(stale)}টি এন্ট্রি এখন আর ফেইল করে না —"
            " র্যাচেট-নামার সুযোগ (advisory, ব্লক নয়):"
        )
        for node in sorted(stale):
            print(f"   {node}")
        print("   full-suite-baseline.json থেকে এগুলো সরিয়ে ঋণ কমান।")

    if args.pytest_rc == 0:
        print("✅ র্যাচেট গেট: পূর্ণ suite সবুজ — কোনো ফেইল নেই।")
    else:
        print(
            f"✅ র্যাচেট গেট: {len(known)}টি ফেইল সবই known-red baseline-ভুক্ত "
            "(নতুন ফেইল নেই) — PASS।"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
