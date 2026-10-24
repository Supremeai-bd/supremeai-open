#!/usr/bin/env python3
"""Check CI failures — #2928 থেকে single-funnel thin wrapper.

# বাংলা মন্তব্য: আগের সংস্করণের ৩টি মারাত্মক বাগ ছিল —
#   ১) GITHUB_TOKEN পড়ত কিন্তু workflow GH_TOKEN দেয় → খালি token → 401 → issue কখনোই জন্মাত না
#   ২) শুধু main-branch স্ক্যান → PR-branch ব্যর্থতা (যেমন PR #2926) চিরকাল অদৃশ্য
#   ৩) প্রতি-ব্যর্থতায় ছড়ানো issue → কোনো গ্রুপিং নেই
# এখন সব লজিক `pipeline_failure_register.py`-এ (একক-ফানেল) — এই ফাইল শুধু
# পুরনো কল-সাইটের (continuous_agent_loop-এর scheduled ci_failure_check)
# সামঞ্জস্যের জন্য দাঁড়িয়ে আছে।
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pipeline_failure_register as pfr  # noqa: E402


def main() -> int:
    # বাংলা মন্তব্য: --dry-run পাস-থ্রু; exit-0 = বুককিপিং সফল (ব্যর্থতা-নিজেই নয়)।
    dry_run = "--dry-run" in sys.argv
    summary = pfr.scan(dry_run=dry_run)
    print(f"✅ register updated: {summary.get('register')} "
          f"(active={summary.get('active')}, healed={summary.get('healed')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
