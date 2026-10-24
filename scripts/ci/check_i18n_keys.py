#!/usr/bin/env python3
"""i18n key-gap checker (warn-only report).

বাংলা মন্তব্য: `frontend/src/i18n/translations.ts`-এ সংজ্ঞাত key-গুলোর সাথে
কোডে `t('...')` ব্যবহৃত key-গুলো মিলিয়ে দেখে — কোডে ব্যবহৃত কিন্তু অসংজ্ঞায়িত
key-এর তালিকা দেয় (ইউজার raw key দেখছে = UX ফাঁক)। এটি **warn-only**: ফাঁক
থাকলেও exit 0 — CI ভাঙে না, অথচ ফাঁক অদৃশ্য থাকে না (সাপ্তাহিক hygiene issue-তে
স্বয়ংক্রিয়ভাবে যুক্ত হয়)। ভাঙা UI-র ঝুঁকি ছাড়াই দৃশ্যমানতা।
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LEAF_RE = re.compile(r"^\s{2,}([A-Za-z0-9_]+)\s*:\s*['\"`{]")
SECTION_RE = re.compile(r"^\s{2}([A-Za-z0-9_]+)\s*:\s*\{")
USE_RE = re.compile(r"\bt\(\s*['\"`]([A-Za-z0-9_.\-]+)['\"`]")


def parse_defined_keys(translations_path: Path) -> set[str]:
    """বাংলা: nested object-এর leaf key-গুলো dotted path হিসেবে সংগ্রহ (lightweight parser)।"""
    defined: set[str] = set()
    stack: list[str] = []
    try:
        lines = translations_path.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines()
    except OSError as exc:
        print(f"[i18n-check] translations unreadable: {exc}", file=sys.stderr)
        return defined
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*")):
            continue
        section = SECTION_RE.match(line)
        if section:
            stack.append(section.group(1))
            continue
        leaf = LEAF_RE.match(line)
        if leaf and stack:
            defined.add(f"{'.'.join(stack)}.{leaf.group(1)}")
        if stripped in ("},", "}") and stack:
            stack.pop()
    return defined


def collect_used_keys(src_dir: Path) -> set[str]:
    used: set[str] = set()
    for path in src_dir.rglob("*"):
        if not path.is_file() or path.suffix not in (".ts", ".tsx"):
            continue
        if "i18n" in path.parts:
            continue
        try:
            used.update(
                USE_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))
            )
        except OSError:
            continue
    return used


def main() -> int:
    parser = argparse.ArgumentParser(description="i18n key-gap warn-only report")
    parser.add_argument("--translations", default="frontend/src/i18n/translations.ts")
    parser.add_argument("--src", default="frontend/src")
    parser.add_argument("--output-json", default="")
    args = parser.parse_args()

    t_path = Path(args.translations)
    src = Path(args.src)
    if not t_path.is_file() or not src.is_dir():
        print(
            f"[i18n-check] inputs missing ({t_path}, {src}) — report skipped honestly",
            file=sys.stderr,
        )
        return 0

    defined = parse_defined_keys(t_path)
    used = collect_used_keys(src)
    # বাংলা: t('appName') আসলে en/bn সেকশনের নিচের key-কে ডাকে — তাই used key-টি
    # defined-এর কোনো না কোনো suffix হলেই defined ধরা হয় (dotted prefix সমস্যা এড়াতে)
    defined_suffixes = {d.split(".", 1)[-1] for d in defined} | defined
    missing = sorted(k for k in used if k not in defined_suffixes)
    unused = sorted(k for k in defined if k not in used)

    print(
        f"[i18n-check] defined={len(defined)} used={len(used)} used-but-missing={len(missing)} defined-but-unused={len(unused)}"
    )
    if missing:
        print(
            "[i18n-check] কোডে ব্যবহৃত কিন্তু translations.ts-এ নেই (ইউজার raw key দেখতে পায়):"
        )
        for key in missing[:20]:
            print(f"  - {key}")
        if len(missing) > 20:
            print(f"  … আরও {len(missing) - 20}টি")
    if unused:
        print(
            f"[i18n-check] (তথ্য) সংজ্ঞাত কিন্তু অব্যবহৃত: {len(unused)}টি — dead-translation candidate"
        )
    # warn-only: কখনো exit non-zero নয় — ভাঙার ঝুঁকি শূন্য
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "defined": len(defined),
                    "used": len(used),
                    "missing": missing,
                    "unused_count": len(unused),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"[i18n-check] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
