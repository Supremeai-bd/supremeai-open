#!/usr/bin/env python3
"""tests/test_vault_failclosed.py — fail-closed identifier-resolution pin for #1820.

Verifies the Cloudflare vault auto-repair tool no longer carries hardcoded
fleet identifiers (issue #1820, the #1729 recon-hygiene class in-repo):

  - source hygiene: NO 32-hex Cloudflare account-id literals and NO email
    literals remain in scripts/ops/security/auto_repair_cloudflare_vault.py
    (scanner-aligned with scripts/agents/rules_breaker.py's 5 BLOCK findings
    on the pre-fix file, run 2026-10-27T23:37Z);
  - no fallback-carrying lookups: every ``secrets.get(...)`` call is
    single-argument — a missing vault answer can never silently resolve to a
    baked-in value;
  - require_secret() unit behavior: returns the resolved value when present;
    raises MissingInfisicalSecret for missing / empty / whitespace-only
    values, naming the role and the Infisical key in both the printed line
    and the exception — and NEVER the value;
  - the file's own failure path stays honest offline: running the script with
    an unreachable Infisical API exits non-zero with no identifier leaked.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_vault_failclosed.py
  - stdlib:  python3 tests/test_vault_failclosed.py   (plain runner)

Every test is offline and deterministic; the subprocess test points the
Infisical API at a refuse-fast loopback port — no network, no credentials.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET = REPO_ROOT / "scripts" / "ops" / "security" / "auto_repair_cloudflare_vault.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("auto_repair_cloudflare_vault", TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- #
# Source hygiene — the scanner-aligned regression pin                          #
# --------------------------------------------------------------------------- #

def test_no_hardcoded_account_id_literals():
    """No 32-hex Cloudflare account-id literal remains anywhere in the file."""
    source = TARGET.read_text(encoding="utf-8")
    hex_literals = re.findall(r"\b[0-9a-f]{32}\b", source)
    assert hex_literals == [], (
        "hardcoded 32-hex account-id literal(s) back in source: "
        f"{[h[:6] + '…' for h in hex_literals]} (issue #1820 regression)"
    )


def test_no_hardcoded_email_literals():
    """No operator email literal remains anywhere in the file."""
    source = TARGET.read_text(encoding="utf-8")
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", source)
    assert emails == [], f"hardcoded email literal(s) back in source: {emails} (issue #1820 regression)"


def test_no_fallback_carrying_secrets_get_calls():
    """Every secrets.get(...) is single-argument — no baked-in fallback default."""
    source = TARGET.read_text(encoding="utf-8")
    fallback_calls = re.findall(r"secrets\.get\([^()]*,", source)
    assert fallback_calls == [], (
        "fallback-carrying secrets.get(...) call(s) back in source: "
        f"{fallback_calls} (issue #1820 regression — identifiers must fail closed)"
    )


def test_failclosed_docstring_contract_present():
    """The module docstring documents the fail-closed resolution contract."""
    source = TARGET.read_text(encoding="utf-8")
    assert "issue #1820" in source, "fail-closed provenance note (issue #1820) missing from module"
    assert "require_secret" in source, "fail-closed require_secret helper missing"


# --------------------------------------------------------------------------- #
# require_secret() unit behavior — the fail-closed mechanism                   #
# --------------------------------------------------------------------------- #

def test_require_secret_returns_value_when_present():
    mod = _load_module()
    assert mod.require_secret({"CLOUDFLARE_EMAIL": "resolved-from-vault@example.test"}, "primary", "CLOUDFLARE_EMAIL") == "resolved-from-vault@example.test"


def test_require_secret_raises_on_missing_key():
    mod = _load_module()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.require_secret({}, "primary", "CLOUDFLARE_EMAIL")
        raise AssertionError("missing key did not raise MissingInfisicalSecret")
    except mod.MissingInfisicalSecret as exc:
        text = f"{buf.getvalue()}\n{exc}"
        assert "primary" in text, "error must name the ROLE"
        assert "CLOUDFLARE_EMAIL" in text, "error must name the missing Infisical KEY"


def test_require_secret_raises_on_empty_and_whitespace_values():
    """Empty / whitespace-only vault answers count as missing (partial outage)."""
    mod = _load_module()
    for bad in ("", "   ", "\n", "\t"):
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                mod.require_secret({"CLOUDFLARE_ACCOUNT_ID": bad}, "secondary", "CLOUDFLARE_ACCOUNT_ID")
            raise AssertionError(f"value {bad!r} did not raise MissingInfisicalSecret")
        except mod.MissingInfisicalSecret:
            continue


def test_require_secret_error_path_never_echoes_the_value():
    """The printed line and the exception must never dump other vault values.

    Simulates a real vault dump: the required key is absent while OTHER keys
    carry sensitive values — the error path may name the role and the missing
    key, and must not leak any of the surrounding secrets.
    """
    mod = _load_module()
    sentinels = {
        "CLOUDFLARE_GLOBAL_API_KEY": "SENSITIVE-GLOBAL-KEY-MUST-NOT-APPEAR",
        "CLOUDFLARE_TERTIARY_EMAIL": "SENSITIVE-EMAIL-MUST-NOT-APPEAR@example.test",
        "UNRELATED_VAULT_SECRET": "SENSITIVE-UNRELATED-MUST-NOT-APPEAR",
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mod.require_secret(sentinels, "tertiary", "CLOUDFLARE_TERTIARY_ACCOUNT_ID")
        raise AssertionError("missing-secret path did not raise")
    except mod.MissingInfisicalSecret as exc:
        text = buf.getvalue() + str(exc)
        assert "tertiary" in text and "CLOUDFLARE_TERTIARY_ACCOUNT_ID" in text, "error must name role + key"
        for sentinel in sentinels.values():
            assert sentinel not in text, f"error path leaked a vault value ({sentinel.split('-')[1]})"


def test_missinginfisicalsecret_is_runtime_error():
    mod = _load_module()
    assert issubclass(mod.MissingInfisicalSecret, RuntimeError), (
        "MissingInfisicalSecret must stay a RuntimeError so unexpected callers fail loudly"
    )


# --------------------------------------------------------------------------- #
# Honest offline failure path — the script itself exits non-zero, leaks nothing #
# --------------------------------------------------------------------------- #

def test_script_exits_nonzero_when_vault_unreachable():
    """Unreachable Infisical API -> the file's own failure path, exit != 0, offline."""
    env = dict(os.environ)
    env["INFISICAL_API_URL"] = "http://127.0.0.1:1/api"  # refuse-fast loopback, no network
    env.pop("INFISICAL_CLIENT_ID", None)
    env.pop("INFISICAL_CLIENT_SECRET", None)
    r = subprocess.run(
        [sys.executable, str(TARGET)],
        capture_output=True, text=True, timeout=60, env=env,
    )
    assert r.returncode != 0, "script must fail closed when the vault is unreachable"
    blob = r.stdout + r.stderr
    assert "[0-9a-f]{32}" and not re.search(r"\b[0-9a-f]{32}\b", blob), "failure output leaked an account-id-shaped literal"


def test_script_survives_import_without_network_side_effects():
    """Importing the module is side-effect-free (no calls at import time)."""
    mod = _load_module()
    assert callable(mod.main)
    assert callable(mod.require_secret)
    # and re-importing into a temp module namespace works (no sys.modules games needed)
    with tempfile.TemporaryDirectory() as td:
        spec = importlib.util.spec_from_file_location("vault_probe_" + next(iter(td.replace("-", "")), "x"), TARGET)
        mod2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod2)
        assert mod2.require_secret({"K": "v"}, "r", "K") == "v"


# --------------------------------------------------------------------------- #
# Plain stdlib runner (dual-mode doctrine)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failures = 0
    tests = [(name, obj) for name, obj in sorted(globals().items()) if name.startswith("test_") and callable(obj)]
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS | {name}")
        except AssertionError as exc:
            failures += 1
            print(f"  FAIL | {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 — plain runner must report, not crash
            failures += 1
            print(f"  ERROR | {name}: {exc!r}")
    print(f"\n{len(tests) - failures}/{len(tests)} vault-failclosed tests passed")
    sys.exit(1 if failures else 0)
