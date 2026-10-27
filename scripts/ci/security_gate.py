#!/usr/bin/env python3
"""Aggregate machine-readable CI security findings with fail-closed semantics.

Resurrection (issue #1735, scout radar VIII lane R26 — classification: adapt):
    This gate was a pre-built-but-unwired security contract — a live Trivy
    JSON parser with ZERO callers (no workflow produced the report; the
    dependency-CVE class had no gate running anywhere). Per the #1554
    precedent (gates land as in-repo tests; admin applies workflow patches —
    `.github/` is admin-owned), this patch resurrects the gate bridge-ably:

      1. `--self-test` — hermetic, offline fixture validation of the whole
         fail-closed contract (findings → exit 1, clean → exit 0, missing or
         malformed report → exit 1 with error evidence). No Trivy binary
         needed; the parser is the contract under test.
      2. Roster wiring — `run_all_guards.py` now invokes
         `security_gate.py --self-test`, so the gate is discoverable,
         executable, and pinned by CI on every dispatcher run.
      3. Admin recipe (the one step only the admin can apply, SHA-pinned per
         the March-2026 trivy-action compromise precedent):

             - name: Dependency CVE gate (Trivy)
               uses: aquasecurity/trivy-action@<full-commit-sha>  # v0.71.x line; NEVER @master
               with:
                 scan-type: fs
                 format: json
                 output: trivy-report.json
             - run: python scripts/ci/security_gate.py --trivy trivy-report.json --output security-report.json

         until that step lands, the live gate runs hermetically via
         `--self-test` and honestly reports the report-absent error path.

Existing contract (unchanged): `--trivy` + `--output` → exit 0 on pass,
exit 1 on blocking findings or errors; report JSON schema stable
(`status` / `blocking_findings` / `errors`).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


def _trivy_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for result in report.get("Results", []):
        for vulnerability in result.get("Vulnerabilities") or []:
            severity = str(vulnerability.get("Severity", "UNKNOWN")).upper()
            if severity in {"HIGH", "CRITICAL"}:
                findings.append(
                    {
                        "target": result.get("Target", "unknown"),
                        "id": vulnerability.get("VulnerabilityID", "unknown"),
                        "severity": severity,
                        "package": vulnerability.get("PkgName", "unknown"),
                    }
                )
    return findings


def _evaluate(trivy_path: Path) -> tuple[int, dict[str, Any]]:
    """Single decision path shared by CLI mode and self-test.

    Returns (exit_code, report_dict). Fail-closed: missing/unparseable
    reports are errors (exit 1), never silent passes.
    """
    errors: list[str] = []
    findings: list[dict[str, Any]] = []
    if not trivy_path.is_file():
        errors.append(f"missing required report: {trivy_path}")
    else:
        try:
            findings = _trivy_findings(json.loads(trivy_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid Trivy report {trivy_path}: {exc}")

    report = {
        "status": "fail" if errors or findings else "pass",
        "blocking_findings": findings,
        "errors": errors,
    }
    return (1 if errors or findings else 0), report


def _write_report(output: Path, report: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def self_test() -> bool:
    """Hermetic, offline validation of the fail-closed contract. No Trivy needed."""
    print("[self-test] Running security gate tests...")

    # Case A: HIGH + CRITICAL findings must be extracted and fail the gate.
    with tempfile.TemporaryDirectory(prefix="secgate-a-") as td:
        report_path = Path(td) / "trivy.json"
        report_path.write_text(
            json.dumps(
                {
                    "Results": [
                        {
                            "Target": "requirements.txt",
                            "Vulnerabilities": [
                                {"VulnerabilityID": "CVE-2026-0001", "Severity": "CRITICAL", "PkgName": "requests"},
                                {"VulnerabilityID": "CVE-2026-0002", "Severity": "HIGH", "PkgName": "urllib3"},
                                {"VulnerabilityID": "CVE-2026-0003", "Severity": "LOW", "PkgName": "idna"},
                                {"VulnerabilityID": "CVE-2026-0004", "Severity": "MEDIUM", "PkgName": "certifi"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        code, report = _evaluate(report_path)
        assert code == 1, (code, report)
        assert report["status"] == "fail"
        ids = sorted(f["id"] for f in report["blocking_findings"])
        assert ids == ["CVE-2026-0001", "CVE-2026-0002"], ids  # LOW/MEDIUM never block
        assert report["blocking_findings"][0]["package"] == "requests"
    print("  PASS | HIGH/CRITICAL findings extracted, gate fails closed")

    # Case B: clean report passes.
    with tempfile.TemporaryDirectory(prefix="secgate-b-") as td:
        report_path = Path(td) / "trivy.json"
        report_path.write_text(json.dumps({"Results": []}), encoding="utf-8")
        code, report = _evaluate(report_path)
        assert code == 0 and report["status"] == "pass" and report["blocking_findings"] == []
    print("  PASS | clean report passes (exit 0)")

    # Case C: missing report is an ERROR, never a silent pass (fail-closed).
    with tempfile.TemporaryDirectory(prefix="secgate-c-") as td:
        code, report = _evaluate(Path(td) / "absent.json")
        assert code == 1 and report["status"] == "fail"
        assert any("missing required report" in e for e in report["errors"]), report
    print("  PASS | missing report fails closed with evidence")

    # Case D: malformed JSON is an ERROR, never a silent pass.
    with tempfile.TemporaryDirectory(prefix="secgate-d-") as td:
        report_path = Path(td) / "trivy.json"
        report_path.write_text("{not json", encoding="utf-8")
        code, report = _evaluate(report_path)
        assert code == 1 and report["status"] == "fail"
        assert any("invalid Trivy report" in e for e in report["errors"]), report
    print("  PASS | malformed report fails closed with evidence")

    # Case E: output writer round-trips the report schema.
    with tempfile.TemporaryDirectory(prefix="secgate-e-") as td:
        out = Path(td) / "nested" / "security-report.json"
        _write_report(out, {"status": "pass", "blocking_findings": [], "errors": []})
        loaded = json.loads(out.read_text(encoding="utf-8"))
        assert loaded == {"status": "pass", "blocking_findings": [], "errors": []}
        assert loaded["status"] == "pass"
    print("  PASS | output writer round-trips schema (nested dirs created)")

    print("[self-test] security gate self-tests PASSED (5 test cases)!")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Dependency-CVE gate: parse a Trivy JSON report, fail closed on HIGH/CRITICAL."
    )
    parser.add_argument("--trivy", type=Path, help="path to the Trivy JSON report")
    parser.add_argument("--output", type=Path, help="path to write the aggregated report JSON")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run hermetic offline contract tests (no Trivy binary or report needed)",
    )
    args = parser.parse_args()

    if args.self_test:
        ok = self_test()
        return 0 if ok else 1

    if args.trivy is None or args.output is None:
        parser.error("--trivy and --output are required unless --self-test is given")

    code, report = _evaluate(args.trivy)
    _write_report(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main", "self_test", "_trivy_findings"]
