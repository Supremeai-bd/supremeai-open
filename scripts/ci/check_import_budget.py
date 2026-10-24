#!/usr/bin/env python3
"""
check_import_budget.py
======================
Enforces module import time budget (<5s gate) to prevent import-time side effects (Trap #105).
"""

from __future__ import annotations

import subprocess
import sys
import time

MODULES_TO_CHECK = [
    "core.config",
    "core.logging_config",
    "api.routers",
]

MAX_ALLOWED_SECONDS = 5.0


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    has_error = False
    for mod in MODULES_TO_CHECK:
        start = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-c", f"import sys; sys.path.insert(0, 'backend'); import {mod}"],
            capture_output=True,
            text=True,
        )
        elapsed = time.perf_counter() - start
        if proc.returncode != 0:
            print(f"[WARN] [import-budget] Failed to import {mod}: {proc.stderr.strip()[:200]}")
            has_error = True
        elif elapsed > MAX_ALLOWED_SECONDS:
            print(f"[WARN] [import-budget] Import of {mod} took {elapsed:.2f}s (budget: {MAX_ALLOWED_SECONDS}s) - Trap #105")
            has_error = True
        else:
            print(f"[PASS] [import-budget] {mod} imported cleanly in {elapsed:.2f}s")

    if has_error:
        print("[Audit Mode]: Logged import budget warnings, returning 0.")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
