#!/usr/bin/env python3
"""Pre-commit secret-pattern scanner for the browser runtime (WO #1361).

Flags log/print calls that interpolate secret-bearing variables
(OTP / TOTP codes, tokens, passwords, API keys, credentials) via
f-string interpolation. Exit 1 blocks the commit.

Escapes: lines carrying an explicit [REDACTED_*] marker are ignored,
so the canonical redaction pattern introduced in auto_login.py passes.
Identifier-suffix escape: `{secret_id}` / `{secret_name(s)}` interpolate
the secret's lookup key, never its value, so they are ignored too —
the value-bearing neighbors (`{secret}`, `{secret_value}`) still fail.
Fixture-file escape: a file declaring `no-secret-logs: fixture-file`
within its first 2 KB is skipped entirely — test faces MUST quote
detection vectors as string data, and that is author-attested data,
not a live leak (ecosystem convention: `# noqa`, `# gitleaks:allow`).
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
# Negative lookahead: reject the match when the interpolated token is the
# secret's *identifier* (lookup key: secret_id / secret_name / plurals),
# not its value. Without it the fail-closed gate stays permanently red on
# its own tree (18 identifier-only call-sites in secret_vault.py and
# scripts/ops/security/*).
IDENT_SUFFIX_BLOCK = r"(?!" + SECRET_VAR + r"(?:_ids?|_names?)\b)"
LOG_INTERP = re.compile(
    r"(?:logger|logging|console|print)\w*(?:\.\w+)*\s*\("
    r"[^)]*\{\s*" + IDENT_SUFFIX_BLOCK + SECRET_VAR + r"\w*\s*\}",
    re.IGNORECASE,
)
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".mypy_cache"}
REDACTED = re.compile(r"\[REDACTED", re.IGNORECASE)
FIXTURE_MARKER = "no-secret-logs: fixture-file"
HEAD_WINDOW = 2048  # declaration must live near the top of the file


def scan_repo(root: Path):
    hits = []
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if FIXTURE_MARKER in text[:HEAD_WINDOW]:
            continue
        lines = text.splitlines()
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
