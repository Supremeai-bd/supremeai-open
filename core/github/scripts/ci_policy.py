#!/usr/bin/env python3
"""Normalize CI findings into explicit pass/warn/fail decisions.

Checks may remain non-blocking, but they must report why. This prevents
`continue-on-error` and shell fallbacks from silently turning real failures
into green builds.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--exit-code", type=int, default=0)
    parser.add_argument("--severity", choices=("info", "low", "medium", "high", "critical"), default="medium")
    parser.add_argument("--blocking", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--confidence", type=float, default=1.0)
    parser.add_argument("--category", default="quality")
    parser.add_argument("--autofixable", action="store_true")
    parser.add_argument("--remediation", default="")
    parser.add_argument("--report", type=Path, default=Path("ci-reports/ci-policy.jsonl"))
    args = parser.parse_args()

    if not 0.0 <= args.confidence <= 1.0:
        parser.error("--confidence must be between 0 and 1")

    status = "pass" if args.exit_code == 0 else ("warn" if args.baseline or not args.blocking else "fail")
    result = {
        "check": args.name,
        "status": status,
        "severity": args.severity,
        "category": args.category,
        "confidence": args.confidence,
        "blocking": status == "fail",
        "baseline": args.baseline,
        "autofixable": args.autofixable,
        "remediation": args.remediation,
        "exit_code": args.exit_code,
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "sha": os.getenv("GITHUB_SHA"),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write(f"- **{args.name}**: `{status}` ({args.severity})\n")
    return 1 if status == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
