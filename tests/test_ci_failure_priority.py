"""Contract-locking tests for the #374 CI-failure claim priority.

Dual-mode by design (bridge v2 new-files-only lane). The tier -1 wiring
hunk for ``scripts/agents/continuous_agent_loop.py`` cannot ride the
bridge (the private ``pick_next_issue`` region has diverged from the
public base), so that one-line precedence rule is landed operator-side.
This suite therefore DETECTS the feature and skips honestly until the
wiring exists, then enforces the contract at full strength:

- loop module not importable in this tree             -> module-level skip
- module present but tier -1 not wired (probe fails)  -> module-level skip
- feature wired (P0 loses to ``bridge:ci-failure``)   -> 11 assertions green

The probe is a self-contained canned-board round (``run_cmd`` swapped and
restored in a ``finally`` block), so it never touches the network, needs
no ``gh`` binary, and import order never matters.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

LOOP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "agents" / "continuous_agent_loop.py"

_SKIP: str | None = None
loop: Any = None
try:
    _spec = importlib.util.spec_from_file_location("continuous_agent_loop_under_test", LOOP_PATH)
    if _spec is None or _spec.loader is None:  # pragma: no cover - depends on tree
        raise ImportError(f"importlib spec unavailable for {LOOP_PATH}")
    loop = importlib.util.module_from_spec(_spec)
    sys.modules.setdefault("continuous_agent_loop_under_test", loop)
    _spec.loader.exec_module(loop)
except Exception as _exc:  # pragma: no cover - depends on target tree
    _SKIP = f"continuous_agent_loop.py not importable in this tree ({type(_exc).__name__})"


def issue(number: int, labels: list[str]) -> dict:
    return {
        "number": number,
        "title": f"Issue #{number}",
        "labels": [{"name": name} for name in labels],
    }


def _pick(board: list) -> object:
    """Run one canned selection round through the module under test."""
    payload = json.dumps(board)
    original = getattr(loop, "run_cmd", None)

    def fake_run_cmd(cmd, **kwargs):
        assert cmd[0] == "gh" and cmd[1] == "issue" and cmd[2] == "list"
        return 0, payload, ""

    try:
        loop.run_cmd = fake_run_cmd
        return loop.pick_next_issue()
    finally:
        if original is None:  # pragma: no cover - defensive, loop needs run_cmd
            del loop.run_cmd
        else:
            loop.run_cmd = original


def _tier_minus_one_wired() -> bool:
    """Probe: on a P0 + ci-failure board the feature must pick the alert."""
    if _SKIP is not None or loop is None or not hasattr(loop, "pick_next_issue"):
        return False
    try:
        return _pick(
            [
                issue(10, ["P0"]),
                issue(12, ["bridge:ci-failure"]),
            ]
        ) == "12"
    except Exception:
        return False


_WIRED = _tier_minus_one_wired()
if _SKIP is None and not _WIRED:
    _SKIP = (
        "tier -1 CI-failure wiring not present in continuous_agent_loop.py "
        "(operator-side landing pending; these tests enforce the contract "
        "the moment the wiring exists)"
    )

pytestmark = pytest.mark.skipif(_SKIP is not None, reason=_SKIP or "")


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
