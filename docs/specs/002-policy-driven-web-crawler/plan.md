# Implementation Plan: Policy-Driven Web Crawler Upgrade

**Branch**: `002-policy-driven-web-crawler` | **Date**: 2026-09-05 | **Spec**: [spec.md](file:///f:/supremeai/specs/002-policy-driven-web-crawler/spec.md)

**Input**: Feature specification from `specs/002-policy-driven-web-crawler/spec.md`

---

## Summary

Upgrade `backend/scout/` from a minimal 14-line stub and single-page fetcher into a robust, policy-driven web crawler:
- Operator-configurable crawl policies (max depth, max results, per-domain trust levels, rate pacing, request timeout, cache TTL, fallback/retry).
- Pure-Python zero-token content deduplication (exact SHA-256 hash + Jaccard similarity).
- Zero-token extractive pre-summarization to slash downstream LLM token consumption by 30–50%.
- Full crawl telemetry and event auditing via the existing event bus and admin APIs.

---

## Technical Context

**Language/Version**: Python 3.11 / 3.13  
**Primary Dependencies**: FastAPI, Pydantic V2, HTTPX, BeautifulSoup4, SQLAlchemy 2.0 async  
**Storage**: PostgreSQL (SQLAlchemy async) for durable policy and history records; Redis / InMemoryFallback for rate limits and caching  
**Testing**: `pytest`, `pytest-asyncio`  
**Target Platform**: Linux / Windows (Containerized Render/Vercel)  
**Project Type**: Backend service module (`backend/scout/`)  
**Performance Goals**: <5ms deduplication per page; <15ms extractive summarization; strict adherence to per-domain rate limits  
**Constraints**: Zero additional infrastructure cost; 100% offline-compatible content reduction (no LLM dependency for summarization/dedup)  
**Scale/Scope**: Up to 50 results per crawl task, up to 5 hops depth, multi-tenant scoped  

---

## Constitution Check

*GATE: Pre-Phase 0 Check & Post-Phase 1 Design Review.*

| Principle | Status | Compliance Verification |
|---|---|---|
| **I — Core Independence** | ✅ PASS | Deduplication and extractive summarization require zero external AI providers. System functions with all LLMs unconfigured. |
| **II — Security & HITL** | ✅ PASS | Enforces `core.security.is_safe_url` to prevent SSRF and DNS rebinding; crawl history respects tenant boundaries; admin endpoints require RBAC. |
| **III — Graceful Degradation** | ✅ PASS | Individual page/domain failures do not crash research tasks; timeout/bot-blocking yields partial results + error events. |
| **IV — Dynamic Config** | ✅ PASS | Policies and per-domain limits are managed dynamically via DB/API without code redeploy. |
| **V — User-Local AI Optional** | ✅ PASS | No dependency on Ollama or local LLM execution. |
| **VI — Existing Architecture First** | ✅ PASS | Reuses `backend/middleware/rate_limiter.py`, `backend/database/`, and `backend/services/browser/main.py`. |
| **VII — Multi-Tenant Safety** | ✅ PASS | All policies and history tables are strictly scoped with `tenant_id`. |
| **VIII — Verification First** | ✅ PASS | Unit tests for dedup, extractor, and crawler policies defined in `quickstart.md`. |
| **IX — Vendor Exit Path** | ✅ PASS | Pure-Python standard library algorithms for dedup and summarization. |
| **X — Resource Awareness** | ✅ PASS | Static HTTP is default; memory-heavy Playwright headless browser used only on demand for specific domains. |

---

## Project Structure

### Documentation (this feature)

```text
specs/002-policy-driven-web-crawler/
├── spec.md              # Feature specification
├── plan.md              # This file (/speckit.plan output)
├── research.md          # Phase 0 output: decisions, rationale, alternatives
├── data-model.md        # Phase 1 output: entities, state machine
├── quickstart.md        # Phase 1 output: verification commands & smoke tests
└── contracts/           # Phase 1 output: OpenAPI & Python interfaces
    ├── crawler-admin-api.yaml
    └── python-interface.md
```

### Source Code Changes

```text
backend/
├── scout/
│   ├── __init__.py           # Package exports
│   ├── crawler.py            # Primary CrawlerService implementation
│   ├── dedup.py              # Exact SHA256 + Jaccard similarity deduplication
│   ├── extractor.py          # Zero-token sentence-ranking extractive summarizer
│   └── models.py             # Pydantic & DB entity schemas for policies/history
├── api/routes/
│   └── crawler_admin.py      # Admin endpoints for policy & event observability
└── tests/
    └── scout/
        ├── test_crawler.py
        ├── test_dedup.py
        └── test_extractor.py
```

---

## Implementation Phases

### Phase 0: Research & Architecture (Complete)
- [x] Evaluated storage options: selected Postgres + Redis cache.
- [x] Evaluated dedup algorithms: selected pure-Python SHA-256 + Jaccard shingling ($k=3$).
- [x] Evaluated summarization: selected Lead-3 + sentence salience graph scoring.
- [x] Reused existing rate limiter and SSRF security validators.

### Phase 1: Design & Contracts (Complete)
- [x] Designed `CrawlPolicy`, `DomainRule`, `CrawlHistory`, and `CrawlEvent` entities in `data-model.md`.
- [x] Created OpenAPI specification for admin routes in `contracts/crawler-admin-api.yaml`.
- [x] Defined internal Python contracts in `contracts/python-interface.md`.
- [x] Documented automated and manual test scenarios in `quickstart.md`.

### Phase 2: Tasks & Implementation (Next Step)
- Generate atomic tasks via `/speckit.tasks` broken down by User Story:
  - Task 1: Deduplication Engine (`scout/dedup.py` + tests)
  - Task 2: Extractive Summarizer (`scout/extractor.py` + tests)
  - Task 3: Policy-Governed Crawler Engine (`scout/crawler.py` + tests)
  - Task 4: Admin API Endpoints (`api/routes/crawler_admin.py` + tests)
