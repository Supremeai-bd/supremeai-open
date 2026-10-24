r"""SupremeAI Toolkit — Plan Guard: duplicate-plan scanner (#2403, seq:2 absorb).

# বাংলা মন্তব্য: `scripts/scan_duplicate_plans.py`-এর ক্যাপাবিলিটি-উত্তরাধিকার।
# মূল স্ক্রিপ্ট MODULE_21 (crown-jewel গভর্নেন্স ডক)-এ সক্রিয়-সনাক্তকারী হিসেবে
# উল্লিখিত, কিন্তু `f:\supremeai` Windows-হার্ডকোডে অচল ছিল। seq:2-তে Golden Rule
# অনুযায়ী ক্যাপাবিলিটিটি হারানো যায় না — তাই এই পোর্টেবল পুনঃসৃষ্টি:
#   - রিপো-আপেক্ষিক ডিফল্ট রুট (docs/plans) — যেকোনো মেশিনে চলে
#   - MD5 hash-অভিন্ন duplicate গ্রুপ (মূল লজিক অক্ষুণ্ণ)
#   - basename-similarity > 0.70, নইলে header-similarity > 0.80 (মূল থ্রেশহোল্ড)
#   - stdout সারসংক্ষেপ; --out-json/--out-txt দিলে ফাইল-রিপোর্ট
# read-only স্ক্যানার — কোনো ফাইল লেখে/সরায় না।
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# বাংলা মন্তব্য: মূল লজিকের থ্রেশহোল্ড — অক্ষরে অক্ষরে সংরক্ষিত (behavior preserved)。
NAME_RATIO_THRESHOLD = 0.70
HEADER_RATIO_THRESHOLD = 0.80
SIMILAR_CAP = 200  # বাংলা মন্তব্য: O(N²) জোড়া-ক্যাপ — বিশাল রুটেও স্ক্যানার থামে না।


def collect_plans(root: Path) -> list[dict]:
    """রুটের সব .md (README.md বাদ) — মূল স্ক্যানারের সংগ্রহ-লজিক।"""
    file_data: list[dict] = []
    for root_dir, _dirs, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".md") or f == "README.md":
                continue
            fp = Path(root_dir) / f
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
            except OSError as err:  # বাংলা মন্তব্য: অপঠনযোগ্য ফাইল স্ক্যান থামায় না।
                print(f"[WARN] পড়া গেল না {fp}: {err}", file=sys.stderr)
                continue
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            file_data.append(
                {
                    "path": str(fp),
                    "rel": str(fp.relative_to(root)),
                    "size": len(text),
                    "header": lines[0] if lines else "",
                    "hash": hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest(),
                }
            )
    return file_data


def find_duplicates(file_data: list[dict]) -> list[tuple[str, str]]:
    """MD5-অভিন্ন জোড়া — মূল লজিক।"""
    seen: dict[str, str] = {}
    dups: list[tuple[str, str]] = []
    for fd in file_data:
        h = fd["hash"]
        if h in seen:
            dups.append((seen[h], fd["rel"]))
        else:
            seen[h] = fd["rel"]
    return dups


def find_similar(file_data: list[dict]) -> list[tuple[str, str, str]]:
    """নাম/হেডার similarity-জোড়া — মূল থ্রেশহোল্ড (0.70 / 0.80)।"""
    pairs: list[tuple[str, str, str]] = []
    n = len(file_data)
    for i in range(n):
        for j in range(i + 1, n):
            if len(pairs) >= SIMILAR_CAP:
                return pairs
            f1, f2 = file_data[i], file_data[j]
            ratio = SequenceMatcher(None, os.path.basename(f1["path"]).lower(), os.path.basename(f2["path"]).lower()).ratio()
            if ratio > NAME_RATIO_THRESHOLD:
                pairs.append((f1["rel"], f2["rel"], f"Name ratio: {ratio:.2f}"))
                continue
            h_ratio = SequenceMatcher(None, f1["header"], f2["header"]).ratio()
            if h_ratio > HEADER_RATIO_THRESHOLD and f1["header"] and f2["header"]:
                pairs.append((f1["rel"], f2["rel"], f"Header ratio: {h_ratio:.2f}"))
    return pairs


def run_scan(root: Path, out_json: Path | None = None, out_txt: Path | None = None) -> tuple[int, int, str]:
    """স্ক্যান চালায় — (ফাইল-সংখ্যা, সমস্যা-সংখ্যা, সারসংক্ষেপ)।"""
    file_data = collect_plans(root)
    dups = find_duplicates(file_data)
    similar = find_similar(file_data)
    problems = len(dups) + len(similar)

    summary = (
        f"[OK] plan-guard: {len(file_data)} plan-scanned, "
        f"{len(dups)} exact-duplicate, {len(similar)} similar-pair (root: {root})"
    )

    if out_txt:
        out_txt.parent.mkdir(parents=True, exist_ok=True)
        out_txt.write_text(_render_txt(root, file_data, dups, similar), encoding="utf-8")
    if out_json:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).isoformat(),
                    "root": str(root),
                    "scanned": len(file_data),
                    "exact_duplicates": [{"keep": a, "dup": b} for a, b in dups],
                    "similar_pairs": [{"a": a, "b": b, "reason": r} for a, b, r in similar],
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return len(file_data), problems, summary


def _render_txt(root: Path, file_data: list[dict], dups: list, similar: list) -> str:
    lines = [
        "=== PLAN GUARD — DUPLICATE AUDIT ===",
        f"root: {root} · scanned: {len(file_data)} · generated: {datetime.now(UTC).isoformat()}",
        "",
        "=== EXACT DUPLICATES ===",
    ]
    lines += [f"{a} <===> {b}" for a, b in dups] or ["(none)"]
    lines += ["", "=== SIMILAR PAIRS ==="]
    lines += [f"{a} <===> {b} ({r})" for a, b, r in similar] or ["(none)"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plan_guard",
        description="Duplicate-plan scanner (scan_duplicate_plans.py-এর পোর্টেবল উত্তরাধিকার, #2403 seq:2)",
    )
    parser.add_argument("--root", default=str(REPO_ROOT / "docs" / "plans"), help="স্ক্যান-রুট (ডিফল্ট: docs/plans)")
    parser.add_argument("--out-json", dest="out_json", default=None, help="JSON রিপোর্ট পাথ")
    parser.add_argument("--out-txt", dest="out_txt", default=None, help="TXT রিপোর্ট পাথ")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"রুট ডিরেক্টরি নেই: {root}")
    scanned, problems, summary = run_scan(root, Path(args.out_json) if args.out_json else None, Path(args.out_txt) if args.out_txt else None)
    print(summary)
    # বাংলা মন্তব্য: exit-code = সমস্যা-সংখ্যা ক্ল্যাম্প — CI গেটে ব্যবহারযোগ্য।
    return 0 if problems == 0 else min(problems, 2)


if __name__ == "__main__":
    raise SystemExit(main())
