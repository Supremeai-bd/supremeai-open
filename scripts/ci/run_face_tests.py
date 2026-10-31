#!/usr/bin/env python3
"""Face-runner: run a subset of pin tests outside the 9-tier verify ladder.

This is a lightweight exposure tool for tests that the structural verify ladder
does not execute. It never mutates state; exit code is non-zero on any failure.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FACE_TESTS = [
    "tests/test_loop_message_consistency.py",
    "tests/test_preflight_observability_audit.py",
    "tests/test_tower_tool_capability_gate.py",
    # বাংলা: প্যারিটি-জাত মুখ — "নতুন scripts/ci গার্ড পেয়ার ছাড়া ল্যান্ড" ক্লাস
    # দুই ঘণ্টায় তিনবার লাল করেছে (#4310 run_face_tests + collection ERROR,
    # #4311 line_budget_guard; heals: glm09 #4313/#4323)। এই মুখগুলো মেরুদণ্ডে
    # যুক্ত হলে প্রতি face-run-এই ক্লাস যান্ত্রিকভাবে ধরা পড়বে — সজাগতা নয়,
    # ব্যবস্থা দিয়ে বন্ধ (Invariant 6)। মুখগুলো hermetic (mocked subprocess) —
    # face-run রিকার্শন-মুক্ত।
    "tests/test_test_parity_guard.py",
    "tests/test_run_face_tests.py",
    "tests/test_line_budget_guard.py",
]


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", *FACE_TESTS]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
