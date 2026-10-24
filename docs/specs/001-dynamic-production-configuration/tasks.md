# Tasks: 001-dynamic-production-configuration

**Input**: Design documents from `/specs/001-dynamic-production-configuration/` (spec.md, plan.md, research.md, data-model.md, contracts/config-contract.md, quickstart.md)

**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included deliberately — constitution Principle VIII makes tests/security checks part of implementation (overrides the "tests optional" default).

**⚠️ Coordination**: `backend/api/routes/health.py`, `backend/core/config_secrets.py`, `backend/core/db_ssl.py`, `backend/database/*` have uncommitted operator WIP. Tasks touching those files (T008, T017) must not start until the WIP is committed or stashed.

**Organization**: Tasks grouped by user story (spec.md US1–US4) for independent implementation and testing.

## Phase 1: Setup (Shared Infrastructure)

- [ ] T001 Create canonical configuration registry (classification, aliases, required-in-production, source) in backend/core/config_classification.py per data-model.md Entity 1 and contracts/config-contract.md
- [ ] T002 [P] Extend the existing scanner scripts/ci/check_hardcoded_deployment_config.py (add specs/ and backend/pyerrorfix/ to IGNORE_PATHS; verify pattern coverage) and run it to record the pre-implementation baseline (FR-011; research.md D6)

**Checkpoint**: contract and enforcement tooling exist — foundational work can start.

---

## Phase 2: Foundational (Blocking Prerequisites)

**⚠️ CRITICAL**: No user story work begins until this phase is complete.

- [ ] T003 Extend production completeness validation in backend/core/config_validation.py to abort production boot listing ALL missing required keys in one error (FR-002, SC-003) — depends on T001
- [ ] T004 Implement ConfigValidationReport builder with structural secret masking in backend/core/config_validation.py (loaded/missing/not_configured/alias_used + source + classification) per data-model.md Entity 3 (FR-007) — depends on T003
- [ ] T005 [P] Add legacy alias resolution with deprecation warnings and malformed-value errors (variable name + parse cause) to backend/middleware/cors_policy.py and backend/core/config.py loading (aliases: ALLOWED_ORIGINS, USER_CORS_ORIGINS; FR-008, FR-012)

**Checkpoint**: Foundation ready — user stories can proceed (US1 first; US2/US3 may parallelize after US1 merges to keep review focused).

---

## Phase 3: User Story 1 — Operator swaps a service through configuration only (Priority: P1) 🎯 MVP

**Goal**: Every backend service location resolves from deployment configuration; hardcoded production hostnames removed from runtime source paths.

**Independent Test**: quickstart.md Drills 1, 2, 4, 6 — swap a service URL via config only, redeploy same revision, verify all surfaces; static scan finds zero occurrences.

### Implementation for User Story 1

- [ ] T006 [US1] Replace hardcoded BACKEND_URL and ENV value in backend/api/routes/config_routes.py /config/public with registry-driven resolution and review the 1h/24h CDN cache headers for staleness on swap (FR-001, FR-010; CHK017)
- [ ] T007 [US1] Replace hardcoded ADMIN_URL/SCRAPER_URL fallbacks in backend/api/routes/health_aggregation.py with registry-driven resolution; scraper absent ⇒ not_configured (FR-001, FR-003)
- [ ] T008 [US1] Replace hardcoded fallbacks in backend/api/routes/service_topology.py the same way (FR-001)
- [ ] T009 [US1] Unify CORS wiring: backend/api/server.py and backend/core/app_builder.py resolve origins exclusively via backend/middleware/cors_policy.py resolvers; dev localhost conveniences move into the policy module (FR-004; research.md D2)
- [ ] T010 [US1] Add backend tests backend/tests/core/test_config_contract.py: fail-fast enumerates all missing keys; canonical-beats-alias; malformed JSON names the variable; portal origin isolation (user list rejects admin origins) — extends existing backend/tests/core/test_security.py patterns

**Checkpoint**: MVP — a service swap requires only configuration changes; Drill 1/2/4/6 pass.

---

## Phase 4: User Story 2 — Frontend resolves endpoints without hardcoded URLs (Priority: P2)

**Goal**: All frontend service resolution flows through the shared resolver; no inline provider hostnames or fake project identifiers in production.

**Independent Test**: quickstart.md Drills 1, 5 — build against a non-production URL, verify runtime targets it; scan of built output finds zero provider hostnames.

### Implementation for User Story 2

- [x] T011 [P] [US2] Export optional SCRAPER_BACKEND_URL resolution from frontend/src/utils/api.ts following the existing fail-fast/portal pattern (FR-003, FR-013; research.md D4)
- [x] T012 [P] [US2] Remove scraper fallback literals in frontend/src/components/admin/data/CrownJewelBrowser.tsx and frontend/src/components/admin/infra/ServiceHealthMonitor.tsx; render not-configured state when unset (FR-001, FR-003)
- [x] T013 [US2] Harden frontend/src/firebase.ts: production requires the complete generated-init or full VITE_FIREBASE_* set; fake/default project values gated to development only (FR-006; research.md D5)
- [x] T014 [US2] Add deploy-artifact check failing on unsubstituted {{USER_BACKEND_URL}} in the generated hosting config (deploy/build script under scripts/ or firebase tooling step) (FR-005, SC-006)
- [x] T015 [US2] Add frontend resolver tests frontend/src/utils/api.test.ts (Vitest): production fail-fast, portal selection, relative-path logic, scraper-optional state

**Checkpoint**: Frontend built from any deployment's configuration talks to that deployment's backend; no silent fallbacks remain.

---

## Phase 5: User Story 3 — Optional services stay optional (Priority: P3)

**Goal**: Absent or unreachable optional integrations produce explicit not-configured/degraded states; core flows never break.

**Independent Test**: quickstart.md Drill 3 — boot with all optional keys unset; core flows work; statuses correct.

### Implementation for User Story 3

- [x] T016 [US3] Ensure backend/api/routes/health.py and frontend/src/components/auth/ServiceHealthBar.tsx distinguish not_configured / unreachable / disabled for optional dependencies (REDIS_URL, SCRAPER_URL, OLLAMA_URL) with latency reporting kept (FR-003, FR-009)
- [x] T017 [US3] Verify Ollama stays optional: missing OLLAMA_URL must not affect boot or availability; add a guard/test only if not already guaranteed (FR-014)

**Checkpoint**: Drill 3 passes — zero functional coupling to optional integrations.

---

## Phase 6: User Story 4 — Configuration validation & visibility artifact (Priority: P4)

**Goal**: Operators can read a masked, classified, provenance-aware configuration report at startup and in admin tooling.

**Independent Test**: Start production with a deliberately incomplete configuration; read the report; every key classified, secrets masked, aliases flagged.

### Implementation for User Story 4

- [x] T018 [US4] Expose the ConfigValidationReport to operators: startup log summary + admin read endpoint in backend/api/routes/config_routes.py (admin-token protected, secret-masked) (FR-007)
- [x] T019 [US4] Surface legacy-alias deprecation warnings and malformed-value warnings in the report and admin view (FR-008, FR-012)

**Checkpoint**: Configuration drift is diagnosable in minutes without shell access to services.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T020 [P] Document the canonical contract for operators: update envs/README and .env.example files (names and classification references only — never values), linking to contracts/config-contract.md (FR-007)
- [x] T021 [P] Wire scripts/ci/check_hardcoded_deployment_config.py into the existing pre-commit chain as advisory (non-blocking until baseline reaches zero) (FR-011)
- [x] T022 Execute all quickstart.md drills (1–6) and record evidence (command output summaries) in this feature directory as verification.md (SC-001…SC-006)
- [x] T023 Reviewer pass on checklists/configuration.md (CHK001–CHK025) before merge request; resolve or formally accept any open items

---

## Dependencies & Execution Order

### Phase dependencies
- Setup (T001–T002) → Foundational (T003–T005) → US1 (T006–T010) → US2 (T011–T015) → US3 (T016–T017) → US4 (T018–T019) → Polish (T020–T023)
- Within phases, [P] tasks are file-independent and parallelizable; T004 depends on T003 (same module); T006–T008 share the registry from T001.

### Story independence
- US2, US3, US4 depend on Foundational only — not on each other — but the pilot runs them sequentially (P1→P4) so each increment is reviewable per `CONTRIBUTING.md`.
- MVP scope = Setup + Foundational + US1 (T001–T010). Validate and demo the swap drill before continuing.

## Implementation Strategy

1. Land T001–T005 as one reviewable commit (contract + enforcement).
2. Land US1 (T006–T010) as the MVP increment; run Drills 1/2/4/6.
3. Land US2 → US3 → US4 increments; run Drill 5 / Drill 3 / report review respectively.
4. Polish (T020–T023) closes verification and documentation before `/speckit-converge`.

## Notes

- Every task cites the FR/SC it serves for traceability (analyze gate).
- No task introduces a new dependency, service, or database (constitution VI/X).
- Tasks touching operator WIP files (T016, and any overlap in backend/core/) must wait for the WIP to be committed or stashed.

