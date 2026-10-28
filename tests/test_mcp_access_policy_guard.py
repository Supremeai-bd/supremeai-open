#!/usr/bin/env python3
"""Offline regression tests for the MCP access-policy deny-matrix guard.

Pins the guard introduced for issue #1843 (five secret/internal-class tools
executed zero-credential by the deployed tower while the in-repo SSOT
correctly denies them). The deployment-side fix is admin-lane; these tests
lock the source-side invariants so the drift class cannot re-enter via a
quiet policy edit, and lock the guard itself into the run_all_guards roster
(zero-callers was the exact failure mode that killed the dependency-CVE gate
resurrected in #1735).

Dual-mode: runs under pytest OR as a stdlib runner
(``python tests/test_mcp_access_policy_guard.py``), mirroring the house style
of test_security_gate_selftest.py / test_gateway_private_import_boundary.py.
Fully offline - no tower, no network, no secrets.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "mcp_access_policy_guard.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
POLICY = REPO_ROOT / "infrastructure" / "mcp-control-plane" / "src" / "policy" / "mcp-access.ts"

# The five tools witnessed executing anonymously against the deployed tower (#1843).
OVEREXPOSED_TOOLS = [
    "github_list_secrets",
    "supabase_read_table",
    "redis_read_key",
    "memory_read_graph",
    "tenant_list",
]


def _run_guard(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_real_tree_check_passes() -> None:
    """The landed SSOT satisfies every pinned invariant."""
    r = _run_guard("--check")
    assert r.returncode == 0, f"guard failed on real tree:\n{r.stdout}\n{r.stderr}"


def test_self_test_matrix_passes() -> None:
    """All hermetic fixture cases behave (clean passes, each tamper fails)."""
    r = _run_guard("--self-test")
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "0/7" not in r.stdout


def test_missing_policy_fails_closed() -> None:
    """Absent SSOT is a red condition, never an honest-skip."""
    with tempfile.TemporaryDirectory() as td:
        r = _run_guard("--policy", str(Path(td) / "does" / "not" / "exist.ts"))
    assert r.returncode == 1
    assert "missing" in r.stdout.lower()


def test_tampered_copy_fails() -> None:
    """Granting an over-exposed tool the public manifest is caught via --policy."""
    assert POLICY.is_file(), f"SSOT disappeared: {POLICY}"
    source = POLICY.read_text(encoding="utf-8")
    tampered = source.replace(
        'name === "github_list_secrets"',
        'name === "github_list_secrets_moved"',
    )
    assert tampered != source, "tamper anchor not found - SSOT restructured, update test"
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "mcp-access.ts"
        path.write_text(tampered, encoding="utf-8")
        r = _run_guard("--policy", str(path))
    assert r.returncode == 1


def test_roster_wiring_pinned() -> None:
    """The guard is discoverable/executable via the run_all_guards roster."""
    roster = ROSTER.read_text(encoding="utf-8")
    assert "scripts/ci/mcp_access_policy_guard.py" in roster, (
        "guard unwired from roster - the #1735 zero-callers death mode repeats"
    )


def test_overexposed_tools_absent_from_public_manifest() -> None:
    """Direct source pin: none of the five #1843 tools is advertised publicly."""
    source = POLICY.read_text(encoding="utf-8")
    start = source.find("publicSafeCapabilities")
    end = source.find("\n];", start)
    manifest = source[start:end]
    for tool in OVEREXPOSED_TOOLS:
        assert f'name: "{tool}"' not in manifest, f"{tool} leaked into publicSafeCapabilities"


def test_admin_recipe_documented() -> None:
    """The guard docstring carries the admin redeploy recipe + honesty caveat."""
    doc = GUARD.read_text(encoding="utf-8")
    assert "#1843" in doc
    assert "ADMIN RECIPE" in doc
    assert "redeploy" in doc.lower()
    assert "Forbidden" in doc
    assert "zod" in doc.lower(), "zod-denial-vs-RBAC audit honesty caveat missing"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"{7 - failures}/7 passed" if failures else "7/7 passed (stdlib mode)")
    sys.exit(1 if failures else 0)
