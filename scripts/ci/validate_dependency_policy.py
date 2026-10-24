#!/usr/bin/env python3
"""Enforce the repository's Poetry/Python dependency authority."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "backend" / "pyproject.toml"


def main() -> int:
    text = PYPROJECT.read_text(encoding="utf-8")
    errors: list[str] = []
    if "[tool.poetry]" not in text or "[build-system]" not in text:
        errors.append("backend/pyproject.toml must remain Poetry-based")
    match = re.search(r'^python\s*=\s*[\"\']\^([0-9]+\.[0-9]+)', text, re.MULTILINE)
    if not match or match.group(1) != "3.11":
        errors.append("Poetry Python constraint must remain ^3.11")
    if not (ROOT / "backend" / "poetry.lock").exists():
        errors.append("backend/poetry.lock is required")
    if (ROOT / "backend" / "uv.lock").exists():
        errors.append("backend/uv.lock is forbidden: Poetry is the sole dependency authority")
    if errors:
        print("DEPENDENCY POLICY: FAIL")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("DEPENDENCY POLICY: OK (Poetry, Python 3.11, poetry.lock)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
