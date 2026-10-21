#!/usr/bin/env python3
"""Execution executor for dispatch-intent records (plan §5 step 6).

Consumes a dispatch-intent record produced by execution_bridge.py and runs a SAFE,
allow-listed set of actions. It NEVER executes the specialist_prompt as arbitrary code.
Supported executors:
  - "null":    record-only (no execution) — default, fail-closed.
  - "verify":  run the verification commands from the envelope; record pass/fail.
  - "mcp":     reserved for MCP Tower integration (not wired) — fail-closed.

Stdlib-only. Fail-closed on invalid intent / IO errors.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

VALID_EXECUTORS = ("null", "verify", "mcp")


def load_intent(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != "dispatch-intent/1":
        return None
    return data


def _run_cmd(cmd: str, cwd: Path, timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, shell=True, capture_output=True, timeout=timeout, check=False
        )
        return p.returncode, (p.stderr or b"").decode("utf-8", errors="replace")[:200]
    except Exception as exc:
        return 127, str(exc)[:200]


def execute_null(intent: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "execution-result/1",
        "task_id": intent.get("task_id"),
        "executor": "null",
        "status": "recorded",
        "passed": True,
        "details": "dispatch intent recorded; no execution performed (fail-closed default)",
        "completed_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def execute_verify(intent: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    cmds = intent.get("verification") or []
    results: list[dict[str, Any]] = []
    all_passed = True
    for cmd in cmds:
        if not isinstance(cmd, str) or not cmd.strip():
            continue
        rc, err = _run_cmd(cmd, repo_root)
        passed = rc == 0
        if not passed:
            all_passed = False
        results.append({"cmd": cmd, "rc": rc, "passed": passed, "stderr": err})
    return {
        "schema": "execution-result/1",
        "task_id": intent.get("task_id"),
        "executor": "verify",
        "status": "completed" if all_passed else "failed",
        "passed": all_passed and len(results) > 0,
        "results": results,
        "completed_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def execute(
    intent: dict[str, Any], executor: str, repo_root: Path
) -> dict[str, Any] | None:
    """Run the chosen executor. Returns result dict or None on failure/unknown executor."""
    if executor not in VALID_EXECUTORS:
        return None
    if executor == "null":
        return execute_null(intent)
    if executor == "verify":
        return execute_verify(intent, repo_root)
    # "mcp": not wired — fail-closed.
    return None


def run(
    intent_path: Path,
    results_dir: Path,
    executor: str,
    repo_root: Path,
) -> Path | None:
    intent = load_intent(intent_path)
    if intent is None:
        return None
    result = execute(intent, executor, repo_root)
    if result is None:
        return None
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        task_id = str(result.get("task_id", "unknown")).replace("/", "_")
        out = results_dir / f"{ts}_{task_id}_{executor}.json"
        out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return out
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execution executor for dispatch-intent records"
    )
    parser.add_argument("--intent", required=True, help="path to dispatch-intent JSON")
    parser.add_argument(
        "--results", default=".execution_results", help="results directory"
    )
    parser.add_argument(
        "--executor", default="null", choices=VALID_EXECUTORS, help="executor to use"
    )
    parser.add_argument("--repo-root", default=".", help="repository root")
    args = parser.parse_args()

    intent_path = Path(args.intent)
    if not intent_path.is_file():
        print("ERROR: intent file not found", __import__("sys").stderr)
        return 1
    out = run(
        intent_path, Path(args.results), args.executor, Path(args.repo_root).resolve()
    )
    if out is None:
        if args.executor == "mcp":
            print(
                "ERROR: mcp executor not wired yet (fail-closed)",
                __import__("sys").stderr,
            )
        else:
            print("ERROR: execution failed", __import__("sys").stderr)
        return 1
    print(f"execution result recorded: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
