#!/usr/bin/env python3
"""Unit tests for scripts/eval/cost_per_task.py (WO #1363 contract item 3).

Covers the 3-Tier test requirement: "Unit test verifying cost aggregator
factors in retry attempts and tool overhead" — plus model fallbacks,
actual-vs-estimated cost policy, zero-success guard, determinism, and the
offline CLI contract.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "cost_per_task",
    Path(__file__).resolve().parents[1] / "scripts" / "eval" / "cost_per_task.py",
)
cpu = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cpu)


def _ev(event_id, request_id=None, success=True, actual=None, estimated=None,
        provider="openai", model="gpt-4o", session_id=None, task_type="chat",
        **extra):
    row = {
        "event_id": event_id,
        "ts": "2026-10-29T00:00:00Z",
        "tenant_id": "t1",
        "session_id": session_id,
        "request_id": request_id,
        "task_type": task_type,
        "provider": provider,
        "model": model,
        "success": success,
        "input_tokens": 10,
        "output_tokens": 5,
        "estimated_cost": estimated,
        "actual_cost": actual,
        "error_class": None,
        "cache_hit": False,
    }
    row.update(extra)
    return row


def test_retry_attempts_factored_into_cost():
    """Two failed retries + one success: all attempt costs stay in numerator."""
    events = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r1", success=False),
        _ev("e3", request_id="r1", success=True, actual=0.30),
    ]
    report = cpu.aggregate_cost_per_task(events)
    assert report["successful_tasks"] == 1
    assert report["retry_events"] == 2
    row = report["tasks"][0]
    assert row["attempts"] == 3
    assert row["retries_failed"] == 2
    assert row["actual_cost"] == pytest.approx(0.40)
    assert row["task_cost"] == pytest.approx(0.40)
    # 0.40 (all three attempts) / 1 successful task
    assert report["cost_per_successful_task"] == pytest.approx(0.40)
    assert report["total_cost_all_tasks"] == pytest.approx(0.40)


def test_tool_overhead_factored():
    """Tool overhead merges into task cost and the headline metric."""
    events = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r1", success=True, actual=0.30),
    ]
    report = cpu.aggregate_cost_per_task(events, tool_costs={"req:r1": 0.25})
    row = report["tasks"][0]
    assert row["tool_overhead_cost"] == pytest.approx(0.25)
    assert row["task_cost"] == pytest.approx(0.65)
    assert report["total_tool_overhead_cost"] == pytest.approx(0.25)
    assert report["cost_per_successful_task"] == pytest.approx(0.65)


def test_model_fallback_counted():
    """Attempts on a non-primary provider/model pair count as fallbacks."""
    events = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r1", success=True, actual=0.30),
        _ev("e3", request_id="r1", success=True, actual=0.05,
            provider="anthropic", model="claude-3"),
    ]
    report = cpu.aggregate_cost_per_task(events)
    row = report["tasks"][0]
    assert row["fallback_events"] == 1
    assert row["attempts"] == 3
    assert sorted(row["providers"]) == ["anthropic/claude-3", "openai/gpt-4o"]
    assert report["fallback_events"] == 1
    # 0.10 + 0.30 + 0.05 = 0.45
    assert report["cost_per_successful_task"] == pytest.approx(0.45)


def test_actual_cost_preferred_over_estimated():
    """When actuals exist for a task, they are the billed base."""
    events = [
        _ev("e1", request_id="r1", success=True, actual=0.30, estimated=9.99),
    ]
    report = cpu.aggregate_cost_per_task(events)
    row = report["tasks"][0]
    assert row["task_cost"] == pytest.approx(0.30)
    assert row["estimated_cost"] == pytest.approx(9.99)
    assert report["cost_per_successful_task"] == pytest.approx(0.30)


def test_estimated_is_floor_when_no_actual():
    """Without actuals, estimated_cost is the cost floor."""
    events = [
        _ev("e1", request_id="r1", success=True, estimated=0.20),
    ]
    report = cpu.aggregate_cost_per_task(events)
    assert report["cost_per_successful_task"] == pytest.approx(0.20)


def test_zero_successful_tasks_returns_none():
    """No success anywhere: metric is None, never ZeroDivisionError."""
    events = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r2", success=False, actual=0.20),
    ]
    report = cpu.aggregate_cost_per_task(events)
    assert report["cost_per_successful_task"] is None
    assert report["successful_tasks"] == 0
    # Failed-task cost still reported in the total numerator.
    assert report["total_cost_all_tasks"] == pytest.approx(0.30)


def test_grouping_fallback_chain():
    """request_id > (session_id, task_type) > event_id singleton."""
    events = [
        _ev("e1", request_id="r1", success=True),
        _ev("e2", session_id="s9", success=True),
        _ev("e3", session_id="s9", task_type="ingest", success=True),
        _ev("e4", success=True, task_type=None),  # no key fields → singleton
        _ev("e5", session_id="s9", success=True),  # same (s9, chat) group as e2
    ]
    report = cpu.aggregate_cost_per_task(events)
    keys = [r["task_key"] for r in report["tasks"]]
    assert keys == sorted(keys)
    assert keys == ["event:e4", "req:r1", "session:s9:task:chat",
                    "session:s9:task:ingest"]
    assert report["total_tasks"] == 4


def test_deterministic_output():
    """Same input in any order → identical report bytes."""
    events = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r1", success=True, actual=0.30),
        _ev("e3", request_id="r2", success=True, estimated=0.15),
    ]
    a = json.dumps(cpu.aggregate_cost_per_task(events), sort_keys=True)
    b = json.dumps(cpu.aggregate_cost_per_task(list(reversed(events))),
                   sort_keys=True)
    assert a == b


def test_malformed_rows_skipped():
    """Non-dict rows and negative costs are ignored defensively."""
    events = [
        "junk",
        None,
        _ev("e1", request_id="r1", success=True, actual=-5.0, estimated=0.20),
    ]
    report = cpu.aggregate_cost_per_task(events)
    assert report["total_tasks"] == 1
    assert report["cost_per_successful_task"] == pytest.approx(0.20)


def test_cli_dry_run_json(tmp_path, capsys):
    """Offline CLI smoke: --rows-file + --tool-costs-file --dry-run prints JSON."""
    rows = [
        _ev("e1", request_id="r1", success=False, actual=0.10),
        _ev("e2", request_id="r1", success=True, actual=0.30),
    ]
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    tools_file = tmp_path / "tools.json"
    tools_file.write_text(json.dumps({"req:r1": 0.25}), encoding="utf-8")

    rc = cpu.main([
        "--rows-file", str(rows_file),
        "--tool-costs-file", str(tools_file),
        "--out", str(tmp_path / "out" / "report.json"),
        "--dry-run",
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["metric"] == "cost_per_successful_task"
    assert payload["cost_per_successful_task"] == pytest.approx(0.65)
    assert payload["retry_events"] == 1
    assert not (tmp_path / "out" / "report.json").exists()  # dry-run wrote nothing


def test_cli_writes_report(tmp_path):
    """Non-dry CLI writes the report file deterministically."""
    rows = [_ev("e1", request_id="r1", success=True, actual=0.30)]
    rows_file = tmp_path / "rows.jsonl"
    rows_file.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    out = tmp_path / "report.json"
    rc = cpu.main(["--rows-file", str(rows_file), "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["cost_per_successful_task"] == pytest.approx(0.30)
