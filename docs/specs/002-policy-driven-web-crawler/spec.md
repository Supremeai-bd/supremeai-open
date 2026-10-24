# Feature Specification: Policy-Driven Web Crawler Upgrade

**Feature Branch**: `002-policy-driven-web-crawler`

**Created**: 2026-09-05

**Status**: Draft

**Input**: User description: "Upgrade the existing web-crawling capability (currently a minimal stub plus a single-page fetcher) into a policy-driven crawler: operator-configurable crawl policies (max depth, max results, per-domain rules with trust levels, per-domain and default rate limits, request timeout, content cache TTL, fallback/retry), content deduplication (exact hash + near-duplicate similarity), zero-token extractive pre-summarization, and full crawl event/history observability. Concepts are informed by the archived Firebase-era scraping engine (reference: `_archive/firebase_functions_removed_20260825/firebase_functions_v1/src/scrapeEngine.ts`, retrievable from git history); no archived code is copied — the feature must reuse the existing backend architecture (SSRF guard, distributed rate limiting, cache abstraction, browser-render service, event bus, admin API)."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Policy-Governed Crawling (Priority: P1)

An operator (agent_operator/admin role) defines a crawl policy: which domains may be crawled, per-domain trust levels and rate limits, a global default rate limit, maximum crawl depth, maximum results per research task, request timeout, and content cache duration. When any agent research/crawl task then runs, the system fetches only from allowed domains, never exceeds the configured depth/results, and paces requests to each domain at or below its rate limit. Any attempt to fetch a disallowed domain is blocked and recorded.

**Why this priority**: Without governance, crawling is unsafe (IP bans, unbounded cost, SSRF-adjacent risk) and cannot be operated in production. This slice alone delivers a safe, controllable crawler — a viable MVP.

**Independent Test**: Configure a policy allowing domain A and forbidding domain B with a depth cap of 2 and a rate limit; run a research task touching both domains and depth 3; verify only domain-A pages up to depth 2 are fetched, pacing never violated, and domain-B attempts are blocked with events.

**Acceptance Scenarios**:

1. **Given** a policy allowing only `example.org` with rate limit 1 request/second, **When** a research task targets `example.org` and `forbidden.net`, **Then** only `example.org` pages are fetched, requests are spaced ≥1 second apart, and every `forbidden.net` attempt is blocked and logged as a `domain_skipped` event.
2. **Given** a policy with max depth 2, **When** a crawl discovers links to depth 4, **Then** no page beyond depth 2 is fetched and a `crawl_depth_reached` event is recorded.
3. **Given** a policy with max results 10, **When** a crawl discovers 40 candidate pages, **Then** at most 10 pages are fetched.
4. **Given** no crawl policy exists or the active policy is disabled, **When** a crawl is requested, **Then** crawling fails closed (no fetches) with a clear configuration-state signal, not a crash.

### User Story 2 - Zero-Token Content Reduction (Priority: P2)

When multiple fetched pages contain the same or near-identical content, the system detects duplicates (exact content hash and near-duplicate similarity) and excludes duplicates from what is handed to downstream AI processing. It also produces a local, extractive summary (selecting the most informative passages of the merged unique content) that requires no AI provider at all. The goal: downstream AI receives the smallest possible unique content set, cutting token spend on research tasks.

**Why this priority**: This is the direct cost lever — research quality stays the same while tokens drop. It is independently valuable even without policy administration UI.

**Independent Test**: Fetch a set of pages where ≥30% of content is duplicated (mirrors/boilerplate); verify the downstream content set contains each unique passage exactly once (hash + similarity check) and that an extractive summary is produced with all AI providers unconfigured.

**Acceptance Scenarios**:

1. **Given** two pages with identical body text from different URLs, **When** both are fetched in one task, **Then** only one copy enters the merged content set and the duplicate is recorded in dedup statistics.
2. **Given** two pages whose text overlaps above the configured similarity threshold, **When** both are processed, **Then** the near-duplicate is excluded from downstream delivery and counted in dedup statistics.
3. **Given** all AI providers unconfigured, **When** a research task completes fetching, **Then** an extractive summary of the merged unique content is still produced (no provider dependency, no failure).

---

### User Story 3 - Crawl Observability & History (Priority: P3)

Operators can inspect what the crawler did: per-task crawl events (navigation start/complete, extraction start/complete, domain skipped, depth reached, rate limited, cached answer, error) and crawl history entries (query, sources, unique-content reference, summary reference, dedup statistics, timestamp, optional feedback). Events and history are queryable through the existing admin API under existing admin authorization.

**Why this priority**: Makes the system auditable and provides the data foundation for the learning loop; required before production trust, but the crawler is already safe and cheap without it.

**Independent Test**: Run a research task against a mix of allowed/forbidden/slow domains; query the admin API for the task's events and history; verify every blocked, rate-limited, cached, and errored interaction appears with timestamps.

**Acceptance Scenarios**:

1. **Given** a completed research task, **When** an operator requests its crawl history, **Then** they see query, source list, dedup statistics, and timestamps within seconds.
2. **Given** a task that hit rate limits and a disallowed domain, **When** the operator lists events for that task, **Then** `rate_limited` and `domain_skipped` events appear with the offending domain and timestamp.
3. **Given** two tenants, **When** tenant A's operator queries crawl history, **Then** no tenant B records are returned (isolation holds at the API level).

### User Story 4 - Resilient Fetching & Graceful Degradation (Priority: P4)

Individual domain failures (timeouts, errors, oversized pages, bot-blocking) never fail a whole research task. Fetches honor the configured timeout; content within the cache duration is served from cache without a new outbound request; and when the optional browser-render path is needed for pages that require it, that path is also policy-governed. Tasks complete with partial results plus accurate error events.

**Why this priority**: Improves completion quality and protects the free-tier footprint, but P1–P3 already deliver a safe, cheap, observable crawler; resilience polish can land last.

**Independent Test**: Run a task where 3 of 10 target domains are unreachable and one URL repeats within cache TTL; verify the task completes with results from the reachable domains, the repeated URL produces no second outbound request, and 3 error events are recorded.

**Acceptance Scenarios**:

1. **Given** a target domain that times out at the configured timeout, **When** the task crawls it, **Then** the domain is skipped with an `error` event and the task continues with remaining domains.
2. **Given** a URL fetched 2 minutes ago with a 1-hour cache duration, **When** the same URL is needed again, **Then** cached content is used, a `cached_answer` event is recorded, and no outbound request is made.
3. **Given** a page larger than the configured size cap, **When** it is fetched, **Then** it is truncated or skipped per policy without failing the task.

### Edge Cases

- What happens when a crawl encounters link cycles (page A → B → A)? Revisit protection plus the depth cap must terminate the walk; no duplicate fetch of the same URL within one task.
- What happens when a redirect crosses from an allowed domain to a disallowed one (including after DNS-level redirects)? Every hop is re-validated against the policy and the SSRF guard; a redirect into a disallowed or private target is blocked and logged.
- What happens when a policy is ambiguous (overlapping domain rules)? The most restrictive applicable rule wins; if a request matches both allow and deny, it is denied.
- What happens when two concurrent tasks crawl the same domain? They share the domain's rate-limit budget; the combined outbound rate never exceeds the configured limit.
- What happens when a fetch target resolves to an internal/private network address? Always blocked by the existing SSRF protection regardless of policy contents.
- What happens when a page requires JavaScript rendering? The optional browser-render path may be used if enabled by policy; it obeys the same domain/rate/depth rules.
- What happens when per-tenant policy overrides conflict with the global default? For that tenant, the override applies; all other tenants keep the global default.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Operators MUST be able to define a crawl policy containing: enabled state, maximum crawl depth, maximum results per task, default request rate limit, request timeout, content cache duration, fallback/retry behavior, and a set of per-domain rules.
- **FR-002**: The system MUST fetch only from domains allowed by the active policy; every disallowed fetch attempt MUST be blocked and recorded as an event.
- **FR-003**: Each domain rule MUST support a trust level (trusted / standard / suspicious), optional path and content-type restrictions, and an optional per-domain rate limit that overrides the default.
- **FR-004**: The system MUST enforce the policy's maximum crawl depth and maximum results per task.
- **FR-005**: The system MUST enforce the applicable per-domain rate limit across all concurrent tasks, so the combined outbound rate to any domain never exceeds its configured limit.
- **FR-006**: The system MUST enforce the request timeout; a timed-out fetch MUST be skipped with an error event and MUST NOT fail the whole task.
- **FR-007**: The system MUST serve repeat fetches of the same URL from content cache within the configured cache duration, without a new outbound request, and record a cached-answer event.
- **FR-008**: The system MUST exclude exact-duplicate content (content hash) and near-duplicate content (configurable similarity threshold) from downstream delivery, and MUST expose dedup statistics per task.
- **FR-009**: The system MUST produce an extractive summary of the merged unique content using only local computation (zero AI tokens), usable when no AI provider is configured.
- **FR-010**: The system MUST record crawl events including at minimum: navigation start/complete, extraction start/complete, domain skipped, depth reached, rate limited, cached answer, and error.
- **FR-011**: The system MUST persist a crawl history entry per task: query, sources, unique-content reference, summary reference, dedup statistics, timestamp, and optional user feedback.
- **FR-012**: All fetch targets MUST pass the existing SSRF/safe-URL protection, re-validated on every redirect hop; private/internal targets are always blocked regardless of policy.
- **FR-013**: Policies MUST resolve globally with optional per-tenant overrides; cache keys, history records, and events MUST be tenant-scoped so no tenant can read another tenant's crawl data.
- **FR-014**: A single domain failure MUST NOT fail the overall research task; tasks complete with partial results plus error events (graceful degradation).
- **FR-015**: The full fetch → dedup → extractive-summary pipeline MUST function with zero AI providers configured; missing optional provider keys surface as a `NOT_CONFIGURED` state for AI enrichment, never as a system failure.
- **FR-016**: Crawling MUST remain read-only; any post-crawl side effects (storing results, notifying users, executing actions) follow the existing HITL approval rules for those action classes.
- **FR-017**: Policy changes MUST take effect for newly started tasks without code change or redeployment (dynamic configuration), referenced by configuration name rather than hardcoded values.
- **FR-018**: Domain rules SHOULD support honoring standard exclusion signals (e.g., robots directives), defaulting to honor.
- **FR-019**: Operators MUST be able to manage policies (list, view, create, update, enable/disable) through the existing admin API surface, under existing admin authorization and audit logging.
- **FR-020**: Operators MUST be able to query crawl events and history through the existing admin API, scoped to their tenant.

### Key Entities *(include if feature involves data)*

- **CrawlPolicy**: The governable configuration for crawling — enabled flag, depth/result caps, default rate limit, timeout, cache duration, fallback behavior, and its domain rules. One global default; optionally overridden per tenant.
- **DomainRule**: A single domain's rules — trust level, allowed paths/content types, rate-limit override, exclusion-signal handling, enabled flag.
- **CrawlTask**: One governed crawl execution — originating query/task, tenant, the policy snapshot it ran under, start time.
- **ContentRecord**: One fetched document — URL, final URL after redirects, content fingerprint (hash + similarity cluster), fetch time, cache expiry.
- **CrawlEvent**: A timestamped observability record — event type, task, domain, payload (no page content bodies).
- **CrawlHistoryEntry**: The durable outcome of a task — query, sources, unique-content and summary references, dedup statistics, confidence, timestamp, optional feedback.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Within the configured cache duration, ≥90% of repeat fetches of the same URL in the same task are served from cache with zero outbound requests.
- **SC-002**: For research tasks whose fetched set contains ≥30% duplicate content, duplicate/near-duplicate material delivered downstream is reduced by ≥80%.
- **SC-003**: In a 100-request mixed-domain load test, zero requests violate the applicable per-domain rate limit.
- **SC-004**: 100% of disallowed-domain fetch attempts are blocked and produce a `domain_skipped` event.
- **SC-005**: Operators retrieve a task's crawl events and history in under 5 seconds via the admin API.
- **SC-006**: When 3 of 10 target domains are unreachable, the task completes with results from the reachable domains plus 3 recorded error events, and overall task success for the remaining domains is unaffected.
- **SC-007**: With all AI providers unconfigured, a complete research task still produces deduplicated content and an extractive summary (zero-token path verified).
- **SC-008**: For an identical research query repeated within cache duration, downstream token consumption drops by ≥50% versus the uncached, non-deduplicated baseline.

## Assumptions

- **v1 administration surface**: policy management via the existing admin API only; a dedicated admin-dashboard UI is out of scope for v1.
- **Policy layering**: a single global default policy is seeded at deploy time; per-tenant overrides are optional and may be introduced incrementally without schema redesign.
- **Retention**: crawl history/events default retention of 90 days, configurable.
- **Similarity threshold**: default 0.8 (configurable per policy).
- **Reuse (Principle VI)**: no new third-party services; existing SSRF protection, distributed rate limiting, cache abstraction, browser-render service, event bus, admin API authorization, and storage are reused. Technology mapping (which existing module implements which requirement) is a plan-phase decision.
- **Legacy reference**: concepts informed by the archived Firebase-era scraping engine (path: `_archive/firebase_functions_removed_20260825/firebase_functions_v1/src/scrapeEngine.ts`). That directory is scheduled for removal from the working tree after this spec lands; the file remains retrievable from git history. No archived code is copied — notably its Firestore coupling, hard-coded search templates, and Node.js runtime are all replaced by existing platform capabilities.
- **Out of scope**: chat/intent classification (already covered by the existing intent-routing stack), email ingestion/OTP extraction (already covered by the existing email agent with stronger security), OCR trigger (no archived implementation existed), and any new frontend UI.

## Brownfield Compliance (Constitution Obligations)

**Configuration classification** (Principle IV): policy defaults are `runtime` configuration, referenced by name (e.g., a default rate limit, timeout, cache TTL, retention days, similarity threshold — exact names decided in plan phase). No `secret`, no `build-time` values. Policy documents themselves are runtime data, not code.

**Multi-tenant data questions** (Principle VII): tenant scope — policies global with optional per-tenant override; history/events tenant-scoped. User scope — operator actions via existing RBAC; tasks carry the initiating user/tenant. Resource owner — the tenant owns its crawl records. Shared resources — global default policy and public domain rules. Cross-tenant access — denied; enforced at API and storage-key level. Cache-key scope — tenant + URL + policy version. Storage-key scope — tenant-prefixed keys. Audit scope — all policy CRUD and crawl events under existing admin audit logging. Telemetry scope — traces/metrics with URL and domain metadata only; page content bodies excluded from telemetry.

**AI/LLM constraints** (constitution §AI): no model required for the core pipeline; optional AI enrichment (e.g., smarter summarization) treats a missing provider key as `NOT_CONFIGURED` and falls back to the local extractive summary (Principles I & III). Token/resource limits — dedup + extractive summary run before any provider call; size caps per policy. Privacy mode — page content is not persisted beyond history retention and never leaves telemetry. Tool permissions — crawling is a read-only operation (auto-approved per AGENTS.md HITL policy); downstream writes keep existing HITL rules. Observability — events + existing error bus + tracing, per the telemetry scope above.

**Principle check**: I (no provider dependency — zero-token path), II (SSRF/RBAC/audit preserved), III (partial-results degradation), IV (dynamic, named configuration), VI (reuse-only, no new subsystems), VII (tenant isolation), VIII (tests + security checks in implementation), IX (fetch backends isolated behind project-owned interfaces).





