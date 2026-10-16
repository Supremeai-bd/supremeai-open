"""Offline tests for the #374 CI-failure claim priority in continuous_agent_loop.

Imports the loop module directly from its file path (it is a script, not a
package) and monkeypatches ``run_cmd`` so ``pick_next_issue`` is exercised
with canned ``gh issue list`` payloads — no network, no gh binary.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

LOOP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "continuous_agent_loop.py"

_spec = importlib.util.spec_from_file_location("continuous_agent_loop_under_test", LOOP_PATH)
loop = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("continuous_agent_loop_under_test", loop)
_spec.loader.exec_module(loop)


def issue(number: int, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": f"Issue #{number}",
        "labels": [{"name": name} for name in labels],
    }


def prime_board(monkeypatch, issues: list) -> None:
    payload = json.dumps(issues)

    def fake_run_cmd(cmd, **kwargs):
        assert cmd[0] == "gh" and cmd[1] == "issue" and cmd[2] == "list"
        return 0, payload, ""

    monkeypatch.setattr(loop, "run_cmd", fake_run_cmd)


def test_ci_failure_outranks_every_priority_tier(monkeypatch):
    prime_board(monkeypatch, [
        issue(10, ["P0-high"]),
        issue(11, ["P1-high"]),
        issue(12, ["bridge:ci-failure", "target:supremeai-skills", "P1-high"]),
        issue(13, ["P3"]),
    ])
    assert loop.pick_next_issue() == "12"


def test_ci_failure_ties_break_oldest_first(monkeypatch):
    prime_board(monkeypatch, [
        issue(21, ["bridge:ci-failure"]),
        issue(20, ["bridge:ci-failure"]),
    ])
    assert loop.pick_next_issue() == "20"


def test_baseline_ordering_unchanged_without_ci_failures(monkeypatch):
    prime_board(monkeypatch, [
        issue(31, ["P2-medium"]),
        issue(30, ["P0"]),
        issue(32, []),  # unlabeled sorts last
    ])
    assert loop.pick_next_issue() == "30"


def test_unlabeled_still_sorts_last(monkeypatch):
    prime_board(monkeypatch, [issue(40, []), issue(41, ["P3-low"])])
    assert loop.pick_next_issue() == "41"


def test_claimed_ci_failure_is_never_picked(monkeypatch):
    prime_board(monkeypatch, [
        issue(50, ["bridge:ci-failure", "status:claimed"]),
        issue(51, ["P2"]),
    ])
    assert loop.pick_next_issue() == "51"


def test_seq_hold_and_private_mirrors_stay_excluded(monkeypatch):
    prime_board(monkeypatch, [
        issue(60, ["bridge:ci-failure", "state:seq-hold"]),
        issue(61, ["mirror:private"]),
        issue(62, ["P1"]),
    ])
    assert loop.pick_next_issue() == "62"


def test_malformed_label_entries_do_not_crash_selection(monkeypatch):
    board = [
        {"number": 70, "title": "broken labels", "labels": ["flat-string", {"no_name": 1}, 42, {"name": "bridge:ci-failure"}]},
        issue(71, ["P0"]),
    ]
    prime_board(monkeypatch, board)
    assert loop.pick_next_issue() == "70"


def test_empty_board_returns_none(monkeypatch):
    prime_board(monkeypatch, [])
    assert loop.pick_next_issue() is None


def test_failed_gh_call_returns_none(monkeypatch):
    def failing_run_cmd(cmd, **kwargs):
        return 1, "", "gh: auth required"

    monkeypatch.setattr(loop, "run_cmd", failing_run_cmd)
    assert loop.pick_next_issue() is None


def test_exclude_prevents_session_local_repick(monkeypatch):
    prime_board(monkeypatch, [
        issue(80, ["bridge:ci-failure"]),
        issue(81, ["bridge:ci-failure"]),
    ])
    assert loop.pick_next_issue(exclude={"80"}) == "81"


def test_case_insensitive_label_matching(monkeypatch):
    prime_board(monkeypatch, [
        issue(90, ["BRIDGE:CI-FAILURE"]),  # gh labels are matched lowercased
        issue(91, ["P0"]),
    ])
    assert loop.pick_next_issue() == "90"
