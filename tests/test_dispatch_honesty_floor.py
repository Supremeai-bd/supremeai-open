#!/usr/bin/env python3
"""Offline contract tests for the R61/#2318 dispatch honesty floor.

Covers _tower_queue_floor() failure modes only — the live tower probe is
network I/O and stays out of unit scope; the gh-present path never calls it.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


class _FakeReachableClient:
    """Stands in for McpTowerClient when the tower is reachable.

    Returns the raw MCP envelope shape call_tool actually produces:
    the queue dict rides as JSON inside content[0].text.
    """

    def connect(self) -> None:
        return None

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        assert name == "bridge_work_queue"
        import json as _json

        payload = _json.dumps(
            {"count": 20, "totalOpen": 87, "windowTruncated": True, "nextStep": "n/a"}
        )
        return {"content": [{"type": "text", "text": payload}]}


class _FakeParsedDictClient:
    """Defensive shape: a future client that returns the parsed dict directly."""

    def connect(self) -> None:
        return None

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return {"count": 20, "totalOpen": 87, "windowTruncated": True}


class _FakeShapelessClient:
    """Tower reachable but payload lacks the totalOpen echo (pre-#2316 shape)."""

    def connect(self) -> None:
        return None

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        return {"count": 20}


def _with_fake_client(monkey_patch_target: str, fake_cls: type) -> None:
    """Install a fake mcp_tower_client module on the import path."""
    import types

    fake_mod = types.ModuleType("mcp_tower_client")
    fake_mod.McpTowerClient = fake_cls
    sys.modules[monkey_patch_target] = fake_mod


class TestTowerQueueFloor(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = sys.modules.get("mcp_tower_client")

    def tearDown(self) -> None:
        if self._saved is not None:
            sys.modules["mcp_tower_client"] = self._saved
        else:
            sys.modules.pop("mcp_tower_client", None)

    def test_reachable_tower_reports_live_count(self) -> None:
        _with_fake_client("mcp_tower_client", _FakeReachableClient)
        note = cal._tower_queue_floor(timeout_s=5.0)
        self.assertIn("87 open work orders", note)
        self.assertIn("P0-drainage gate", note)
        self.assertIn("dark", note)

    def test_parsed_dict_shape_also_accepted(self) -> None:
        _with_fake_client("mcp_tower_client", _FakeParsedDictClient)
        note = cal._tower_queue_floor(timeout_s=5.0)
        self.assertIn("87 open work orders", note)

    def test_payload_without_totolopen_degrades_to_p0_dark(self) -> None:
        _with_fake_client("mcp_tower_client", _FakeShapelessClient)
        note = cal._tower_queue_floor(timeout_s=5.0)
        self.assertIn("no totalOpen", note)
        self.assertIn("P0-drainage gate", note)

    def test_import_failure_degrades_to_p0_dark(self) -> None:
        # No fake installed AND any pre-existing real module removed -> the
        # lazy import itself must not be what breaks the floor. Point the
        # module at a class whose constructor explodes.
        class _BoomClient:
            def __init__(self, *a: object, **k: object) -> None:
                raise RuntimeError("boom")

        _with_fake_client("mcp_tower_client", _BoomClient)
        note = cal._tower_queue_floor(timeout_s=5.0)
        self.assertIn("probe failed (RuntimeError)", note)
        self.assertIn("P0-drainage gate", note)

    def test_hang_degrades_to_timeout_note(self) -> None:
        import threading
        import time as _time

        class _HangingClient:
            def connect(self) -> None:
                _time.sleep(30)

            def call_tool(self, name: str, arguments: dict | None = None) -> dict:
                return {}

        _with_fake_client("mcp_tower_client", _HangingClient)
        note = cal._tower_queue_floor(timeout_s=1.0)
        self.assertIn("timed out", note)
        self.assertIn("P0-drainage gate", note)
        # The daemon probe thread must not block the interpreter exit.
        self.assertLess(threading.active_count(), 64)

    def test_floor_not_invoked_on_gh_error_paths(self) -> None:
        # Source-level contract: the floor call is guarded by the exact
        # gh-absent error, so gh-present-but-erroring runtimes are untouched.
        src = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(encoding="utf-8")
        guard_idx = src.find('if board_error == "gh CLI not found on PATH"')
        floor_idx = src.find("_tower_queue_floor()")
        skip_idx = src.find("issue board unavailable (")
        self.assertGreater(guard_idx, -1, "gh-absent guard missing")
        self.assertGreater(floor_idx, guard_idx, "floor call must sit inside the gh-absent guard")
        self.assertGreater(skip_idx, -1)
        self.assertLess(skip_idx, guard_idx, "guard must follow the generic skip line")


if __name__ == "__main__":
    unittest.main()
