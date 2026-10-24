#!/usr/bin/env python3
"""Aggregate machine-readable CI security findings with fail-closed semantics."""

from __future__ import annotations

import argparse
import json
import sys
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trivy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    errors: list[str] = []
    findings: list[dict[str, Any]] = []
    if not args.trivy.is_file():
        errors.append(f"missing required report: {args.trivy}")
    else:
        try:
            findings = _trivy_findings(json.loads(args.trivy.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"invalid Trivy report {args.trivy}: {exc}")

    report = {
        "status": "fail" if errors or findings else "pass",
        "blocking_findings": findings,
        "errors": errors,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if errors or findings else 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = ["main"]
