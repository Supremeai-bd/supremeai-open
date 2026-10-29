#!/usr/bin/env python3
"""Aggregate true cost per successful task from the durable learning plane.

WO #1363 contract item 3 (AIQ-090): track and aggregate overall cost per
successful task from ``learning_events`` (fed by ``core.learning.store``
via ``core.llm.telemetry``), FACTORING IN:
  - failed retries  (every failed attempt's cost stays in the numerator)
  - model fallbacks (cost of attempts on non-primary provider/model pairs)
  - tool overhead   (optional per-task tool cost mapping, merged in)

Reconstruction contract (durable plane only, no in-memory metadata):
  - Attempts of one logical task share ``request_id``. Events without a
    ``request_id`` fall back to a ``(session_id, task_type)`` group; events
    with neither are singletons keyed by ``event_id``.
  - Note: ``core.llm.telemetry`` records ``retry_count``/``fallback_count``
    on its in-memory metadata plane, but the durable serialization whitelist
    (``LEARNING_EVENT_FIELDS``) does not persist them — so this aggregator
    reconstructs retries/fallbacks from durable fields only.

Cost policy: prefer ``actual_cost`` when positive, fall back to
``estimated_cost`` (calibration-aware callers fill actual; estimates are the
floor). Output is deterministic: task rows sorted by task key, stable key
order. ``cost_per_successful_task`` is ``None`` (never a ZeroDivisionError)
when no successful task exists. Failed tasks keep their retry cost in the
total numerator but never enter the per-success denominator.

Usage:
    python scripts/eval/cost_per_task.py --rows-file rows.json
        [--tool-costs-file tool_costs.json] [--out PATH] [--dry-run]
    python scripts/eval/cost_per_task.py --dsn "$DATABASE_URL" [--limit N]

Exit codes: 0 success (including zero rows), 1 usage/DB error.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

DEFAULT_OUT = "data/eval/cost_per_task.json"

# Cost-relevant event fields (subset of LEARNING_EVENT_FIELDS — nothing
# outside the durable whitelist is read).
COST_FIELDS: tuple[str, ...] = (
    "event_id",
    "ts",
    "tenant_id",
    "session_id",
    "request_id",
    "task_type",
    "skill_id",
    "provider",
    "model",
    "success",
    "input_tokens",
    "output_tokens",
    "estimated_cost",
    "actual_cost",
    "error_class",
    "cache_hit",
)


def _event_cost(event: dict[str, Any]) -> float:
    """actual_cost preferred (when positive), estimated_cost fallback, else 0.0."""
    for key in ("actual_cost", "estimated_cost"):
        value = event.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return float(value)
    return 0.0


def task_key_of(event: dict[str, Any]) -> str:
    """Stable task grouping key (durable fields only)."""
    request_id = str(event.get("request_id") or "").strip()
    if request_id:
        return f"req:{request_id}"
    session_id = str(event.get("session_id") or "").strip()
    task_type = str(event.get("task_type") or "").strip()
    if session_id or task_type:
        return f"session:{session_id or '-'}:task:{task_type or '-'}"
    return f"event:{event.get('event_id') or ''}"


def aggregate_cost_per_task(
    events: Iterable[dict[str, Any]] | None,
    tool_costs: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Pure function: aggregate learning_events dicts into a cost report.

    Mirrors ``core.learning.store.aggregate_provider_metrics`` style: pure,
    defensive against malformed rows, deterministic ordering.
    """
    tools = {
        str(k): float(v)
        for k, v in (tool_costs or {}).items()
        if isinstance(v, (int, float)) and v >= 0
    }
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for event in events or []:
        if not isinstance(event, dict):
            continue
        key = task_key_of(event)
        group = groups.get(key)
        if group is None:
            group = {
                "task_key": key,
                "task_type": str(event.get("task_type") or ""),
                "attempts": 0,
                "successes": 0,
                "retries_failed": 0,
                "cache_hits": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost": 0.0,
                "actual_cost": 0.0,
                "attempt_pairs": [],
                "event_cost_sum": 0.0,
            }
            groups[key] = group
            order.append(key)
        group["attempts"] += 1
        if event.get("success") is True:
            group["successes"] += 1
        elif event.get("success") is False:
            group["retries_failed"] += 1
        if event.get("cache_hit") is True:
            group["cache_hits"] += 1
        for tok in ("input_tokens", "output_tokens"):
            value = event.get(tok)
            if isinstance(value, (int, float)) and value >= 0:
                group[tok] += int(value)
        for cost_key, sink in (("estimated_cost", "estimated_cost"),
                               ("actual_cost", "actual_cost")):
            value = event.get(cost_key)
            if isinstance(value, (int, float)) and value >= 0:
                group[sink] += float(value)
        group["attempt_pairs"].append(
            (str(event.get("provider") or "-"), str(event.get("model") or "-"))
        )
        group["event_cost_sum"] += _event_cost(event)

    rows: list[dict[str, Any]] = []
    successful_tasks = 0
    total_cost_all = 0.0
    total_estimated = 0.0
    total_actual = 0.0
    total_tool = 0.0
    retry_events = 0
    fallback_events = 0

    for key in sorted(order):
        group = groups[key]
        pairs = group["attempt_pairs"]
        primary = pairs[0] if pairs else None
        fallbacks = sum(1 for pair in pairs[1:] if pair != primary)
        tool_overhead = tools.get(key, 0.0)
        # Billed base: prefer durable actuals; estimated is the floor.
        base = group["actual_cost"] if group["actual_cost"] > 0 else group["estimated_cost"]
        task_cost = base + tool_overhead
        rows.append(
            {
                "task_key": group["task_key"],
                "task_type": group["task_type"],
                "attempts": group["attempts"],
                "successes": group["successes"],
                "retries_failed": group["retries_failed"],
                "fallback_events": fallbacks,
                "cache_hits": group["cache_hits"],
                "input_tokens": group["input_tokens"],
                "output_tokens": group["output_tokens"],
                "estimated_cost": round(group["estimated_cost"], 6),
                "actual_cost": round(group["actual_cost"], 6),
                "tool_overhead_cost": round(tool_overhead, 6),
                "task_cost": round(task_cost, 6),
                "providers": sorted({f"{p}/{m}" for p, m in pairs}),
            }
        )
        retry_events += group["retries_failed"]
        fallback_events += fallbacks
        total_estimated += group["estimated_cost"]
        total_actual += group["actual_cost"]
        total_tool += tool_overhead
        total_cost_all += task_cost
        if group["successes"] > 0:
            successful_tasks += 1

    return {
        "metric": "cost_per_successful_task",
        "cost_per_successful_task": (
            round(total_cost_all / successful_tasks, 6)
            if successful_tasks > 0
            else None
        ),
        "successful_tasks": successful_tasks,
        "total_tasks": len(rows),
        "total_events": sum(r["attempts"] for r in rows),
        "retry_events": retry_events,
        "fallback_events": fallback_events,
        "total_estimated_cost": round(total_estimated, 6),
        "total_actual_cost": round(total_actual, 6),
        "total_tool_overhead_cost": round(total_tool, 6),
        "total_cost_all_tasks": round(total_cost_all, 6),
        "tasks": rows,
    }


def fetch_rows(dsn: str, limit: int) -> list[dict[str, Any]]:
    """Read learning-event rows from the durable learning plane (Postgres)."""
    try:
        import psycopg  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise SystemExit(
            "psycopg is required to read the learning plane; install it or run "
            "with a rows file via --rows-file for offline processing"
        ) from exc

    cols = ", ".join(COST_FIELDS)
    query = f"SELECT {cols} FROM learning_events ORDER BY event_id LIMIT %s"
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(query, (limit,))
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def load_rows_file(path: str) -> list[dict[str, Any]]:
    """Load rows from a JSONL/JSON file (offline mode, testable without a DB)."""
    text = Path(path).read_text(encoding="utf-8")
    if not text.strip():
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # JSONL: one event object per line.
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(data, dict):
        # {"rows": [...]} report shape, or a bare single event object.
        data = data.get("rows") or [data]
    return list(data)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("LEARNING_DB_DSN", ""),
                        help="Postgres DSN for learning_events")
    parser.add_argument("--rows-file", default="",
                        help="offline mode: read rows from this JSONL/JSON file")
    parser.add_argument("--tool-costs-file", default="",
                        help="JSON mapping task_key -> tool overhead cost")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help=f"output JSON path (default {DEFAULT_OUT})")
    parser.add_argument("--limit", type=int, default=1000,
                        help="max rows to fetch (default 1000)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print report to stdout, do not write files")
    args = parser.parse_args(argv)

    if args.rows_file:
        events = load_rows_file(args.rows_file)
    elif args.dsn:
        events = fetch_rows(args.dsn, args.limit)
    else:
        parser.error("provide --rows-file (offline) or --dsn")
        return 1

    tool_costs: dict[str, float] = {}
    if args.tool_costs_file:
        raw = json.loads(Path(args.tool_costs_file).read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            tool_costs = {
                str(k): float(v)
                for k, v in raw.items()
                if isinstance(v, (int, float)) and v >= 0
            }

    report = aggregate_cost_per_task(events, tool_costs)

    if args.dry_run:
        print(json.dumps(report, indent=2, sort_keys=False))
        return 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {out_path} ({report['total_tasks']} tasks, "
        f"{report['successful_tasks']} successful)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
