#!/usr/bin/env python3
"""Delegation shim for migration_safety_diff.

This file delegates to scripts/advanced_analysis/migration_safety_diff.py
to eliminate code duplication while preserving full backwards compatibility.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

_TARGET_SCRIPT = (
    Path(__file__).resolve().parent.parent / "advanced_analysis" / "migration_safety_diff.py"
)

if __name__ == "__main__":
    runpy.run_path(str(_TARGET_SCRIPT), run_name="__main__")
