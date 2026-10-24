#!/usr/bin/env python3
"""Reconcile secrets_registry.yaml against code-used environment keys (#1098).

The issue's acceptance criterion: "Registry and .env.example/code usage are
machine-reconciled in CI" — this script is that machine check.

What it does (read-only):
1. Scans backend/ + scripts/ + frontend/ for env keys read via os.environ[],
   os.getenv(), and settings fields backed by env (heuristic: UPPER_SNAKE
   tokens >= 8 chars with at least one underscore — excludes local helpers).
2. Loads secrets_registry.yaml and reports:
   - UNCLASSIFIED: security-sensitive code-used key absent from the registry
     (SENSITIVE heuristic: key name contains KEY|TOKEN|SECRET|PASSWORD|
     CREDENTIAL|DSN|SERVICE_ACCOUNT — those MUST have a registry row or an
     explicit --allow).
   - STALE: registry rows never referenced in code (informational; entries
     can be platform-only, e.g. Render dashboard vars).
3. Exit codes: 0 = clean; 1 = unclassified sensitive keys found (strict mode,
   --strict); 2 = usage/registry errors. Default is report-only so the first
   run doesn't break CI — flip the CI step to --strict once the ledger is at
   zero (tracked in #1098).

Usage:
    python3 scripts/ci/reconcile_secrets_registry.py [--strict] [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY = REPO_ROOT / "secrets_registry.yaml"

# Security-sensitive key-name heuristics.
SENSITIVE_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|DSN|SERVICE_ACCOUNT|API_KEY)", re.I
)
# Candidate env keys: UPPER_SNAKE, reasonably long, has a separator or suffix.
CANDIDATE_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")
MIN_LEN = 6

# Noise: test fixtures, example placeholders, well-known non-secret config.
NOISE_EXACT = {
    "GITHUB_STEP_SUMMARY", "GITHUB_OUTPUT", "GITHUB_ACTIONS", "GITHUB_REF",
    "GITHUB_SHA", "GITHUB_TOKEN", "RUNNER_TEMP", "CI", "PATH", "HOME",
    "PYTHONPATH", "NODE_ENV", "NODE_OPTIONS", "PORT", "HOST", "ENV",
    "TZ", "LANG", "LC_ALL", "TMPDIR", "DATABASE_URL_POOLER",
}
NOISE_SUBSTR = ("EXAMPLE", "PLACEHOLDER", "_TEMPLATE", "DUMMY", "MOCK_", "TEST_ONLY")

SCAN_ROOTS = ["backend", "scripts", "frontend/src", "infrastructure"]
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".yaml", ".yml"}
SKIP_DIRS = {
    "node_modules", ".venv", ".venv-audit", ".venv_ci", "__pycache__", "dist",
    "build", ".git", "coverage", "htmlcov", "audit_reports", "reports",
    "ci-reports",
}
# also skip any dot-venv* variant
def _keep_dir(d: str) -> bool:
    return d not in SKIP_DIRS and not d.startswith(".venv")


def discover_code_used_keys() -> dict[str, list[str]]:
    """Return {key: [files]} for env keys referenced in code."""
    found: dict[str, list[str]] = {}
    for root in SCAN_ROOTS:
        base = REPO_ROOT / root
        if not base.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if _keep_dir(d)]
            for fn in filenames:
                if Path(fn).suffix not in SCAN_SUFFIXES:
                    continue
                p = Path(dirpath) / fn
                try:
                    text = p.read_text(errors="replace")
                except OSError:
                    continue
                # Only trust explicit read sites (not arbitrary prose):
                for m in re.finditer(
                    r"os\.environ(?:\.get)?\(\s*['\"]([A-Z0-9_]+)['\"]|"
                    r"os\.getenv\(\s*['\"]([A-Z0-9_]+)['\"]|"
                    r"import\.meta\.env\.([A-Z0-9_]+)",
                    text,
                ):
                    key = next(g for g in m.groups() if g)
                    found.setdefault(key, []).append(str(p.relative_to(REPO_ROOT)))
    return found


def load_registry_names() -> set[str]:
    if not REGISTRY.exists():
        raise SystemExit(f"registry missing: {REGISTRY}")
    try:
        import yaml
    except ImportError:
        # stdlib fallback: minimal parse of "- name: X" rows
        names = set()
        for line in REGISTRY.read_text().splitlines():
            m = re.match(r"-\s*name:\s*([A-Z0-9_]+)\s*$", line.strip())
            if m:
                names.add(m.group(1))
        return names
    data = yaml.safe_load(REGISTRY.read_text())
    return {row.get("name") for row in data.get("keys", []) if row.get("name")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when sensitive code-used keys lack registry rows")
    ap.add_argument("--json", dest="json_out", metavar="FILE",
                    help="also write the report as JSON")
    args = ap.parse_args()

    used = discover_code_used_keys()
    registered = load_registry_names()

    unclassified_sensitive: dict[str, list[str]] = {}
    for key, files in sorted(used.items()):
        if key in registered or key in NOISE_EXACT or len(key) < MIN_LEN:
            continue
        if any(s in key for s in NOISE_SUBSTR):
            continue
        if SENSITIVE_RE.search(key):
            unclassified_sensitive[key] = sorted(set(files))[:5]

    stale = sorted(
        k for k in registered
        if k not in used
        and not k.startswith(("GITHUB_", "AWS_", "RENDER_API_KEY"))
    )

    print(f"code-used env keys: {len(used)}; registry rows: {len(registered)}")
    print(f"unclassified SENSITIVE keys: {len(unclassified_sensitive)}")
    for key, files in list(unclassified_sensitive.items())[:20]:
        print(f"  UNCLASSIFIED {key}  (e.g. {files[0]})")
    print(f"registry rows not seen in code (informational, platform-only allowed): {len(stale)}")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps({
            "generated_by": "scripts/ci/reconcile_secrets_registry.py",
            "code_used_count": len(used),
            "registry_count": len(registered),
            "unclassified_sensitive": unclassified_sensitive,
            "stale_informational": stale,
        }, indent=2))

    if args.strict and unclassified_sensitive:
        print("::error::security-sensitive env keys are not classified in secrets_registry.yaml — add rows or explicit exceptions (#1098).")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
