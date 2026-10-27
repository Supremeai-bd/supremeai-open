#!/usr/bin/env python3
"""SupremeAI Memory Sidecar MCP Server (STDIO).

Standard Model Context Protocol (MCP) server providing 20 memory tools
for Knowledge Graph, Vector Store, Episodic Memory, and Long-Term Facts.

Stdlib-only (Python 3.10+), zero external pip requirements.
Interfaces with Supabase REST API and Qdrant REST API when configured;
gracefully falls back to in-memory persistence when offline.
"""

from __future__ import annotations

import json
import os
import re as _re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any, Dict, List, Optional

# In-memory stores for offline fallback
_GRAPH_NODES: Dict[str, Dict[str, Any]] = {}
_GRAPH_EDGES: List[Dict[str, Any]] = []
_DOCUMENTS: List[Dict[str, Any]] = []
_LEARNED_FACTS: List[Dict[str, Any]] = []
_EPISODES: List[Dict[str, Any]] = []

# bridge-20261027-memory-graph-empty (#1341): TTL + recency policy for the
# in-memory episode store. Configurable via MEMORY_EPISODE_TTL_MS (<=0 disables).
_EPISODE_TTL_MS = int(os.environ.get("MEMORY_EPISODE_TTL_MS", "0") or 0)

# ── bridge-20261028-memory-graph-persistence (#1359) ──────────────────────
# P0: graph entities/relations were process-global only — every restart reset
# graph_nodes to 0 (AIQ-057/062/098). This wires a stdlib-SQLite write-through
# store: hydrate once at boot, persist on every mutation, degrade to the
# legacy in-memory graph if storage is unavailable (fail-open).
from graph_store import GraphStore, resolve_db_path  # noqa: E402

# Transient-entity TTL for the knowledge graph (task/topic nodes only; user
# created durable entities are never expired). <=0 disables (default).
_GRAPH_TTL_MS = int(os.environ.get("MEMORY_GRAPH_TTL_MS", "0") or 0)

_STORE = GraphStore(resolve_db_path())
try:
    _loaded_nodes, _loaded_edges = _STORE.load()
    if _loaded_nodes:
        _GRAPH_NODES.update(_loaded_nodes)
    if _loaded_edges:
        _GRAPH_EDGES.extend(_loaded_edges)
    if _loaded_nodes or _loaded_edges:
        sys.stderr.write(
            f"[MemorySidecar] graph hydrated from storage: "
            f"{len(_loaded_nodes)} entities, {len(_loaded_edges)} relations "
            f"({_STORE.db_path})\n"
        )
except Exception as _hydration_err:  # hydration must never kill the sidecar
    sys.stderr.write(f"[MemorySidecar] graph hydration skipped: {_hydration_err}\n")


def _node_ts_ms(node: Dict[str, Any]) -> float:
    _ts = str(node.get("created_at", ""))
    try:
        from datetime import datetime

        return datetime.fromisoformat(_ts.replace("Z", "+00:00")).timestamp() * 1000.0
    except Exception:
        return 0.0


def _prune_expired_graph(now_ms: Optional[float] = None) -> int:
    """Drop transient (task/topic) graph entities past MEMORY_GRAPH_TTL_MS.

    Durable entities (any entityType other than task/topic) are never
    auto-expired — only machine-generated working-set nodes age out.
    Mirrors the delete path so the persistent store stays in sync.
    """
    if _GRAPH_TTL_MS <= 0:
        return 0
    cutoff = (now_ms if now_ms is not None else time.time() * 1000.0) - _GRAPH_TTL_MS
    stale = [
        n
        for n, node in _GRAPH_NODES.items()
        if node.get("entityType") in ("task", "topic") and _node_ts_ms(node) < cutoff
    ]
    if not stale:
        return 0
    for n in stale:
        _GRAPH_NODES.pop(n, None)
    _GRAPH_EDGES[:] = [e for e in _GRAPH_EDGES if e.get("from") not in stale and e.get("to") not in stale]
    _STORE.delete_entities(stale)
    return len(stale)


def _episode_ts_ms(episode: Dict[str, Any]) -> float:
    _ts = str(episode.get("created_at", ""))
    try:
        from datetime import datetime

        return datetime.fromisoformat(_ts.replace("Z", "+00:00")).timestamp() * 1000.0
    except Exception:
        return 0.0


def _prune_expired(now_ms: Optional[float] = None) -> int:
    """Drop episodes past TTL (fail-loud knob: MEMORY_EPISODE_TTL_MS)."""
    if _EPISODE_TTL_MS <= 0:
        return 0
    import time as _time

    cutoff = (now_ms if now_ms is not None else _time.time() * 1000.0) - _EPISODE_TTL_MS
    before = len(_EPISODES)
    _EPISODES[:] = [e for e in _EPISODES if _episode_ts_ms(e) >= cutoff]
    return before - len(_EPISODES)



def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


SUPABASE_URL = _get_env("SUPABASE_URL")
SUPABASE_KEY = _get_env("SUPABASE_SERVICE_ROLE_KEY") or _get_env("SUPABASE_KEY")
QDRANT_URL = _get_env("QDRANT_URL")
QDRANT_KEY = _get_env("QDRANT_API_KEY")


def _supabase_request(table: str, method: str = "GET", data: Optional[Any] = None, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except Exception as err:
        sys.stderr.write(f"[MemorySidecar] Supabase error ({table}): {err}\n")
        return None


def _qdrant_request(endpoint: str, method: str = "GET", data: Optional[Any] = None) -> Optional[Any]:
    if not QDRANT_URL:
        return None
    url = f"{QDRANT_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if QDRANT_KEY:
        headers["api-key"] = QDRANT_KEY
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except Exception as err:
        sys.stderr.write(f"[MemorySidecar] Qdrant error ({endpoint}): {err}\n")
        return None


TOOLS_SCHEMA = [
    {
        "name": "create_entities",
        "description": "Create entities in the Knowledge Graph.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "entityType": {"type": "string"},
                            "observations": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "entityType"],
                    },
                }
            },
            "required": ["entities"],
        },
    },
    {
        "name": "create_relations",
        "description": "Create directed relations between entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "relationType": {"type": "string"},
                        },
                        "required": ["from", "to", "relationType"],
                    },
                }
            },
            "required": ["relations"],
        },
    },
    {
        "name": "add_observations",
        "description": "Add observations to an existing entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entityName": {"type": "string"},
                            "contents": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["entityName", "contents"],
                    },
                }
            },
            "required": ["observations"],
        },
    },
    {
        "name": "delete_entities",
        "description": "Delete entities and their relations.",
        "inputSchema": {
            "type": "object",
            "properties": {"entityNames": {"type": "array", "items": {"type": "string"}}},
            "required": ["entityNames"],
        },
    },
    {
        "name": "delete_observations",
        "description": "Remove observations from an entity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deletions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entityName": {"type": "string"},
                            "observations": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["entityName", "observations"],
                    },
                }
            },
            "required": ["deletions"],
        },
    },
    {
        "name": "delete_relations",
        "description": "Delete specific relations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "relations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from": {"type": "string"},
                            "to": {"type": "string"},
                            "relationType": {"type": "string"},
                        },
                        "required": ["from", "to", "relationType"],
                    },
                }
            },
            "required": ["relations"],
        },
    },
    {
        "name": "read_graph",
        "description": "Return the entire Knowledge Graph.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_nodes",
        "description": "Search Knowledge Graph nodes.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "open_nodes",
        "description": "Open specific nodes and relations.",
        "inputSchema": {
            "type": "object",
            "properties": {"names": {"type": "array", "items": {"type": "string"}}},
            "required": ["names"],
        },
    },
    {
        "name": "store_document",
        "description": "Store a document in the vector store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "search_semantic",
        "description": "Semantic search over vector store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ingest_document_rag",
        "description": "Chunk + ingest a document into RAG.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "chunk_size": {"type": "integer"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "record_task",
        "description": "Record a task execution into episodic memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "description": {"type": "string"},
                "result": {"type": "string"},
                "metadata": {"type": "object"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "get_similar_tasks",
        "description": "Retrieve similar past task executions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_recent_episodes",
        "description": "Retrieve recent episodic records.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
        },
    },
    {
        "name": "build_context",
        "description": "Build token-budget-aware context string.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "token_budget": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_session_stats",
        "description": "Sliding window stats for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
        },
    },
    {
        "name": "clear_session",
        "description": "Clear sliding window memory for a session.",
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string"}},
        },
    },
    {
        "name": "remember_fact",
        "description": "Save a long-term fact (Supabase/SQLite).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string"},
                "category": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["fact"],
        },
    },
    {
        "name": "search_learned_facts",
        "description": "Search stored long-term facts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "export_memory",
        "description": "Export all stored memory for a user (knowledge-graph entities + relations, episodes, documents, learned facts) as JSON — GDPR data-portability surface (AIQ-062/098).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "wipe_memory",
        "description": "GDPR-compliant hard wipe: deletes graph entities + relations (persistent store included) and, with scope=all, clears episodes, documents and learned facts (AIQ-098).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["all", "graph"], "description": "graph = knowledge graph only; all (default) = every memory lane"},
            },
        },
    },
]


def handle_tool(name: str, args: Dict[str, Any]) -> Any:
    global _GRAPH_EDGES
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # --- Knowledge Graph Tools ---
    if name == "create_entities":
        created = []
        for e in args.get("entities", []):
            ename = str(e.get("name", "")).strip()
            if ename:
                _GRAPH_NODES[ename] = {
                    "name": ename,
                    "entityType": e.get("entityType", "concept"),
                    "observations": list(e.get("observations", [])),
                    "created_at": now,
                }
                created.append(_GRAPH_NODES[ename])
                # (#1359) write-through: durable entity row (upsert)
                _STORE.upsert_entity(ename, _GRAPH_NODES[ename]["entityType"], _GRAPH_NODES[ename]["observations"], now)
        return {"created": created, "count": len(created)}

    elif name == "create_relations":
        created = []
        for r in args.get("relations", []):
            rel = {
                "from": str(r.get("from", "")).strip(),
                "to": str(r.get("to", "")).strip(),
                "relationType": str(r.get("relationType", "related")),
                "created_at": now,
            }
            if rel["from"] and rel["to"]:
                _GRAPH_EDGES.append(rel)
                created.append(rel)
                # (#1359) write-through: durable relation row (UNIQUE-deduped)
                _STORE.insert_relation(rel["from"], rel["to"], rel["relationType"], now)
        return {"created": created, "count": len(created)}

    elif name == "add_observations":
        updated = []
        for o in args.get("observations", []):
            ename = str(o.get("entityName", "")).strip()
            contents = list(o.get("contents", []))
            if ename in _GRAPH_NODES:
                _GRAPH_NODES[ename].setdefault("observations", []).extend(contents)
                updated.append(_GRAPH_NODES[ename])
                # (#1359) write-through: keep the stored observation list in sync
                _STORE.update_observations(ename, _GRAPH_NODES[ename].get("observations", []))
        return {"updated": updated, "count": len(updated)}

    elif name == "delete_entities":
        names = set(args.get("entityNames", []))
        for n in names:
            _GRAPH_NODES.pop(n, None)
        _GRAPH_EDGES = [e for e in _GRAPH_EDGES if e.get("from") not in names and e.get("to") not in names]
        # (#1359) write-through: cascade removal in the persistent store too
        _STORE.delete_entities(sorted(names))
        return {"deleted": list(names)}

    elif name == "delete_observations":
        for d in args.get("deletions", []):
            ename = str(d.get("entityName", "")).strip()
            obs = set(d.get("observations", []))
            if ename in _GRAPH_NODES:
                _GRAPH_NODES[ename]["observations"] = [o for o in _GRAPH_NODES[ename].get("observations", []) if o not in obs]
                # (#1359) write-through: persist the filtered observation list
                _STORE.delete_observations(ename, _GRAPH_NODES[ename]["observations"])
        return {"status": "ok"}

    elif name == "delete_relations":
        to_del = {(r.get("from"), r.get("to"), r.get("relationType")) for r in args.get("relations", [])}
        _GRAPH_EDGES = [e for e in _GRAPH_EDGES if (e.get("from"), e.get("to"), e.get("relationType")) not in to_del]
        # (#1359) write-through: exact-tuple removal in the persistent store
        _STORE.delete_relations(sorted(to_del))
        return {"status": "ok"}

    elif name == "read_graph":
        return {"entities": list(_GRAPH_NODES.values()), "relations": _GRAPH_EDGES}

    elif name == "search_nodes":
        q = str(args.get("query", "")).lower()
        matches = [n for n in _GRAPH_NODES.values() if q in n.get("name", "").lower() or any(q in o.lower() for o in n.get("observations", []))]
        return {"matches": matches, "count": len(matches)}

    elif name == "open_nodes":
        names = set(args.get("names", []))
        nodes = [_GRAPH_NODES[n] for n in names if n in _GRAPH_NODES]
        rels = [e for e in _GRAPH_EDGES if e.get("from") in names or e.get("to") in names]
        return {"entities": nodes, "relations": rels}

    # --- Vector & RAG Tools ---
    elif name == "store_document":
        doc_id = str(uuid.uuid4())
        doc = {
            "id": doc_id,
            "title": args.get("title", "Untitled Document"),
            "content": args.get("content", ""),
            "metadata": args.get("metadata", {}),
            "created_at": now,
        }
        _DOCUMENTS.append(doc)
        # Attempt Supabase sync
        _supabase_request("documents", method="POST", data=doc)
        return {"id": doc_id, "status": "stored", "title": doc["title"]}

    elif name == "search_semantic":
        q = str(args.get("query", "")).lower()
        limit = int(args.get("limit", 5))
        matches = [d for d in _DOCUMENTS if q in d.get("content", "").lower() or q in d.get("title", "").lower()][:limit]
        return {"results": matches, "query": q, "count": len(matches)}

    elif name == "ingest_document_rag":
        content = str(args.get("content", ""))
        title = str(args.get("title", "RAG Document"))
        chunk_size = int(args.get("chunk_size", 500))
        chunks = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]
        stored_chunks = []
        for idx, chunk in enumerate(chunks):
            cid = str(uuid.uuid4())
            item = {"id": cid, "title": f"{title} (Part {idx + 1})", "content": chunk, "chunk_index": idx}
            _DOCUMENTS.append(item)
            stored_chunks.append(item)
        return {"status": "ingested", "chunks_count": len(stored_chunks)}

    # --- Episodic Memory Tools ---
    elif name == "record_task":
        tid = args.get("task_id") or f"task-{uuid.uuid4().hex[:8]}"
        episode = {
            "task_id": tid,
            "description": args.get("description", ""),
            "result": args.get("result", ""),
            "metadata": args.get("metadata", {}),
            "created_at": now,
        }
        _EPISODES.append(episode)

        # ── bridge-20261027-memory-graph-empty (#1341): write-through ──
        # Episodes previously never fed the knowledge graph, so graph_nodes
        # stayed 0 forever and cross-session recall (read_graph/search_nodes)
        # had nothing to read. Every recorded task now lands as a namespaced
        # task entity plus up to 5 topic entities linked via "mentions" edges.
        _ns = str(args.get("tenant_id") or "tenant_default")
        _sess = str(args.get("session_id") or "default")
        _task_name = f"{_ns}:{_sess}:task:{tid}"
        _GRAPH_NODES[_task_name] = {
            "name": _task_name,
            "entityType": "task",
            "observations": [
                str(episode.get("description", ""))[:300],
                f"result: {str(episode.get('result', ''))[:300]}",
                f"at: {now}",
            ],
            "created_at": now,
        }
        # (#1359) write-through: task entities survive restarts too
        _STORE.upsert_entity(_task_name, "task", _GRAPH_NODES[_task_name]["observations"], now)
        _topic_pool = _re.findall(r"[A-Za-z_][A-Za-z0-9_]{3,}", f"{episode.get('description', '')} {episode.get('result', '')}")
        _topics: List[str] = []
        for _raw in _topic_pool:
            _t = f"{_ns}:topic:{_raw.lower()}"
            if _t not in _topics:
                _topics.append(_t)
            if len(_topics) >= 5:
                break
        for _t in _topics:
            if _t not in _GRAPH_NODES:
                _GRAPH_NODES[_t] = {
                    "name": _t,
                    "entityType": "topic",
                    "observations": [f"mentioned by task {tid} at {now}"],
                    "created_at": now,
                }
                # (#1359) write-through: topic entities survive restarts too
                _STORE.upsert_entity(_t, "topic", _GRAPH_NODES[_t]["observations"], now)
            _GRAPH_EDGES.append({"from": _task_name, "to": _t, "relationType": "mentions", "created_at": now})
            _STORE.insert_relation(_task_name, _t, "mentions", now)

        return {"task_id": tid, "status": "recorded", "graph_nodes_written": 1 + len(_topics)}

    elif name == "get_similar_tasks":
        q = str(args.get("query", "")).lower()
        limit = int(args.get("limit", 5))
        matches = [e for e in _EPISODES if q in e.get("description", "").lower() or q in e.get("result", "").lower()][:limit]
        return {"tasks": matches, "count": len(matches)}

    elif name == "get_recent_episodes":
        limit = int(args.get("limit", 10))
        return {"episodes": _EPISODES[-limit:]}

    elif name == "build_context":
        q = str(args.get("query", "")).lower()
        budget = int(args.get("token_budget", 2000))
        facts = [f.get("fact", "") for f in _LEARNED_FACTS if q in f.get("fact", "").lower()]
        tasks = [t.get("description", "") for t in _EPISODES if q in t.get("description", "").lower()]
        context_str = "Learned Facts:\n" + "\n".join(facts) + "\nPast Tasks:\n" + "\n".join(tasks)
        return {"context": context_str[: budget * 4], "facts_used": len(facts), "tasks_used": len(tasks)}

    elif name == "get_session_stats":
        sid = args.get("session_id", "default")
        # Latent-bug fix (#1359): _prune_expired expects epoch-ms; the ISO
        # string `now` only worked because TTL defaulted to 0 (early return).
        # Any operator setting MEMORY_EPISODE_TTL_MS>0 hit a TypeError here.
        _prune_expired()
        _prune_expired_graph()
        return {"session_id": sid, "active_episodes": len(_EPISODES), "graph_nodes": len(_GRAPH_NODES)}

    elif name == "export_memory":
        # (#1359, AIQ-062/098) GDPR data portability: one call returns every
        # stored lane. Graph comes straight from the persistent store when
        # available (independent of the hydrated cache) so the export is the
        # honest durable state, not a process-local view.
        _prune_expired()
        _prune_expired_graph()
        if _STORE.available:
            graph = _STORE.export_all()
        else:
            graph = {"entities": list(_GRAPH_NODES.values()), "relations": list(_GRAPH_EDGES)}
        return {
            "exported_at": now,
            "graph": graph,
            "episodes": list(_EPISODES),
            "documents": list(_DOCUMENTS),
            "learned_facts": list(_LEARNED_FACTS),
        }

    elif name == "wipe_memory":
        # (#1359, AIQ-098) GDPR hard wipe. Persistent store first (fail-open
        # inside), then the in-process mirrors — so a wiped graph cannot
        # resurrect via hydration on the next boot.
        scope = str(args.get("scope", "all"))
        _STORE.wipe()
        _GRAPH_NODES.clear()
        _GRAPH_EDGES.clear()
        cleared = {"graph": True}
        if scope != "graph":
            _EPISODES.clear()
            _DOCUMENTS.clear()
            _LEARNED_FACTS.clear()
            cleared.update(episodes=True, documents=True, learned_facts=True)
        return {"status": "wiped", "scope": scope, "cleared": cleared}

    elif name == "clear_session":
        sid = args.get("session_id", "default")
        _EPISODES.clear()
        return {"session_id": sid, "cleared": True}

    # --- Long-Term Learned Facts Tools ---
    elif name == "remember_fact":
        fact_text = str(args.get("fact", "")).strip()
        fid = str(uuid.uuid4())
        record = {
            "id": fid,
            "fact": fact_text,
            "category": args.get("category", "general"),
            "confidence": float(args.get("confidence", 1.0)),
            "created_at": now,
        }
        _LEARNED_FACTS.append(record)
        # Attempt Supabase sync to learned_facts
        _supabase_request("learned_facts", method="POST", data={"content": fact_text, "source": "mcp_sidecar", "confidence": record["confidence"]})
        return {"id": fid, "status": "saved", "fact": fact_text}

    elif name == "search_learned_facts":
        q = str(args.get("query", "")).lower()
        limit = int(args.get("limit", 10))
        # 1. Try Supabase
        sb_facts = _supabase_request("learned_facts", method="GET", params={"content": f"ilike.*{q}*", "limit": str(limit)})
        if sb_facts and isinstance(sb_facts, list):
            return {"facts": sb_facts, "source": "supabase"}
        # 2. In-memory fallback
        matches = [f for f in _LEARNED_FACTS if q in f.get("fact", "").lower()][:limit]
        return {"facts": matches, "source": "memory"}

    return {"error": f"Unknown tool: {name}"}


def main():
    """Main MCP STDIO loop handling JSON-RPC requests."""
    sys.stderr.write("[MemorySidecar] Python memory MCP sidecar started (ready for STDIO)\n")
    sys.stderr.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as err:
            sys.stderr.write(f"[MemorySidecar] Parse error: {err}\n")
            continue

        msg_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        # Handle MCP Handshake / Capabilities
        if method == "initialize":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "supremeai-memory-sidecar",
                        "version": "1.0.0",
                    },
                },
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            # Handshake notification, no response required
            pass

        elif method == "tools/list":
            res = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": TOOLS_SCHEMA},
            }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            try:
                data = handle_tool(tool_name, tool_args)
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(data, indent=2) if isinstance(data, (dict, list)) else str(data),
                            }
                        ]
                    },
                }
            except Exception as ex:
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Error: {ex}"}],
                    },
                }
            sys.stdout.write(json.dumps(res) + "\n")
            sys.stdout.flush()

        elif method == "ping":
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": {}}) + "\n")
            sys.stdout.flush()

        else:
            if msg_id is not None:
                err_res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                sys.stdout.write(json.dumps(err_res) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    main()
