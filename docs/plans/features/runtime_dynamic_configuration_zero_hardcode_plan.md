---
id: runtime-dynamic-configuration-zero-hardcode
subject: "SupremeAI — Remaining Dynamic Configuration / Zero-Hardcode Implementation Plan"
document_role: implementation
planning_authority: Architecture Circle
canonical: candidate
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
related: docs/plans/architecture/dynamic_configuration_zero_hardcode_roadmap.md
target_scope: combined_ecosystem
---

# SupremeAI — Remaining Dynamic Configuration / Zero-Hardcode Implementation Plan

> ## Reconciliation Status (final-test, 2026-09-14 — verify-before-implement audit against main@83a7cfba)
>
> | § | Item | Verdict on main | Where |
> |---|------|-----------------|-------|
> | 2 | Remove production docs-password hardcoded fallback | **DONE on main** (PR #293 tri-state docs-auth policy; `dev_password_only` never valid in production/staging) | `backend/core/middleware/docs_auth.py` |
> | 3 | Remove unsafe ALLOWED_HOSTS fallback (bare `onrender.com`) | **FIXED in this branch** — bare-apex last-resort fallback removed (fail-closed), platform-env discovery kept, explicit bare platform apex domains now rejected outright (suffix Host-matching would trust every platform subdomain). Regression-locked by 14 tests incl. 3 real-boot subprocess probes | `backend/core/config_validation.py`, `backend/tests/core/test_allowed_hosts_policy.py` |
> | 4 | Firebase generator correctness (rewrite contract) | **FIXED in this branch** — generator now fail-closed: missing `/api/**` + `/api/v1/**` + `/admin-api/**` rewrites, foreign rewrite destinations, source-prefix-proof violations and missing SPA fallback all exit 1 (missing `/api/**` was WARNING-only before). Bonus latent bug fixed: raw `"}}"` substring false-positived on JSON tails like `{"hosting": {...}}` | `scripts/deploy/generate_firebase_config.py`, `backend/tests/scripts/test_generate_firebase_config.py` |
> | 5 | `VITE_PORTAL_TYPE` user/admin build selection | **OBSOLETE** — unified single frontend (no portal split build; `firebase.template.json` ships `user` + `admin` hosting targets from one build) | — |
> | 6 | Rewrite semantics unification | **DONE on main** (single `{{BACKEND_URL}}` placeholder drives all sites) | `firebase.template.json` |
> | 7 | Silent failures (`set -e` etc.) | **DONE on main** | `scripts/render_build_frontend.sh` |
> | 8 | Production CORS source-of-truth | **VERIFIED no hardcoded origins** (defaults are empty frozensets; denylist-enforced) | `backend/core/middleware/cors_policy.py` |
> | 9 | Operational rollout | **OPERATIONAL** (deploy scripts fail-fast on missing backend URL) | `scripts/render_build_frontend.sh` |
> | 10 | Hardcoded-config CI enforcement | **P1 deferred** (tracked; do not block this milestone) | — |
>
> Scope note: §2/§5/§6/§7 were closed by main (PR #293 + unified-frontend migration) BEFORE this branch — re-implementing them would duplicate shipped capability. This branch delivers §3 + §4 only.

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Scope:** Finish the dynamic-configuration migration without breaking the live frontend/backend deployment.

## 1. Current Audit Verdict

The previous dynamic-configuration plan is **partially implemented**.

Already in place:
- `firebase.template.json` exists with `{{USER_BACKEND_URL}}` and `{{ADMIN_BACKEND_URL}}`.
- `scripts/render_build_frontend.sh` now fails when the required portal backend variable is missing instead of deriving a Render hostname.
- `frontend/src/utils/api.ts` uses `VITE_ADMIN_BACKEND` / `VITE_USER_BACKEND` and the canonical `/api/v1/health/live`.
- Cross-portal backend failover is intentionally disabled.
- Backend CORS is centralized.
- Some cross-variable integration validation already exists.

The remaining risks are:

```text
P0  hardcoded/unsafe production fallback configuration
P0  Firebase generated-config pipeline correctness
P0  portal-aware frontend build correctness
P0  production CORS source-of-truth
P1  hostname-based frontend routing residue
P1  centralized endpoint/config cleanup
P1  hardcoded-config CI enforcement
P2  config drift / documentation
```

The current `firebase.template.json` is correctly placeholder-driven. fileciteturn116file0

---

# 2. P0 — Remove Hardcoded Production Password Fallback

Current `backend/core/config_validation.py` still contains a hardcoded production fallback password:

```text
supreme-admin-2026-prod
```

This violates the zero-hardcode policy.

### Required

When:

```text
ENV=production
DOCS_AUTH_ENABLED=true
SUPREMEAI_DOCS_PASSWORD missing
```

the application must:

```text
FAIL FAST
```

Do not generate a silent production password and do not use a hardcoded fallback.

### Acceptance

- [ ] No production password exists in source.
- [ ] Missing production docs password fails clearly.
- [ ] Development behavior remains intentional and documented.

---

# 3. P0 — Remove Hardcoded ALLOWED_HOSTS Production Fallback

Current validation can auto-populate deployment-specific production hosts when `ALLOWED_HOSTS` is missing.

This violates:

> Production configuration comes from environment/Infisical, not code.

### Required

```text
ENV=production
ALLOWED_HOSTS missing
        ↓
FAIL FAST
```

Keep localhost/test-host filtering for production.

---

# 4. P0 — Complete Firebase Dynamic Configuration Pipeline

The template now exists, but the build script still performs inline copying/substitution and ignores generation failures.

Current build script:

```text
cp firebase.template.json firebase.json ... || true
sed ... || true
```

This must become deterministic and fail-closed. fileciteturn115file0

### Required

Create:

```text
scripts/deploy/generate_firebase_config.py
```

Responsibilities:

1. Read the canonical environment values.
2. Validate required values.
3. Load `firebase.template.json`.
4. Replace `{{USER_BACKEND_URL}}`.
5. Replace `{{ADMIN_BACKEND_URL}}`.
6. Fail if any `{{...}}` placeholder remains.
7. Validate resulting JSON.
8. Verify user and admin rewrites.
9. Write `firebase.json`.
10. Print only non-secret diagnostics.

### Never

```text
generation failure → || true
```

---

# 5. P0 — Fix Portal-Aware Frontend Build

Current `scripts/render_build_frontend.sh` always runs:

```text
pnpm run build:user
```

even when:

```text
VITE_PORTAL_TYPE=admin
```

is present. fileciteturn115file0

### Required

```text
VITE_PORTAL_TYPE=user
    → build:user

VITE_PORTAL_TYPE=admin
    → build:admin
```

Then verify:

```text
user  → dist-user
admin → dist-admin
```

---

# 6. P0 — Firebase Rewrite Semantics

The template correctly maps:

```text
user
  → USER_BACKEND_URL

admin
  → ADMIN_BACKEND_URL
```

fileciteturn116file0

Before declaring this done:

- [ ] user artifact routes to user backend.
- [ ] admin artifact routes to admin backend.
- [ ] no cross-portal backend route exists.
- [ ] `/api/v1/**` routes correctly.
- [ ] `/api/**` behavior is intentional and tested.
- [ ] SPA fallback remains intact.

---

# 7. P0 — No Silent Firebase Build Failures

Current build script has `2>/dev/null || true` around configuration-generation operations. fileciteturn115file0

Replace this with explicit checks:

```text
template exists
↓
variables exist
↓
generator succeeds
↓
JSON valid
↓
no placeholders
↓
correct destinations
↓
deploy
```

---

# 8. P0 — Production CORS Must Be Environment-Driven

Current `backend/middleware/cors_policy.py` centralizes CORS, which is good, but still contains built-in origin defaults. The policy includes admin/user origin sets in source. fileciteturn106file0

### Required

Production must use:

```text
USER_CORS_ORIGINS
ADMIN_CORS_ORIGINS
```

from environment/Infisical.

If either is missing in production:

```text
FAIL FAST
```

Do not silently fall back to stale domains.

Keep:

- wildcard rejection
- deduplication
- admin/user separation
- production localhost filtering

---

# 9. P0 — Verify the Actual Live User-Origin Configuration

The production CORS environment must contain the actual user portal origin.

Do not add a new hardcoded origin to Python.

Verify the value currently configured in Render/Infisical.

---

# 10. P1 — Simplify `frontend/src/utils/api.ts`

Current API configuration is substantially correct:

```text
VITE_ADMIN_BACKEND
VITE_USER_BACKEND
VITE_API_BASE
VITE_API_URL
VITE_WS_BASE_URL
```

and health uses:

```text
/api/v1/health/live
```

fileciteturn117file0

However, hostname-based relative routing still exists through:

```text
VITE_RELATIVE_PATH_HOSTS
hostname.includes(...)
```

### Required

Production routing should primarily depend on:

```text
VITE_PORTAL_TYPE
+
explicit VITE_*_BACKEND
```

Use relative-path mode only as an explicit deployment capability.

---

# 11. P1 — Remove Deprecated `RENDER_BACKENDS`

`api.ts` still exports the deprecated `RENDER_BACKENDS` array. fileciteturn117file0

Audit consumers.

If unused:

```text
remove it
```

If used:

```text
migrate consumers
→ remove deprecated export
```

---

# 12. P1 — Centralize Backend Runtime Endpoints

Do not create a second configuration framework if the current settings system can be extended.

Audit:

```text
backend/core/config*
backend/core/settings*
backend/core/env_validator*
backend/core/config_validation*
```

Add endpoint fields to the canonical settings object where appropriate:

```text
user_backend_url
admin_backend_url
websocket_url
n8n_base_url
storage endpoints
observability endpoints
provider overrides
```

---

# 13. P1 — Audit Direct Environment Reads

Search the repository for:

```text
os.getenv(
os.environ[
getenv(
```

Classify each occurrence:

```text
central config
secret bootstrap
CLI/build
runtime
test
```

Move runtime configuration into the canonical settings layer where practical.

Do not blindly replace legitimate secret/bootstrap/build-time access.

---

# 14. P1 — Required vs Optional Configuration

Current LLM behavior is already improved: when some keys are missing while others are available, missing keys are logged as optional rather than fatal. fileciteturn113file0

Maintain:

```text
>=1 usable LLM provider
    → LLM capability available

some provider keys missing
    → INFO / NOT_CONFIGURED

all usable providers unavailable
    → WARNING/ERROR
```

Do not regress this.

---

# 15. P1 — Configuration Contract

Document each production configuration field:

```text
name
required_when
secret/public
format
failure_mode
owner
```

Examples:

```text
DATABASE_URL
required_when=production/staging
failure_mode=FAIL_FAST

N8N_BASE_URL
required_when=N8N_ENABLED
failure_mode=FAIL_FAST

DEEPSEEK_API_KEY
required_when=never
failure_mode=NOT_CONFIGURED
```

---

# 16. P1 — Infisical/Environment Naming Contract

Update/document the mapping:

```text
Infisical key
      ↓
environment variable
      ↓
canonical settings field
      ↓
consumer
```

Update:

```text
secrets_registry.yaml
.env.example
deployment documentation
```

Never commit real values.

---

# 17. P1 — Configuration Drift Detection

Check consistency between:

```text
settings fields
.env.example
secrets_registry.yaml
firebase.template.json
deployment configuration
```

Detect:

```text
missing variable
unused variable
renamed variable
duplicate variable
```

---

# 18. P1 — Hardcoded Deployment Config Scanner

Create:

```text
scripts/ci/check_hardcoded_deployment_config.py
```

Detect newly introduced deployment-specific values such as:

```text
.onrender.com
.web.app
.firebaseapp.com
.vercel.app
known production hostnames
hardcoded production passwords
private service URLs
```

Allow only documented exceptions for:

```text
tests
docs
provider canonical metadata
examples
```

Every exception should include a reason.

---

# 19. P2 — Frontend Public-Config Security

Vite `VITE_*` values are public/bundled.

Therefore:

```text
VITE_*
```

may only contain public configuration.

Never put:

```text
API secrets
Infisical credentials
JWT secrets
payment secrets
n8n secrets
private tokens
```

inside `VITE_*`.

Add CI detection for suspicious frontend secret usage.

---

# 20. P2 — Production Build Artifact Validation

After each portal build:

```text
build
 ↓
inspect artifact
 ↓
verify correct backend URL
 ↓
verify correct portal identity
 ↓
search for old deployment hostname
 ↓
search for secret leakage
```

Required:

- [ ] user build correct.
- [ ] admin build correct.
- [ ] no old Render URL.
- [ ] no production secret.
- [ ] no cross-portal endpoint.

---

# 21. P2 — Service Replacement Test

Prove the architecture is genuinely dynamic.

### Backend

Change:

```text
VITE_USER_BACKEND
```

to staging backend.

No source edit.

### Admin

Change:

```text
VITE_ADMIN_BACKEND
```

to staging admin backend.

No source edit.

### Automation

Change:

```text
N8N_BASE_URL
```

to staging n8n.

No source edit.

### Storage

Change provider + credentials through configuration.

No application-domain edits.

---

# 22. P2 — Configuration Test Matrix

Every important variable:

```text
present + valid
present + invalid
missing
empty
wrong type
wrong environment
```

Expected:

```text
required missing → fail fast
optional missing → graceful
invalid → explicit failure
```

---

# 23. P2 — Staging Environment Parity

Verify staging and production differ through configuration, not source branches.

Same code:

```text
codebase
   ↓
staging config → staging services
production config → production services
```

---

# 24. Do NOT Redo

Already implemented and should be hardened:

```text
firebase.template.json
VITE_ADMIN_BACKEND
VITE_USER_BACKEND
VITE_WS_BASE_URL
canonical health path
centralized CORS policy
Infisical secret loading
n8n/appwrite configuration
optional LLM-key semantics
cross-portal failover removal
```

---

# 25. Implementation Order

## P0

```text
1. Remove hardcoded docs password fallback.
2. Remove hardcoded ALLOWED_HOSTS fallback.
3. Fix portal-aware frontend build.
4. Complete deterministic Firebase config generation.
5. Remove silent Firebase generation failures.
6. Enforce production CORS from environment.
7. Verify actual production portal/backend environment variables.
8. Run end-to-end frontend → Firebase/Render → backend smoke tests.
```

## P1

```text
9. Simplify api.ts hostname routing.
10. Remove deprecated RENDER_BACKENDS consumers.
11. Centralize runtime endpoint configuration.
12. Audit direct environment reads.
13. Formalize required/optional configuration contract.
14. Add configuration drift detection.
15. Add hardcoded deployment configuration scanner.
```

## P2

```text
16. Frontend artifact secret/hardcode scan.
17. Service-replacement tests.
18. Staging configuration-parity tests.
19. Documentation update.
```

---

# 26. Agent Safety Rules

The implementation agent MUST:

1. Read current files before editing.
2. Preserve the existing Infisical/environment architecture.
3. Never add production values to source code.
4. Never introduce a fallback that guesses a deployment hostname.
5. Never put secrets in `VITE_*`.
6. Never restore cross-portal backend failover.
7. Never weaken CORS isolation.
8. Never make optional LLM keys mandatory.
9. Never use `|| true` to hide production configuration-generation failures.
10. Keep the existing security and SHA-pinning model intact.
11. Add tests for every changed configuration path.
12. Verify both admin and user builds.
13. Verify generated Firebase config before deployment.
14. Remove obsolete configuration only after checking consumers.
15. Prove service replacement through configuration-only changes.

---

# 27. Definition of Done

```text
[ ] No hardcoded production password.
[ ] No hardcoded deployment-specific backend hostname.
[ ] Firebase config is template/generated from environment.
[ ] Firebase generation is fail-fast.
[ ] User/admin builds select the correct build target.
[ ] User/admin backend URLs are external configuration.
[ ] Production CORS is external configuration.
[ ] Production ALLOWED_HOSTS is external configuration.
[ ] Optional LLM keys do not create noisy/fatal warnings.
[ ] Required configuration fails fast.
[ ] Frontend artifacts contain no secrets.
[ ] CI detects new deployment hardcodes.
[ ] Service replacement works without source-code edits.
[ ] Staging and production use the same codebase with different config.
```

---

# 28. Final Architecture

```text
                 SUPREMEAI SOURCE CODE
                          |
                 Project-owned behavior
                          |
                  Canonical Settings
                          |
               Infisical / Environment
                          |
        +-----------------+------------------+
        |                 |                  |
     Frontend           Backend          Integrations
        |                 |                  |
      VITE_*          DB/Redis/AI       n8n/storage/etc.
        |                 |
 Firebase generated    Runtime config
   deployment config

Service changes:
Infisical/env change
        ↓
rebuild/redeploy
        ↓
same source code
        ↓
new service
```

> **Core rule: configuration changes should change where/how SupremeAI runs, not require editing what SupremeAI is.**