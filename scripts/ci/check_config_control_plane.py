#!/usr/bin/env python3
"""Fail only on structural violations of the canonical configuration contract."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.core.config_control_plane import BY_NAME, ALIAS_TO_CANONICAL  # noqa: E402

PATTERNS = (
    re.compile(r"os\.getenv\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\.get\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]"),
    re.compile(r"os\.environ\[\s*['\"]([A-Z][A-Z0-9_]*)['\"]\s*\]"),
    re.compile(r"process\.env\.([A-Z][A-Z0-9_]*)"),
    re.compile(r"import\.meta\.env\.([A-Z][A-Z0-9_]*)"),
)
SENSITIVE = re.compile(r"(KEY|SECRET|TOKEN|PASSWORD|PRIVATE|CREDENTIAL|AUTH)", re.I)
SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".pytest_cache"}
EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml"}


def scan() -> set[str]:
    found: set[str] = set()
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS or any(x in SKIP for x in p.parts):
            continue
        if p.name in {".env", ".env.example", "secrets_registry.yaml"}:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in PATTERNS:
            found.update(pattern.findall(text))
    return found


def main() -> int:
    failures = []
    for alias, canonical in ALIAS_TO_CANONICAL.items():
        if canonical not in BY_NAME:
            failures.append(f"alias {alias} -> missing canonical {canonical}")
        if alias in BY_NAME and alias != canonical:
            failures.append(f"alias {alias} is duplicated as canonical")

    used = scan()
    unknown_sensitive = sorted(k for k in used if k not in BY_NAME and k not in ALIAS_TO_CANONICAL and SENSITIVE.search(k))
    if unknown_sensitive:
        failures.extend(f"unclassified security-sensitive ENV reference: {k}" for k in unknown_sensitive)

    print(f"canonical keys: {len(BY_NAME)}")
    print(f"aliases: {len(ALIAS_TO_CANONICAL)}")
    print(f"scanned env references: {len(used)}")
    if failures:
        for failure in failures:
            print(f"::error::{failure}")
        print("FAIL: configuration control-plane contract violated")
        return 1
    print("PASS: configuration control-plane contract is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
