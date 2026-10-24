import importlib.util
import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.degraded_mode import sqlite_fallback_allowed
from core.logging_config import logger

# বাংলা মন্তব্য: রেন্ডার ফ্রি টায়ারে মেমোরি সংকট এড়াতে LOW_MEMORY_MODE চেক করা হচ্ছে
# REVISION 2: Default to true for 512MB RAM constraint to avoid SentenceTransformer memory hog
LOW_MEMORY_MODE = os.getenv("LOW_MEMORY_MODE", "true").lower() == "true"


def _check_module(name: str) -> bool:
    if LOW_MEMORY_MODE:
        return False
    try:
        return importlib.util.find_spec(name) is not None
    except (ValueError, AttributeError):
        return False


HAS_SENTENCE_TRANSFORMERS = _check_module("sentence_transformers")
HAS_CHROMADB = _check_module("chromadb")
HAS_QDRANT = _check_module("qdrant_client")

# P0 (Task 9-c2): warn at most once per process about the disabled store.
_degrade_warned = False


def _warn_degraded_once() -> None:
    """P0: announce the pass-through degraded state loudly, but only once."""
    global _degrade_warned
    if not _degrade_warned:
        _degrade_warned = True
        logger.warning(
            "[P0] ExperienceDatabase DISABLED (pass-through): SQLite experience store "
            "refused in production and no vector backend available — writes are DROPPED "
            "and queries return no matches (semantic cache = cache-miss only). The "
            "degradation flag no longer permits SQLite fallback — provision "
            "Supabase pgvector."
        )


# Issue #441: one-time LOUD boot warning for the degraded self-learning memory
# stack. Mirrors the "🚨 BOOT-TIME WARNING" style of core/config_validation.py
# (merged PR #716 pattern): the fail-closed policy above is correct, but the
# degraded state must be visible at boot, not discovered from missing data.
_low_memory_boot_warned = False


def _warn_low_memory_learning_degraded_once() -> None:
    """Issue #441: announce ONCE per process that learning features are degraded."""
    global _low_memory_boot_warned
    if not _low_memory_boot_warned:
        _low_memory_boot_warned = True
        logger.warning(
            "🚨 BOOT-TIME WARNING: LOW_MEMORY_MODE=true — the self-learning experience "
            "store is DEGRADED: ExperienceDatabase runs as a pass-through in production "
            "(local SQLite/ChromaDB/Qdrant/SentenceTransformer all disabled; experience "
            "writes and semantic recall persist only while the Supabase pgvector backend "
            "is available). Learning-platform features are degraded — see "
            "docs/operations/LEARNING_PLATFORM_ENABLEMENT.md (issue #441) before "
            "enabling learning agents."
        )


@dataclass
class Experience:
    id: int | None = None
    timestamp: str = ""
    user_id: str = ""
    request: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    action_taken: str = ""
    result: str = "success"
    error_message: str | None = None
    user_feedback: str | None = None
    generated_code: str | None = None
    deployment_logs: str | None = None
    what_worked: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    suggested_improvements: list[str] = field(default_factory=list)


class ExperienceDatabase:
    def __init__(self, db_path: str | None = None):
        import os

        # P0 (Task 9-c2): this DB backs the semantic cache used by llm_gateway.
        # When the SQLite fallback is refused in production (no explicit db_path,
        # no SUPABASE_ALLOW_DB_DEGRADATION=true) the database becomes a
        # PASS-THROUGH NO-OP: queries return no matches, writes no-op with a
        # WARN — the gateway NEVER crashes and imports NEVER break. The gate is
        # evaluated lazily here (first use), never at import time.
        self._degraded_no_store = False
        if db_path is None and not sqlite_fallback_allowed("experience_db"):
            self._degraded_no_store = True
            # Issue #441: one-time loud boot warning — under LOW_MEMORY_MODE the
            # learning features backed by this store are degraded (see runbook).
            if LOW_MEMORY_MODE:
                _warn_low_memory_learning_degraded_once()
            self.db_path = Path(":memory:")
            self.encoder = None
            self.chroma_collection: Any = None
            self._chroma_initialized = True
            self.qdrant_client: Any = None
            self._qdrant_initialized = True
            self.qdrant_collection = "experience"
            self.vector_backend_degraded = True
            self.supabase_backend: Any = None
            # Issue #441 fix: the old gate returned here BEFORE the Supabase
            # pgvector backend was ever constructed — but pgvector needs NO
            # SQLite and NO local disk, so refusing the SQLite fallback must
            # not kill the persistent remote store. Bring pgvector up; only
            # when it is unavailable too do we stay a true pass-through.
            if os.getenv("USE_SUPABASE_VECTOR", "true").lower() == "true":
                try:
                    from adaptive_engine.supabase_vector_backend import (
                        SupabaseVectorBackend,
                    )

                    backend = SupabaseVectorBackend()
                    if backend.is_available:
                        self.supabase_backend = backend
                        self.vector_backend_degraded = False
                        logger.info(
                            "✅ ExperienceDatabase local-storage-degraded mode: "
                            "Supabase pgvector backend ACTIVE (persistent, no SQLite)"
                        )
                except Exception as exc:
                    logger.warning(f"SupabaseVectorBackend init in degraded mode failed: {exc}")
            if self.supabase_backend is None:
                _warn_degraded_once()
            return

        if not db_path:
            db_path = os.getenv("EXPERIENCE_DB_PATH", "data/experience.db")
        if not db_path:
            db_path = "data/experience.db"
        self.db_path = Path(db_path)
        if str(self.db_path) != ":memory:":
            try:
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
            except (PermissionError, OSError) as _perm_err:
                import tempfile

                tmp_dir = Path(tempfile.gettempdir()) / "data"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                self.db_path = tmp_dir / self.db_path.name
        self._init_db()
        self.encoder = None
        self.chroma_collection: Any = None
        self._chroma_initialized = False
        self.qdrant_client: Any = None
        self._qdrant_initialized = False
        self.qdrant_collection = "experience"
        # বাংলা: vector-DB backend fail করলে find_similar() একটা খালি লিস্ট রিটার্ন করে —
        # যেটা "কোনো relevant memory নেই" এবং "vector DB নিজেই down" — এই due অবস্থাকে
        # আলাদা করতে পারে না। এই ফ্ল্যাগ দিয়ে health_probes/self_healer বাস্তব degradation
        # ধরতে পারবে, memory silently গায়েব হয়ে যাবে না।
        self.vector_backend_degraded = False

        # FREE-TIER FIX: prefer Supabase pgvector (no Render disk needed).
        # Render free-tier does NOT support persistent disks — ChromaDB/Qdrant
        # store vectors in local files which are LOST on every container restart.
        # Supabase pgvector is remote + persistent + already provisioned (ai_memory table).
        # Set USE_SUPABASE_VECTOR=false to force ChromaDB/Qdrant (requires disk).
        self.supabase_backend: Any = None
        use_supabase = os.getenv("USE_SUPABASE_VECTOR", "true").lower() == "true"
        if use_supabase:
            try:
                from adaptive_engine.supabase_vector_backend import SupabaseVectorBackend

                self.supabase_backend = SupabaseVectorBackend()
                if self.supabase_backend.is_available:
                    logger.info(
                        "✅ ExperienceDatabase using Supabase pgvector "
                        "(persistent, no Render disk needed)"
                    )
                else:
                    logger.warning(
                        "⚠️ Supabase pgvector not available — falling back to "
                        "ChromaDB/Qdrant (data NOT persistent on Render free-tier)"
                    )
                    self.supabase_backend = None
            except Exception as exc:
                logger.warning(
                    f"SupabaseVectorBackend init failed: {exc} — using local "
                    "ChromaDB/Qdrant (data NOT persistent on Render free-tier)"
                )
                self.supabase_backend = None

    def _ensure_chroma(self) -> None:
        """
        বাংলা মন্তব্য: মেমরি ও রিসোর্স সাশ্রয় করতে ChromaDB ক্লায়েন্ট অলসভাবে (lazily) তৈরি করা হচ্ছে।
        """
        if self._chroma_initialized:
            return
        self._chroma_initialized = True
        if HAS_CHROMADB:
            try:
                import os

                import chromadb

                # FIX (ANALYSIS-D): original used EphemeralClient() which means ALL
                # learned experiences are LOST on every container restart
                # (Render free-tier cold-starts every 15 min). Switch to
                # PersistentClient with a configurable path. Admin must mount
                # /data/ volume (see ADMIN_TASKS.md) for persistence across
                # restarts; falls back to local /tmp/chroma if not set.
                chroma_path = os.getenv("EXPERIENCE_DB_PATH", "/tmp/chroma")
                logger.info(f"Initializing ChromaDB PersistentClient at {chroma_path}...")
                self.chroma_collection = chromadb.PersistentClient(
                    path=chroma_path
                ).get_or_create_collection("experience")
            except Exception as exc:
                logger.error(f"ChromaDB lazy init failed: {exc}")

    def _ensure_qdrant(self) -> None:
        """
        বাংলা মন্তব্য: মেমরি ও রিসোর্স সাশ্রয় করতে QdrantClient অলসভাবে (lazily) তৈরি করা হচ্ছে।
        """
        if self._qdrant_initialized:
            return
        self._qdrant_initialized = True
        if HAS_QDRANT:
            try:
                import os

                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams

                # FIX (ANALYSIS-D): same persistence bug as Chroma — ':memory:'
                # means all learned experiences vanish on restart. Switch to
                # local file path. Qdrant local mode uses path-based storage.
                qdrant_path = os.getenv("QDRANT_PATH", "/tmp/qdrant")
                logger.info(f"Initializing QdrantClient at {qdrant_path}...")
                self.qdrant_client = QdrantClient(path=qdrant_path)
                if not self.qdrant_client.collection_exists(collection_name=self.qdrant_collection):
                    self.qdrant_client.create_collection(
                        collection_name=self.qdrant_collection,
                        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
                    )
            except Exception as exc:
                logger.error(f"Qdrant lazy init failed: {exc}")

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    user_id TEXT,
                    request TEXT,
                    context TEXT,
                    action_taken TEXT,
                    result TEXT,
                    error_message TEXT,
                    user_feedback TEXT,
                    generated_code TEXT,
                    deployment_logs TEXT,
                    what_worked TEXT,
                    what_failed TEXT,
                    suggested_improvements TEXT,
                    embedding BLOB
                )
                """)
            cursor.execute("PRAGMA table_info(experiences)")
            columns = {row[1] for row in cursor.fetchall()}
            if "embedding" not in columns:
                # বাংলা মন্তব্য: পুরনো SQLite ডাটাবেসে embedding কলাম না থাকলে সেটি স্বয়ংক্রিয়ভাবে যোগ করা হচ্ছে
                cursor.execute("ALTER TABLE experiences ADD COLUMN embedding BLOB")
            conn.commit()

    def _embed(self, text: str) -> list[float] | None:
        if self.encoder is None and HAS_SENTENCE_TRANSFORMERS:
            try:
                # বাংলা মন্তব্য: ওটিপি চেক বা এপিআই স্টার্টআপে অপ্রয়োজনীয় ওভারহেড এড়াতে প্রথম ব্যবহারের সময় মডেলটি লোড করা হচ্ছে।
                from sentence_transformers import SentenceTransformer

                logger.info("Initializing SentenceTransformer('all-MiniLM-L6-v2') lazily...")
                self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as exc:
                logger.error(
                    f"[ExperienceDB] Lazy SentenceTransformer initialization failed: {exc}"
                )

        if self.encoder:
            try:
                return self.encoder.encode(text).tolist()
            except Exception as embed_err:
                logger.warning(
                    f"[ExperienceDB] SentenceTransformer embedding failed: {embed_err!r}. "
                    f"Falling back to embed_for_pgvector."
                )

        # Fallback to zero-cost canonical embedder (embed_for_pgvector, 384-dim)
        try:
            from core.embeddings import embed_for_pgvector

            vec = embed_for_pgvector(text)
            if vec:
                return vec
        except Exception as fallback_err:
            logger.warning(
                f"[ExperienceDB] Fallback embedder failed: {fallback_err!r}. "
                f"Semantic memory degraded for this entry."
            )
        return None

    def record_experience(self, exp: Experience) -> int:
        # P0: pass-through degraded mode — writes no-op with a WARN (never crash).
        if getattr(self, "_degraded_no_store", False):
            # Issue #441 fix: with the pgvector backend alive, writes PERSIST to
            # Supabase instead of being DROPPED (semantic cache stays real).
            backend = getattr(self, "supabase_backend", None)
            if backend is None:
                _warn_degraded_once()
                return 0
            request_text = exp.request or ""
            embedding = self._embed(request_text)
            if not embedding:
                logger.warning(
                    "[ExperienceDB] degraded-mode write: embedding unavailable — "
                    "experience not persisted (no vector space to store it in)."
                )
                return 0
            import uuid as _uuid

            ok = backend.upsert(
                exp_id=f"degraded-{_uuid.uuid4().hex}",
                text=request_text,
                embedding=embedding,
                result=exp.result or "success",
                response_text=exp.generated_code or exp.action_taken or "",
                user_id=exp.user_id or "",
            )
            if not ok:
                logger.warning(
                    "[ExperienceDB] degraded-mode pgvector upsert failed — write dropped."
                )
                return 0
            return 1  # persisted via pgvector (synthetic id)
        timestamp = (
            exp.timestamp
            or __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        )
        request_text = exp.request or ""
        embedding = self._embed(request_text)
        embedding_blob = json.dumps(embedding).encode() if embedding else None

        # Determine the code or response text to save in vector metadata
        response_text = exp.generated_code or exp.action_taken or ""

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO experiences (
                    timestamp, user_id, request, context, action_taken, result,
                    error_message, user_feedback, generated_code, deployment_logs,
                    what_worked, what_failed, suggested_improvements, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    exp.user_id,
                    request_text,
                    json.dumps(exp.context or {}),
                    exp.action_taken,
                    exp.result,
                    exp.error_message,
                    exp.user_feedback,
                    exp.generated_code,
                    exp.deployment_logs,
                    json.dumps(exp.what_worked or []),
                    json.dumps(exp.what_failed or []),
                    json.dumps(exp.suggested_improvements or []),
                    embedding_blob,
                ),
            )
            conn.commit()
            exp_id = int(cursor.lastrowid or 0)
        if embedding:
            self._upsert_vector_db(
                exp_id, request_text, embedding, exp.result, response_text, exp.user_id
            )

        # ROADMAP §13, §14: Experience -> Capability Promotion
        # If success, check if it's a repeated pattern to promote to LearningLoop
        # FIX(casing): writers store lowercase "success" (Experience default + all call
        # sites), so compare case-insensitively — the old `== "SUCCESS"` never matched
        # and the promotion loop was dead code.
        result_normalized = (exp.result or "").strip().lower()
        if result_normalized == "success":
            try:
                import asyncio

                from adaptive_engine.learning_loop import get_learning_loop

                loop_instance = get_learning_loop()

                # Check if we have seen this successful pattern multiple times
                similar = self.find_similar(request_text, limit=3, threshold=0.85)
                success_count = sum(
                    1 for s in similar if str(s.get("result") or "").strip().lower() == "success"
                )

                if success_count >= 2:
                    evidence = [
                        s.get("request")
                        for s in similar
                        if str(s.get("result") or "").strip().lower() == "success"
                    ]
                    coro = loop_instance.record_signal(
                        kind="REPEATED_SUCCESS",
                        description=f"Repeated success pattern detected: {request_text}",
                        evidence=evidence,
                        capability_hint=exp.action_taken,
                    )
                    # Fire and forget if in async context, otherwise block
                    try:
                        asyncio.get_running_loop().create_task(coro)
                    except RuntimeError:
                        asyncio.run(coro)
            except Exception as e:
                logger.error(f"[ExperienceDB] Failed to promote to LearningLoop: {e}")

        return exp_id

    def _upsert_vector_db(
        self,
        exp_id: int,
        text: str,
        embedding: list[float],
        result: str,
        response_text: str = "",
        user_id: str = "",
    ) -> None:
        # FREE-TIER FIX: prefer Supabase pgvector (persistent, no Render disk)
        if self.supabase_backend is not None:
            ok = self.supabase_backend.upsert(
                exp_id=exp_id,
                text=text,
                embedding=embedding,
                result=result,
                response_text=response_text,
                user_id=user_id,
            )
            if ok:
                return  # Supabase took it — skip ChromaDB/Qdrant entirely
            # else fall through to ChromaDB/Qdrant (data NOT persistent on Render free-tier)

        # বাংলা মন্তব্য: মেমরি সাশ্রয়ের জন্য ভেক্টর ডেটাবেস ব্যবহারের ঠিক পূর্বে ইনিশিয়ালাইজেশন নিশ্চিত করা হচ্ছে।
        self._ensure_chroma()
        self._ensure_qdrant()
        try:
            if self.chroma_collection:
                self.chroma_collection.upsert(
                    ids=[str(exp_id)],
                    embeddings=[embedding],
                    metadatas=[{"result": result, "response": response_text, "user_id": user_id}],
                    documents=[text],
                )
        except Exception as e:
            self.vector_backend_degraded = True
            logger.error(f"Chroma upsert failed (vector memory degraded, exp_id={exp_id}): {e}")
        try:
            if self.qdrant_client:
                from qdrant_client.models import PointStruct

                self.qdrant_client.upsert(
                    collection_name=self.qdrant_collection,
                    points=[
                        PointStruct(
                            id=exp_id,
                            vector=embedding,
                            payload={
                                "result": result,
                                "text": text,
                                "response": response_text,
                                "user_id": user_id,
                            },
                        )
                    ],
                )
        except Exception as e:
            self.vector_backend_degraded = True
            logger.error(f"Qdrant upsert failed (vector memory degraded, exp_id={exp_id}): {e}")

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        import math

        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if not norm_a or not norm_b:
            return 0.0
        return dot / (norm_a * norm_b)

    def find_similar(
        self, query: str, limit: int = 5, threshold: float = 0.7, user_id: str | None = None
    ) -> list[dict[str, Any]]:
        # P0: pass-through degraded mode — "no matches" (semantic cache miss).
        if getattr(self, "_degraded_no_store", False):
            # Issue #441 fix: with the pgvector backend alive, degraded-mode
            # queries hit the persistent remote store instead of always []
            # (semantic cache gets real hits, not cache-miss-only).
            backend = getattr(self, "supabase_backend", None)
            if backend is None:
                return []
            embedding = self._embed(query)
            if not embedding:
                return []
            try:
                results = backend.query(
                    query_embedding=embedding,
                    limit=limit,
                    threshold=threshold,
                )
                return self._map_supabase_hits(results)
            except Exception as e:
                self.vector_backend_degraded = True
                logger.error(f"find_similar() degraded pgvector query failed: {e}")
                return []
        embedding = self._embed(query)
        if not embedding:
            return []

        # FREE-TIER FIX: prefer Supabase pgvector (persistent, no Render disk)
        if self.supabase_backend is not None:
            try:
                results = self.supabase_backend.query(
                    query_embedding=embedding,
                    limit=limit,
                    threshold=threshold,
                )
                if results:
                    return self._map_supabase_hits(results)
                # Supabase returned empty — fall through to ChromaDB/Qdrant
                # (could be because no experiences stored yet, or Supabase unreachable)
            except Exception as e:
                logger.debug(
                    f"Supabase pgvector find_similar failed: {e} — falling back to ChromaDB/Qdrant"
                )

        # বাংলা মন্তব্য: মেমরি সাশ্রয়ের জন্য ভেক্টর ডেটাবেস ব্যবহারের ঠিক পূর্বে ইনিশিয়ালাইজেশন নিশ্চিত করা হচ্ছে।
        self._ensure_chroma()
        self._ensure_qdrant()
        hits = []
        try:
            if self.chroma_collection:
                where_clause = {"user_id": user_id} if user_id else None
                res = self.chroma_collection.query(
                    query_embeddings=[embedding], n_results=limit, where=where_clause
                )
                ids = res.get("ids", [[]])[0]
                metadatas = res.get("metadatas", [[]])[0]
                distances = res.get("distances", [[]])[0]
                documents = res.get("documents", [[]])[0]
                for idx, meta, dist, doc in zip(ids, metadatas, distances, documents, strict=True):
                    # ChromaDB distance can be Euclidean (L2). Convert to approximate similarity
                    score = 1.0 - float(dist)
                    if score >= threshold:
                        hits.append(
                            {
                                "source": "chroma",
                                "id": idx,
                                "score": score,
                                "meta": meta,
                                "response": meta.get("response", ""),
                                "text": doc,
                            }
                        )
            elif self.qdrant_client:
                query_filter = None
                if user_id:
                    from qdrant_client.models import FieldCondition, Filter, MatchValue

                    query_filter = Filter(
                        must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]
                    )
                res = self.qdrant_client.search(
                    collection_name=self.qdrant_collection,
                    query_vector=embedding,
                    limit=limit,
                    query_filter=query_filter,
                )
                for hit in res:
                    if hit.score >= threshold:
                        hits.append(
                            {
                                "source": "qdrant",
                                "id": hit.id,
                                "score": hit.score,
                                "meta": hit.payload,
                                "response": hit.payload.get("response", ""),
                                "text": hit.payload.get("text", ""),
                            }
                        )
        except Exception as e:
            self.vector_backend_degraded = True
            logger.error(
                f"find_similar() query failed (returning empty, but this is a DEGRADED state, not 'no matches'): {e}"
            )
        return hits

    @staticmethod
    def _map_supabase_hits(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize Supabase pgvector rows to the existing hit schema."""
        hits: list[dict[str, Any]] = []
        for row in results:
            meta = row.get("metadata", {}) or {}
            hits.append(
                {
                    "source": "supabase_pgvector",
                    "id": row.get("id"),
                    "score": float(row.get("similarity", 0.0)),
                    "meta": meta,
                    "response": meta.get("response", ""),
                    "text": row.get("content", ""),
                }
            )
        return hits

    def get_experiences(self, limit: int = 50) -> list[Experience]:
        # P0: pass-through degraded mode — no durable experiences to return.
        if getattr(self, "_degraded_no_store", False):
            return []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM experiences ORDER BY id DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [
                Experience(
                    id=r["id"],
                    timestamp=r["timestamp"],
                    user_id=r["user_id"],
                    request=r["request"],
                    context=json.loads(r["context"] or "{}"),
                    action_taken=r["action_taken"],
                    result=r["result"],
                    error_message=r["error_message"],
                    user_feedback=r["user_feedback"],
                    generated_code=r["generated_code"],
                    deployment_logs=r["deployment_logs"],
                    what_worked=json.loads(r["what_worked"] or "[]"),
                    what_failed=json.loads(r["what_failed"] or "[]"),
                    suggested_improvements=json.loads(r["suggested_improvements"] or "[]"),
                )
                for r in rows
            ]

    def sync_to_gcs(self, bucket_name: str, blob_name: str = "experience_db_backup.sqlite.gz"):
        """
        Compresses the SQLite database and uploads it to Google Cloud Storage.
        This minimizes bandwidth usage and prevents data loss on Cloud Run restarts.
        """
        import gzip
        import shutil

        import loguru
        from google.cloud import storage

        # P0: pass-through degraded mode — there is no local DB file to sync.
        if getattr(self, "_degraded_no_store", False):
            loguru.logger.warning("[P0] ExperienceDatabase disabled — GCS sync skipped.")
            return

        try:
            if str(self.db_path) == ":memory:":
                loguru.logger.warning("Cannot sync in-memory DB to GCS directly.")
                return

            gz_path = self.db_path.with_suffix(".sqlite.gz")
            with open(self.db_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            # Set metadata to indicate it's a gzipped sqlite file
            blob.content_encoding = "gzip"
            blob.upload_from_filename(str(gz_path), content_type="application/x-sqlite3")

            loguru.logger.info(
                f"Successfully synced experience db to GCS: gs://{bucket_name}/{blob_name}"
            )

            # Clean up local compressed file
            gz_path.unlink(missing_ok=True)

        except Exception as e:
            loguru.logger.error(f"Failed to sync experience db to GCS: {e}")
