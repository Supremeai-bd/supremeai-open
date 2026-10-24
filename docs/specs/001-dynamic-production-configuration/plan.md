# Implementation Plan: Production Configuration & Dynamic Endpoint Hardening

**Branch**: `chore/spec-kit-bootstrap` (pilot rides the adoption branch; feature PR target per `CONTRIBUTING.md`) | **Date**: 2026-08-29 | **Spec**: [specs/001-dynamic-production-configuration/spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-dynamic-production-configuration/spec.md`

## Summary

Make SupremeAI's production configuration deployment-agnostic by establishing one
canonical configuration contract across the backend services, the frontend builds,
and deploy-time hosting artifacts. The approach hardens and unifies modules that
already exist — `backend/middleware/cors_policy.py` (portal CORS policy),
`backend/core/config_validation.py` (production completeness validation),
`frontend/src/utils/api.ts` (portal-based endpoint resolution with production
fail-fast), `frontend/src/firebase.ts` (init.json-first Firebase config) — and
removes every hardcoded provider hostname from runtime source paths. No new
services, databases, or runtime dependencies are introduced.

## Technical Context

**Language/Version**: Python 3.11+ (FastAPI 0.104+, pydantic v2 settings); TypeScript 5 / React 18 / Vite; Node 18+

**Primary Dependencies**: FastAPI + existing pydantic `Settings` (`backend/core/config.py`), existing secret vault (`backend/core/security/secret_vault.py`, Infisical-backed), Firebase Hosting generated config (`firebase.template.json`), existing portal CORS policy module. **No new dependencies** (Principle VI).

**Storage**: N/A — configuration only; no schema or data changes. Configuration provenance is observable through the new validation report.

**Testing**: `pytest` (backend, incl. existing `backend/tests/core/test_security.py` CORS tests), Vitest (frontend, existing `App.test.tsx` patterns), `ruff` (already wired), plus a repo-local static scan script (FR-011).

**Target Platform**: Render free-tier services (main backend, admin backend, scraper), Firebase Hosting (user portal), local dev (Windows/PowerShell primary).

**Project Type**: Polyglot web service + SPA monorepo (existing `backend/` + `frontend/` layout).

**Performance Goals**: Production boot with missing required config fails in < 5s; zero added latency on the request path (validation is startup/admin-time only).

**Constraints**: Free-tier resource ceilings (no new always-on process); secrets MUST never appear in logs, reports, or specs; backward compatibility for existing env var names (one-release deprecation cycle); Windows-primary dev environment (PowerShell scripts).

**Scale/Scope**: 4 logical services (main backend, admin surface, scraper, studio-client); ~25 configuration keys in the contract; touches ~10 existing source files + 1 new scan script + 1 new classification registry.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Evidence |
|---|---|---|
| I — Core Independence | ✅ PASS | Endpoints move behind configuration; no provider coupling added |
| II — Security & HITL | ✅ PASS | No auth/HITL surface changes; validation report masks secret values; CORS isolation per portal preserved |
| III — Graceful Degradation | ✅ PASS | Optional keys yield `not_configured` status, never system failure |
| IV — Dynamic Production Configuration | ✅ PASS | This feature implements the principle (env/Infisical sourcing, no hardcoded values) |
| V — User-Local AI Is Optional | ✅ PASS | Ollama stays optional/user-controlled (FR-014) |
| VI — Existing Architecture First | ✅ PASS | Reuses `cors_policy.py`, `config_validation.py`, `config_secrets.py`, `utils/api.ts`, `firebase.ts`; zero new subsystems/deps |
| VII — Multi-Tenant Safety | ✅ PASS | No tenant data touched; per-portal origin isolation actually strengthened |
| VIII — Verification Before Completion | ✅ PASS | Static scan + fail-fast drills + backend/frontend tests are in-scope tasks |
| IX — Vendor Exit Path | ✅ PASS | Host-agnostic placeholder mechanism (`{{USER_BACKEND_URL}}`) keeps hosting replaceable |
| X — Resource Awareness | ✅ PASS | Static script instead of a validation service; no new always-on component |

**Post-Phase-1 re-check**: No violations introduced by design artifacts (see
`research.md`, `data-model.md`, `contracts/config-contract.md`, `quickstart.md`).
Complexity Tracking table remains empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-dynamic-production-configuration/
├── spec.md                    # Feature specification (done)
├── plan.md                    # This file
├── research.md                # Phase 0: decisions & rationale
├── data-model.md              # Phase 1: config-domain entities
├── quickstart.md              # Phase 1: end-to-end validation drills
├── contracts/
│   └── config-contract.md     # Phase 1: canonical configuration key contract
├── checklists/
│   └── configuration.md       # Requirements-quality checklist (reviewer-owned)
└── tasks.md                   # Phase 2 (/speckit-tasks output)
```

### Source Code (repository root — existing layout, no new top-level dirs)

```text
backend/
├── core/
│   ├── config.py                      # Settings (env parsing)
│   ├── config_secrets.py              # secret batch-load (Infisical) — reuse
│   ├── config_validation.py           # production completeness validation — extend
│   ├── config_classification.py       # NEW: canonical key registry (classification, aliases)
│   └── db_ssl.py                      # CA-cert handling (existing, uncommitted WIP)
├── middleware/cors_policy.py          # portal CORS source of truth — extend (aliases)
├── api/
│   ├── server.py                      # legacy ALLOWED_ORIGINS wiring — unify via cors_policy
│   ├── routes/config_routes.py        # /config/public hardcoded URL — config-driven
│   ├── routes/health_aggregation.py   # hardcoded service fallbacks — settings-driven
│   └── routes/service_topology.py     # hardcoded service fallbacks — settings-driven
└── tests/core/                        # contract & CORS tests (pytest)

frontend/
├── src/utils/api.ts                   # sole endpoint resolver (already fail-fast) — extend w/ scraper
├── src/firebase.ts                    # init.json-first; fake defaults gated to dev
├── src/components/admin/data/CrownJewelBrowser.tsx      # remove scraper fallback literal
├── src/components/admin/infra/ServiceHealthMonitor.tsx  # remove scraper fallback literal
├── src/components/auth/ServiceHealthBar.tsx             # not-configured labeling
└── src/utils/api.test.ts              # NEW: resolver tests (Vitest)

scripts/
└── ci/check_hardcoded_deployment_config.py  # EXISTING scanner (FR-011) — extend exclusions (specs/, pyerrorfix)

firebase.template.json                 # {{USER_BACKEND_URL}} placeholder — deploy check
envs/                                  # machine-local env composition (untracked)
```

**Structure Decision**: Reuse the existing polyglot layout. The only new files are
one backend registry module and one frontend test file; the static scan reuses the
existing `scripts/ci/check_hardcoded_deployment_config.py` rather than introducing
a duplicate (Principle VI). No new package, service, or top-level directory
(Principle X).

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|

*(Empty — no constitution violations; no justified complexity.)*


