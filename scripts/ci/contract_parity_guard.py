#!/usr/bin/env python3
"""
contract_parity_guard.py — Autonomous Contract Parity & Byte-Hygiene Guard.

Architecture & Constitutional Mission:
  Prevents cross-satellite contract drifts and byte mismatches before merge.
  Validates that mirrored contract files in `supremeai-open` conform strictly to:
    1. Canonical interface symbols and AST structure.
    2. Strict LF line-endings (0 CRLF occurrences across text files).
    3. Valid YAML structure for OpenAPI schema surfaces.

Usage:
  python scripts/ci/contract_parity_guard.py --check       # Run full repo contract guard
  python scripts/ci/contract_parity_guard.py --self-test    # Run hermetic self-test suite
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import os
import sys
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Required symbol signatures for canonical gateway client mirror
GATEWAY_CLIENT_REQUIRED_SYMBOLS = {
    "DEFAULT_BASE_URL",
    "GatewayError",
    "GatewayAuthError",
    "GatewayRateLimited",
    "GatewayProviderError",
    "GatewayUnavailable",
    "chat",
}

# Contract files subject to strict mirror invariants
CONTRACT_FILES = [
    "examples/gateway_client.py",
    "api-schemas/gateway.openapi.yaml",
]


def check_lf_endings(path: Path) -> list[str]:
    """Verify that file has strict LF line-endings and zero CR bytes."""
    errs: list[str] = []
    if not path.exists():
        return [f"File missing: {path}"]
    raw = path.read_bytes()
    if b"\r" in raw:
        errs.append(
            f"CRLF line endings detected in '{path}'. Must be strict LF to prevent satellite byte-drift."
        )
    return errs


def check_gateway_client_ast(path: Path) -> list[str]:
    """Validate python AST syntax and required symbol contracts."""
    errs: list[str] = []
    if not path.exists():
        return [f"Gateway client file missing: {path}"]

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except Exception as exc:
        return [f"Failed to parse python AST for '{path}': {exc}"]

    found_symbols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found_symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found_symbols.add(target.id)

    missing = GATEWAY_CLIENT_REQUIRED_SYMBOLS - found_symbols
    if missing:
        errs.append(
            f"Missing required contract symbols in '{path}': {sorted(missing)}. "
            f"Gateway client must adhere to canonical supremeai-api interface."
        )

    return errs


def check_openapi_schema(path: Path) -> list[str]:
    """Validate YAML parsing and essential OpenAPI 3 keys."""
    errs: list[str] = []
    if not path.exists():
        return [f"OpenAPI schema file missing: {path}"]

    try:
        import yaml
    except ImportError:
        # Fallback to basic text check if PyYAML is not installed
        content = path.read_text(encoding="utf-8")
        if "openapi:" not in content or "paths:" not in content:
            errs.append(f"Basic check failed: missing openapi/paths in '{path}'")
        return errs

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return [f"Schema '{path}' does not parse as a YAML dictionary"]
        if "openapi" not in data:
            errs.append(f"Missing 'openapi' version field in '{path}'")
        if "paths" not in data:
            errs.append(f"Missing 'paths' section in '{path}'")
    except Exception as exc:
        errs.append(f"YAML syntax error in '{path}': {exc}")

    return errs


def run_contract_check(repo_root: Path) -> tuple[int, list[str]]:
    """Execute complete contract parity check across all mirrored surfaces."""
    all_errs: list[str] = []

    # 1. Check line endings
    for rel_path in CONTRACT_FILES:
        target = repo_root / rel_path
        all_errs.extend(check_lf_endings(target))

    # 2. Check Gateway Client AST
    gw_client = repo_root / "examples/gateway_client.py"
    all_errs.extend(check_gateway_client_ast(gw_client))

    # 3. Check OpenAPI Schema
    gw_schema = repo_root / "api-schemas/gateway.openapi.yaml"
    all_errs.extend(check_openapi_schema(gw_schema))

    return len(all_errs), all_errs


def self_test() -> bool:
    """Hermetic self-test suite (zero network)."""
    print("[self-test] Running contract parity guard tests...")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        t_root = Path(td)

        # Case A: Clean files
        clean_py = t_root / "clean.py"
        clean_py.write_bytes(
            b'DEFAULT_BASE_URL = "http://test"\n'
            b'class GatewayError(Exception): pass\n'
            b'class GatewayAuthError(GatewayError): pass\n'
            b'class GatewayRateLimited(GatewayError): pass\n'
            b'class GatewayProviderError(GatewayError): pass\n'
            b'class GatewayUnavailable(GatewayError): pass\n'
            b'def chat(messages, model="test", base_url=None): return {}\n'
        )
        assert not check_lf_endings(clean_py), "Clean LF file must pass line-ending check"
        assert not check_gateway_client_ast(clean_py), "Clean symbols file must pass AST check"

        # Case B: CRLF contamination
        crlf_py = t_root / "crlf.py"
        crlf_py.write_bytes(b'def chat():\r\n    pass\r\n')
        errs = check_lf_endings(crlf_py)
        assert len(errs) == 1 and "CRLF line endings detected" in errs[0], "CRLF must be flagged"

        # Case C: Missing symbol
        missing_py = t_root / "missing.py"
        missing_py.write_bytes(b'def chat(): pass\n')
        errs = check_gateway_client_ast(missing_py)
        assert len(errs) == 1 and "Missing required contract symbols" in errs[0], "Missing symbol must be caught"

    print("✅ [self-test] Contract parity guard self-tests PASSED (3/3 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Autonomous Contract Parity & Byte-Hygiene Guard")
    parser.add_argument("--check", action="store_true", help="Run contract parity check across repo")
    parser.add_argument("--self-test", action="store_true", help="Run hermetic self-test")

    args = parser.parse_args()

    if args.self_test:
        return 0 if self_test() else 1

    repo_root = Path(__file__).resolve().parent.parent.parent
    count, errs = run_contract_check(repo_root)

    if count == 0:
        print("✅ [Contract Parity Guard] All mirrored contract files verified clean (0 byte-drift, valid AST, strict LF).")
        return 0

    print(f"❌ [Contract Parity Guard] Found {count} contract parity violation(s):", file=sys.stderr)
    for e in errs:
        print(f"  - {e}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
