#!/usr/bin/env python3
"""tests/test_tower_queue_tool_name_epochs.py — rename-wave oscillation tolerance guard.

Failure class being locked out (wave-3, live 2026-10-31, GLM Agent 31):

  The tower's tool registry OSCILLATES between spellings across deploys —
  wave 1 (2026-10-29, #2454 r3): underscore → dotted
  (``bridge_work_queue`` → ``bridge.work_queue``; #2457 response);
  wave 3 (2026-10-31 ~21:45Z, live-verified): dotted → underscore again —
  the dotted form answered ``MCP error -32602: Tool bridge.work_queue not
  found`` while ``bridge_work_queue`` served 67 rows in the same minute.
  Callers that hardcode ONE spelling go silently dark on every opposite
  wave (the rename-wave caller debt class of
  tests/test_tower_tool_name_drift.py — that guard pins per-wave DEAD
  names, but an oscillating name cannot be pinned one-directionally).
  Root cause fixed here: the loop's two tower-queue call sites now try
  every documented spelling in order and fail closed on the last error —
  the class "opposite wave breaks the call site" cannot recur without a
  THIRD spelling, and a third spelling is a one-line candidate append.

  This guard pins the tolerance machinery itself: candidate list shape,
  first-live-wins order, last-error re-raise (honest fail-closed), and
  the not-found envelope predicate (both JSON-RPC error and isError-text
  shapes).

বাংলা সারসংক্ষেপ:
------------------
টাওয়ারের টুল-নাম ডিপ্লয়ে দুলে (ঢেউ-১: underscore→dotted; ঢেউ-৩: dotted→underscore)।
এক বানান hardcode প্রতি বিপরীত ঢেউয়ে কলারকে নীরবে অন্ধ করে। এই গার্ড লুপের
নাম-সহনশীলতা যন্ত্রটাই পিন করে: প্রার্থী-তালিকা, প্রথম-জীবিত-জয়ী ক্রম, শেষ-ত্রুটি
পুনঃউত্থান (সৎ fail-closed), আর not-found envelope-এর দুই আকৃতিই শনাক্তকারী predicate।

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):
  - pytest:  pytest tests/test_tower_queue_tool_name_epochs.py
  - stdlib:  python3 tests/test_tower_queue_tool_name_epochs.py

Every test is offline and deterministic (no network, no tower).
"""

from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "agents"))

import continuous_agent_loop as loop  # noqa: E402


def test_candidates_cover_both_documented_epochs() -> None:
    cands = loop.TOWER_QUEUE_TOOL_NAME_CANDIDATES
    assert isinstance(cands, tuple) and len(cands) >= 2
    assert "bridge.work_queue" in cands, "wave-1 epoch (2026-10-29..31) spelling missing"
    assert "bridge_work_queue" in cands, "wave-3 epoch (2026-10-31..) spelling missing"
    assert len(set(cands)) == len(cands), "duplicate spellings waste a retry"


def test_first_live_spelling_wins_without_retry() -> None:
    calls: list[str] = []

    def call_by_name(name: str) -> str:
        calls.append(name)
        if name == "bridge.work_queue":
            return "dotted-ok"
        raise AssertionError("second candidate must not be called after first live")

    assert loop.call_tool_across_rename_epochs(call_by_name) == "dotted-ok"
    assert calls == ["bridge.work_queue"]


def test_dead_first_spelling_falls_through_to_second() -> None:
    calls: list[str] = []

    def call_by_name(name: str) -> str:
        calls.append(name)
        if name == "bridge.work_queue":
            raise RuntimeError("RPC error -32602: Tool bridge.work_queue not found")
        return "underscore-ok"

    assert loop.call_tool_across_rename_epochs(call_by_name) == "underscore-ok"
    assert calls == ["bridge.work_queue", "bridge_work_queue"]


def test_dead_spelling_via_iserror_content_falls_through() -> None:
    # লাইভ আকৃতি (2026-10-31): টাওয়ার মৃত-নামে JSON-RPC error নয় — HTTP-200
    # success envelope-এর isError content-text-এ ব্যর্থতা বহন করে।
    calls: list[str] = []

    def call_by_name(name: str) -> dict:
        calls.append(name)
        if name == "bridge.work_queue":
            return {
                "isError": True,
                "content": [{"type": "text", "text": "MCP error -32602: Tool bridge.work_queue not found"}],
            }
        return {
            "content": [{"type": "text", "text": "{\"workOrders\": [], \"totalOpen\": 67}"}],
        }

    resp = loop.call_tool_across_rename_epochs(call_by_name)
    assert isinstance(resp, dict) and "workOrders" in str(resp)
    assert calls == ["bridge.work_queue", "bridge_work_queue"]
    assert loop.envelope_says_tool_not_found(resp) is False, "live payload must not read as not-found"


def test_all_dead_re_raises_last_error_fail_closed() -> None:
    class WaveError(RuntimeError):
        pass

    def call_by_name(name: str) -> str:
        raise WaveError(f"dead in this epoch: {name}")

    try:
        loop.call_tool_across_rename_epochs(call_by_name)
    except WaveError as exc:
        assert "bridge_work_queue" in str(exc), "must re-raise the LAST attempt's error"
    else:  # pragma: no cover
        raise AssertionError("all-dead must raise (no silent green)")


def test_not_found_predicate_both_shapes() -> None:
    # JSON-RPC error envelope shape (code -32602)
    assert loop.is_tool_not_found_error_env(
        {"error": {"code": -32602, "message": "Tool bridge.work_queue not found"}}
    )
    # message-only shape
    assert loop.is_tool_not_found_error_env(
        {"error": {"message": "MCP error -32602: Tool bridge.work_queue not found"}}
    )
    # not an error envelope → False
    assert not loop.is_tool_not_found_error_env({"result": {"content": []}})
    assert not loop.is_tool_not_found_error_env("MCP error -32602: ...")
    # a DIFFERENT error (e.g. RBAC Forbidden) must NOT read as not-found
    assert not loop.is_tool_not_found_error_env(
        {"error": {"code": -32000, "message": "Forbidden: role 'viewer' ..."}}
    )


def test_not_found_predicate_success_envelope_iserror_text() -> None:
    # লাইভ আকৃতি: success envelope (কোনো 'error' কি নেই) কিন্তু isError-text
    assert loop.envelope_says_tool_not_found(
        {"isError": True, "content": [{"type": "text", "text": "MCP error -32602: Tool bridge.work_queue not found"}]}
    )
    assert loop.envelope_says_tool_not_found(
        {"content": [{"type": "text", "text": "Tool bridge_work_queue not found (-32602)"}]}
    )
    # প্রকৃত পেলোড (error-free, বড় JSON text) → False
    assert not loop.envelope_says_tool_not_found(
        {"content": [{"type": "text", "text": "{\"workOrders\": [{\"number\": 1}], \"totalOpen\": 67}"}]}
    )
    # RBAC-জাতীয় অন্য ব্যর্থতা → False (not-found নয়)
    assert not loop.envelope_says_tool_not_found(
        {"isError": True, "content": [{"type": "text", "text": "Forbidden: role 'viewer' has no repository read access"}]}
    )


def main() -> int:
    tests = [
        test_candidates_cover_both_documented_epochs,
        test_first_live_spelling_wins_without_retry,
        test_dead_first_spelling_falls_through_to_second,
        test_dead_spelling_via_iserror_content_falls_through,
        test_all_dead_re_raises_last_error_fail_closed,
        test_not_found_predicate_both_shapes,
        test_not_found_predicate_success_envelope_iserror_text,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
