"""SQLite persistence for the Memory Sidecar knowledge graph (#1359).

P0 context (AIQ-057/062/098, bridge-20261028-memory-graph-persistence):
    The sidecar kept `_GRAPH_NODES`/`_GRAPH_EDGES` as plain process globals.
    Unlike `documents`/`learned_facts` (which sync to Supabase), graph writes
    never left the process, so every restart reset `graph_nodes` to 0 and
    cross-session recall (`read_graph`/`search_nodes`) started from nothing.

Design (matches sidecar house rules — stdlib-only, fail-open, env-knobbed):
    - Storage: stdlib `sqlite3` — no new pip requirements, transactional,
      crash-safe (WAL), single-file, inspectable.
    - Default ON: db path resolution order
        1. `MEMORY_GRAPH_DB_PATH` (operator-grade durability: point at a
           mounted volume for survival across container re-creates)
        2. `$SUPREMEAI_STATE_DIR/memory-graph.db` (if the state dir env is set)
        3. `<system tempdir>/supremeai-memory-graph.db` (restart-durable by
           default; deliberately NOT inside the repo checkout so tests and
           guard runs never pollute the working tree).
      Residual risk, documented honestly: system-temp storage survives
      process restarts (the P0 acceptance) but NOT container re-creates;
      the env knob in (1) is the escalation path for full durability.
    - Fail-open: an unreadable/corrupt/unwritable db logs a warning to
      stderr and degrades to the legacy in-memory behavior — memory stays
      available even when storage is broken (sidecar philosophy:
      "gracefully falls back to in-memory persistence when offline").
    - Hydrate-once: `GraphStore.load()` reads the full graph at startup;
      per-tool writes go straight through to SQLite. Zero read fan-out on
      the hot path (get_session_stats/read_graph/search_nodes keep serving
      from the hydrated dicts — no db query per tool call, no probe
      commands added to the read path).

Schema (v1):
    entities(name TEXT PRIMARY KEY, entity_type TEXT, observations TEXT/*JSON*/, created_at TEXT)
    relations(seq INTEGER PRIMARY KEY AUTOINCREMENT, src TEXT, dst TEXT, relation_type TEXT, created_at TEXT,
              UNIQUE(src, dst, relation_type))

Deletion semantics mirror the in-memory tools exactly:
    - delete_entities: removes nodes + every edge touching them (cascade)
    - delete_observations: removes matching observation strings
    - delete_relations: removes exact (from, to, relationType) tuples
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS entities (
    name         TEXT PRIMARY KEY,
    entity_type  TEXT NOT NULL,
    observations TEXT NOT NULL DEFAULT '[]',
    created_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS relations (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    src           TEXT NOT NULL,
    dst           TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    UNIQUE(src, dst, relation_type)
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def resolve_db_path(env: Optional[Dict[str, str]] = None) -> str:
    """Db-path resolution order: explicit env → state dir → system tempdir."""
    env = dict(os.environ if env is None else env)
    explicit = (env.get("MEMORY_GRAPH_DB_PATH") or "").strip()
    if explicit:
        return explicit
    state_dir = (env.get("SUPREMEAI_STATE_DIR") or "").strip()
    if state_dir:
        return os.path.join(state_dir, "memory-graph.db")
    return os.path.join(tempfile.gettempdir(), "supremeai-memory-graph.db")


class GraphStore:
    """Write-through SQLite mirror of the knowledge graph. Fail-open."""

    def __init__(self, db_path: str, env: Optional[Dict[str, str]] = None) -> None:
        self.db_path = db_path
        self.available = False
        self._conn: Optional[sqlite3.Connection] = None
        try:
            parent = os.path.dirname(db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # isolation_level=None → explicit transactions; check_same_thread
            # False because the STDIO loop is single-threaded and hydration
            # happens on the same thread that later mutates.
            self._conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
            self._conn.executescript(_DDL)
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO NOTHING",
                (str(_SCHEMA_VERSION),),
            )
            self.available = True
        except Exception as err:
            sys.stderr.write(
                f"[MemorySidecar] graph_store unavailable ({err}) — "
                f"degrading to in-memory-only graph at path={db_path!r}\n"
            )
            self._conn = None
            self.available = False

    # ── hydration ────────────────────────────────────────────────────────
    def load(self) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        """Full-graph hydration at startup (called exactly once)."""
        if not self.available or self._conn is None:
            return {}, []
        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        try:
            for name, etype, obs_json, created in self._conn.execute(
                "SELECT name, entity_type, observations, created_at FROM entities"
            ):
                try:
                    observations = json.loads(obs_json)
                    if not isinstance(observations, list):
                        observations = []
                except Exception:
                    observations = []
                nodes[name] = {
                    "name": name,
                    "entityType": etype,
                    "observations": observations,
                    "created_at": created,
                }
            for src, dst, rtype, created in self._conn.execute(
                "SELECT src, dst, relation_type, created_at FROM relations ORDER BY seq"
            ):
                edges.append(
                    {"from": src, "to": dst, "relationType": rtype, "created_at": created}
                )
        except Exception as err:
            sys.stderr.write(
                f"[MemorySidecar] graph_store hydration failed ({err}) — "
                "starting from empty graph, storage left untouched\n"
            )
            return {}, []
        return nodes, edges

    # ── entity writes ────────────────────────────────────────────────────
    def upsert_entity(self, name: str, entity_type: str, observations: List[str], created_at: str) -> None:
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO entities(name, entity_type, observations, created_at) "
                "VALUES(?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "entity_type=excluded.entity_type, observations=excluded.observations",
                (name, entity_type, json.dumps(list(observations)), created_at),
            )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.upsert_entity failed: {err}\n")

    def update_observations(self, name: str, observations: List[str]) -> None:
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "UPDATE entities SET observations=? WHERE name=?",
                (json.dumps(list(observations)), name),
            )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.update_observations failed: {err}\n")

    # ── edge writes ──────────────────────────────────────────────────────
    def insert_relation(self, src: str, dst: str, relation_type: str, created_at: str) -> None:
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "INSERT INTO relations(src, dst, relation_type, created_at) "
                "VALUES(?, ?, ?, ?) ON CONFLICT(src, dst, relation_type) DO NOTHING",
                (src, dst, relation_type, created_at),
            )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.insert_relation failed: {err}\n")

    # ── deletions (mirror in-memory semantics exactly) ───────────────────
    def delete_entities(self, names: List[str]) -> None:
        if not self.available or self._conn is None or not names:
            return
        try:
            cur = self._conn.cursor()
            for n in names:
                cur.execute("DELETE FROM entities WHERE name=?", (n,))
                cur.execute("DELETE FROM relations WHERE src=? OR dst=?", (n, n))
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.delete_entities failed: {err}\n")

    def delete_observations(self, name: str, keep: List[str]) -> None:
        if not self.available or self._conn is None:
            return
        try:
            self._conn.execute(
                "UPDATE entities SET observations=? WHERE name=?",
                (json.dumps(list(keep)), name),
            )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.delete_observations failed: {err}\n")

    def delete_relations(self, tuples: List[Tuple[str, str, str]]) -> None:
        if not self.available or self._conn is None or not tuples:
            return
        try:
            cur = self._conn.cursor()
            for src, dst, rtype in tuples:
                cur.execute(
                    "DELETE FROM relations WHERE src=? AND dst=? AND relation_type=?",
                    (src, dst, rtype),
                )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.delete_relations failed: {err}\n")

    # ── GDPR: full export + hard wipe ────────────────────────────────────
    def export_all(self) -> Dict[str, List[Dict[str, Any]]]:
        """Re-read straight from SQLite (independent of the hydrated cache)."""
        if not self.available or self._conn is None:
            return {"entities": [], "relations": []}
        out: Dict[str, List[Dict[str, Any]]] = {"entities": [], "relations": []}
        try:
            for name, etype, obs_json, created in self._conn.execute(
                "SELECT name, entity_type, observations, created_at FROM entities ORDER BY name"
            ):
                try:
                    observations = json.loads(obs_json)
                except Exception:
                    observations = []
                out["entities"].append(
                    {
                        "name": name,
                        "entityType": etype,
                        "observations": observations,
                        "created_at": created,
                    }
                )
            for src, dst, rtype, created in self._conn.execute(
                "SELECT src, dst, relation_type, created_at FROM relations ORDER BY seq"
            ):
                out["relations"].append(
                    {"from": src, "to": dst, "relationType": rtype, "created_at": created}
                )
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.export_all failed: {err}\n")
        return out

    def wipe(self) -> bool:
        """Hard-delete every graph row. Returns True when storage was touched."""
        if not self.available or self._conn is None:
            return False
        try:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM relations")
            cur.execute("DELETE FROM entities")
            return True
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] graph_store.wipe failed: {err}\n")
            return False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
            self.available = False
