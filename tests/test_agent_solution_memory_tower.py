#!/usr/bin/env python3
"""tests/test_agent_solution_memory_tower.py — offline suite for the #1747 slice 1.

Wires the tower semantic-memory tier into agent_solution_memory (#1747):
fallback-when-thin, tier labels on every hit, graceful degradation,
additive provenance stamping.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_agent_solution_memory_tower.py
  - stdlib:  python3 tests/test_agent_solution_memory_tower.py

Fully OFFLINE: the tower transport (urllib) and the episodic-memory import
are stubbed via unittest.mock / sys.modules — no network, no data dir.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = REPO_ROOT / "scripts" / "agents" / "agent_solution_memory.py"

_spec = importlib.util.spec_from_file_location("agent_solution_memory", _SCRIPT)
asm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asm)


# --- helpers ---------------------------------------------------------------

def sse_body(result: dict, msg_id: int = 1) -> str:
    """Build an SSE body carrying one MCP result payload."""
    payload = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    return "event: message\ndata: " + json.dumps(payload) + "\n\n"


def tool_result(items_json: str) -> dict:
    """Wrap a JSON text payload as an MCP tools/call result."""
    return {"content": [{"type": "text", "text": items_json}]}


class FakeResponse:
    """Minimal urlopen() stand-in: SSE body + session header."""

    def __init__(self, body: str, session_id: str = "sess-1"):
        self._body = body
        self.status = 200
        self.headers = {"mcp-session-id": session_id}

    def read(self) -> bytes:
        return self._body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_fake_episodic(episodes: list[dict]) -> list[list]:
    """Inject a fake memory.episodic_memory package; returns call recorder."""
    calls: list[list] = []

    class FakeEpisodicMemory:
        def __init__(self, db_path=None):
            self.db_path = db_path

        def recall_episodes(self, query):
            calls.append(episodes)
            return episodes

        def store_episode(self, **kw):  # pragma: no cover - used by record tests
            calls.append([kw])

    pkg = types.ModuleType("memory")
    pkg.__path__ = []
    mod = types.ModuleType("memory.episodic_memory")
    mod.EpisodicMemory = FakeEpisodicMemory
    sys.modules["memory"] = pkg
    sys.modules["memory.episodic_memory"] = mod
    return calls


# --- tests -----------------------------------------------------------------

class TestTierLabels(unittest.TestCase):
    """Acceptance: output labels every hit's tier."""

    def test_lessons_hits_carry_tier(self):
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
            fh.write("| Date | Task | Problem | Solution | Lesson |\n")
            fh.write("| :--- | :--- | :--- | :--- | :--- |\n")
            fh.write("| 2026-10-28 | #1 | UnicodeEncodeError charmap | set PYTHONIOENCODING | always |\n")
            path = fh.name
        try:
            with mock.patch.object(asm, "LESSONS_FILE", Path(path)):
                hits = asm.search_local_lessons("UnicodeEncodeError")
        finally:
            Path(path).unlink(missing_ok=True)
        self.assertTrue(hits)
        for hit in hits:
            self.assertEqual(hit["tier"], "lessons-file")

    def test_local_episodic_hits_carry_tier(self):
        install_fake_episodic([{
            "task_id": "9", "event_type": "solution",
            "context": "p", "outcome": "s", "success": True,
        }])
        hits = asm.search_database_memory("anything")
        # No tower stub installed here, but local hits already meet threshold? No:
        # one hit < default threshold 3 -> tower fallback attempted. Offline test:
        # tower is unreachable, degrade path appends nothing, local hit survives.
        self.assertEqual([h["tier"] for h in hits if h.get("tier") == "local-episodic"],
                         ["local-episodic"])


class TestFallbackWiring(unittest.TestCase):
    """Acceptance: fallback fires only when local recall is thin."""

    def test_no_fallback_when_local_recall_rich(self):
        install_fake_episodic([{"task_id": str(i), "context": "p", "outcome": "s"}
                               for i in range(5)])
        with mock.patch.object(asm, "_tower_semantic_hits") as stub:
            hits = asm.search_database_memory("q")
        stub.assert_not_called()
        self.assertEqual(len(hits), 5)

    def test_fallback_fires_when_recall_thin(self):
        install_fake_episodic([])
        with mock.patch.object(asm, "_tower_semantic_hits",
                               return_value=[{"tier": "tower-semantic", "task_id": "t",
                                              "type": "semantic", "problem": "p",
                                              "solution": "", "success": True,
                                              "source": "tower:memory_search_semantic"}]) as stub:
            hits = asm.search_database_memory("q")
        stub.assert_called_once()
        self.assertEqual(hits[0]["tier"], "tower-semantic")

    def test_degrade_path_local_only_warn_exit0(self):
        """Tower unreachable -> local-only results, warn line, never a crash."""
        install_fake_episodic([{"task_id": "1", "context": "p", "outcome": "s"}])
        err = io.StringIO()
        with mock.patch.object(asm, "_tower_semantic_hits",
                               side_effect=RuntimeError("tower HTTP 503")):
            with redirect_stderr(err):
                hits = asm.search_database_memory("q")
        self.assertEqual(len(hits), 1)  # local hit survives
        self.assertIn("[WARN] Tower semantic tier unavailable", err.getvalue())

    def test_threshold_env_overridable(self):
        # 5 local hits < raised threshold 10 -> fallback still fires.
        with mock.patch.dict("os.environ", {"MEMORY_TOWER_FALLBACK_MIN_HITS": "10"}):
            install_fake_episodic([{"task_id": str(i)} for i in range(5)])
            with mock.patch.object(asm, "_tower_semantic_hits") as stub:
                asm.search_database_memory("q")
            stub.assert_called_once()


class TestTowerSessionProtocol(unittest.TestCase):
    """initialize -> Mcp-Session-Id -> tools/call (examples client session pattern)."""

    def test_session_sequence_and_tool_names(self):
        calls: list[tuple[str, str | None, str | None]] = []

        def fake_urlopen(req, timeout=None):
            headers = dict(req.header_items())
            sid = headers.get("mcp-session-id") or headers.get("Mcp-session-id")
            payload = json.loads(req.data.decode("utf-8"))
            method = payload.get("method", "tools/call")
            tool = payload.get("params", {}).get("name") if method == "tools/call" else None
            calls.append((method, sid, tool))
            if method == "initialize":
                return FakeResponse(sse_body({"content": []}), session_id="sess-9")
            if method == "tools/call":
                if tool == "memory_search_semantic":
                    return FakeResponse(sse_body(tool_result(json.dumps(
                        {"results": [{"task_id": "t1", "text": "hit one"}]}))),
                        session_id="sess-9")
                return FakeResponse(sse_body(tool_result(json.dumps(
                    {"tasks": []}))), session_id="sess-9")
            return FakeResponse("", session_id="sess-9")  # notifications/initialized

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            hits = asm._tower_semantic_hits("deploy stuck")

        # methods: initialize, notifications/initialized, 2 x tools/call
        self.assertEqual([m for m, _, _ in calls],
                         ["initialize", "notifications/initialized", "tools/call", "tools/call"])
        self.assertIsNone(calls[0][1])            # initialize carries no session yet
        self.assertEqual(calls[1][1], "sess-9")   # initialized now carries it
        self.assertEqual(calls[2][2], "memory_search_semantic")
        self.assertEqual(calls[3][2], "memory_get_similar_tasks")
        self.assertEqual(hits[0]["task_id"], "t1")

    def test_result_mapping_and_tiers(self):
        def fake_urlopen(req, timeout=None):
            payload = json.loads(req.data.decode("utf-8"))
            if payload.get("method") == "initialize":
                return FakeResponse(sse_body({"content": []}), session_id="s")
            if payload.get("method") == "tools/call":
                name = payload["params"]["name"]
                if name == "memory_search_semantic":
                    return FakeResponse(sse_body(tool_result(json.dumps(
                        {"results": [{"task_id": "t1", "text": "hit one", "solution": "do x"}]}))),
                        session_id="s")
                return FakeResponse(sse_body(tool_result(json.dumps(
                    {"tasks": [{"id": "t2", "summary": "task two"}]}))), session_id="s")
            return FakeResponse("", session_id="s")

        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            hits = asm._tower_semantic_hits("q")
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0]["tier"], "tower-semantic")
        self.assertEqual(hits[0]["source"], "tower:memory_search_semantic")
        self.assertEqual(hits[0]["problem"], "hit one")
        self.assertEqual(hits[0]["solution"], "do x")
        self.assertEqual(hits[1]["tier"], "tower-similar-tasks")
        self.assertEqual(hits[1]["task_id"], "t2")

    def test_wired_call_visible_in_source(self):
        """Acceptance: rg memory_search_semantic scripts/ shows the wired call."""
        src = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn("memory_search_semantic", src)
        self.assertIn("memory_get_similar_tasks", src)


class TestProvenanceStamping(unittest.TestCase):
    """Acceptance: record path stamps source/task_id/verified (schema-compatible)."""

    def test_record_solution_stamps_provenance(self):
        calls = install_fake_episodic([])
        with tempfile.TemporaryDirectory() as tmp:
            lessons = Path(tmp) / "LESSONS_LEARNED.md"
            lessons.write_text(
                "| Date | Task | Problem | Solution | Lesson |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n",
                encoding="utf-8",
            )
            with mock.patch.object(asm, "LESSONS_FILE", lessons):
                ok = asm.record_solution(task_id="#123", problem="p", solution="s",
                                         lesson="l", status="VERIFIED")
            self.assertTrue(ok)
            meta = calls[0][0]["metadata"]
            self.assertEqual(meta["source"], "agent_solution_memory")
            self.assertEqual(meta["task_id"], "123")
            self.assertTrue(meta["verified"])
            # LESSONS format untouched: pipe table row, date-first, task ref
            row = [ln for ln in lessons.read_text().splitlines() if "#123" in ln][0]
            self.assertTrue(row.startswith("| "))
            self.assertEqual(len(row.split("|")), 7)  # 5 columns -> 7 pipe-split cells

    def test_record_unverified_stamps_verified_false(self):
        calls = install_fake_episodic([])
        with tempfile.TemporaryDirectory() as tmp:
            lessons = Path(tmp) / "LESSONS_LEARNED.md"
            lessons.write_text(
                "| Date | Task | Problem | Solution | Lesson |\n"
                "| :--- | :--- | :--- | :--- | :--- |\n",
                encoding="utf-8",
            )
            with mock.patch.object(asm, "LESSONS_FILE", lessons):
                asm.record_solution(task_id="124", problem="p", solution="s",
                                    lesson="l", status="EXPERIMENTAL")
            self.assertFalse(calls[0][0]["metadata"]["verified"])

    def test_record_gap_stamps_source(self):
        calls = install_fake_episodic([])
        asm.record_solution_gap(task_id="125", problem="p", failed_attempts="f",
                                missing_capability="m", future_path="fp")
        self.assertEqual(calls[0][0]["metadata"]["source"], "agent_solution_memory")


# --- stdlib runner ----------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
