from __future__ import annotations

import logging
import os
import sys

# বাংলা মন্তব্য: Python path ঠিক করা হচ্ছে — core.* import করার আগেই sys.path এ backend/ যোগ করা আবশ্যক
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

#!/usr/bin/env python3
"""
SupremeAI 2.0 — Memory MCP Server
====================================
বাংলা মন্তব্য: এই ফাইলটি আমাদের সম্পূর্ণ Memory System (ChromaDB, Supabase, Episodic, Sliding Window)
কে একটি MCP (Model Context Protocol) Server হিসেবে expose করে।
Official MCP Memory Server-এর সকল সুবিধা + আমাদের Enterprise-grade features একসাথে পাওয়া যাবে।

Transport সমর্থন:
  - stdio  (Claude Desktop, Cursor, VS Code)
  - SSE    (MEMORY_MCP_TRANSPORT=sse এনভায়রনমেন্ট ভেরিয়েবল দিলে)

Tools (MCP protocol):
  Knowledge Graph (Official server-এর মতো):
    - create_entities
    - create_relations
    - add_observations
    - delete_entities
    - delete_observations
    - delete_relations
    - read_graph
    - search_nodes
    - open_nodes

  Vector / Semantic (আমাদের নিজস্ব):
    - store_document
    - search_semantic
    - ingest_document_rag

  Episodic Memory (আমাদের নিজস্ব):
    - record_task
    - get_similar_tasks
    - get_recent_episodes

  Sliding Window / Context (আমাদের নিজস্ব):
    - build_context
    - get_session_stats
    - clear_session

  Long Term Facts (আমাদের নিজস্ব):
    - remember_fact
    - recall_facts
    - save_learned_fact
    - search_learned_facts
"""


import asyncio
import json
import time
from typing import Any

from core.logging_config import logger
from core.mcp_audit import audit_tool_call
from core.mcp_policy import evaluate_tool

try:
    import mcp.types as types
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        TextContent,
        Tool,
    )

    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


# বাংলা মন্তব্য: মেমোরি লেয়ার সমূহ import করা হচ্ছে — ব্যর্থ হলে graceful degradation ও স্পষ্ট লগিং
try:
    from memory.chromadb_store import ChromaDBStore

    _CHROMA_OK = True
except Exception as e:
    logger.debug(f"ChromaDB store not available: {e}")
    _CHROMA_OK = False

try:
    from memory.episodic_memory import EpisodicMemory

    _EPISODIC_OK = True
except Exception as e:
    logger.debug(f"EpisodicMemory store not available: {e}")
    _EPISODIC_OK = False

try:
    from memory.sliding_window import SlidingWindowConfig, SlidingWindowMemory

    _SLIDING_OK = True
except Exception as e:
    logger.debug(f"SlidingWindowMemory not available: {e}")
    _SLIDING_OK = False

try:
    from memory.supabase_store import SupabaseStore

    _SUPABASE_OK = True
except Exception as e:
    logger.debug(f"SupabaseStore not available: {e}")
    _SUPABASE_OK = False

try:
    from memory.rag_pipeline import RAGPipeline

    _RAG_OK = True
except Exception as e:
    logger.debug(f"RAGPipeline not available: {e}")
    _RAG_OK = False


# =============================================================================
# Knowledge Graph Storage (Official MCP-compatible)
# বাংলা মন্তব্য: Official MCP memory server-এর Knowledge Graph structure অনুসরণ করা হচ্ছে
# =============================================================================


class KnowledgeGraph:
    """
    In-memory knowledge graph backed by ChromaDB for persistent vector search.
    Official MCP memory server-এর মতো Entity-Relation-Observation structure।
    """

    def __init__(self, chroma_store: ChromaDBStore | None = None) -> None:
        # বাংলা মন্তব্য: entities ও relations dict-এ রাখা হচ্ছে fast lookup এর জন্য
        self._entities: dict[str, dict[str, Any]] = {}
        self._relations: list[dict[str, Any]] = []
        self._chroma = chroma_store

    # ------------------------------------------------------------------
    # Entity operations
    # ------------------------------------------------------------------
    def create_entities(self, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """নতুন entity তৈরি করে — duplicate skip করে।"""
        created: list[dict[str, Any]] = []
        for ent in entities:
            name = ent.get("name", "")
            if not name or name in self._entities:
                continue
            record = {
                "name": name,
                "entityType": ent.get("entityType", "unknown"),
                "observations": list(ent.get("observations", [])),
            }
            self._entities[name] = record
            # বাংলা মন্তব্য: ChromaDB-তেও সংরক্ষণ করা হচ্ছে যাতে semantic search কাজ করে
            if self._chroma:
                obs_text = " ".join(record["observations"])
                self._chroma.add_document(
                    doc_id=f"entity::{name}",
                    text=f"{name} ({record['entityType']}): {obs_text}",
                    metadata={
                        "type": "entity",
                        "entity_name": name,
                        "entity_type": record["entityType"],
                    },
                )
            created.append(record)
        return created

    def delete_entities(self, names: list[str]) -> list[str]:
        """Entity এবং তার সম্পর্কিত relations মুছে দেয়।"""
        deleted = []
        for name in names:
            if name in self._entities:
                del self._entities[name]
                # বাংলা মন্তব্য: সংশ্লিষ্ট relations-ও সরানো হচ্ছে
                self._relations = [
                    r for r in self._relations if r["from"] != name and r["to"] != name
                ]
                if self._chroma:
                    try:
                        self._chroma.delete(f"entity::{name}")
                    except Exception as err:
                        # বাংলা মন্তব্য: ChromaDB entity ডিলেট না করা গেলে লগ রেকর্ড করা হচ্ছে
                        logger.warning("Failed to delete entity %s from ChromaDB: %s", name, err)
                deleted.append(name)
        return deleted

    def add_observations(self, entity_name: str, observations: list[str]) -> list[str]:
        """বিদ্যমান entity-তে নতুন observation যোগ করে।"""
        if entity_name not in self._entities:
            raise ValueError(f"Entity '{entity_name}' not found.")
        existing = set(self._entities[entity_name]["observations"])
        new_obs = [o for o in observations if o not in existing]
        self._entities[entity_name]["observations"].extend(new_obs)
        # বাংলা মন্তব্য: ChromaDB vector আপডেট করা হচ্ছে
        if self._chroma and new_obs:
            ent = self._entities[entity_name]
            obs_text = " ".join(ent["observations"])
            self._chroma.add_document(
                doc_id=f"entity::{entity_name}",
                text=f"{entity_name} ({ent['entityType']}): {obs_text}",
                metadata={
                    "type": "entity",
                    "entity_name": entity_name,
                    "entity_type": ent["entityType"],
                },
            )
        return new_obs

    def delete_observations(self, entity_name: str, observations: list[str]) -> list[str]:
        if entity_name not in self._entities:
            return []
        before = set(self._entities[entity_name]["observations"])
        to_remove = set(observations)
        self._entities[entity_name]["observations"] = [
            o for o in self._entities[entity_name]["observations"] if o not in to_remove
        ]
        return list(before & to_remove)

    # ------------------------------------------------------------------
    # Relation operations
    # ------------------------------------------------------------------
    def create_relations(self, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """নতুন relation তৈরি করে — duplicate skip করে।"""
        created = []
        for rel in relations:
            # বাংলা মন্তব্য: duplicate check করে তারপর যোগ করা হচ্ছে
            duplicate = any(
                r["from"] == rel.get("from")
                and r["to"] == rel.get("to")
                and r["relationType"] == rel.get("relationType")
                for r in self._relations
            )
            if not duplicate:
                record = {
                    "from": rel["from"],
                    "to": rel["to"],
                    "relationType": rel.get("relationType", "related_to"),
                }
                self._relations.append(record)
                created.append(record)
        return created

    def delete_relations(self, relations: list[dict[str, Any]]) -> int:
        before = len(self._relations)
        self._relations = [
            r
            for r in self._relations
            if not any(
                d.get("from") == r["from"]
                and d.get("to") == r["to"]
                and d.get("relationType") == r["relationType"]
                for d in relations
            )
        ]
        return before - len(self._relations)

    # ------------------------------------------------------------------
    # Read / Search
    # ------------------------------------------------------------------
    def read_graph(self) -> dict[str, Any]:
        return {
            "entities": list(self._entities.values()),
            "relations": self._relations,
        }

    def search_nodes(self, query: str) -> list[dict[str, Any]]:
        """Keyword search — ChromaDB vector search fallback।"""
        query_lower = query.lower()
        keyword_hits = [
            ent
            for ent in self._entities.values()
            if query_lower in ent["name"].lower()
            or query_lower in ent["entityType"].lower()
            or any(query_lower in obs.lower() for obs in ent["observations"])
        ]
        if keyword_hits:
            return keyword_hits
        # বাংলা মন্তব্য: keyword miss হলে ChromaDB semantic search চেষ্টা করা হচ্ছে
        if self._chroma:
            try:
                results = self._chroma.query(query_text=query, n_results=5)
                semantic_hits = []
                for _doc_id, _score, data in results:
                    meta = data.get("metadata", {})
                    if meta.get("type") == "entity":
                        name = meta.get("entity_name", "")
                        if name in self._entities:
                            semantic_hits.append(self._entities[name])
                return semantic_hits
            except Exception as err:
                # বাংলা মন্তব্য: ChromaDB search query ব্যর্থ হলে লগ রেকর্ড করা হচ্ছে
                logger.warning("ChromaDB search query failed for '%s': %s", query, err)
        return []

    def open_nodes(self, names: list[str]) -> dict[str, Any]:
        entities = [self._entities[n] for n in names if n in self._entities]
        relations = [r for r in self._relations if r["from"] in names or r["to"] in names]
        return {"entities": entities, "relations": relations}


# =============================================================================
# Policy & Audit Shim (Constitution Law #11 + #19)
# =============================================================================


def _check_policy(name: str) -> dict[str, Any] | None:
    """Evaluate policy for a tool call. Returns None if allowed, or a dict with denial info."""
    decision, risk_level = evaluate_tool(name)
    if decision == "ALLOW":
        return None
    if decision == "REQUIRE_APPROVAL":
        return {
            "approval_required": True,
            "risk_level": risk_level,
            "tool": name,
            "reason": f"Tool '{name}' is classified as {risk_level}. Requires explicit human approval.",
        }
    return {
        "approval_required": True,
        "risk_level": risk_level,
        "tool": name,
        "reason": f"Tool '{name}' blocked by policy (decision={decision}).",
    }


def _audit(
    name: str,
    decision: str,
    risk_level: str,
    start_time: float,
    tenant_id: str,
    error: str | None = None,
) -> None:
    """Log a tenant-scoped tool call to the audit trail."""
    latency = (time.monotonic() - start_time) * 1000
    audit_tool_call(
        name,
        decision,
        risk_level,
        latency_ms=latency,
        error=error,
        tenant_id=tenant_id,
    )


# =============================================================================
# MCP Server Builder
# =============================================================================


def build_server() -> Server:
    """
    SupremeAI Memory MCP Server তৈরি করে সব tools সহ।
    বাংলা মন্তব্য: Official MCP SDK-এর Server class ব্যবহার করা হচ্ছে।
    """
    if not _MCP_AVAILABLE:
        raise RuntimeError("mcp package not installed. Run: poetry add mcp")

    server = Server("supremeai-memory")

    # বাংলা মন্তব্য: Memory layers একবারই initialize করা হচ্ছে (singleton pattern)
    chroma = ChromaDBStore(collection_name="supremeai_kg") if _CHROMA_OK else None
    kg = KnowledgeGraph(chroma_store=chroma)
    episodic = EpisodicMemory(vector_store=chroma) if _EPISODIC_OK and chroma else None
    sliding = SlidingWindowMemory(config=SlidingWindowConfig()) if _SLIDING_OK else None
    supabase = SupabaseStore() if _SUPABASE_OK else None
    rag = RAGPipeline(vector_store=chroma) if _RAG_OK and chroma else None

    # =========================================================================
    # Tool Definitions
    # =========================================================================

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """সকল available tools এর তালিকা।"""
        return [
            # --- Knowledge Graph (Official MCP compatible) ---
            Tool(
                name="create_entities",
                description=(
                    "Create new entities in the Knowledge Graph. Each entity has a name, "
                    "type (e.g. person, project, concept), and observations. "
                    "Duplicate names are silently skipped. "
                    "নতুন entity তৈরি করে — existing entity skip করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Unique entity name"},
                                    "entityType": {
                                        "type": "string",
                                        "description": "Category/type of entity",
                                    },
                                    "observations": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Observed facts about this entity",
                                    },
                                },
                                "required": ["name", "entityType"],
                            },
                        }
                    },
                    "required": ["entities"],
                },
            ),
            Tool(
                name="create_relations",
                description=(
                    "Create directed relations between entities in the Knowledge Graph. "
                    "relationType should be an active-voice verb phrase e.g. 'works_at', 'owns', 'depends_on'."
                    "দুটি entity-র মধ্যে সম্পর্ক তৈরি করে।"
                ),
                inputSchema={
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
            ),
            Tool(
                name="add_observations",
                description=(
                    "Add new observations (facts) to an existing entity. "
                    "Duplicate observations are ignored. "
                    "বিদ্যমান entity-তে নতুন তথ্য যোগ করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_name": {"type": "string"},
                        "observations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["entity_name", "observations"],
                },
            ),
            Tool(
                name="delete_entities",
                description="Delete entities and their relations from the Knowledge Graph. সংশ্লিষ্ট relations-ও মুছে যাবে।",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of entity names to delete",
                        },
                    },
                    "required": ["names"],
                },
            ),
            Tool(
                name="delete_observations",
                description="Remove specific observations from an entity without deleting the entity itself.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "entity_name": {"type": "string"},
                        "observations": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["entity_name", "observations"],
                },
            ),
            Tool(
                name="delete_relations",
                description="Delete specific relations from the Knowledge Graph.",
                inputSchema={
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
            ),
            Tool(
                name="read_graph",
                description="Return the entire Knowledge Graph — all entities and relations. সম্পূর্ণ গ্রাফ পড়ে।",
                inputSchema={"type": "object", "properties": {}},
            ),
            Tool(
                name="search_nodes",
                description=(
                    "Search nodes in the Knowledge Graph using keyword + semantic vector search (ChromaDB). "
                    "Returns matching entities. কীওয়ার্ড ও vector similarity দিয়ে entity খোঁজে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query text"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="open_nodes",
                description="Open specific nodes and their direct relations from the Knowledge Graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "names": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["names"],
                },
            ),
            # --- Vector / Semantic ---
            Tool(
                name="store_document",
                description=(
                    "Store a document with optional metadata in the vector store (ChromaDB). "
                    "Supports incremental indexing — unchanged documents are not re-indexed. "
                    "একটি ডকুমেন্ট ChromaDB-তে store করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string", "description": "Unique document identifier"},
                        "text": {"type": "string", "description": "Document content to store"},
                        "metadata": {"type": "object", "description": "Optional metadata dict"},
                        "incremental": {
                            "type": "boolean",
                            "default": True,
                            "description": "Skip re-indexing if content unchanged (hash check)",
                        },
                    },
                    "required": ["doc_id", "text"],
                },
            ),
            Tool(
                name="search_semantic",
                description=(
                    "Search the vector store using semantic similarity (ChromaDB cosine distance). "
                    "Returns ranked results with similarity scores. "
                    "AI-grade semantic similarity search করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "n_results": {
                            "type": "integer",
                            "default": 5,
                            "description": "Number of results to return",
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="ingest_document_rag",
                description=(
                    "Chunk and ingest a large document into the RAG pipeline (ChromaDB). "
                    "Automatically splits by word count with configurable chunk_size and overlap. "
                    "বড় ডকুমেন্ট chunk করে RAG pipeline-এ index করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "doc_id": {"type": "string"},
                        "content": {"type": "string"},
                        "metadata": {"type": "object"},
                        "chunk_size": {"type": "integer", "default": 500},
                        "overlap": {"type": "integer", "default": 100},
                    },
                    "required": ["doc_id", "content"],
                },
            ),
            # --- Episodic Memory ---
            Tool(
                name="record_task",
                description=(
                    "Record a task execution event (prompt + response + metrics) into episodic memory (ChromaDB). "
                    "Used for reflection and cognitive recall of past solutions. "
                    "AI task-এর ইতিহাস episodic memory-তে সংরক্ষণ করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "response": {"type": "string"},
                        "success": {"type": "boolean", "default": True},
                        "latency_ms": {"type": "number", "default": 0.0},
                        "model_used": {"type": "string", "default": "default"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["task_id", "prompt", "response"],
                },
            ),
            Tool(
                name="get_similar_tasks",
                description=(
                    "Retrieve past task executions similar to a given query using vector similarity. "
                    "Enables AI agents to learn from past experience. "
                    "অতীতের সদৃশ task গুলো vector search দিয়ে খুঁজে বের করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "n": {"type": "integer", "default": 3},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="get_recent_episodes",
                description="Retrieve recent episodic memory records filtered by event type and importance.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Filter by event type (optional)",
                        },
                        "min_importance": {
                            "type": "number",
                            "description": "Minimum importance threshold",
                        },
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            ),
            # --- Sliding Window / Context ---
            Tool(
                name="build_context",
                description=(
                    "Build a token-budget-aware context string from session memory with auto-compaction. "
                    "Hierarchically summarizes older windows to fit within budget. "
                    "Token budget অনুযায়ী context তৈরি করে — পুরানো windows স্বয়ংক্রিয়ভাবে compress হয়।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "documents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "New documents to add to the context window",
                        },
                        "session_id": {"type": "string", "default": "default"},
                        "query": {
                            "type": "string",
                            "description": "Optional query to prioritize relevant chunks",
                        },
                        "budget": {
                            "type": "integer",
                            "description": "Max token budget (default: 4000)",
                        },
                    },
                    "required": ["documents"],
                },
            ),
            Tool(
                name="get_session_stats",
                description="Get sliding window memory statistics for a session (window count, token totals, compact summaries).",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "default": "default"},
                    },
                },
            ),
            Tool(
                name="clear_session",
                description="Clear all sliding window memory for a session. সেশনের সমস্ত memory মুছে দেয়।",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string", "default": "default"},
                    },
                },
            ),
            # --- Long Term Facts (Supabase) ---
            Tool(
                name="remember_fact",
                description=(
                    "Save a long-term fact to Supabase with vector embedding for semantic recall. "
                    "Falls back to SQLite if Supabase is unavailable. "
                    "দীর্ঘমেয়াদী তথ্য Supabase-এ pgvector embedding সহ সংরক্ষণ করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "Fact content"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Categorization tags",
                        },
                        "id": {"type": "string", "description": "Optional fact ID"},
                    },
                    "required": ["content"],
                },
            ),
            Tool(
                name="search_learned_facts",
                description=(
                    "Search stored long-term facts using pgvector semantic similarity search (Supabase). "
                    "Falls back to ilike substring search if vector search fails. "
                    "pgvector দিয়ে semantic fact search করে।"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            ),
        ]

    # =========================================================================
    # Resources (MCP Protocol — Data/State Exposure)
    # বাংলা মন্তব্য: AI clients এই resources পড়তে পারে সরাসরি — কোনো tool call ছাড়াই
    # =========================================================================

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        """সকল available resources এর তালিকা।"""
        return [
            types.Resource(
                uri="mcp://memory/knowledge-graph",
                name="Knowledge Graph",
                description="Complete knowledge graph state — entities, relations, observations",
                mimeType="application/json",
            ),
            types.Resource(
                uri="mcp://memory/session-stats",
                name="Session Statistics",
                description="Sliding window memory statistics — token counts, window summaries",
                mimeType="application/json",
            ),
            types.Resource(
                uri="mcp://memory/health",
                name="Memory System Health",
                description="Health status of all memory layers (ChromaDB, Supabase, Episodic, RAG)",
                mimeType="application/json",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        """নির্দিষ্ট URI থেকে resource data পড়ে।"""
        if uri == "mcp://memory/knowledge-graph":
            data = {
                "entities": kg._entities,
                "relations": kg._relations,
                "entity_count": len(kg._entities),
                "relation_count": len(kg._relations),
            }
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif uri == "mcp://memory/session-stats":
            if sliding is None:
                return json.dumps({"error": "SlidingWindowMemory not available"})
            stats = sliding.get_stats() if hasattr(sliding, "get_stats") else {"status": "active"}
            return json.dumps(stats, ensure_ascii=False, indent=2)

        elif uri == "mcp://memory/health":
            health = {
                "chroma": {"available": _CHROMA_OK, "connected": chroma is not None},
                "episodic": {"available": _EPISODIC_OK, "connected": episodic is not None},
                "sliding_window": {"available": _SLIDING_OK, "connected": sliding is not None},
                "supabase": {"available": _SUPABASE_OK, "connected": supabase is not None},
                "rag": {"available": _RAG_OK, "connected": rag is not None},
                "overall": "healthy"
                if any([chroma, episodic, sliding, supabase, rag])
                else "degraded",
            }
            return json.dumps(health, ensure_ascii=False, indent=2)

        return json.dumps({"error": f"Unknown resource: {uri}"})

    # =========================================================================
    # Prompts (MCP Protocol — Reusable Workflow Templates)
    # বাংলা মন্তব্য: AI clients এই prompt templates ব্যবহার করে জটিল workflow automate করতে পারে
    # =========================================================================

    @server.list_prompts()
    async def list_prompts() -> list[types.Prompt]:
        """সকল available prompt templates এর তালিকা।"""
        return [
            types.Prompt(
                name="heal_error",
                description="Analyze an error, search memory for similar past fixes, and generate a healing plan",
                arguments=[
                    types.PromptArgument(
                        name="error_message",
                        description="The error message or stack trace to analyze",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="context",
                        description="Additional context about where the error occurred",
                        required=False,
                    ),
                ],
            ),
            types.Prompt(
                name="deploy_preflight",
                description="Run a complete deployment preflight check — memory state, service health, and readiness",
                arguments=[
                    types.PromptArgument(
                        name="target_environment",
                        description="Target environment (staging, production)",
                        required=True,
                    ),
                ],
            ),
            types.Prompt(
                name="recall_context",
                description="Recall relevant context from all memory layers for a given topic or query",
                arguments=[
                    types.PromptArgument(
                        name="query",
                        description="The topic or query to recall context for",
                        required=True,
                    ),
                    types.PromptArgument(
                        name="max_results",
                        description="Maximum number of results to return (default: 5)",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, Any] | None) -> types.GetPromptResult:
        """নির্দিষ্ট prompt template return করে।"""
        if arguments is None:
            arguments = {}

        if name == "heal_error":
            error_msg = arguments.get("error_message", "Unknown error")
            ctx = arguments.get("context", "No additional context provided")
            prompt_text = f"""## Error Healing Workflow

### Error to Analyze
{error_msg}

### Context
{ctx}

### Instructions
1. Search memory for similar past errors using `search_semantic` tool
2. Check episodic memory for past fixes using `get_similar_tasks`
3. Analyze the root cause
4. Generate a step-by-step healing plan
5. If successful, record the fix using `record_task` for future reference

### Policy Note
This workflow operates under R2 risk level — read-only memory access unless explicitly approved for mutations.
"""
            return types.GetPromptResult(
                description="Error healing workflow prompt",
                messages=[
                    types.PromptMessage(
                        role="user", content=types.TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        elif name == "deploy_preflight":
            env = arguments.get("target_environment", "staging")
            prompt_text = f"""## Deployment Preflight Check — {env}

### Checklist
1. **Memory Health**: Read `mcp://memory/health` to verify all memory layers are operational
2. **Knowledge Graph**: Read `mcp://memory/knowledge-graph` to check entity/relation integrity
3. **Session Stats**: Read `mcp://memory/session-stats` to verify sliding window state
4. **Recent Episodes**: Use `get_recent_episodes` to check for recent deployment-related events
5. **Similar Tasks**: Use `get_similar_tasks` to find past deployment experiences

### Authorization
- Target environment: {env}
- Risk level: R3 (REQUIRE_APPROVAL for production deployments)
- Human approval required before any deployment action

### Output Format
Return a structured preflight report with:
- overall_status: "ready" | "blocked" | "degraded"
- checks: array of individual check results
- blockers: array of issues preventing deployment
- recommendations: array of suggested actions
"""
            return types.GetPromptResult(
                description=f"Deployment preflight checklist for {env}",
                messages=[
                    types.PromptMessage(
                        role="user", content=types.TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        elif name == "recall_context":
            query = arguments.get("query", "")
            max_results = arguments.get("max_results", 5)
            prompt_text = f"""## Context Recall — {query}

### Instructions
Search all memory layers for relevant context about: **{query}**

### Steps
1. Use `search_semantic` to find vector-similar documents (n={max_results})
2. Use `search_nodes` to find knowledge graph entities related to the query
3. Use `get_similar_tasks` to find past similar task executions
4. Use `recall_facts` to find stored long-term facts
5. Synthesize all results into a coherent context summary

### Output Format
Return a structured context report with:
- summary: synthesized context summary
- sources: array of sources (knowledge graph, episodic, semantic, facts)
- confidence: overall confidence score (0-1)
- gaps: array of missing information

### Query Details
- Original query: {query}
- Max results per layer: {max_results}
"""
            return types.GetPromptResult(
                description=f"Context recall workflow for: {query}",
                messages=[
                    types.PromptMessage(
                        role="user", content=types.TextContent(type="text", text=prompt_text)
                    )
                ],
            )

        return types.GetPromptResult(
            description="Unknown prompt",
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(type="text", text=f"Unknown prompt: {name}"),
                )
            ],
        )

    # =========================================================================
    # Tool Handlers
    # =========================================================================

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """সকল tool call এখানে route হয়।"""
        # ── Policy evaluation (Constitution Law #11: Think Before You Act) ──
        decision, risk_level = evaluate_tool(name)
        start_time = time.monotonic()
        tenant_id = str((arguments or {}).get("tenant_id") or "").strip()
        if not tenant_id or tenant_id == "default":
            # Issue #1440: the gate used to return a bare error that spec-following
            # clients could not act on (no schema advertises tenant_id). Keep the
            # gate strict but make the failure self-explanatory: the control tower
            # injects tenant_id automatically; direct sidecar callers must pass it.
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": "tenant_id is required",
                            "hint": (
                                "Pass a non-'default' tenant_id string identifying your tenant. "
                                "The MCP control tower injects it automatically for memory.* calls "
                                "(issue #1440); direct sidecar callers must provide it explicitly."
                            ),
                        }
                    ),
                )
            ]

        policy_block = _check_policy(name)
        if policy_block is not None:
            _audit(name, decision, risk_level, start_time, tenant_id, error="policy_blocked")
            logger.warning(f"MCP tool '{name}' blocked by policy: {risk_level}")
            return [
                TextContent(
                    type="text", text=json.dumps(policy_block, ensure_ascii=False, indent=2)
                )
            ]

        # বাংলা মন্তব্য: tool নাম অনুযায়ী সঠিক handler-এ dispatch করা হচ্ছে
        try:
            result = await _dispatch(name, arguments, kg, episodic, sliding, supabase, chroma, rag)
            _audit(name, decision, risk_level, start_time, tenant_id)
            return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
        except Exception as exc:
            logger.exception(f"Tool '{name}' failed: {exc}")
            _audit(name, decision, risk_level, start_time, tenant_id, error=str(exc))
            return [
                TextContent(
                    type="text",
                    text=json.dumps({"error": str(exc), "tool": name}, ensure_ascii=False),
                )
            ]

    return server


async def _dispatch(
    name: str,
    args: dict[str, Any],
    kg: KnowledgeGraph,
    episodic: EpisodicMemory | None,
    sliding: SlidingWindowMemory | None,
    supabase: SupabaseStore | None,
    chroma: ChromaDBStore | None,
    rag: RAGPipeline | None,
) -> Any:
    """
    বাংলা মন্তব্য: Tool নাম অনুসারে সঠিক memory layer-এ dispatch করা হচ্ছে।
    প্রতিটি tool failure-safe — error JSON হিসেবে ফেরত দেয়।
    """

    # ---- Knowledge Graph ----
    if name == "create_entities":
        return {"created": kg.create_entities(args["entities"])}

    if name == "create_relations":
        return {"created": kg.create_relations(args["relations"])}

    if name == "add_observations":
        added = kg.add_observations(args["entity_name"], args["observations"])
        return {"entity": args["entity_name"], "new_observations": added}

    if name == "delete_entities":
        return {"deleted": kg.delete_entities(args["names"])}

    if name == "delete_observations":
        removed = kg.delete_observations(args["entity_name"], args["observations"])
        return {"entity": args["entity_name"], "removed": removed}

    if name == "delete_relations":
        count = kg.delete_relations(args["relations"])
        return {"deleted_count": count}

    if name == "read_graph":
        return kg.read_graph()

    if name == "search_nodes":
        return {"results": kg.search_nodes(args["query"])}

    if name == "open_nodes":
        return kg.open_nodes(args["names"])

    # ---- Vector / Semantic ----
    if name == "store_document":
        if not chroma:
            return {"error": "ChromaDB not available"}
        incremental = args.get("incremental", True)
        if incremental:
            updated = chroma.add_document_incremental(
                doc_id=args["doc_id"],
                text=args["text"],
                metadata=args.get("metadata"),
            )
            return {"doc_id": args["doc_id"], "indexed": updated, "mode": "incremental"}
        else:
            chroma.add_document(args["doc_id"], args["text"], args.get("metadata"))
            return {"doc_id": args["doc_id"], "indexed": True, "mode": "full"}

    if name == "search_semantic":
        if not chroma:
            return {"error": "ChromaDB not available"}
        results = chroma.query(
            query_text=args["query"],
            n_results=args.get("n_results", 5),
        )
        return {
            "results": [
                {"doc_id": doc_id, "score": round(score, 4), "data": data}
                for doc_id, score, data in results
            ]
        }

    if name == "ingest_document_rag":
        if not rag:
            return {"error": "RAG pipeline not available"}
        rag.vector_store = chroma
        getattr(rag, "chunk_text", None)  # ensure method exists
        rag.ingest_document(
            doc_id=args["doc_id"],
            content=args["content"],
            metadata=args.get("metadata"),
        )
        return {"doc_id": args["doc_id"], "status": "ingested"}

    # ---- Episodic Memory ----
    if name == "record_task":
        if not episodic:
            return {"error": "Episodic memory not available"}
        ok = await episodic.record_task(
            task_id=args["task_id"],
            prompt=args["prompt"],
            response=args["response"],
            success=args.get("success", True),
            latency_ms=args.get("latency_ms", 0.0),
            model_used=args.get("model_used", "default"),
            metadata=args.get("metadata"),
        )
        return {"recorded": ok, "task_id": args["task_id"]}

    if name == "get_similar_tasks":
        if not episodic:
            return {"error": "Episodic memory not available"}
        results = await episodic.get_similar_past_tasks(
            query=args["query"],
            n=args.get("n", 3),
        )
        return {"results": results}

    if name == "get_recent_episodes":
        if not episodic:
            return {"error": "Episodic memory not available"}
        episodes = episodic.recall_episodes(
            event_type=args.get("event_type"),
            min_importance=args.get("min_importance"),
            limit=args.get("limit", 10),
        )
        return {"episodes": episodes}

    # ---- Sliding Window ----
    if name == "build_context":
        if not sliding:
            return {"error": "Sliding window memory not available"}
        ctx = sliding.build_context(
            documents=args["documents"],
            query=args.get("query", ""),
            session_id=args.get("session_id", "default"),
            budget=args.get("budget"),
        )
        return {"context": ctx}

    if name == "get_session_stats":
        if not sliding:
            return {"error": "Sliding window memory not available"}
        return sliding.get_session_stats(args.get("session_id", "default"))

    if name == "clear_session":
        if not sliding:
            return {"error": "Sliding window memory not available"}
        ok = sliding.clear(args.get("session_id", "default"))
        return {"cleared": ok}

    # ---- Long Term Facts ----
    if name == "remember_fact":
        if not supabase:
            return {"error": "Supabase store not available"}
        fact: dict[str, Any] = {
            "content": args["content"],
            "tags": args.get("tags", []),
        }
        if args.get("id"):
            fact["id"] = args["id"]
        supabase.save_learned_fact(fact)
        return {"saved": True, "fact_id": fact.get("id")}

    if name == "search_learned_facts":
        if not supabase:
            return {"error": "Supabase store not available"}
        results = supabase.search_facts(args["query"])
        return {"results": results}

    return {"error": f"Unknown tool: {name}"}


# =============================================================================
# Entry Point
# =============================================================================


async def main() -> None:
    """
    বাংলা মন্তব্য: MEMORY_MCP_TRANSPORT env var দেখে transport নির্ধারণ করা হয়।
    - stdio: Claude Desktop, Cursor, VS Code এর জন্য (default)
    - sse:   HTTP-based remote deployment এর জন্য

    CRITICAL (Unified Gateway): stdio mode-এ stdout শুধুমাত্র MCP JSON-RPC
    frames-এর জন্য সংরক্ষিত। সমস্ত logging অবশ্যই stderr-এ যাবে — নইলে
    Control Tower-এর StdioClientTransport handshake ভেঙে যায়।
    """
    transport = os.getenv("MEMORY_MCP_TRANSPORT", "stdio").lower()

    if transport == "stdio":
        # stdout MUST stay pure for MCP frames → log only to stderr.
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
            force=True,
        )
        # loguru (imported via core.*) defaults to stdout — redirect to stderr.
        try:
            from loguru import logger as _loguru

            _loguru.remove()
            _loguru.add(sys.stderr, level="WARNING")
        except Exception as exc:
            # বাংলা: best-effort — loguru redirect ব্যর্থ হলে stdlib logging
            # (stderr) থেকেই চলবে; কিন্তু কারণ debug-এ রাখা হয় যাতে নীরব
            # ব্যর্থতা না মনে হয়। stdout অবশ্যই অপবিত্র করা যাবে না (MCP frames)।
            logging.getLogger(__name__).debug(
                f"loguru stderr redirect unavailable ({type(exc).__name__}: {exc}); "
                f"continuing with stdlib logging"
            )
    else:
        logging.basicConfig(
            level=logging.WARNING,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )

    logger.info(f"Starting SupremeAI Memory MCP Server (transport={transport})")

    server = build_server()

    if transport == "stdio":
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    else:
        # বাংলা মন্তব্য: SSE transport — FastAPI/Starlette-এ mount করা হবে
        try:
            import uvicorn
            from mcp.server.sse import SseServerTransport
            from starlette.applications import Starlette
            from starlette.routing import Mount, Route

            sse_transport = SseServerTransport("/messages/")

            async def handle_sse(request):
                async with sse_transport.connect_sse(
                    request.scope, request.receive, request._send
                ) as streams:
                    await server.run(
                        streams[0],
                        streams[1],
                        server.create_initialization_options(),
                    )

            app = Starlette(
                routes=[
                    Route("/sse", endpoint=handle_sse),
                    Mount("/messages/", app=sse_transport.handle_post_message),
                ]
            )
            port = int(os.getenv("MEMORY_MCP_PORT") or "8765")
            host = os.getenv("MEMORY_MCP_HOST", "0.0.0.0")  # is_local()
            logger.info(f"SSE MCP Server listening on {host}:{port}")
            uvicorn.run(app, host=host, port=port)
        except ImportError as e:
            logger.error(f"SSE transport requires starlette + uvicorn: {e}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
