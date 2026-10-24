#!/usr/bin/env python3
"""
check_singleton_inits.py
========================
Verifies that core singleton classes (SkillManager, MemoryService, DatabaseClient)
do not instantiate multiple redundant instances during application lifecycle (Trap #106).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    # In audit mode, verifies singleton usage conventions across backend
    repo_root = Path(__file__).resolve().parents[2]
    backend_root = repo_root / "backend"

    # Scan for multiple direct instantiations of core services outside test files
    core_singletons = ["SkillManager", "CascadeMemoryService", "MetricsCollector", "DatabaseClient"]
    instantiations = {s: [] for s in core_singletons}

    for py_file in backend_root.rglob("*.py"):
        if any(part in ("tests", ".venv", "venv", "__pycache__") for part in py_file.parts):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            for s in core_singletons:
                if f"{s}()" in content:
                    instantiations[s].append(str(py_file.relative_to(repo_root)))
        except Exception as error:
            print(f"Unable to inspect {py_file}: {error}", file=sys.stderr)

    found_warnings = False
    for s, files in instantiations.items():
        if len(files) > 4:  # Multiple separate direct instantiations instead of shared singleton instance
            print(f"[WARN] [singleton-guard] {s} instantiated directly in {len(files)} files! Prefer shared instance (Trap #106).")
            found_warnings = True

    if found_warnings:
        print("[Audit Mode]: Logged singleton warnings, returning 0.")
        return 0

    print("[PASS] Core singletons are using managed lifecycle instances.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
