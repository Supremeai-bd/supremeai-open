#!/usr/bin/env python3
"""Execution bridge for task envelopes (plan §5 step 6 / §10.3 gap 1).

Consumes a task envelope (agent-loop output), validates it fail-closed, and records a
dispatch intent into a queue directory. By default runs in DRY-RUN mode: it never
executes code, only writes a dispatch record that a real MCP/agent executor can later
consume. --execute is reserved for a future MCP integration and currently refuses to
run (fail-closed) until an executor is wired.

Stdlib-only. Fail-closed on invalid envelope / IO errors.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

REQUIRED_ENVELOPE_KEYS = ("task_envelope",)
REQUIRED_TASK_KEYS = ("task_id", "role", "specialist_prompt", "scope", "submission")


def load_envelope(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def validate_envelope(env: dict[str, Any]) -> list[str]:
    """Return list of error codes; empty == valid. Fail-closed."""
    errors: list[str] = []
    if not isinstance(env, dict):
        return ["E_NOT_OBJECT"]
    te = env.get("task_envelope")
    if not isinstance(te, dict):
        errors.append("E_NO_TASK_ENVELOPE")
        return errors
    for k in REQUIRED_TASK_KEYS:
        if k not in te:
            errors.append(f"E_MISSING_{k.upper()}")
    scope = te.get("scope")
    if not isinstance(scope, dict):
        errors.append("E_BAD_SCOPE")
    else:
        tf = scope.get("touching_files", [])
        if not isinstance(tf, list):
            errors.append("E_BAD_TOUCHING_FILES")
        elif len(tf) > 30:
            errors.append("E_SCOPE_TOO_WIDE")
    prompt = te.get("specialist_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        errors.append("E_EMPTY_PROMPT")
    role = te.get("role")
    if not isinstance(role, str) or not role.strip():
        errors.append("E_BAD_ROLE")
    return errors


def build_dispatch_record(envelope: dict[str, Any], dry_run: bool = True) -> dict[str, Any]:
    te = envelope["task_envelope"]
    return {
        "schema": "dispatch-intent/1",
        "created_ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "dry_run": dry_run,
        "task_id": te.get("task_id"),
        "role": te.get("role"),
        "objective": te.get("objective"),
        "scope": te.get("scope", {}),
        "acceptance": te.get("acceptance", []),
        "verification": te.get("verification", []),
        "specialist_prompt": te.get("specialist_prompt"),
        "submission": te.get("submission", {}),
        "status": "queued",
    }


def dispatch(
    envelope: dict[str, Any],
    queue_dir: Path,
    dry_run: bool = True,
    execute: bool = False,
) -> Path | None:
    """Validate + record dispatch intent. Returns record path or None on failure.

    execute=True is reserved for future MCP integration and currently refuses
    (fail-closed) to avoid running unverified code.
    """
    errs = validate_envelope(envelope)
    if errs:
        return None
    if execute:
        # Not wired yet — fail-closed rather than silently no-op.
        return None
    try:
        queue_dir.mkdir(parents=True, exist_ok=True)
        record = build_dispatch_record(envelope, dry_run=dry_run)
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        task_id = str(record["task_id"]).replace("/", "_")
        out = queue_dir / f"{ts}_{task_id}.json"
        out.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        return out
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Execution bridge for task envelopes")
    parser.add_argument("--envelope", required=True, help="path to task envelope JSON")
    parser.add_argument("--queue", default=".dispatch_queue", help="queue directory")
    parser.add_argument("--results", default=".execution_results", help="results directory (used with --execute)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="record only (default)")
    parser.add_argument("--execute", action="store_true", help="run safe executor (verify) on the dispatch record")
    parser.add_argument("--executor", default="verify", choices=("null", "verify"), help="executor for --execute")
    parser.add_argument("--repo-root", default=".", help="repository root")
    args = parser.parse_args()

    import sys as _sys
    root = Path(args.repo_root).resolve()
    env = load_envelope(Path(args.envelope))
    if env is None:
        print("ERROR: cannot load envelope", file=_sys.stderr)
        return 1
    errs = validate_envelope(env)
    if errs:
        print("ERROR: invalid envelope:", errs, file=_sys.stderr)
        return 1

    rec_path = dispatch(env, Path(args.queue), dry_run=not args.execute, execute=False)
    if rec_path is None:
        print("ERROR: dispatch failed", file=_sys.stderr)
        return 1
    print(f"dispatch recorded: {rec_path}")

    if args.execute:
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        import execution_executor as _ee
        res_path = _ee.run(rec_path, Path(args.results), args.executor, root)
        if res_path is None:
            print("ERROR: execution failed", file=_sys.stderr)
            return 1
        print(f"execution result recorded: {res_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
