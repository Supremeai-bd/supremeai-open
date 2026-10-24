#!/usr/bin/env python3
"""Bengali/Banglish Mandate Check — AGENTS.md Hard Rule 4.

বাংলা মন্তব্য: PR description-এ অন্তত ১টি বাংলা ইউনিকোড ক্যারেক্টার থাকতে হবে।
Bengali Unicode range: U+0980–U+09FF.

Exit codes: 0 = pass, 1 = fail (advisory — WARNING, not BLOCK).
"""
import re
import sys

BENGALI_PATTERN = re.compile(r"[\u0980-\u09FF]")

def check_bengali(text: str) -> tuple[bool, str]:
    """Check if text contains at least one Bengali Unicode character."""
    if BENGALI_PATTERN.search(text):
        return True, "বাংলা ক্যারেক্টার পাওয়া গেছে ✅"
    return False, "⚠️ PR description-এ কোনো বাংলা ক্যারেক্টার নেই — Hard Rule 4 অনুযায়ী বাংলা/বাংলিশ বাধ্যতামূলক"

if __name__ == "__main__":
    pr_body = sys.argv[1] if len(sys.argv) > 1 else ""
    ok, msg = check_bengali(pr_body)
    if ok:
        print(f"✅ Bengali check: {msg}")
        sys.exit(0)
    else:
        print(f"::warning::{msg}")
        sys.exit(0)  # advisory — warning only, not blocking
