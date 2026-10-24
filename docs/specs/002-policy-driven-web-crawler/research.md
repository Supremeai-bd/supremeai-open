# Research & Architecture Decisions: Policy-Driven Web Crawler Upgrade

**Feature**: `002-policy-driven-web-crawler`  
**Date**: 2026-09-05  
**Status**: Completed (Phase 0)  

---

## 1. Crawl Policy & History Persistence

### Decision
Store `CrawlPolicy`, `DomainRule`, and `CrawlHistory` using PostgreSQL (via the existing SQLAlchemy 2.0 async session and tenant models in `backend/database/`). Fast read caching is backed by `core.cache.redis_manager` (Upstash Redis with in-memory fallback).

### Rationale
- **Principle VI (Existing Architecture First)**: Reuses our existing PostgreSQL database and async session management rather than creating a separate database.
- **Principle VII (Multi-Tenant Safety)**: Policies and history are scoped by `tenant_id` and enforced via standard tenant filters.
- **Principle X (Resource Awareness & Zero-Cost)**: Avoids introducing external document stores (like the archived Firebase Firestore) or redundant processes.

### Alternatives Considered
- *Firebase Firestore*: Used in the legacy 2026-08 archive. Rejected because the system has fully migrated to Python/FastAPI/Postgres.
- *Local YAML / JSON files*: Rejected because multi-tenant operators must be able to adjust per-domain policies dynamically at runtime via the Admin API without redeploying code.

---

## 2. Zero-Token Deduplication (Exact + Near-Duplicate)

### Decision
Use a two-tier pure-Python deduplication engine in `backend/scout/dedup.py`:
1. **Tier 1 (Exact Hash)**: Normalized body text SHA-256 hash. Instant $O(1)$ lookup.
2. **Tier 2 (Near-Duplicate)**: Word $k$-shingling ($k=3$) with Jaccard similarity / MinHash signatures. Threshold configurable (default: 0.80).

### Rationale
- **Zero Token Cost**: Operates entirely in-process using standard Python library data structures (`hashlib`, `set`).
- **Principle I & III (Core Independence & Graceful Degradation)**: Does not depend on any third-party AI provider or embedding API. Runs in <5ms per page.

### Alternatives Considered
- *pgvector Embedding Cosine Distance*: Requires computing vector embeddings via OpenAI/Gemini/Ollama for every single crawled webpage. Rejected because it incurs high token cost, adds network latency, and breaks when AI providers are unconfigured.

---

## 3. Extractive Pre-Summarization

### Decision
Implement a pure-Python, zero-token sentence-ranking extractive summarizer (`backend/scout/extractor.py`) using frequency-weighted sentence scoring and position salience (Lead-3 + TextRank-lite).

### Rationale
- **Zero Provider Dependency**: Guarantees that when AI providers are in `NOT_CONFIGURED` state (Principle I & User Story 2), research tasks still produce structured, readable summary snippets.
- **Downstream Token Reduction**: Condenses 3,000–10,000 words of boilerplate web content into 300–500 words of high-density informative text before any LLM ingestion.

### Alternatives Considered
- *LLM Map-Reduce Summarizer*: Rejected because it requires active API keys, costs tokens, and fails if external providers are down.

---

## 4. Rate Limiting, SSRF & Network Safety

### Decision
Directly integrate with:
1. `backend/middleware/rate_limiter.py` (`AsyncRateLimiter` and `InMemoryFallbackLimiter`) for per-domain sliding-window request pacing.
2. `backend/core/security` (`is_safe_url`) to validate every discovered URL against DNS rebinding, private IP ranges (RFC 1918), and local metadata endpoints (169.254.169.254).

### Rationale
- **Principle II (Security & HITL)** & **Principle VI (Existing Architecture First)**: Protects against internal network scanning without reinventing URL security logic.

### Alternatives Considered
- *Separate in-memory sleep queue*: Prone to concurrency race conditions in multi-worker environments and duplicates existing rate-limiter logic.

---

## 5. Fetching Pipeline & Headless Browser Fallback

### Decision
Tiered fetching pipeline in `backend/scout/crawler.py`:
- **Tier 1 (Fast Path)**: `httpx.AsyncClient` with custom user agent, redirect limits (max 5), stream size cap (max 5MB), and connection timeouts. Handles 90%+ of standard web documents.
- **Tier 2 (Render Path)**: Delegates to `backend/services/browser/main.py` (Playwright service) only if the domain policy specifies `render_js: true` or if static HTML is empty/SPA placeholder.

### Rationale
- **Principle X (Resource Awareness)**: Headless Chromium instances consume ~150MB+ RAM per tab. Restricting browser rendering to policy-explicit targets keeps memory consumption well within Render/Supabase free-tier bounds.
