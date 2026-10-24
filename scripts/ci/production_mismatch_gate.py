#!/usr/bin/env python3
"""Classify CI findings as production-critical failures or advisory warnings."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    critical: bool


CRITICAL_CHECKS = (
    Check("API contract mismatch", ("scripts/advanced_analysis/api_contract_diff.py", "--fail-on-critical"), True),
    Check("database model drift", ("scripts/advanced_analysis/db_model_drift_checker.py", "--fail-on-critical"), True),
    Check("migration safety mismatch", ("scripts/advanced_analysis/migration_safety_diff.py", "--fail-on-critical"), True),
    Check("environment contract mismatch", ("scripts/advanced_analysis/env_var_reconciler.py", "--fail-on-critical"), True),
    Check("workflow contract mismatch", (".github/scripts/validate_workflow_contracts.py",), True),
)

ADVISORY_CHECKS = (
    Check("error handling consistency", ("scripts/advanced_analysis/error_handling_consistency_checker.py",), False),
    Check("blocking call audit", ("scripts/advanced_analysis/blocking_call_detector.py",), False),
    Check("duplicate logic audit", ("scripts/advanced_analysis/duplicate_logic_detector.py",), False),
)


import os

def run_check(check: Check) -> tuple[int, str]:
    command = [sys.executable, *check.command]
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, check=False)
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode, output


def emit_summary(findings: list[tuple[Check, int, str]], summary_path: str | None) -> None:
    critical = [(check, code, output) for check, code, output in findings if check.critical and code != 0]
    warnings = [(check, code, output) for check, code, output in findings if not check.critical and code != 0]
    lines = ["## Production mismatch gate", "", f"- Critical failures: {len(critical)}", f"- Warnings: {len(warnings)}", ""]
    for check, code, output in critical + warnings:
        label = "CRITICAL" if check.critical else "WARNING"
        lines.append(f"### {label}: {check.name} (exit {code})")
        if output:
            lines.append("```text")
            lines.extend(output[-3000:].splitlines())
            lines.append("```")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    for check, code, output in critical:
        print(f"::error title=Production-critical mismatch::{check.name} failed (exit {code})")
        if output:
            print(output[-3000:])
    for check, code, output in warnings:
        print(f"::warning title=Advisory mismatch::{check.name} reported findings (exit {code})")
        if output:
            print(output[-1500:])
    print(f"Production mismatch gate: {len(critical)} critical failure(s), {len(warnings)} warning(s)")
    if critical:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default=None, help="Append a Markdown report to this file")
    parser.add_argument("--critical-only", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    checks = CRITICAL_CHECKS if args.critical_only else CRITICAL_CHECKS + ADVISORY_CHECKS
    findings: list[tuple[Check, int, str]] = []
    for check in checks:
        script = root / check.command[0]
        if not script.exists():
            findings.append((check, 2, f"Missing checker: {script}"))
            continue
        code, output = run_check(check)
        findings.append((check, code, output))
        if code == 0:
            print(f"PASS: {check.name}")
    emit_summary(findings, args.summary)
    return 0


if __name__ == "__main__":
    main()
