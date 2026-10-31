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
]


def main() -> int:
    cmd = [sys.executable, "-m", "pytest", "-q", *FACE_TESTS]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
