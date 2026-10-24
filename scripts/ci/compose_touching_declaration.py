#!/usr/bin/env python3
"""(#2464) 'Touching files:' ডিক্লিয়ারেশন কম্পোজার — atomic_claim.sh-এর জন্য।

সমস্যা (issue #2464): 101% test-policy অনুযায়ী প্রতিটি fix-PR নতুন/সংশোধিত
টেস্ট ফাইল আনে, কিন্তু claim-জেনারেশন সেগুলো 'Touching files:' ঘোষণায় রাখে
না — ফলে Scope Gate প্রতিটি PR-এ একটি বাড়তি BLOCK-চক্র খায় (লাইভ প্রমাণ:
PR #2461 — `tests/test_issue_ops_storm_guard.py` ঘোষণার বাইরে ছিল)।

Deterministic ফিক্স: FILES_DECLARATION সেট থাকলে এবং তাতে `tests` গাছ
(bare `tests`, `tests/`, `tests/**`) না থাকলে, ঘোষণার শেষে `tests/` অটো-যোগ
হয় — সাথে parse-safe অ্যানোটেশন:

  * Scope Gate-এর `parse_declared_files` harvest `(...)` স্ট্রিপ করে →
    টোকেন `tests/` অক্ষত থাকে (directory-declaration, subtree ম্যাচ)
  * গ্রুপ-বাউন্ড্রি (#2378) harvest প্রথম whitespace-টোকেন `tests/` নেয় →
    norm-এ `tests` — overlap_pair-এর (#2464) exemption সেটাকে ট্রি-টোকেন
    হিসেবে চেনে

খালি ঘোষণা → Rule 2 fallback (ইটালিক, আগের আচরণের byte-exact) — এক্ষেত্রে
অটো-ইনক্লুড হয় না, কারণ এজেন্ট ফলো-আপ কমেন্টে পুরো ঘোষণাই দেবে।

ব্যবহার: compose_touching_declaration.py --files "src/a.py, docs/b.md"
stdout: "src/a.py, docs/b.md, tests/ (auto: 101% test-policy, #2464)"
"""

from __future__ import annotations

import argparse
import re
import sys

# Rule 2 fallback — atomic_claim.sh-এর আগের ইনলাইন ডিফল্ট, byte-exact
FALLBACK_DECLARATION = "_(declared in a follow-up comment before PR — Rule 2)_"

# parse-safe অ্যানোটেশন — harvest-গুলো `(...)` স্ট্রিপ/উপেক্ষা করে
AUTO_ANNOTATION = " (auto: 101% test-policy, #2464)"


def norm_token(token: str) -> str:
    """'`tests/`' / 'tests/**' / ' tests ' → 'tests' (গাছ-রুট নরমালাইজেশন)।"""
    t = (token or "").strip().strip("`").strip("*").strip(",").strip()
    t = re.split(r"[\s(]", t, 1)[0] or ""
    t = t.removesuffix("/").removesuffix("/**")
    return t


def covers_tests_tree(declaration: str) -> bool:
    """ঘোষণায় `tests` গাছ (bare রুট) আছে কি না — নির্দিষ্ট টেস্ট-ফাইল গণনায় আসে না।"""
    for token in re.split(r"[,`\n]+", declaration or ""):
        if norm_token(token) == "tests":
            return True
    return False


def compose(declaration: str | None) -> str:
    """ফাইনাল 'Touching files:' লাইন-কনটেন্ট।

    খালি → FALLBACK; tests-গাছ আছে → byte-exact পাসথ্রু; না হলে
    `, tests/` + অ্যানোটেশন অ্যাপেন্ড।
    """
    decl = (declaration or "").strip()
    if not decl:
        return FALLBACK_DECLARATION
    if covers_tests_tree(decl):
        return decl
    return f"{decl}, tests/{AUTO_ANNOTATION}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", default="", help="FILES_DECLARATION (atomic_claim.sh --files)")
    args = parser.parse_args(argv)
    print(compose(args.files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
