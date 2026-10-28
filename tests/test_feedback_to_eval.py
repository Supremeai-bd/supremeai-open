"""Unit tests for scripts/eval/feedback_to_eval.py (WO #1363 item 2, T3 tier).

Covers the privacy + selection contract:
- negative-type selection (strong by default, weak opt-in)
- allowlist emission (no unexpected fields)
- forbidden-key scrubbing at nested depth (prompt/response/content never leak)
- deterministic ordering by event_id
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval" / "feedback_to_eval.py"
_spec = importlib.util.spec_from_file_location("feedback_to_eval", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("feedback_to_eval", mod)
_spec.loader.exec_module(mod)


def _row(event_id: int, feedback: str, **extra):
    base = {
        "event_id": event_id,
        "ts": "2026-10-29T00:00:00Z",
        "task_type": "code",
        "skill_id": None,
        "provider": "gemini",
        "model": "gemini-2.5",
        "feedback": feedback,
        "error_class": None,
        "metadata": {},
    }
    base.update(extra)
    return base


def test_selects_only_strong_negatives_by_default():
    rows = [_row(1, "thumbs_up"), _row(2, "thumbs_down"), _row(3, "retry"), _row(4, "correction")]
    picked = mod.select_negative_rows(rows)
    assert [r["event_id"] for r in picked] == [2, 4]


def test_weak_signals_opt_in():
    rows = [_row(2, "thumbs_down"), _row(3, "retry"), _row(5, "regenerate")]
    strong = mod.select_negative_rows(rows)
    assert [r["event_id"] for r in strong] == [2]
    with_weak = mod.select_negative_rows(rows, include_weak=True)
    assert [r["event_id"] for r in with_weak] == [2, 3, 5]


def test_deterministic_ordering_by_event_id():
    rows = [_row(9, "correction"), _row(3, "thumbs_down"), _row(6, "correction")]
    picked = mod.select_negative_rows(rows)
    assert [r["event_id"] for r in picked] == [3, 6, 9]


def test_candidate_allowlist_shape():
    candidate = mod.row_to_candidate(_row(2, "thumbs_down", unexpected_field="x"))
    assert candidate["id"] == "eval-fb-2"
    assert candidate["source"] == "feedback"
    assert set(candidate.keys()) == {"id", "source", "event_id", "ts", "task_type", "provider", "model", "feedback"}


def test_forbidden_metadata_keys_scrubbed_at_depth():
    row = _row(
        2,
        "thumbs_down",
        metadata={
            "route": "/api/feedback/ingest",
            "user_prompt": "leak me",
            "nested": {"response_text": "leak me too", "model_region": "eu"},
            "ok_key": "fine",
        },
    )
    candidate = mod.row_to_candidate(row)
    meta = candidate["metadata"]
    assert "user_prompt" not in meta
    assert "ok_key" in meta and meta["ok_key"] == "fine"
    assert "response_text" not in meta["nested"]
    assert meta["nested"] == {"model_region": "eu"}


def test_dry_run_cli_writes_stdout(tmp_path, capsys):
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps([_row(2, "thumbs_down"), _row(1, "correction")]), encoding="utf-8")
    rc = mod.main(["--rows-file", str(rows_file), "--dry-run"])
    assert rc == 0
    lines = [json.loads(l) for l in capsys.readouterr().out.strip().splitlines()]
    assert [c["id"] for c in lines] == ["eval-fb-1", "eval-fb-2"]


def test_out_file_written_deterministic(tmp_path):
    rows_file = tmp_path / "rows.json"
    rows_file.write_text(json.dumps([_row(2, "thumbs_down"), _row(1, "correction")]), encoding="utf-8")
    out = tmp_path / "out" / "candidates.jsonl"
    rc = mod.main(["--rows-file", str(rows_file), "--out", str(out)])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(l)["id"] for l in lines] == ["eval-fb-1", "eval-fb-2"]
