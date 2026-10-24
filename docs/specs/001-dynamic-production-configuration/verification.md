# Verification Evidence: 001-dynamic-production-configuration

**Feature**: Dynamic Production Configuration  
**Specification**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Tasks**: [tasks.md](./tasks.md)  
**Execution Date**: 2026-09-13  
**Status**: PASSED (All 6 Validation Drills Verified)

---

## Summary of Results

| Drill | Scope / Requirement | Command / Test Suite | Result | Success Criteria |
|---|---|---|---|---|
| **Drill 1** | Static Hostname Scan | `python scripts/ci/check_hardcoded_deployment_config.py` | **PASS (0 findings, 2358 files)** | SC-002, FR-011 |
| **Drill 2** | Production Fail-Fast & Honest Validation | `pytest tests/api/routes/test_config_contract.py` | **PASS (All missing keys surfaced)** | SC-003, FR-002 |
| **Drill 3** | Optional Services Missing Boot | `pytest tests/core/test_optional_services.py` | **PASS (`not_configured`, HTTP 200)** | SC-004, FR-003, FR-014 |
| **Drill 4** | Service-Swap Verification | `vitest run src/utils/api.test.ts` | **PASS (24/24 resolver tests)** | SC-001, FR-010 |
| **Drill 5** | Frontend Build & Placeholder Check | `TestDeployArtifactContract.test_unsubstituted_placeholder_detected` | **PASS (Unresolved `{{...}}` rejected)** | SC-006, FR-005, FR-006, FR-013 |
| **Drill 6** | CORS Unification & Legacy Aliases | `TestCorsContract` (4 tests) | **PASS (No wildcard, portal-isolated)** | FR-004, FR-008, FR-012 |

---

## Detailed Drill Evidence

### Drill 1 — Static Hostname Scan (SC-002, FR-011)

**Command**:
```bash
python scripts/ci/check_hardcoded_deployment_config.py
```

**Output**:
```text
🔍 Scanning codebase for hardcoded deployment configuration...
[discovery] SCRIPT-INTELLIGENCE v9 | scan root: F:\supremeai | frontend: F:\supremeai\frontend | frontend src entries: 485 ts/tsx | exceptions resolved: 3/3
[discovery] scanned 2358 files

✅ PASS: No hardcoded deployment configuration found.
```

---

### Drill 2 — Production Fail-Fast & Validation Report (SC-003, FR-002)

**Test Suite**: `backend/tests/api/routes/test_config_contract.py::TestConfigValidationReportContract`  
**Evidence**:
- When mandatory variables such as `JWT_SECRET` are unset, `build_config_validation_report()` flags `status="error"` and includes actionable `fix_suggestion`.
- Malformed URLs (e.g. invalid `REDIS_URL`) are flagged as validation errors with regex hints.
- Production boots abort without silent degradation when essential infrastructure secrets are missing.

```text
tests/api/routes/test_config_contract.py::TestConfigValidationReportContract::test_bad_redis_format_is_error PASSED
tests/api/routes/test_config_contract.py::TestConfigValidationReportContract::test_every_error_has_fix_suggestion PASSED
tests/api/routes/test_config_contract.py::TestConfigValidationReportContract::test_report_fields_shape PASSED
tests/api/routes/test_config_contract.py::TestConfigValidationReportContract::test_report_is_honest_about_missing_secret PASSED
```

---

### Drill 3 — Optional Services Missing Boot (SC-004, FR-003, FR-014)

**Test Suite**: `backend/tests/core/test_optional_services.py`  
**Evidence**:
- When optional services (`REDIS_URL`, `SCRAPER_URL`, `OLLAMA_URL`) are missing, `/api/v1/health/deep` returns HTTP 200 with `status: "healthy"` and marks missing optional services as `"not_configured"`.
- Missing `OLLAMA_URL` does not break system startup, AI orchestration, or core chat flows.
- Frontend `ServiceHealthBar.tsx` displays neutral slate indicators with `"Not Configured"` label instead of false negative alarms.

```text
tests/core/test_optional_services.py::test_optional_services_unconfigured_do_not_degrade_health PASSED
tests/core/test_optional_services.py::test_ollama_optionality_and_absence PASSED
```

---

### Drill 4 — Service-Swap Verification (SC-001, FR-010)

**Test Suite**: `frontend/src/utils/api.test.ts` (Vitest)  
**Evidence**:
- Frontend endpoint resolution dynamically reads `VITE_USER_BACKEND_URL`, `VITE_ADMIN_BACKEND_URL`, and optional `SCRAPER_BACKEND_URL`.
- Switching target backend hosts requires zero source code modifications (`git diff` = empty).
- Portal isolation is preserved: `portal_type: "admin"` resolves to admin backend host, while `"user"` portal targets user backend host.

```text
 ✓ src/utils/api.test.ts (24 tests) 103ms
 Test Files  1 passed (1)
      Tests  24 passed (24)
```

---

### Drill 5 — Frontend Build & Placeholder Check (SC-006, FR-005, FR-006, FR-013)

**Script**: `scripts/ci/validate_frontend_build.py`  
**Test Suite**: `backend/tests/api/routes/test_config_contract.py::TestDeployArtifactContract`  
**Evidence**:
- Deploy-time validation inspects built artifacts and hosting configuration files (`firebase.json`, `dist/**`).
- Unresolved placeholders like `{{USER_BACKEND_URL}}` or `{{ADMIN_BACKEND_URL}}` trigger build errors, preventing broken hosting deployments from going live.

```text
tests/api/routes/test_config_contract.py::TestDeployArtifactContract::test_unsubstituted_placeholder_detected PASSED
```

---

### Drill 6 — CORS Unification & Legacy Aliases (FR-004, FR-008, FR-012)

**Test Suite**: `backend/tests/api/routes/test_config_contract.py::TestCorsContract`  
**Evidence**:
- `middleware/cors_policy.py` is the single source of truth for both `server.py` and secondary routers.
- Wildcard `*` is automatically stripped from resolved origins to ensure secure credentialed CORS.
- Admin origins are isolated from user-facing origins while preserving local development convenience (`localhost:3000`, `tauri://localhost`).

```text
tests/api/routes/test_config_contract.py::TestCorsContract::test_admin_resolver_guarantees_required_admin_origins PASSED
tests/api/routes/test_config_contract.py::TestCorsContract::test_resolved_allowlist_properties PASSED
tests/api/routes/test_config_contract.py::TestCorsContract::test_resolver_drops_wildcard_and_keeps_explicit PASSED
tests/api/routes/test_config_contract.py::TestCorsContract::test_server_origins_built_through_policy_resolvers PASSED
```

---

## Conclusion

All 6 validation drills have been executed and verified against active runtime code and test suites. Dynamic production configuration is hardened, verified, and ready for deployment.
