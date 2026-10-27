#!/usr/bin/env python3
"""tests/test_security_gate_selftest.py — pin the resurrected dependency-CVE gate (#1735).

Auditor finding (scout radar VIII, R26): scripts/ci/security_gate.py was a
pre-built-but-unwired contract — a live Trivy JSON parser with zero callers
anywhere in the repo (pipeline.yml, run_all_guards.py, audit_suite.py). The
dependency-CVE class had no gate running at all.

Resurrection envelope (bridge-able, .github/ untouched per the admin-sovereignty
contract — #1554 precedent: gates land as in-repo tests, admin applies the
workflow patch):

  1. ``security_gate.py --self-test``  — hermetic fixture validation of the
     fail-closed contract (added by this patch; no Trivy binary required).
  2. ``run_all_guards.py`` roster wiring (added by this patch).
  3. This test file pins BOTH: the contract behavior end-to-end via the real
     CLI (subprocess) and the roster wiring (regression lock against silent
     un-wiring — the exact failure mode that killed the gate originally).

The admin recipe for the real Trivy step (SHA-pinned action, json output,
feeding ``--trivy``) lives in the security_gate.py module docstring.

Dual mode (zero-dependency doctrine):
  - pytest:  pytest tests/test_security_gate_selftest.py
  - stdlib:  python3 tests/test_security_gate_selftest.py

Every test is offline and deterministic.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = REPO_ROOT / "scripts" / "ci" / "security_gate.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"


def _run_gate(*extra: str) -> tuple[int, str]:
    """Run the real gate CLI (subprocess, offline)."""
    r = subprocess.run(
        [sys.executable, str(GATE), *extra],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False,
    )
    return r.returncode, r.stdout + r.stderr


def _write_trivy(td: Path, name: str, payload: str) -> Path:
    p = td / name
    p.write_text(payload, encoding="utf-8")
    return p


def test_self_test_mode_passes() -> None:
    code, out = _run_gate("--self-test")
    assert code == 0, out
    assert "PASSED" in out, out


def _agg_report(td: Path) -> tuple[int, dict, Path]:
    trivy = _write_trivy(
        td,
        "trivy.json",
        json.dumps(
            {
                "Results": [
                    {
                        "Target": "requirements.txt",
                        "Vulnerabilities": [
                            {"VulnerabilityID": "CVE-2026-9999", "Severity": "CRITICAL", "PkgName": "flask"},
                        ],
                    }
                ]
            }
        ),
    )
    out = td / "security-report.json"
    code, out_text = _run_gate("--trivy", str(trivy), "--output", str(out))
    return code, json.loads(out.read_text(encoding="utf-8")), out


def test_blocking_findings_fail_closed_with_report() -> None:
    with tempfile.TemporaryDirectory(prefix="secgate-t1-") as td:
        code, report, out = _agg_report(Path(td))
        assert code == 1
        assert out.is_file(), "aggregated report must be written even on failure"
        assert report["status"] == "fail"
        assert report["blocking_findings"] == [
            {"target": "requirements.txt", "id": "CVE-2026-9999", "severity": "CRITICAL", "package": "flask"}
        ]
        assert report["errors"] == []


def test_clean_report_passes() -> None:
    with tempfile.TemporaryDirectory(prefix="secgate-t2-") as td:
        trivy = _write_trivy(Path(td), "trivy.json", json.dumps({"Results": []}))
        out = Path(td) / "security-report.json"
        code, _ = _run_gate("--trivy", str(trivy), "--output", str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 0
        assert report["status"] == "pass" and report["blocking_findings"] == []


def test_missing_report_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="secgate-t3-") as td:
        out = Path(td) / "security-report.json"
        code, out_text = _run_gate("--trivy", str(Path(td) / "absent.json"), "--output", str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 1
        assert report["status"] == "fail"
        assert any("missing required report" in e for e in report["errors"])


def test_malformed_report_fails_closed() -> None:
    with tempfile.TemporaryDirectory(prefix="secgate-t4-") as td:
        trivy = _write_trivy(Path(td), "trivy.json", "{definitely not json")
        out = Path(td) / "security-report.json"
        code, _ = _run_gate("--trivy", str(trivy), "--output", str(out))
        report = json.loads(out.read_text(encoding="utf-8"))
        assert code == 1
        assert any("invalid Trivy report" in e for e in report["errors"])


def test_gate_is_roster_wired() -> None:
    """Regression lock: the gate must stay wired into the guard dispatcher.

    Zero callers is the exact failure mode that killed this gate originally
    (#1735) — if someone removes the roster line, this test goes red.
    """
    roster_src = ROSTER.read_text(encoding="utf-8")
    assert "scripts/ci/security_gate.py" in roster_src, (
        "security_gate.py vanished from run_all_guards.py roster — dependency-CVE "
        "gate would be dead again (the #1735 failure mode)"
    )
    assert '"--self-test"' in roster_src


def test_admin_recipe_is_documented() -> None:
    """The module docstring must carry the SHA-pinned admin recipe.

    The real Trivy step can only be applied by the admin (.github/ is
    admin-owned); the recipe living in-repo keeps the resurrection honest
    and reviewable.
    """
    doc = GATE.read_text(encoding="utf-8")
    assert "trivy-action" in doc
    assert "full-commit-sha" in doc, "recipe must mandate SHA pinning (March-2026 compromise precedent)"
    assert "NEVER @master" in doc
    assert "--trivy" in doc and "--output" in doc


class _Skip(Exception):
    """Honest skip signal (dual-mode; mirrors test_ci_guards.py)."""


def main() -> int:  # plain stdlib runner (dual mode)
    tests = [
        test_self_test_mode_passes,
        test_blocking_findings_fail_closed_with_report,
        test_clean_report_passes,
        test_missing_report_fails_closed,
        test_malformed_report_fails_closed,
        test_gate_is_roster_wired,
        test_admin_recipe_is_documented,
    ]
    for t in tests:
        try:
            t()
        except _Skip as exc:
            print(f"SKIP {t.__name__}: {exc}")
            continue
        except AssertionError as exc:
            print(f"FAIL {t.__name__}: {exc}")
            return 1
        print(f"PASS {t.__name__}")
    print("ALL PASS: dependency-CVE gate contract + wiring pinned (7 tests)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
