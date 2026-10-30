#!/usr/bin/env python3
"""pipeline_timeout_guard.py — job-budget tripwire for workflow YAMLs (issue #3386 option B, U6 mechanical guard).

# বাংলা নোট (R82 স্কাউট রিসিট, GLM Agent 20 / Job 486804): আমাদের নিজের
# `.github/workflows/pipeline.yml`-এর ২২টি `runs-on` জবের মধ্যে ১৮টিতে স্পষ্ট
# `timeout-minutes` (৩–১৫) আছে, কিন্তু ৪টিতে নেই — ফলে GitHub-hosted ডিফল্ট
# **৩৬০ মিনিট** সিলিং খোলা থাকে। `test-matrix` জবে `strategy.fail-fast: false`
# থাকায় ২টি matrix leg × ৬ ঘণ্টা = একটি আটকে-যাওয়া রানে সর্বোচ্চ ১২ রানার-ঘণ্টা।
# ফ্রি-টিয়ারের ২,০০০ মিনিট/মাস ফেডারেশন বাজেটের কথা মাথায় রাখলে একটাই hung
# `npm ci` মাসের বাজেটের সর্বোচ্চ ১৮% পুড়িয়ে দিতে পারে। ১৮/৪ ভাগটাই প্রমাণ যে
# ৪টি জব নীতিগতভাবে নয়, ভুলে পিনহীন হয়েছে। চারটি এক-লাইনের YAML পিন (option A)
# admin-গেটেড সুরক্ষিত পাথে (`.github/**`, #1643 আইন) — এই গার্ড হলো option B:
# আজকের ৪টি ভাঙা সারি শুধু heal করে না, কালকের নতুন জবও পিনহীন থাকতে পারবে না।
# admin পিনগুলো বসানোর পর `--strict` দিয়ে শূন্য-অবস্থা স্থায়ীভাবে প্রয়োগ হবে
# (sequencing-honesty flip — #3352 zizmor গার্ডের একই চুক্তি)।

Why a guard and not just the 4 edits: the 18/4 drift is mechanical proof that
job authors forget the pin when adding jobs (none relies on the default by
design — every guard job pins 3, deploy jobs pin 10–15). A mistake once
discovered must never recur (U6): only a mechanical tripwire keeps the
default-360 trap closed for tomorrow's job additions. zizmor does not cover
this surface (security-class, not budget-class) — first-hand verified by the
R82 receipt (actionlint 1.7.7 live run flags only the known head_ref site).

Two-mode sequencing honesty (mirrors tests/test_zizmor_profile_guard.py):
  - **baseline mode (default)**: the R82-known unpinned jobs are disclosed
    inline but non-fatal; ANY job outside that baseline running unpinned is a
    regression -> exit 1. The 4 edits (option A) do NOT need to land first.
  - **strict mode (`--strict`)**: every `runs-on` job must carry an explicit
    pin (zero-state enforcement). Flip CI wiring to this once option A lands.

Protected-path compliance: this script READS `.github/workflows/*.yml` and
edits nothing (admin lane owns the yml, #1643/#1776 doctrine). It lives in
`scripts/ci/` and never writes state.

Exit codes (fail-closed family, mirrors #1814 drift-detector convention):
  0  every `runs-on` job pinned, or only KNOWN_BASELINE_GAPS unpinned in
     baseline mode (each gap disclosed inline — a known gap is never silent)
  1  budget violation: an unpinned job beyond the baseline (baseline mode) or
     any unpinned job at all (strict mode)
  2  fail-closed: workflow file missing / unparseable / PyYAML absent — an
     unreadable budget surface is never reported as green (#1760 honest-skip)

Usage:
  python3 scripts/ci/pipeline_timeout_guard.py                    # baseline mode, pipeline.yml
  python3 scripts/ci/pipeline_timeout_guard.py --all              # every .github/workflows/*.yml
  python3 scripts/ci/pipeline_timeout_guard.py --workflow PATH    # one explicit file
  python3 scripts/ci/pipeline_timeout_guard.py --strict           # zero-state enforcement
  python3 scripts/ci/pipeline_timeout_guard.py --json             # machine-readable report
  python3 scripts/ci/pipeline_timeout_guard.py --self-test        # hermetic, offline

Refs: #3386 (R82 scout receipt, Job 486804) · #2125 (push-branch corruption
RCA family that motivated budget hygiene) · #1814 (exit-code family) · #1760
(honest-skip) · #3352 (sequencing-honesty flip precedent) · #612 (60-second
satellite budget; the monorepo jobs carry their own explicit pins) ·
docs/CI_MINIMUM_PIPELINE_STANDARD.md (budget tables this guard defends).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# R82 receipt (live tree c996c21, re-verified on 4841217 by GLM Agent 04,
# Job 486718, 2026-10-30T14:1xZ): exactly these jobs ran unpinned. Remove
# entries here in the SAME PR that lands option A pins; when the set is
# empty the baseline mode and strict mode become equivalent.
KNOWN_BASELINE_GAPS = {
    "test-matrix",    # strategy.fail-fast: false -> 2 legs x 6h ceiling
    "secrets-scan",   # fetch-depth: 0 full-history checkout
    "mcp-tower",      # npm ci + tsc --noEmit (network-bound installs)
    "sdk-typescript", # same npm-ci/tsc shape
}

GITHUB_DEFAULT_TIMEOUT_MINUTES = 360  # the trap this guard closes


def _load_yaml(path: Path) -> dict[str, Any]:
    """Parse a workflow file, fail-closed on any unreadable surface."""
    try:
        import yaml  # PyYAML: installed explicitly by pipeline.yml jobs (pip install pyyaml)
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise WorkflowUnreadableError(
            f"PyYAML unavailable ({exc}); the budget surface cannot be read honestly. "
            "Install pyyaml (CI already does: `pip install pyyaml`) — never report green on a dark surface."
        ) from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowUnreadableError(f"cannot parse {path}: {exc}") from exc
    if data is None:
        raise WorkflowUnreadableError(f"{path} parses to empty document")
    if not isinstance(data, dict):
        raise WorkflowUnreadableError(f"{path} is not a mapping at top level")
    return data


class WorkflowUnreadableError(Exception):
    """Raised when a workflow surface cannot be read — always exit 2 (fail-closed)."""


def scan_workflow(path: Path, strict: bool = False) -> dict[str, Any]:
    """Scan one workflow file; return a machine-readable report dict.

    A job participates when it declares `runs-on` (i.e. it consumes runner
    minutes). Jobs without `runs-on` (reusable-workflow `uses:` calls,
    metadata-only entries) are skipped — they consume no runner budget.
    """
    data = _load_yaml(path)
    jobs = data.get("jobs") or {}
    if not isinstance(jobs, dict):
        raise WorkflowUnreadableError(f"{path}: `jobs:` is not a mapping")

    rows: list[dict[str, Any]] = []
    for name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        if not job.get("runs-on"):
            continue  # no runner consumption -> outside the budget surface
        timeout = job.get("timeout-minutes")
        rows.append(
            {
                "job": name,
                "timeoutMinutes": timeout,
                "pinned": timeout is not None,
                "failFast": (job.get("strategy") or {}).get("fail-fast") is False
                if isinstance(job.get("strategy"), dict)
                else False,
            }
        )

    unpinned = [r["job"] for r in rows if not r["pinned"]]
    if strict:
        violations = list(unpinned)
    else:
        violations = [j for j in unpinned if j not in KNOWN_BASELINE_GAPS]
    known = [j for j in unpinned if j in KNOWN_BASELINE_GAPS]

    return {
        "workflow": str(path),
        "runnerJobs": len(rows),
        "pinned": len(rows) - len(unpinned),
        "unpinned": unpinned,
        "knownBaselineGaps": known,
        "violations": violations,
        "rows": rows,
        "githubDefaultCeilingMinutes": GITHUB_DEFAULT_TIMEOUT_MINUTES,
        "mode": "strict" if strict else "baseline",
        "ok": not violations,
    }


def scan_all(strict: bool = False) -> list[dict[str, Any]]:
    """Scan every workflow yml in .github/workflows (sorted, deterministic)."""
    files = sorted(WORKFLOWS_DIR.glob("*.y*ml"))
    if not files:
        raise WorkflowUnreadableError(f"no workflow files found under {WORKFLOWS_DIR}")
    return [scan_workflow(p, strict=strict) for p in files]


def _self_test() -> int:
    """Hermetic offline battery — no repo files, no network (sentinel convention)."""
    import tempfile

    failures = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal failures
        if cond:
            print(f"  ok  {name}")
        else:
            failures += 1
            print(f"  FAIL {name}{(' — ' + detail) if detail else ''}")

    clean = (
        "name: clean\n"
        "jobs:\n"
        "  a:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 5\n"
        "    steps: [{run: 'true'}]\n"
        "  b:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 15\n"
        "    steps: [{run: 'true'}]\n"
    )
    r82 = (
        "name: r82\n"
        "jobs:\n"
        "  test-matrix:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy: {fail-fast: false}\n"
        "    steps: [{run: 'true'}]\n"
        "  secrets-scan:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: [{run: 'true'}]\n"
        "  mcp-tower:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: [{run: 'true'}]\n"
        "  sdk-typescript:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: [{run: 'true'}]\n"
        "  guard-job:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 3\n"
        "    steps: [{run: 'true'}]\n"
    )
    growth = (
        "name: growth\n"
        "jobs:\n"
        "  test-matrix:\n"
        "    runs-on: ubuntu-latest\n"
        "    strategy: {fail-fast: false}\n"
        "    steps: [{run: 'true'}]\n"
        "  brand-new-job:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: [{run: 'true'}]\n"
    )
    metadata = (
        "name: metadata\n"
        "jobs:\n"
        "  call-reusable:\n"
        "    uses: ./.github/workflows/other.yml\n"
        "  pinned:\n"
        "    runs-on: ubuntu-latest\n"
        "    timeout-minutes: 3\n"
        "    steps: [{run: 'true'}]\n"
    )

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        def wf(name: str, body: str) -> Path:
            p = tdp / name
            p.write_text(body, encoding="utf-8")
            return p

        # 1. clean workflow: green in both modes
        p = wf("clean.yml", clean)
        check("clean/baseline ok", scan_workflow(p)["ok"] is True)
        check("clean/strict ok", scan_workflow(p, strict=True)["ok"] is True)

        # 2. the R82 shape: baseline discloses 4 known gaps, stays green; strict is red
        p = wf("r82.yml", r82)
        rep = scan_workflow(p)
        check("r82/baseline ok (known gaps non-fatal)", rep["ok"] is True)
        check("r82 baseline discloses all 4", sorted(rep["knownBaselineGaps"]) == sorted(KNOWN_BASELINE_GAPS))
        check("r82 runner jobs counted", rep["runnerJobs"] == 5)
        check("r82 fail-fast flag carried", any(r["failFast"] and r["job"] == "test-matrix" for r in rep["rows"]))
        check("r82 strict red", scan_workflow(p, strict=True)["ok"] is False)

        # 3. growth beyond baseline: a NEW unpinned job is a violation in baseline mode
        p = wf("growth.yml", growth)
        rep = scan_workflow(p)
        check("growth/baseline red", rep["ok"] is False)
        check("growth violation named", rep["violations"] == ["brand-new-job"])
        check("growth keeps known gap out of violations", "test-matrix" not in rep["violations"])

        # 4. metadata-only jobs (no runs-on) are outside the budget surface
        p = wf("metadata.yml", metadata)
        rep = scan_workflow(p)
        check("metadata-only skipped", rep["runnerJobs"] == 1 and rep["ok"] is True)

        # 5. unreadable surfaces fail closed (exit-2 contract)
        bad = wf("bad.yml", "jobs: [oops, not: a: mapping")
        try:
            scan_workflow(bad)
            check("unparseable raises", False, "no exception raised")
        except WorkflowUnreadableError:
            check("unparseable raises", True)

        missing = tdp / "absent.yml"
        try:
            scan_workflow(missing)
            check("missing file raises", False, "no exception raised")
        except WorkflowUnreadableError:
            check("missing file raises", True)

    print()
    if failures:
        print(f"SELF-TEST FAILED ({failures})")
        return 1
    print("SELF-TEST PASSED (pipeline_timeout_guard)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed on workflow jobs that consume runner minutes without an explicit timeout-minutes pin (#3386)."
    )
    parser.add_argument("--workflow", type=Path, default=None, help="scan one workflow file (default: pipeline.yml)")
    parser.add_argument("--all", action="store_true", help="scan every .github/workflows/*.yml")
    parser.add_argument("--strict", action="store_true", help="zero-state enforcement: every runs-on job must be pinned (flip after #3386 option A lands)")
    parser.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    parser.add_argument("--self-test", action="store_true", help="hermetic offline battery, no repo files")
    args = parser.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        reports = scan_all(strict=args.strict) if args.all else [scan_workflow(args.workflow or DEFAULT_WORKFLOW, strict=args.strict)]
    except WorkflowUnreadableError as exc:
        print(f"FAIL-CLOSED (exit 2): {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(reports, indent=2))
    else:
        for rep in reports:
            rel = Path(rep["workflow"]).name
            print(f"── {rel}: {rep['pinned']}/{rep['runnerJobs']} runner jobs pinned ({rep['mode']} mode)")
            for j in rep["unpinned"]:
                tag = "KNOWN-BASELINE" if j in rep["knownBaselineGaps"] else "VIOLATION"
                print(f"   [{tag}] {j}: no timeout-minutes (GitHub default {GITHUB_DEFAULT_TIMEOUT_MINUTES} min ceiling)")
            if not rep["unpinned"]:
                print("   all runner jobs carry explicit pins")

    violations = [v for rep in reports for v in rep["violations"]]
    if violations:
        print(f"\nFAIL (exit 1): {len(violations)} unpinned runner job(s) beyond baseline: {', '.join(violations)}")
        print("Fix: add timeout-minutes to each job (option A, admin lane) — then rerun with --strict to keep the zero state permanent.")
        return 1
    known_total = sum(len(rep["knownBaselineGaps"]) for rep in reports)
    if known_total:
        print(f"\nOK (exit 0): {known_total} known baseline gap(s) disclosed above — non-fatal until #3386 option A lands.")
    else:
        print("\nOK (exit 0): every runner job carries an explicit timeout-minutes pin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
