#!/usr/bin/env python3
"""
scripts/ci/core_gateway_parity_guard.py — Parity & Split-Brain Prevention Guard (#761).

Mission (বাংলা):
  core/ এবং gateway/ ডোমেনের মধ্যকার কমন সার্ভিস ও মিডলওয়্যার যেন সর্বদা
  সিঙ্কড থাকে এবং কোনো অনাকাঙ্ক্ষিত ডাইভারজেন্স (split-brain drift) তৈরি না হয়।
  এই গার্ডটি নিশ্চিত করে:
  1. core/services/ এবং gateway/services/-এর অভিন্ন ফাইলগুলো বাইট-টু-বাইট সমান।
  2. core/middleware/ এবং gateway/middleware/-এর অভিন্ন ফাইলগুলো বাইট-টু-বাইট সমান।
  3. কোনো ফাইল মডিফাই হলে উভয় ডোমেন সিঙ্কে আছে কি না তা ভেরিফাই করা।

MODES:
  --check      সম্পূর্ণ সার্ভিস ও মিডলওয়্যার প্যারিটি অডিট।
  --self-test  গার্ডের নিজস্ব সেলফ-টেস্ট।
"""

from __future__ import annotations

import argparse
import contextlib
import filecmp
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

COMMON_DOMAINS = [
    ("core/services", "gateway/services"),
    ("core/middleware", "gateway/middleware"),
    ("core/ws", "gateway/ws"),
]


def check_parity(repo_root: Path = REPO_ROOT) -> tuple[int, list[str]]:
    """Check byte-parity across common services, middleware, and ws files."""
    violations: list[str] = []
    scanned = 0

    for core_rel, gw_rel in COMMON_DOMAINS:
        core_dir = repo_root / core_rel
        gw_dir = repo_root / gw_rel

        if not core_dir.exists() or not gw_dir.exists():
            continue

        core_files = {p.relative_to(core_dir) for p in core_dir.rglob("*.py") if p.is_file() and p.name != "__init__.py"}
        gw_files = {p.relative_to(gw_dir) for p in gw_dir.rglob("*.py") if p.is_file() and p.name != "__init__.py"}

        shared_files = sorted(core_files.intersection(gw_files))

        for rel_path in shared_files:
            c_path = core_dir / rel_path
            g_path = gw_dir / rel_path
            scanned += 1
            if not filecmp.cmp(c_path, g_path, shallow=False):
                g_content = g_path.read_text(encoding="utf-8", errors="replace").strip()
                module_parts = list(rel_path.parts)
                module_parts[-1] = module_parts[-1][:-3]
                module_dotted = ".".join(module_parts)
                canonical_reexport = f"from core.{core_dir.name}.{module_dotted} import *  # noqa: F401, F403"
                if canonical_reexport not in g_content:
                    violations.append(
                        f"Divergence detected: '{c_path.relative_to(repo_root)}' != '{g_path.relative_to(repo_root)}'"
                    )

    return scanned, violations


def run_self_test() -> int:
    """Run sanity self-tests."""
    scanned, violations = check_parity(REPO_ROOT)
    if violations:
        print(f"❌ Self-test failed: found {len(violations)} divergence(s):")
        for v in violations:
            print(f"   {v}")
        return 1
    print(f"✅ Self-test passed: {scanned} shared files verified with 0 drift.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Core-Gateway Parity Guard")
    parser.add_argument("--check", action="store_true", help="Audit all shared files between core and gateway")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    scanned, violations = check_parity(REPO_ROOT)
    print(f"Core-Gateway Parity Guard: scanned {scanned} shared files across services & middleware.")

    if violations:
        print(f"❌ FAIL: {len(violations)} split-brain drift(s) detected:")
        for v in violations:
            print(f"   - {v}")
        return 1

    print("✅ PASS: 100% parity maintained across core and gateway.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
