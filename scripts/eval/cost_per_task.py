#!/usr/bin/env python3
"""scripts/eval/cost_per_task.py — Aggregate cost per successful task from telemetry (#1363, AIQ-090).

CONTRACT:
  - Stdlib only, offline, deterministic.
  - Input: JSONL (one task-telemetry record per line) or a JSON array via --input.
  - Aggregates: total cost of SUCCESSFUL tasks / number of successful tasks, plus
    retry overhead, tool-call overhead, and model-fallback overhead.
  - A task is "successful" iff status in {"success","completed","ok"} (case-insensitive).
  - Costs: cost_usd (preferred) OR tokens_input*tokens_output priced via --cost-per-1k
    (default 0.0 when no price given -> token counts still reported).
  - Output: JSON report to --output (or stdout) with summary + per-task breakdown.
  - Exit 0 on success, 2 on input/schema error.

Task telemetry record schema (all fields optional):
  {
    "task_id": str,
    "status": "success" | "failed" | "completed" | ...,
    "cost_usd": float,
    "tokens_input": int,
    "tokens_output": int,
    "retries": int,
    "tool_calls": int,
    "model_fallbacks": int,
    "duration_ms": int,
    "task_type": str
  }
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

SUCCESS_STATUSES = {"success", "completed", "ok", "done", "passed"}


def is_success(rec: dict[str, Any]) -> bool:
    return str(rec.get("status", "")).strip().lower() in SUCCESS_STATUSES


def task_cost(rec: dict[str, Any], cost_per_1k: float = 0.0) -> float:
    if "cost_usd" in rec and rec.get("cost_usd") is not None:
        try:
            return float(rec["cost_usd"])
        except (TypeError, ValueError):
            pass
    ti = int(rec.get("tokens_input") or 0)
    to = int(rec.get("tokens_output") or 0)
    return (ti + to) / 1000.0 * cost_per_1k


def aggregate(records: list[Any], cost_per_1k: float = 0.0) -> dict[str, Any]:
    total_tasks = 0
    successful: list[dict[str, Any]] = []
    failed = 0
    total_cost_all = 0.0
    total_retries = 0
    total_tool_calls = 0
    total_fallbacks = 0
    total_tokens_in = 0
    total_tokens_out = 0

    for rec in records:
        if not isinstance(rec, dict):
            continue
        total_tasks += 1
        cost = task_cost(rec, cost_per_1k)
        total_cost_all += cost
        total_retries += int(rec.get("retries") or 0)
        total_tool_calls += int(rec.get("tool_calls") or 0)
        total_fallbacks += int(rec.get("model_fallbacks") or 0)
        total_tokens_in += int(rec.get("tokens_input") or 0)
        total_tokens_out += int(rec.get("tokens_output") or 0)
        if is_success(rec):
            successful.append({"task_id": rec.get("task_id"), "cost_usd": round(cost, 6),
                               "retries": int(rec.get("retries") or 0),
                               "tool_calls": int(rec.get("tool_calls") or 0),
                               "model_fallbacks": int(rec.get("model_fallbacks") or 0),
                               "task_type": rec.get("task_type")})
        else:
            failed += 1

    n_succ = len(successful)
    cost_per_successful = (sum(s["cost_usd"] for s in successful) / n_succ) if n_succ else 0.0
    # retry/tool/fallback overhead attributed to successful tasks' attempt history
    retry_overhead = sum(s["retries"] for s in successful)
    tool_overhead = sum(s["tool_calls"] for s in successful)
    fallback_overhead = sum(s["model_fallbacks"] for s in successful)

    return {
        "total_tasks": total_tasks,
        "successful_tasks": n_succ,
        "failed_tasks": failed,
        "success_rate": round(n_succ / total_tasks, 4) if total_tasks else 0.0,
        "total_cost_usd": round(total_cost_all, 6),
        "cost_per_successful_task_usd": round(cost_per_successful, 6),
        "total_tokens_input": total_tokens_in,
        "total_tokens_output": total_tokens_out,
        "retry_overhead_on_successes": retry_overhead,
        "tool_call_overhead_on_successes": tool_overhead,
        "model_fallback_overhead_on_successes": fallback_overhead,
        "cost_per_1k_tokens_usd": cost_per_1k,
        "per_task": successful,
    }


def _read_input(path: str | None) -> list[Any]:
    if path is None or path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    raw = raw.strip()
    if not raw:
        return []
    if raw.startswith("["):
        data = json.loads(raw)
        if not isinstance(data, list):
            raise ValueError("top-level JSON must be an array")
        return data
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Aggregate cost per successful task from telemetry")
    p.add_argument("--input", "-i", default=None, help="Input JSON/JSONL file (default stdin)")
    p.add_argument("--output", "-o", default=None, help="Output JSON report file (default stdout)")
    p.add_argument("--cost-per-1k", type=float, default=0.0, help="USD per 1k tokens when cost_usd missing")
    p.add_argument("--self-test", action="store_true", help="Run offline unit probes")
    args = p.parse_args(argv)

    if args.self_test:
        return _self_test()

    try:
        records = _read_input(args.input)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    report = aggregate(records, args.cost_per_1k)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
            f.write("\n")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _self_test() -> int:
    recs = [
        {"task_id": "t1", "status": "success", "cost_usd": 0.05, "tokens_input": 100, "tokens_output": 50, "retries": 1, "tool_calls": 2, "model_fallbacks": 0},
        {"task_id": "t2", "status": "failed", "cost_usd": 0.02, "tokens_input": 30, "tokens_output": 10, "retries": 3, "tool_calls": 1, "model_fallbacks": 1},
        {"task_id": "t3", "status": "completed", "cost_usd": 0.10, "tokens_input": 200, "tokens_output": 80, "retries": 0, "tool_calls": 4, "model_fallbacks": 0},
    ]
    r = aggregate(recs)
    assert r["total_tasks"] == 3
    assert r["successful_tasks"] == 2
    assert r["failed_tasks"] == 1
    assert abs(r["cost_per_successful_task_usd"] - 0.075) < 1e-9
    assert r["retry_overhead_on_successes"] == 1
    assert r["tool_call_overhead_on_successes"] == 6
    # token pricing fallback
    r2 = aggregate([{"task_id": "t", "status": "success", "tokens_input": 1000, "tokens_output": 1000}], cost_per_1k=0.5)
    assert abs(r2["cost_per_successful_task_usd"] - 1.0) < 1e-9
    # empty input
    r3 = aggregate([])
    assert r3["total_tasks"] == 0 and r3["cost_per_successful_task_usd"] == 0.0
    print("[self-test] cost_per_task: all probes passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
