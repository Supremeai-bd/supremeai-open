# Phase 0 — Research & Decisions

Feature: 001-dynamic-production-configuration · Date: 2026-08-29
Method: direct codebase inspection (files cited inline); no external research required.

## D1 — Canonical CORS variable names

**Decision**: `cors_policy.py` is the single CORS source of truth. Canonical keys:
`CORS_ORIGINS` (user portal) and `ADMIN_CORS_ORIGINS` (admin portal). Legacy
`ALLOWED_ORIGINS` (read today by `api/server.py`) and `USER_CORS_ORIGINS`
(present in machine-local `envs/*.env`, never read by any tracked code) map onto
the canonical keys with deprecation warnings.

**Rationale**: `cors_policy.py` already implements the security-critical rules
(wildcard rejection, per-portal filtering, no-FastAPI dependency design, existing
tests). `server.py` duplicating origin logic is the drift risk.

**Alternatives considered**: (a) keep three independent names — rejected:
untestable contract, proven misconfiguration risk; (b) move everything into
pydantic Settings only — rejected: portal filtering logic belongs in the
dependency-free policy module that both app boot paths and tests can use.

## D2 — Single CORS wiring path

**Decision**: `api/server.py` and `core/app_builder.py` both resolve origins via
`cors_policy.resolve_user_cors_origins()` / `resolve_admin_cors_origins()`.
Dev localhost conveniences stay as explicit dev-only additions inside the policy
module, not inline literals at call sites.

**Rationale**: one enforcement point for wildcard filtering and portal isolation.

## D3 — Backend endpoint resolution

**Decision**: Service locations (`main backend`, `admin backend`, `scraper`)
resolve from Settings: explicit env value first, then `RENDER_SERVICE_NAME`-derived
default (logic already present in `config_validation.py`), then — only if the
service is optional — `not_configured`. Required services with no resolvable
location abort production boot listing all missing keys. Remove hardcoded
fallbacks in `config_routes.py`, `health_aggregation.py`, `service_topology.py`.

**Rationale**: reuses the existing validation module and its
`validate_production_completeness()` extension point; free-tier Render naming is
already understood there.

**Alternatives**: hard-fail every service URL — rejected: scraper/cache are
optional by architecture (Principle III).

## D4 — Frontend endpoint resolution

**Decision**: `utils/api.ts` stays the sole resolver; export an optional
`SCRAPER_BACKEND_URL` (unset → consumers render not-configured state). Delete the
inline `|| 'https://<render-scraper-url>'` literals in
`CrownJewelBrowser.tsx` and `ServiceHealthMonitor.tsx`.

**Rationale**: api.ts already has production fail-fast, portal selection, and
relative-path hosting logic; components bypassing it is the defect.

## D5 — Firebase configuration

**Decision**: `firebase.ts` keeps `init.json`-first flow; in production builds the
env fallback requires a complete config (all fields) — fake defaults become
dev-only. Deploy-time validation rejects a generated hosting config still
containing `{{USER_BACKEND_URL}}`.

**Rationale**: today a prod build with `apiKey` set but other fields missing
silently receives placeholder project values (`supremeai-a`), pointing auth at
the wrong project — fail loud instead.

## D6 — Static hostname scan (FR-011)

**Decision**: Extend the **existing** scanner `scripts/ci/check_hardcoded_deployment_config.py`
(already implements `.onrender.com` / `.vercel.app` / `.firebaseapp.com` / `.web.app`
patterns with ignore lists and non-zero CI exit). Required extensions: add `specs/`
(feature artifacts legitimately cite hostnames as evidence — they contain no
secret values) and `backend/pyerrorfix/` (detector knowledge base) to
`IGNORE_PATHS`; wire into pre-commit as advisory until baseline reaches zero.

**Rationale**: The scanner already exists with the right design (Principle VI);
duplicating it as a new `scripts/check_hardcoded_hosts.py` was rejected.

**Alternatives**: new standalone script — rejected as duplication; third-party
linter — rejected: new dependency for an existing 130-line check (Principle X).
