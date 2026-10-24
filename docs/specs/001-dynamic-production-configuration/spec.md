# Feature Specification: Production Configuration & Dynamic Endpoint Hardening

**Feature Branch**: `feature/001-dynamic-production-configuration` (planned per `CONTRIBUTING.md`; current adoption work rides on `chore/spec-kit-bootstrap`)

**Created**: 2026-08-29

**Status**: Draft

**Input**: User description: "Make SupremeAI production configuration deployment-agnostic. Users and admins must be able to use the correct backend without hardcoded deployment URLs in application source. Optional provider configuration must remain optional, required configuration must fail fast, and changing backend services must be possible through deployment configuration without changing application code."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Operator swaps a backend service through configuration only (Priority: P1)

An operator moves a SupremeAI service (main backend, admin backend, scraper) to a
different host — for example a different Render service or hosting provider — by
changing deployment configuration (environment/secret manager) and redeploying.
After redeploy, every consumer (user portal, admin portal, health aggregation,
service topology) reaches the service at its new location. No application source
change and no rebuild of unrelated services is required.

**Why this priority**: This is the core promise of deployment-agnostic
configuration and removes the highest-risk failure mode observed today: stale
hardcoded production URLs baked into source.

**Independent Test**: Can be fully tested by changing one service URL in
deployment configuration, redeploying the same source revision, and verifying all
client surfaces reach the new host — plus a source scan proving zero code edits.

**Acceptance Scenarios**:

1. **Given** deployment configuration defines the main backend location, **When** the operator changes it and redeploys, **Then** user portal and admin portal requests reach the new location without any source change.
2. **Given** deployment configuration defines the scraper and admin service locations, **When** either is changed and redeployed, **Then** health aggregation and service topology views report the new locations.
3. **Given** a required deployment value is missing in a production start, **When** the application boots, **Then** startup fails fast with one actionable error naming every missing key — never silently falling back to a hardcoded hostname.

---

### User Story 2 - Frontend resolves service endpoints without hardcoded production URLs (Priority: P2)

As a user or admin, the web app I load always talks to the correct backend for the
deployment I am using. Frontend builds take service locations exclusively from
build/deploy-time configuration (including deploy-time generated hosting
configuration), and no component silently falls back to a specific provider's
production hostname or to placeholder project identifiers.

**Why this priority**: Frontend hardcoding is the primary cause of
"works-on-my-deployment, broken-after-swap" incidents and directly violates the
dynamic-configuration invariant.

**Independent Test**: Can be fully tested by building the frontend against a
non-production service URL and verifying at runtime that all API/stream calls
target it — plus a static scan of built source finding zero provider hostnames.

**Acceptance Scenarios**:

1. **Given** a frontend build receives service locations via build configuration, **When** a user opens the app, **Then** all API and stream calls go to the configured backend.
2. **Given** the deploy-time generated hosting configuration still contains a backend URL placeholder, **When** the deployment artifact is produced, **Then** the deployment fails with a clear error naming the unsubstituted placeholder — it is never silently served.
3. **Given** production Firebase web configuration is incomplete, **When** the app boots in production mode, **Then** it aborts with an explicit configuration error naming the missing key — never falling back to fake/default project values.

---

### User Story 3 - Optional services stay optional (Priority: P3)

As a user, when an optional integration (scraper service, local Ollama, cache,
optional AI providers) is not configured or is unreachable, core functionality
still works, and health/status surfaces clearly present that capability as
"not configured" or "degraded" rather than broken.

**Why this priority**: Protects the graceful-degradation and provider-optional
architecture SupremeAI is built on; prevents configuration hardening from
accidentally turning optional dependencies into hard dependencies.

**Independent Test**: Can be fully tested by starting the backend with all
optional keys removed and verifying core user flows work while status surfaces
report the missing capabilities as not-configured.

**Acceptance Scenarios**:

1. **Given** an optional integration's key is absent, **When** the system starts, **Then** that capability is reported as not-configured and all core flows function normally.
2. **Given** an optional integration is configured but unreachable, **When** a user invokes a dependent feature, **Then** the user receives a clear degraded/unavailable response, the health view marks that dependency down, and unrelated features are unaffected.

---

### User Story 4 - Operators get a configuration validation & visibility artifact (Priority: P4)

As an operator, on production startup (and in admin tooling) I can see a
validation report that classifies every configuration key
(required/optional/conditional/secret/public), shows where each loaded value came
from (environment vs secret manager vs build-time), and lists missing keys —
without ever exposing secret values.

**Why this priority**: Makes the configuration contract observable, turning
future misconfigurations into 30-second diagnoses instead of multi-hour hunts.

**Independent Test**: Can be fully tested by starting the system in production
with a deliberately incomplete configuration and reading the validation report.

**Acceptance Scenarios**:

1. **Given** a production start with complete required configuration, **When** the validation report is produced, **Then** every key is listed with its classification and source, and secret values are masked.
2. **Given** a legacy configuration name is used, **When** validation runs, **Then** the report warns and names the canonical replacement while still honoring the legacy value.

---

### Edge Cases

- What happens when a CORS origin list is provided as malformed JSON? Production startup fails fast naming the variable and the parse error; non-production logs a warning and uses the safe default.
- What happens when a deploy-time hosting placeholder is not substituted? The deployment artifact check fails the release before it can be served.
- What happens when both a legacy and a canonical variable name are set? The canonical value wins and a deprecation warning is logged.
- What happens when the managed database CA certificate value is absent? The system warns and uses the base trust store; if verification then fails, the error is explicit — no insecure downgrade is ever attempted.
- What happens when the optional cache is disabled? Status shows "disabled"; no retry storm and no failure of core flows.
- What happens when an unknown portal type value is supplied? The system falls back to the default portal with a warning surfaced in the validation report.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST derive every service endpoint (main backend, admin backend, scraper, studio/client hosting) from deployment configuration; application source MUST NOT contain provider-specific production hostnames as defaults or fallbacks.
- **FR-002**: The system MUST fail fast at startup in production when any required configuration key is missing or empty, listing all missing keys in a single actionable error.
- **FR-003**: The system MUST treat optional integrations as not-configured (not failures) when their keys are absent, and core user flows MUST function without them.
- **FR-004**: The system MUST maintain a single source of truth for allowed CORS origins per portal (user/admin) consumed by all API surfaces; individual components MUST NOT define their own origin lists.
- **FR-005**: The system MUST support deploy-time generated hosting configuration that replaces backend-location placeholders during deployment; an unsubstituted placeholder MUST fail the deployment.
- **FR-006**: The system MUST read web authentication/identity configuration from build/deployment configuration; in production, missing required values MUST abort with an explicit error, and placeholder/default project values MUST NOT be used.
- **FR-007**: The system MUST classify every configuration key as required, optional, conditional, secret, or public, and MUST expose this classification through a startup/admin validation report with secret values masked.
- **FR-008**: The system MUST preserve backward compatibility with existing environment variable names; where a name is superseded, the legacy name MUST continue working and map to the canonical key with a deprecation warning for at least one release cycle.
- **FR-009**: Health and readiness surfaces MUST report per-dependency status (configured / not-configured / healthy / unreachable) including the configured source of each endpoint, without exposing secret values.
- **FR-010**: Replacing any service MUST be achievable by changing deployment configuration and redeploying the same source revision — no code change required.
- **FR-011**: A static verification check MUST be able to detect provider-specific production hostnames in runtime application source; after implementation the scan result MUST be zero occurrences (tests, fixtures, and documentation excepted).
- **FR-012**: Configuration parsing errors (e.g., malformed JSON lists) MUST surface the variable name and the nature of the parse problem.
- **FR-013**: Frontend service resolution MUST go through a single shared resolution path; components MUST NOT construct backend locations from inline literals or ad-hoc fallbacks.
- **FR-014**: User-local Ollama (when present) MUST remain optional and user-controlled; backend availability MUST NOT depend on it.

**Multi-tenant note**: This feature is platform-infrastructure only and does not
touch customer/tenant data — per-tenant scoping questions (cache keys, storage
keys, cross-tenant access) are not applicable. Audit scope: configuration
provenance is observable via the validation report and deployment logs.

### Key Entities *(include if feature involves data)*

- **DeploymentConfiguration**: a named configuration key with a classification (required/optional/conditional/secret/public), a source (environment, secret manager, build-time), and a scope (backend service, frontend build, deploy-time).
- **ServiceEndpoint**: a logical service (main backend, admin backend, scraper, studio client) with its resolved location, required/optional status, and the surfaces that consume it.
- **ConfigValidationReport**: a startup/admin artifact listing each key's status (loaded / missing / not-configured), source, and classification, with secret values masked.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A service-swap drill (change a service location via configuration only, redeploy the same source revision) completes with zero source-code edits and all client surfaces operational.
- **SC-002**: A static scan finds zero provider-specific production hostnames in runtime application source (backend and frontend) after implementation.
- **SC-003**: Production startup with any single required key missing fails in under 5 seconds with an error naming that key.
- **SC-004**: With all optional integrations unconfigured, core user flows (authentication, chat via a configured provider, health) still function, with degraded-capability labeling visible.
- **SC-005**: 100% of required configuration keys have a documented classification and appear in the startup validation report.
- **SC-006**: A production frontend build with an unsubstituted hosting placeholder is blocked before release.

---

## Assumptions

- The secret manager (Infisical) remains the authority for secret-classified values; machine-local composition files under `envs/` remain uncommitted and are not a distribution mechanism.
- Existing variable names (`ALLOWED_HOSTS`, `CORS_ORIGINS`, `USER_CORS_ORIGINS`, `ADMIN_CORS_ORIGINS`, `SUPREMEAI_USER_BACKEND_URL`, `SUPREMEAI_ADMIN_BACKEND_URL`, `OLLAMA_URL`, …) form the canonical contract baseline unless explicitly superseded with a deprecation path.
- The current hosting target (Firebase Hosting with deploy-time generated configuration) is the reference deployment; requirements are written target-agnostically so another host can be used through the same placeholder/validation mechanism.
- Existing modules for CORS policy and configuration validation are the reuse points — this feature hardens and unifies them rather than replacing the architecture (Principle VI).
- Free-tier constraints apply: no new always-on service is introduced to validate configuration (Principle X).


