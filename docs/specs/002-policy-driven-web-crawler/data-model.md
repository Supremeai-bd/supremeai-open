# Data Model: Policy-Driven Web Crawler Upgrade

**Feature**: `002-policy-driven-web-crawler`  
**Date**: 2026-09-05  
**Status**: Completed (Phase 1)  

---

## 1. Entities & Schemas

### Entity: `CrawlPolicy`
Defines the boundary, limits, and pacing rules for all crawling within a tenant workspace.

| Field | Type | Constraints / Validation | Description |
|---|---|---|---|
| `id` | `UUID` | Primary Key, default UUIDv4 | Unique policy identifier |
| `tenant_id` | `str` | Indexed, foreign key to tenant | Tenant boundary ownership |
| `name` | `str` | 1..100 chars | Human-readable policy label |
| `is_active` | `bool` | Default `True` | Whether policy governs active runs |
| `max_depth` | `int` | Range 1..5, default 2 | Max link hop distance |
| `max_results` | `int` | Range 1..50, default 10 | Max pages returned per task |
| `default_rate_limit_per_min` | `int` | Range 1..600, default 30 | Fallback pacing per unlisted domain |
| `request_timeout_seconds` | `int` | Range 3..60, default 15 | Timeout per HTTP/render request |
| `cache_ttl_hours` | `int` | Range 0..720, default 24 | Content cache freshness lifespan |
| `domain_rules` | `list[DomainRule]` | Relationship (Cascade delete) | Domain-specific overrides & allowlist |
| `created_at` | `datetime` | UTC timestamp | Record creation time |
| `updated_at` | `datetime` | UTC timestamp | Last modification time |

---

### Entity: `DomainRule`
Per-domain permissions, pacing, and security categorization.

| Field | Type | Constraints / Validation | Description |
|---|---|---|---|
| `id` | `UUID` | Primary Key | Unique rule identifier |
| `policy_id` | `UUID` | FK to `CrawlPolicy.id` | Parent policy link |
| `domain` | `str` | Valid FQDN, lowercase, normalized | Target hostname (e.g. `github.com`) |
| `trust_level` | `str` | Enum: `trusted`, `standard`, `suspicious`, `blocked` | Trust classification |
| `rate_limit_per_min` | `int` | Range 1..1200, default 60 | Max requests allowed to this domain |
| `render_js` | `bool` | Default `False` | Whether to route through Playwright |
| `max_depth` | `int | None` | Nullable, overrides policy | Domain-specific depth ceiling |
| `allowed_path_patterns` | `list[str]` | Regex / glob strings | Only crawl matching subpaths |
| `disallowed_path_patterns` | `list[str]` | Regex / glob strings | Disallowed paths (e.g. `/logout`) |

---

### Entity: `CrawlHistory`
Durable audit and downstream payload record for each research task.

| Field | Type | Constraints / Validation | Description |
|---|---|---|---|
| `id` | `UUID` | Primary Key | History record ID |
| `task_id` | `str` | Indexed | Correlated orchestration task ID |
| `tenant_id` | `str` | Indexed | Tenant scope |
| `query` | `str` | Non-empty | Original research query or URL |
| `sources_crawled` | `list[str]` | Array of URLs | List of unique URLs successfully parsed |
| `total_pages_fetched` | `int` | $\ge 0$ | Total pages retrieved from network |
| `duplicate_pages_skipped` | `int` | $\ge 0$ | Duplicate pages discarded by dedup engine |
| `unique_content_hash` | `str` | SHA-256 hex string | Fingerprint of merged unique content |
| `extractive_summary` | `str` | Max 5000 chars | Zero-token salient sentence summary |
| `token_reduction_pct` | `float` | 0.0..100.0 | Estimated token savings percentage |
| `created_at` | `datetime` | UTC timestamp | Task execution timestamp |

---

### Entity: `CrawlEvent`
Ephemeral or durable telemetry event emitted into the shared event bus (`core.messaging.event_bus`).

| Field | Type | Description |
|---|---|---|
| `event_type` | `Enum` | `nav_start`, `nav_complete`, `extract_start`, `extract_complete`, `domain_skipped`, `depth_reached`, `rate_limited`, `cached_answer`, `error` |
| `task_id` | `str` | Correlated task identifier |
| `tenant_id` | `str` | Tenant identifier |
| `domain` | `str` | Target domain |
| `url` | `str` | Target URL |
| `details` | `dict` | Additional context (status code, reason, latency ms) |
| `timestamp` | `datetime` | Event occurrence timestamp |

---

## 2. State Transitions & Lifecycle

### Crawl Execution State Machine
```
[Task Initiated] 
       │
       ▼
[Policy Evaluation] ────(Domain not allowed or blocked)───► [Event: domain_skipped] ──► [Finish]
       │
       ▼ (Domain allowed)
[Cache Check] ──────────(Valid cache exists)─────────────► [Event: cached_answer] ──► [Deliver]
       │
       ▼ (Cache miss)
[Rate Limit Gate] ──────(Limit exceeded)─────────────────► [Event: rate_limited] ──► [Backoff / Retry]
       │
       ▼ (Allowed)
[Fetch Pipeline] ───────(Static httpx or Playwright)────► [Event: nav_complete]
       │
       ▼
[Deduplication Engine] ─(Exact SHA256 / Jaccard > 0.8)───► [Skip Duplicate]
       │
       ▼ (Unique content)
[Extractive Summarizer]
       │
       ▼
[Save History & Handoff to AI Spoke] ───────────────────► [Task Completed]
```
