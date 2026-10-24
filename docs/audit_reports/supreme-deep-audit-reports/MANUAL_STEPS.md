# Manual Task List

Remaining work that requires operator review, external credentials, or a deliberate rollout:

## External and production-only tasks

- [ ] Provision and verify MCP gateway persistence in the production database.
- [ ] Complete MCP gateway route registration and end-to-end transport tests against deployed nodes.
- [ ] Review tenant isolation, authorization scopes, SSRF policy, secret handling, and audit retention for gateway connections. Code-level synthetic tenant fallbacks are now fail-closed in task, research, crawler, admin, remediation, memory, and MCP audit paths; production authorization/RLS review remains required.
- [ ] Configure and verify Supabase `ai_memory` schema, RLS, retention, and privacy sign-off.
- [x] Triage the six skipped tests reported by the latest checkpoint; reconciled: the "6 skipped" count was an import-time `--collect-only` artifact, while the active codebase has 103 markers across 53 files documented in `docs/SKIPPED_TESTS.md`.
- [ ] Run root-level lint across `tools/`, `scripts/`, `packages/`, and `.github/scripts/`, then fix or explicitly baseline findings.
- [ ] Install the backend test/runtime dependencies in CI or the deployment validation environment, then rerun router-import and startup checks; the local run is currently blocked by missing `fastapi`, so it is not evidence of a route defect.
- [ ] Review stale remote branches and repository stashes before cleanup; preserve any needed work before deletion.
- [ ] Perform production deployment verification, health checks, rollback readiness, and observability review.
- [ ] Complete CI hard-blocking, branch protection/CODEOWNERS, backup-restore drill, and data-retention/privacy approval before customer launch.

## Code follow-ups requiring an intentional implementation slice

- [x] Require an explicit authenticated `tenant_id` for canonical task execution; synthetic default tenant contexts now fail closed (`runtime/task_context.py`, `runtime/task_runtime.py`, with regression coverage).
- [x] Validate the execution-mode Settings UI end to end against the backend contract, including authorization and persistence (`SettingsPage.tsx` wired to `connectionsApi`, contracts, and `SettingsPage.test.tsx`).
- [x] Finish unified-store staging rollout: exercised `chatSlice` behind the feature flag, verified legacy-store compatibility, and confirmed instant rollback via localStorage/disableUnifiedStore (`unifiedStore.ts`, `unifiedStore.test.ts`, `chatStore.test.ts`).
- [x] Decide whether medium-priority provider stubs (`cloud_sandbox_orchestrator`, resource lifecycle, swarm base classes, skill provisioning) should be implemented, converted to explicit capability responses, or formally deferred; resolved: `PersistentSandbox` & `SandboxSession` implemented in `cloud_sandbox_orchestrator.py`, 7/7 previously skipped tests in `test_cloud_sandbox_full.py` now unskipped and passing, `collaborative_editor.py` import path corrected, and abstract base contracts verified.
- [ ] Raise backend/frontend coverage to the project gates after skip-marker triage; do not count skipped tests as coverage.

## Configuration and integration findings from the root audit

- [ ] Deploy the canonical `USER_CORS_ORIGINS`, `ADMIN_CORS_ORIGINS`, and `CORS_ORIGINS` values consistently across every backend node; verify authenticated browser preflight from each production frontend.
- [ ] Run the production compose stack with and without the `observability` profile; confirm OTLP is disabled in the base profile and healthy when the collector profile is enabled.
- [x] Correct the OTEL collector bind mount to the canonical `infrastructure/monitoring/opentelemetry/` path; the deployment checkout still needs a clean observability-profile startup check.
- [x] Intentionally remove the production Alertmanager service from the lightweight observability profile; no Alertmanager config was present, and Prometheus no longer points at an unavailable alert target. Reintroduce it only with an approved config and routing owner.
- [ ] Verify the corrected Grafana and Prometheus bind mounts exist in the deployment checkout and that dashboards load after a clean volume/bootstrap; Grafana provisioning was intentionally omitted because that directory is absent, so dashboard datasource/bootstrap behavior remains a deployment check.
- [ ] Verify the deployed image exposes `/health/live`, `/api/v1/health/live`, and `/api/v1/health/ready` on the same application entrypoint used by the container healthcheck.
- [ ] Validate that the deployed frontend build uses the intended `VITE_USER_BACKEND`/`VITE_ADMIN_BACKEND` values; build-time Vite variables cannot be changed after deployment.
- [ ] Execute browser preflight and authenticated request tests for `X-Device-Fingerprint`, `X-CSRF-Token`, `Authorization`, and `X-JIT-OTP` against each portal origin.

## Lightweight QA rollout follow-ups

- [x] Add a small machine-readable QA contract covering build, type, unit, integration, security, release, MCP, privacy, accessibility, and human-review boundaries (`qa/checklist/core.yaml`).
- [x] Add deterministic checklist validation and a focused CI workflow (`scripts/ci/validate_qa_checklist.mjs`, `.github/workflows/qa-contract.yml`).
- [ ] Add browser E2E suites only after stable staging URLs, seeded QA accounts, and cleanup/rollback fixtures exist; do not add credential-dependent tests to PR CI prematurely.
- [ ] Add release-gate aggregation only when the deployment workflow has a single authoritative artifact/report path; avoid duplicating the existing CI gates.
- [ ] Pin the third-party setup actions in `qa-contract.yml` to approved full SHAs before enabling repository-wide supply-chain enforcement.
- [ ] Reconcile the checklist IDs and severities with the authoritative manual QA catalog during the next audit pass.

## Findings reconciled during this review

- [x] `chatSlice` is present in the checkout; the older audit statement that it is missing is stale. Its rollout is still unverified.
- [x] Device-fingerprint generation and API-client collection are present; middleware/backend propagation and enforcement still need an end-to-end proof.
- [x] Existing `pass` matches are mostly exception-handler fallbacks, test fixtures, or intentional empty classes; review only runtime stubs that raise `NotImplementedError` before changing them.
- [x] Re-run the audit against the current commit and update stale counts/statuses: the 103-vs-6 skipped test discrepancy is reconciled. 6 was an import-time `--collect-only` count, while 103 active markers exist across 53 test files governed in `docs/SKIPPED_TESTS.md` with target <30.
