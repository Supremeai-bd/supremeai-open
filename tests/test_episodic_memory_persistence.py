#!/usr/bin/env python3
"""tests/test_episodic_memory_persistence.py — persistence root-cause regression.

Live evidence (2026-10-30, Job 486718, dispatch #2281): store_episode() only
mutated the process-local episode list — every agent_solution_memory record/gap
call printed success while the collective knowledge plane stayed empty, so the
next process's search_database_memory() always returned zero hits. The fix
persists episodes best-effort through the ChromaDBStore (chroma or TF-IDF
fallback JSON) and merges persisted hits back in query-mode recall.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_episodic_memory_persistence.py
  - stdlib:  python3 tests/test_episodic_memory_persistence.py

Fully OFFLINE: a temp-directory ChromaDBStore (chroma present or TF-IDF
fallback) carries the persistence; no network, no repo data dir.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CORE = str(REPO_ROOT / "core")
# Order-immune resolution: full-suite collection lets earlier satellite test
# modules prepend their own dirs (gateway/tests/test_stealth_dns_guards.py
# prepends gateway/ — its own header comment documents this drift class).
# core/memory/ (package) and gateway/memory.py (module) share the top-level
# name `memory`; a fresh `from memory... import` while gateway/ sits in front
# resolves to the MODULE and dies with "'memory' is not a package". Keep core/
# pinned at sys.path[0] so the canonical core package always wins the search.
if _CORE in sys.path:
    if sys.path.index(_CORE) != 0:
        sys.path.remove(_CORE)
        sys.path.insert(0, _CORE)
else:
    sys.path.insert(0, _CORE)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(1, str(REPO_ROOT))

from memory.chromadb_store import ChromaDBStore
from memory.episodic_memory import EpisodicMemory


def _make_store(tmp: str) -> ChromaDBStore:
    return ChromaDBStore(collection_name="epi_persist_test", db_path=str(Path(tmp) / "store"))


class TestStoreEpisodePersists(unittest.TestCase):
    """Acceptance: a stored episode reaches the persistent vector store."""

    def test_store_episode_writes_vector_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            em = EpisodicMemory(vector_store=store)
            ep = em.store_episode(
                event_type="solution",
                context="PowerShell cp1252 stdout fails on UTF-8 emojis",
                outcome="set PYTHONIOENCODING=utf-8",
                importance=1.0,
                success=True,
                tags=["windows", "encoding"],
                metadata={"task_id": "999", "status": "VERIFIED"},
            )
            # deterministic upsert id for task-backed records
            self.assertEqual(ep.get("doc_id"), "episode_999")
            hits = store.query(query_text="UTF-8 emojis cp1252", n_results=5)
            self.assertTrue(hits, "episode must be readable from the persistent store")
            doc_id, _score, doc = hits[0]
            self.assertEqual(doc_id, "episode_999")
            self.assertEqual(doc["metadata"].get("task_id"), "999")
            self.assertEqual(doc["metadata"].get("event_type"), "solution")

    def test_persistence_failure_does_not_break_write_contract(self):
        class ExplodingStore:
            def add_document(self, *a, **kw):
                raise RuntimeError("disk full")

            def query(self, *a, **kw):
                return []

        em = EpisodicMemory(vector_store=ExplodingStore())
        ep = em.store_episode(event_type="solution", context="ctx", outcome="out")
        self.assertEqual(ep["status"], "ok")
        self.assertEqual(len(em._episodes), 1, "session memory must still receive the episode")
        self.assertNotIn("doc_id", ep)


class TestCrossProcessRecall(unittest.TestCase):
    """Acceptance: a fresh process recalls what an earlier process stored."""

    def test_recall_after_reinstantiation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            writer = EpisodicMemory(vector_store=store)
            writer.store_episode(
                event_type="solution",
                context="PowerShell cp1252 stdout fails on UTF-8 emojis",
                outcome="set PYTHONIOENCODING=utf-8",
                metadata={"task_id": "999"},
            )
            # fresh reader over the same persistent path — the pre-fix defect:
            # this recall always returned [] because only the volatile list existed
            reader = EpisodicMemory(vector_store=_make_store(tmp))
            hits = reader.recall_episodes(query="UTF-8 emojis cp1252 encoding")
            self.assertTrue(hits, "persisted episode must be recallable cross-process")
            top = hits[0]
            self.assertIn("UTF-8", top["context"])
            self.assertEqual(top["outcome"], "set PYTHONIOENCODING=utf-8")
            self.assertEqual(top["task_id"], "999")
            self.assertEqual(top["event_type"], "solution")
            self.assertEqual(top["source"], "vector_store")

    def test_event_type_filter_applies_to_persisted_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = EpisodicMemory(vector_store=_make_store(tmp))
            writer.store_episode(
                event_type="solution",
                context="solution context alpha",
                outcome="works",
                metadata={"task_id": "11"},
            )
            writer.store_episode(
                event_type="solution_gap",
                context="gap context beta",
                outcome="no capability",
                metadata={"task_id": "12"},
            )
            reader = EpisodicMemory(vector_store=_make_store(tmp))
            gaps = reader.recall_episodes(query="context", event_type="solution_gap")
            self.assertTrue(gaps)
            self.assertTrue(all(g["event_type"] == "solution_gap" for g in gaps))

    def test_task_backed_rerecord_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            em = EpisodicMemory(vector_store=store)
            em.store_episode(event_type="solution", context="c1", outcome="o1", metadata={"task_id": "7"})
            em.store_episode(event_type="solution", context="c2", outcome="o2", metadata={"task_id": "7"})
            hits = em.recall_episodes(query="c", limit=10)
            # dedupe on task_id: the two same-task records collapse to one hit
            def _describes_task7(h):
                return str(h.get("task_id") or "") == "7" or str(
                    (h.get("metadata") or {}).get("task_id") or ""
                ) == "7"
            self.assertEqual(sum(1 for h in hits if _describes_task7(h)), 1,
                             "same-task records dedupe on task_id")


class TestContractPreservation(unittest.TestCase):
    """Acceptance: pre-fix call shapes keep working (no consumer breakage)."""

    def test_recall_without_query_stays_session_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            em = EpisodicMemory(vector_store=_make_store(tmp))
            em.store_episode(event_type="solution", context="session only", outcome="o")
            hits = em.recall_episodes()
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["episode_id"], "ep_1")
            self.assertNotIn("source", hits[0], "session hits keep their pre-fix shape")

    def test_record_task_keeps_rich_doc_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _make_store(tmp)
            em = EpisodicMemory(vector_store=store)
            ok = asyncio.run(
                em.record_task(task_id="t-1", prompt="P", response="R", success=True)
            )
            self.assertTrue(ok)
            hits = store.query(query_text="Prompt", n_results=5)
            self.assertEqual(len(hits), 1, "record_task must persist exactly one rich doc")
            _doc_id, _score, doc = hits[0]
            self.assertEqual(doc["text"], "Prompt: P\nResponse: R")
            self.assertEqual(doc["metadata"].get("task_id"), "t-1")

    def test_store_episode_return_shape_additive_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            em = EpisodicMemory(vector_store=_make_store(tmp))
            ep = em.store_episode(event_type="general", context="c", outcome="o")
            for key in ("status", "episode_id", "id", "event_type", "context", "outcome",
                        "importance", "success", "latency_ms", "tags", "timestamp"):
                self.assertIn(key, ep, f"pre-fix key {key} must survive")


if __name__ == "__main__":
    unittest.main(verbosity=2)
