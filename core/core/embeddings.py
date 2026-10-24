"""Canonical local-first embedding utility for SupremeAI.

Production Supabase ``ai_memory.embedding`` is ``vector(384)``.  This module
therefore guarantees that every pgvector embedding is exactly 384 dimensions.

Embedding provider chain (issue #442 — Module 01 core):
  1. local SentenceTransformer (skipped under LOW_MEMORY_MODE, loud once)
  2. Cloudflare Workers AI ``@cf/baai/bge-small-en-v1.5`` (real 384-d semantic
     embeddings; free tier ≈10k/day) when CLOUDFLARE_API_TOKEN +
     CLOUDFLARE_ACCOUNT_ID are configured
  3. LiteLLM remote embedding (existing path)
  4. Improved feature-hashing fallback (stopword-filtered, sublinear-TF,
     multi-probe signature) — explicit DEGRADED mode, announced loudly once.

NOTE for operators: enabling a semantic provider changes the embedding space.
Vectors stored under the hash fallback are NOT comparable with vectors from a
semantic provider — reindex/refresh stored memories after switching providers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import re
from collections import OrderedDict

from core.config import settings
from core.i18n import bengali_text
from core.logging_config import logger

LOW_MEMORY_MODE = os.getenv("LOW_MEMORY_MODE", "false").lower() == "true"
# Issue #442: this used to be hardcoded False even where sentence-transformers
# WAS importable, permanently pinning deployments to the hash fallback.
# find_spec() is a cheap importability probe — it does NOT load the model.
_HAS_SENTENCE_TRANSFORMERS = importlib.util.find_spec("sentence_transformers") is not None

_LOCAL_MODEL_NAME = "all-MiniLM-L6-v2"
_LOCAL_DIM = 384
_PG_DIM = 384
_REMOTE_MODEL = settings.embedding_model
_REMOTE_DIM = 384

# Module 01: Cloudflare Workers AI embedding gateway (free tier ≈10k/day).
_CF_EMBED_MODEL = "@cf/baai/bge-small-en-v1.5"
_CF_EMBED_DIM = 384

_encoder = None

# Loud degraded-mode announcement state (one warning per process).
_degraded_announced = False
_cf_failed_announced = False

# Audit B-09 fix (2026-09-17): the embedding cache used to be an unbounded
# module-level dict (one entry per unique text, no eviction) — an OOM leak
# vector on the 512MB Render container. It is now a bounded LRU.
_EMBEDDING_CACHE_MAX = 2048
_embedding_cache: OrderedDict[str, list[float]] = OrderedDict()
_cache_hits = 0
_cache_misses = 0


def _cache_put(cache_key: str, vec: list[float]) -> list[float]:
    """Store an embedding in the bounded LRU cache (audit B-09)."""
    _embedding_cache[cache_key] = vec
    _embedding_cache.move_to_end(cache_key)
    while len(_embedding_cache) > _EMBEDDING_CACHE_MAX:
        _embedding_cache.popitem(last=False)
    return vec


def get_cache_stats() -> dict[str, int]:
    """Return embedding cache hit/miss statistics."""
    return {"hits": _cache_hits, "misses": _cache_misses, "size": len(_embedding_cache)}


def get_local_encoder():
    """Lazy-load the local SentenceTransformer encoder (graceful on failure).

    Issue #442: under LOW_MEMORY_MODE the model is deliberately NOT loaded —
    but the refusal is now announced loudly (once) so operators know semantic
    quality is capped at the hash fallback instead of failing silently.
    """
    global _encoder
    if LOW_MEMORY_MODE:
        static_announce_low_memory()
        return None
    if _encoder is None and _HAS_SENTENCE_TRANSFORMERS:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info(f"[embeddings] Loading local SentenceTransformer('{_LOCAL_MODEL_NAME}')...")
            _encoder = SentenceTransformer(_LOCAL_MODEL_NAME)
        except Exception as exc:
            logger.warning(f"[embeddings] Failed to load local encoder: {exc}")
    return _encoder


_low_memory_announced = False


def static_announce_low_memory() -> None:
    """Announce (once per process) that LOW_MEMORY_MODE caps semantic quality."""
    global _low_memory_announced
    if _low_memory_announced:
        return
    _low_memory_announced = True
    logger.warning(
        "[embeddings] LOW_MEMORY_MODE=true → local SentenceTransformer disabled "
        "(ChromaDB/SentenceTransformer excluded by the 512MB policy). Semantic "
        "quality depends on the remote provider chain; without one, memory falls "
        "back to the DEGRADED hash embedder (issue #442)."
    )


def _stable_hash(token: str) -> int:
    """Deterministic 64-bit hash — independent of PYTHONHASHSEED and process.

    Python's built-in ``hash()`` randomizes str hashes per process, which made
    ``hash_vectorize()`` output non-reproducible across workers/restarts and
    silently broke stored-vs-query cosine comparisons in every vector store
    that used this fallback.
    """
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


# Issue #442 (founder demand): stopword filtering for the hash fallback.
# The old tokenizer kept every len>1 token, so generic words ("how", "to",
# "is", "the", ...) dominated vectors and produced the observed recall
# INVERSION (relevant target 0.2357 vs irrelevant 0.2520 — stopwords collided
# harder than the actual topic terms).
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "then",
        "else",
        "when",
        "while",
        "of",
        "to",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "doing",
        "have",
        "has",
        "had",
        "having",
        "i",
        "you",
        "he",
        "she",
        "it",
        "we",
        "they",
        "me",
        "him",
        "her",
        "us",
        "them",
        "my",
        "your",
        "his",
        "its",
        "our",
        "their",
        "this",
        "that",
        "these",
        "those",
        "there",
        "here",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "why",
        "how",
        "can",
        "could",
        "should",
        "would",
        "will",
        "shall",
        "may",
        "might",
        "must",
        "about",
        "into",
        "over",
        "under",
        "again",
        "further",
        "once",
        "all",
        "any",
        "both",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "also",
        "get",
        "got",
        "make",
        "made",
        "want",
        "need",
        "use",
        "used",
        "using",
        "please",
        "help",
        "কিভাবে",
        "কী",
        "কি",
        "এবং",
        "বা",
        "তবে",
        "যদি",
        "তাহলে",
        "যখন",
        "থেকে",
        "সাথে",
        "জন্য",
        "দিয়ে",
        "হয়",
        "হবে",
        "করে",
        "করা",
        "করতে",
        "আমি",
        "আমার",
        "তুমি",
        "তোমার",
        "সে",
        "তার",
        "আমরা",
        "তারা",
        "এই",
        "সেই",
        "ঐ",
        "কোথায়",
        "কেন",
        "কখন",
        "কীভাবে",
        "করুন",
        "দিন",
        "হলো",
        "না",
        "আছে",
        "ছিল",
        "হয়েছে",
    ]
)

# Multi-probe signature hashing: each token contributes m signed hits at
# positions derived from distinct hash seeds. This is the classic
# feature-hashing variance-reduction trick — it spreads information across
# more dimensions and makes spurious cross-topic collisions far less likely
# than the single-probe scheme.
_HASH_PROBES = 3


_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def hash_vectorize(text: str, size: int = _LOCAL_DIM) -> list[float]:
    """Feature-hashing DEGRADED-mode embedder — zero-cost and exactly ``size`` dims.

    Improvements over the old fallback (issue #442, Module 01 design):
      * stopword filtering (English + Bengali function words)
      * sublinear term weighting: 1 + log(count) — repeated filler words no
        longer dominate the vector
      * multi-probe signed hashing (3 probes/token) for lower collision noise
    Uses process-stable blake2b, so identical text always maps to the same
    vector in every process, on every restart, on every worker.

    This embedder has NO real semantic capability — it is lexical overlap
    only. The module announces DEGRADED mode loudly when it is the active
    provider for pgvector/memory paths.
    """
    vector = [0.0] * size
    tokens = [t.lower() for t in _TOKEN_RE.findall(text or "")]
    words = [w for w in tokens if len(w) > 1 and w not in _STOPWORDS]
    if not words:
        vector[0] = 1.0
        return vector
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    for word, count in counts.items():
        weight = 1.0 + math.log(count)  # sublinear TF
        for probe in range(_HASH_PROBES):
            hv = _stable_hash(f"{probe}:{word}")
            h = hv % size
            sign = 1.0 if ((hv // size) % 2 == 0) else -1.0
            vector[h] += sign * weight
    norm = math.sqrt(sum(x * x for x in vector))
    if norm > 0:
        vector = [x / norm for x in vector]
    return vector


def _cf_credentials() -> tuple[str, str] | None:
    token = os.getenv("CLOUDFLARE_API_TOKEN") or getattr(settings, "cloudflare_api_token", "")
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID") or getattr(settings, "cloudflare_account_id", "")
    if token and account:
        return token, account
    return None


def remote_embed_cf(text: str) -> list[float] | None:
    """Real 384-d semantic embedding via Cloudflare Workers AI (Module 01).

    Sync implementation (httpx.Client) — the same blocking precedent as the
    pre-existing sync LiteLLM call inside embed_for_pgvector. Using ONE sync
    provider across embed_query and embed_for_pgvector keeps the embedding
    space consistent (issue #442). Returns None when not configured or on
    failure; one WARNING per process on the first runtime failure.
    """
    global _cf_failed_announced
    creds = _cf_credentials()
    if creds is None:
        return None
    token, account = creds
    try:
        import httpx

        url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{_CF_EMBED_MODEL}"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json={"text": [text]},
            )
        if resp.status_code != 200:
            if not _cf_failed_announced:
                _cf_failed_announced = True
                logger.warning(
                    "[embeddings] Cloudflare Workers AI embedding failed (HTTP %s): %s "
                    "— falling down the provider chain (issue #442).",
                    resp.status_code,
                    resp.text[:160],
                )
            return None
        data = resp.json()
        vec = ((data or {}).get("result", {}) or {}).get("data", [[]])[0]
        if isinstance(vec, list) and len(vec) == _CF_EMBED_DIM:
            return [float(x) for x in vec]
        logger.warning(
            "[embeddings] CF Workers AI returned %s dims; expected %s",
            len(vec) if isinstance(vec, list) else type(vec).__name__,
            _CF_EMBED_DIM,
        )
    except Exception as exc:  # noqa: BLE001 — provider failures fall through
        if not _cf_failed_announced:
            _cf_failed_announced = True
            logger.warning(
                "[embeddings] Cloudflare Workers AI embedding error: %s — falling "
                "down the provider chain (issue #442).",
                exc,
            )
    return None


def _announce_degraded(text: str) -> None:
    """Announce (once per process) that the hash embedder served a request."""
    global _degraded_announced
    if _degraded_announced:
        return
    _degraded_announced = True
    logger.warning(
        "[embeddings] SEMANTIC MEMORY DEGRADED: serving '%s...' with the lexical "
        "hash embedder (no real semantics). Fix options: (1) install "
        "sentence-transformers + set LOW_MEMORY_MODE=false, (2) set "
        "CLOUDFLARE_API_TOKEN + CLOUDFLARE_ACCOUNT_ID for Workers AI embeddings "
        "(Module 01), or (3) configure a LiteLLM embedding model. Reindex stored "
        "memories after switching providers (issue #442).",
        (text or "")[:60],
    )


def local_embed(text: str) -> list[float] | None:
    """Return a 384-dim local embedding, or None if the encoder is unavailable."""
    enc = get_local_encoder()
    if enc is not None:
        try:
            vec = enc.encode(text).tolist()
            if len(vec) == _LOCAL_DIM:
                return vec
            logger.warning(
                f"[embeddings] local encoder returned {len(vec)} dims; expected {_LOCAL_DIM}"
            )
        except Exception as exc:
            logger.warning(f"[embeddings] local encode failed: {exc}")
    return None


def _pad_to_dim(vec: list[float], dim: int) -> list[float]:
    """Legacy compatibility helper; pgvector embeddings are never padded."""
    if len(vec) == dim:
        return vec
    if len(vec) > dim:
        return vec[:dim]
    return vec + [0.0] * (dim - len(vec))


def embed_for_pgvector(text: str, pg_dim: int = _PG_DIM) -> list[float]:
    """Return a pgvector-safe 384-dimensional embedding.

    The argument is retained for backward compatibility.  Production memory
    has a fixed ``vector(384)`` contract, so a caller asking for 1536 dims is
    normalized to 384 rather than creating an incompatible vector.
    """
    global _cache_hits, _cache_misses

    # M19 P-D: NFC গোছানো — একই পাঠ্যের NFC/NFD/ZWNJ-ভিন্ন রূপ আলাদা
    # cache-key/vector তৈরি করত (বাংলা ইনপুটে অতিরিক্ত miss + ভেক্টর-বিভ্রম)।
    text = bengali_text.nfc(text)

    if pg_dim != _PG_DIM:
        logger.warning(
            f"[embeddings] requested pg_dim={pg_dim}, but ai_memory requires {_PG_DIM}; using {_PG_DIM}."
        )

    cache_key = f"{text}:{_PG_DIM}"
    if cache_key in _embedding_cache:
        _cache_hits += 1
        _embedding_cache.move_to_end(cache_key)
        return _embedding_cache[cache_key].copy()

    _cache_misses += 1

    # Zero-cost local path first.
    local_vec = local_embed(text)
    if local_vec is not None:
        _cache_put(cache_key, local_vec)
        return local_vec.copy()

    # Module 01: Cloudflare Workers AI — real 384-d semantic embeddings.
    cf_vec = remote_embed_cf(text)
    if cf_vec is not None and len(cf_vec) == _PG_DIM:
        _cache_put(cache_key, cf_vec)
        return cf_vec.copy()

    # Optional remote fallback. text-embedding-3-small supports reduced dimensions.
    try:
        import litellm

        resp = litellm.embedding(model=_REMOTE_MODEL, input=text, dimensions=_REMOTE_DIM)
        vec = resp.data[0]["embedding"]
        if len(vec) == _PG_DIM:
            if len(_embedding_cache) >= 5000:
                _embedding_cache.clear()
            _cache_put(cache_key, vec)
            return vec.copy()
        logger.warning(f"[embeddings] remote provider returned {len(vec)} dims; expected {_PG_DIM}")
    except Exception as exc:
        logger.warning(f"[embeddings] LiteLLM embedding failed: {exc}; using local hash fallback")

    # Never return a dimension-incompatible vector to the memory layer.
    vec = hash_vectorize(text, size=_PG_DIM)
    _announce_degraded(text)
    if len(_embedding_cache) >= 5000:
        _embedding_cache.clear()
    _cache_put(cache_key, vec)
    return vec.copy()


def embed_query(text: str) -> list[float]:
    """Default 384-dimensional embedding for semantic search.

    Provider chain (issue #442): local ST → Cloudflare Workers AI → hash
    (DEGRADED, announced loudly). The CF call is the same sync provider used
    by embed_for_pgvector, so query and document vectors always share ONE
    embedding space.
    """
    vec = local_embed(text)
    if vec is not None:
        return vec
    cf_vec = remote_embed_cf(text)
    if cf_vec is not None and len(cf_vec) == _PG_DIM:
        return cf_vec
    _announce_degraded(text)
    return hash_vectorize(text, size=_PG_DIM)


class EmbeddingEngine:
    """Singleton embedding engine for local-first zero-cost semantic search."""

    _instance: EmbeddingEngine | None = None

    @classmethod
    def get_instance(cls) -> EmbeddingEngine:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def embed(self, text: str) -> list[float]:
        """Compute a 384-dimensional embedding asynchronously."""
        return embed_query(text)

    def cosine(self, v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between equal-length vectors."""
        if not v1 or not v2 or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2, strict=True))
        norm1 = math.sqrt(sum(x * x for x in v1))
        norm2 = math.sqrt(sum(x * x for x in v2))
        if norm1 <= 0 or norm2 <= 0:
            return 0.0
        return dot / (norm1 * norm2)

    async def vector_search(self, query: str, corpus: list[dict], top_k: int = 5) -> list[dict]:
        """Search top-k matching documents using cosine similarity."""
        q_vec = await self.embed(query)
        scored = []
        for doc in corpus:
            doc_vec = doc.get("vector") or await self.embed(doc.get("text", ""))
            score = self.cosine(q_vec, doc_vec)
            scored.append((score, doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [dict(doc, score=score) for score, doc in scored[:top_k]]
