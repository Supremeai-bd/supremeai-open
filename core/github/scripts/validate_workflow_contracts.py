#!/usr/bin/env python3
"""Validate safety invariants for GitHub Actions workflows.

This is intentionally offline and deterministic so it can run before any
network-dependent CI job. It fails on supply-chain and execution-control gaps,
while reporting softer maintenance smells as warnings.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

SHA_ACTION = re.compile(r"^uses:\s+[^\s#]+@[0-9a-f]{40}(?:\s+#.*)?$")
LOCAL_ACTION = re.compile(r"^uses:\s+\./")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(".github/workflows"))
    parser.add_argument("--json", type=Path, default=Path("workflow-contract-report.json"))
    args = parser.parse_args()

    failures: list[str] = []
    warnings: list[str] = []
    checked: list[str] = []
    for path in sorted(args.root.glob("*.y*ml")):
        checked.append(str(path))
        raw = path.read_text(encoding="utf-8")
        try:
            document = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            failures.append(f"{path}: invalid YAML: {exc}")
            continue
        is_reusable = "workflow_call:" in raw
        if "permissions:" not in raw:
            failures.append(f"{path}: missing explicit permissions")
        if not is_reusable and "concurrency:" not in raw:
            failures.append(f"{path}: missing concurrency control")
        if "curl -s" in raw and "|" in raw:
            warnings.append(f"{path}: remote installer pipe detected; pin and checksum installers")
        for line_no, line in enumerate(raw.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("uses:") and not (SHA_ACTION.match(stripped) or LOCAL_ACTION.match(stripped)):
                failures.append(f"{path}:{line_no}: external action must be pinned to a full commit SHA")
        jobs = document.get("jobs", {})
        if not isinstance(jobs, dict) or not jobs:
            failures.append(f"{path}: no jobs found")
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                failures.append(f"{path}: job {job_name!r} is not an object")
                continue
            if "uses" not in job and "timeout-minutes" not in job:
                warnings.append(f"{path}: job {job_name!r} missing timeout-minutes; add an explicit execution budget")
            if "permissions" not in job and "permissions:" not in raw:
                failures.append(f"{path}: job {job_name!r} has no effective permissions")
            for step in job.get("steps", []):
                if isinstance(step, dict) and "run" in step and "|| true" in str(step["run"]):
                    warnings.append(f"{path}: job {job_name!r} contains non-blocking shell failure")

    report = {"workflows": checked, "failures": failures, "warnings": warnings}
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
