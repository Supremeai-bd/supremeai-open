#!/usr/bin/env python3
"""Offline tests for the boundary contract sentinel (#1819 D3, seed #1874).

The sentinel's live mode probes the served edge (report-only by default);
these tests deliberately do NOT touch the network: they run the guard's own
--self-test (hermetic pre-fix/post-fix fixture servers, miss=0 +
false-positive=0 proof), pin the roster wiring, the wolf-proof methodology
constants (CSP Report-Only acceptance, allowlisted preflight origin), the
SSOT operator-field import, and the honest-skip exit code. The probe table
covers the full redaction class end-to-end: the original 10-probe #1819
boundary table plus the #1901 docs-lockdown and #1902 readiness-redaction
probes (12/12 live-verified against the edge serving the #1904/#1908 build).
Dual-mode (pytest + stdlib runner), mirroring test_contract_fuzz_guard.py.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SENTINEL = REPO_ROOT / "scripts" / "ci" / "boundary_contract_sentinel.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

PASS = 0
FAIL = 1


def _load_sentinel_module():
    spec = importlib.util.spec_from_file_location("boundary_contract_sentinel", SENTINEL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_roster_wiring():
    src = ROSTER.read_text(encoding="utf-8")
    assert ("scripts/ci/boundary_contract_sentinel.py", "--self-test") and \
        '["python", "scripts/ci/boundary_contract_sentinel.py", "--self-test"]' in src, \
        "sentinel missing from run_all_guards.py GUARDS roster"


def test_probe_table_and_wolfproof_constants():
    mod = _load_sentinel_module()
    # 12 probes: the exact #1819/#1874 table + the #1901/#1902 redaction-class
    # extension (live-verified 12/12 against the edge serving #1904/#1908).
    src = SENTINEL.read_text(encoding="utf-8")
    for needle in ('"GET / 4-field root"', '"HEAD / 200"',
                   '"OPTIONS / preflight (allowlisted origin)"',
                   '"security headers on /"', '"security headers on 404"',
                   '"/internal/status"', '"/webhook/scout/status"',
                   '"GET /openapi.json inventory not served unauth"',
                   '"GET /readyz redacted readiness"'):
        assert needle in src, f"probe pin missing: {needle}"
    # Wolf-proof lesson (a): CSP accepted in both names, lookup case-insensitive.
    assert "content-security-policy-report-only" in src
    assert "content-security-policy" in src
    # Wolf-proof lesson (b): preflight-shaped from the allowlisted origin only.
    assert mod.ALLOWLISTED_ORIGIN == "https://supremeai-studio.pages.dev"
    assert mod.FOREIGN_ORIGIN != mod.ALLOWLISTED_ORIGIN
    # Root/liveness/readiness field SSOTs mirror the merged contract.
    assert mod.ROOT_FIELDS == {"status", "service_name", "version", "chat_ready"}
    assert mod.LIVENESS_FIELDS >= {"status", "chat_ready", "timestamp"}
    assert mod.READINESS_FIELDS == {"status", "chat_ready", "timestamp"}
    # #1902 leak-class markers: the reason string must not carry the posture
    # vocabulary either (env-var names contain "stealth"; store names "infisical").
    assert "stealth" in mod.READINESS_LEAK_MARKERS
    assert "infisical" in mod.READINESS_LEAK_MARKERS
    assert len(mod.OPERATOR_ONLY_FIELDS) >= 9, "operator-field SSOT lost"


def test_missing_headers_case_insensitive_and_csp_variants():
    mod = _load_sentinel_module()
    mixed = {
        "Strict-Transport-Security": "v", "X-Content-Type-Options": "v",
        "X-Frame-Options": "v", "Content-Security-Policy-Report-Only": "v",
        "Referrer-Policy": "v", "Permissions-Policy": "v",
    }
    assert mod._missing_headers(mixed) == []
    enforced = dict(mixed)
    del enforced["Content-Security-Policy-Report-Only"]
    enforced["content-security-policy"] = "v"
    assert mod._missing_headers(enforced) == []
    assert sorted(mod._missing_headers({})) == sorted(mod.SECURITY_HEADERS)


def test_self_test_hermetic():
    r = subprocess.run([sys.executable, str(SENTINEL), "--self-test"],
                       cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    m = re.search(r"(\d+)/(\d+) self-test cases PASS", r.stdout)
    assert m and m.group(1) == m.group(2), r.stdout


def test_live_mode_honest_skip_on_unreachable():
    # Exit 2 (skip), never 0/1, when the edge is unreachable — a sentinel that
    # reports a pass on a network failure would defeat its own purpose.
    r = subprocess.run(
        [sys.executable, str(SENTINEL), "--base-url", "http://127.0.0.1:9",
         "--timeout", "2"],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)
    assert r.returncode == 2, f"expected honest-skip exit 2, got {r.returncode}\n{r.stdout}"
    assert "SKIP" in r.stdout


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"[ RUN ] {name}")
            try:
                fn()
                print(f"[  OK ] {name}")
            except AssertionError as e:
                failures += 1
                print(f"[ FAIL] {name}: {e}")
    print(f"\n==== {sum(1 for n in globals() if n.startswith('test_') and callable(globals()[n])) - failures}"
          f"/{sum(1 for n in globals() if n.startswith('test_') and callable(globals()[n]))} PASS ====")
    sys.exit(FAIL if failures else PASS)
