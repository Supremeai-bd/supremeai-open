#!/usr/bin/env python3
"""Pre-commit secret-pattern scanner for the browser runtime (WO #1361).

Flags log/print calls that interpolate secret-bearing variables
(OTP / TOTP codes, tokens, passwords, API keys, credentials) via
f-string interpolation. Exit 1 blocks the commit.

Escapes: lines carrying an explicit [REDACTED_*] marker are ignored,
so the canonical redaction pattern introduced in auto_login.py passes.
Limitation (documented): pattern-based; covers f-string interpolation,
not .format()/% formatting or variable re-aliasing.
"""
import re
import sys
from pathlib import Path

SECRET_VAR = (
    r"(current_otp|otp_code|totp_secret|totp_code|password|passwd|pwd"
    r"|api_key|apikey|access_token|refresh_token|auth_token|secret|credential)"
)
LOG_INTERP = re.compile(
    r"(?:logger|logging|console|print)\w*(?:\.\w+)*\s*\("
    r"[^)]*\{\s*" + SECRET_VAR + r"\w*\s*\}",
    re.IGNORECASE,
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"}
REDACTED = re.compile(r"\[REDACTED", re.IGNORECASE)


def scan_repo(root: Path):
    hits = []
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if REDACTED.search(line):
                continue
            m = LOG_INTERP.search(line)
            if m:
                hits.append(f"{p.relative_to(root)}:{i}: {line.strip()[:120]}")
    return hits


def main():
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    hits = scan_repo(root)
    if hits:
        print("SECRET-LOG SCAN FAILED — plaintext secret interpolation in log calls:")
        for h in hits:
            print("  " + h)
        return 1
    print("secret-log scan: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
