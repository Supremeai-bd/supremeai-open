---
id: dynamic-configuration-zero-hardcode-roadmap
subject: "SupremeAI Dynamic Configuration & Zero-Hardcode Roadmap"
document_role: architecture
planning_authority: Architecture Circle
canonical: candidate
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-17
supersedes: []
superseded_by: []
related:
  - docs/plans/features/runtime_dynamic_configuration_zero_hardcode_plan.md
  - docs/plans/architecture/vendor_independent_integration_architecture_plan.md
target_scope: supremeai_internal
---

# SupremeAI Dynamic Configuration & Zero-Hardcode Roadmap

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Goal:** Make production configuration truly dynamic and environment/vault-driven so service/provider changes do not require source-code edits.

---

## 1. Core Rule

> **Code defines behavior; configuration defines deployment.**

Source code should NOT contain environment-specific:

- backend URLs
- frontend URLs
- Render service URLs
- Firebase project/domain values
- API endpoints
- API keys/secrets
- provider activation decisions
- production CORS origins
- webhook URLs
- storage endpoints
- telemetry endpoints
- database/Redis URLs
- deployment-specific worker values
- third-party service IDs

Production-specific values should come from:

```text
Infisical / deployment environment
        ↓
environment variables
        ↓
centralized application configuration
        ↓
typed config consumers
```

---

# 2. Important Current-Codebase Findings

The current codebase already has a strong dynamic-configuration direction:

- `frontend/src/utils/api.ts` uses `VITE_ADMIN_BACKEND`, `VITE_USER_BACKEND`, `VITE_API_BASE`, and `VITE_API_URL`.
- It intentionally fails fast in production if the portal's backend URL is missing.
- Backend CORS is centralized in `backend/middleware/cors_policy.py`.
- Backend configuration/secrets are centralized in configuration modules.
- Provider API keys are already discovered through environment-variable names rather than hard-coded secrets.
- Integration settings already have enable/disable controls.

However, there are still **hardcoded deployment values and fallback paths** that can override or conflict with the dynamic configuration strategy.

Examples that must be audited:

```text
firebase.json
    → contains a concrete Render backend URL

scripts/render_build_frontend.sh
    → constructs a Render fallback URL when VITE_* backend variables are absent

backend/middleware/cors_policy.py
    → contains default production origins

backend/provider/configuration
    → contains provider API base URLs/templates

frontend/api.ts
    → contains built-in localhost/Vercel hostname routing heuristics

deployment/build scripts
    → may contain service-specific assumptions
```

`firebase.json` currently contains a concrete `<render-backend-host>` destination, while the current live backend discussed for production is `<render-backend-host>`. fileciteturn105file0

The frontend API client is already designed around build-time environment variables, but it also contains hostname-based routing and development fallbacks that need to be audited for production consistency. fileciteturn101file0

The Render frontend build script currently creates a backend URL fallback from `RENDER_EXTERNAL_HOSTNAME`; that is useful as a recovery mechanism but conflicts with a strict “no deployment values in code” policy and can point to the frontend service itself. fileciteturn103file0

---

# 3. Configuration Precedence

Define ONE global precedence model:

```text
1. Explicit deployment environment / Infisical
2. Environment-specific config file where intentionally supported
3. Safe non-production defaults
4. No production hardcoded fallback
```

For production:

```text
missing required configuration
        ↓
fail fast
```

Never:

```text
missing production URL
        ↓
guess another URL
```

---

# 4. Dynamic Endpoint Registry

Create a centralized deployment-aware endpoint map.

Suggested:

```text
backend/core/config/endpoints.py
```

or the project's existing settings module.

Define logical names:

```text
USER_BACKEND_URL
ADMIN_BACKEND_URL
PUBLIC_API_URL
WEBSOCKET_URL

N8N_BASE_URL
APPWRITE_ENDPOINT
LANGFUSE_ENDPOINT
SENTRY_DSN
POSTHOG_HOST

STORAGE_ENDPOINT
REDIS_URL
DATABASE_URL
```

The exact environment variable names should follow existing project conventions; do not create duplicates unnecessarily.

---

# 5. Remove Hardcoded Service URLs

Perform a repository-wide search for:

```text
https://
http://
.onrender.com
.web.app
.firebaseapp.com
.vercel.app
localhost:
127.0.0.1
api.openai.com
api.deepseek.com
api.groq.com
api-inference.huggingface.co
```

Classify each match:

```text
A = protocol/standard example
B = third-party public default endpoint that belongs to provider metadata
C = deployment-specific hardcode
D = test fixture
E = documentation/example
F = dangerous production fallback
```

Remove or externalize C/F.

Do not blindly remove B from provider metadata when a provider's canonical public API base URL is part of the provider definition. Instead, make provider metadata explicit and replaceable.

---

# 6. Firebase Hosting

Current `firebase.json` contains concrete backend rewrite destinations. fileciteturn105file0

This must not become the long-term source of truth.

Preferred architecture:

```text
Infisical / CI
      ↓
VITE_BACKEND_URL
      ↓
build step
      ↓
generated firebase hosting config
```

or use a deployment-specific generated configuration artifact.

Never manually edit the committed application source every time the Render backend changes.

## Required

Create a deterministic deployment templating step:

```text
firebase.template.json
        +
production environment
        ↓
firebase.json/generated config
```

The generated artifact should not be mistaken for canonical source configuration.

---

# 7. Frontend Backend URL Strategy

Current `frontend/src/utils/api.ts` already follows a strong model:

```text
VITE_ADMIN_BACKEND
VITE_USER_BACKEND
VITE_API_BASE
VITE_API_URL
```

Keep this.

But remove deployment-specific heuristics that can become stale.

### Avoid

```text
hostname contains vercel.app
hostname contains localhost
```

as the production source of backend routing.

### Prefer

```text
VITE_PORTAL_TYPE
+
explicit VITE_*_BACKEND
```

Production should never infer its backend from the frontend hostname.

---

# 8. No Cross-Portal Backend Guessing

Maintain:

```text
Admin portal
    ↓
ADMIN_BACKEND_URL

User portal
    ↓
USER_BACKEND_URL
```

Do not create automatic:

```text
admin → user backend fallback
user → admin backend fallback
```

This preserves RBAC/CORS separation.

---

# 9. WebSocket URL

Current `api.ts` derives WebSocket URL from the backend URL.

That is good when protocol transformation is correct.

Allow an explicit override:

```text
VITE_WS_BASE_URL
```

Then:

```text
explicit WS URL
        ↓
fallback from canonical backend URL
```

Do not hardcode a Render hostname.

---

# 10. Health Endpoint

Do not hardcode:

```text
/health/live
```

when the canonical API contract is:

```text
/api/v1/health/live
```

Prefer a configuration constant:

```text
PUBLIC_LIVENESS_PATH=/api/v1/health/live
```

or, preferably, keep the path in the API contract and use the generated/typed client.

Production endpoint path should have one source of truth.

---

# 11. CORS Configuration

Current CORS policy already centralizes origins, which is good. fileciteturn106file0

However, default production origins are currently embedded in source:

```text
https://supremeai-admin.web.app
https://supremeai-lac.vercel.app
https://supremeai-studio.vercel.app
```

These should be treated as documented safe development/default values only if needed.

For production:

```text
ADMIN_CORS_ORIGINS
USER_CORS_ORIGINS
```

must come from deployment configuration / Infisical.

### Required

If production CORS is missing:

```text
fail fast
```

rather than silently trusting an outdated domain.

---

# 12. Provider Configuration

The provider registry correctly uses:

```text
api_key_env_var
```

and avoids storing actual keys in source code.

Continue this pattern.

For each provider:

```text
provider_id
display_name
api_key env name
base_url
models
priority
limits
free/paid classification
enabled
```

Separate:

```text
provider metadata
```

from:

```text
deployment activation
```

A provider's API base URL may be canonical provider metadata, but custom/private/proxy endpoints must always be overridable.

---

# 13. Optional LLM Provider Rule

Never require:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
HF_API_KEY
GROQ_API_KEY
...
```

all at once.

Correct:

```text
Any >= 1 usable provider
        ↓
LLM capability available
```

Missing optional providers:

```text
NOT_CONFIGURED
→ INFO
```

not:

```text
ERROR
```

---

# 14. Infisical as Source of Production Secrets

Use Infisical for:

```text
API keys
database URL
Redis URL
JWT secrets
encryption secrets
n8n secrets
storage credentials
analytics keys
payment credentials
OAuth secrets
provider custom endpoints
```

The application should only consume environment variables.

It should not contain provider secrets or deployment credentials.

---

# 15. Infisical Naming Contract

Create a documented naming contract:

```text
AI/
    GEMINI_API_KEY
    GROQ_API_KEY
    OPENAI_API_KEY
    DEEPSEEK_API_KEY
    HF_API_KEY
    ...

INFRA/
    DATABASE_URL
    REDIS_URL

PORTALS/
    ADMIN_BACKEND_URL
    USER_BACKEND_URL
    ADMIN_CORS_ORIGINS
    USER_CORS_ORIGINS

INTEGRATIONS/
    N8N_BASE_URL
    N8N_WEBHOOK_SECRET
    APPWRITE_ENDPOINT
    ...

OBSERVABILITY/
    LANGFUSE_HOST
    LANGFUSE_PUBLIC_KEY
    LANGFUSE_SECRET_KEY
    SENTRY_DSN
```

The exact Infisical folder structure can follow your existing project convention.

---

# 16. Backend Central Configuration

Avoid this pattern:

```python
os.getenv("SOME_URL")
```

inside many unrelated modules.

Prefer:

```text
settings.some_url
```

from one configuration object.

Exceptions:

- secrets bootstrap layer
- one-time startup diagnostics
- CLI/build scripts

Even then, central configuration is preferred.

---

# 17. Frontend Configuration

Because Vite exposes build-time variables to browser code, only public configuration may use:

```text
VITE_*
```

Never put secrets in:

```text
VITE_*
```

Secrets such as:

```text
API keys
JWT secrets
Infisical credentials
payment secret keys
n8n webhook secrets
```

must remain backend-only.

---

# 18. Build-Time vs Runtime Configuration

This distinction must be explicit.

### Frontend

```text
Build-time public config
```

because Vite bundles environment variables.

### Backend

```text
Runtime config
```

loaded from the deployment environment/secret manager.

Therefore:

```text
backend URL change
```

may require a frontend rebuild when baked into the frontend bundle.

The roadmap should optimize this by keeping the canonical value external and making rebuild/deploy automatic through CI/CD.

---

# 19. Dynamic Firebase Deployment

Create:

```text
scripts/generate_firebase_config.py
```

or shell equivalent using a template.

Inputs:

```text
FIREBASE_PROJECT_ID
FIREBASE_SITE_USER
FIREBASE_SITE_ADMIN
USER_BACKEND_URL
ADMIN_BACKEND_URL
```

Outputs:

```text
generated firebase config
```

No live backend hostname is committed to source.

---

# 20. Render Configuration

Audit:

```text
render.yaml
Dockerfile
start scripts
frontend build scripts
environment variables
```

Remove:

```text
hardcoded fallback Render service names
```

especially:

```text
<render-backend-host>
<render-backend-host>
```

from code/scripts where they represent deployment-specific configuration.

---

# 21. Important Current Script Risk

Current:

```text
scripts/render_build_frontend.sh
```

uses:

```text
RENDER_EXTERNAL_HOSTNAME
```

as a fallback for frontend backend URLs. fileciteturn103file0

This should be removed for production.

Preferred:

```text
if required VITE_* value missing
    → fail the build
```

not:

```text
missing
    → guess from current Render hostname
```

A wrong guess can produce a successfully built but broken frontend.

---

# 22. Environment Validation

Add a centralized production validator:

```text
environment
    ↓
required variables
    ↓
format validation
    ↓
cross-variable consistency
    ↓
startup
```

Examples:

```text
ADMIN_BACKEND_URL is valid https URL
USER_BACKEND_URL is valid https URL
USER_CORS_ORIGINS contains user origin
ADMIN_CORS_ORIGINS contains admin origin
N8N_BASE_URL valid when n8n enabled
LANGFUSE endpoint valid when enabled
```

---

# 23. Cross-Environment Configuration

Support:

```text
development
staging
production
```

without source changes.

Example:

```text
SupremeAI-dev
SupremeAI-staging
SupremeAI-prod
```

Each environment supplies its own values.

The code stays identical.

---

# 24. No Service-Specific Code Branches

Avoid:

```python
if "render" in url:
    ...
```

or:

```python
if hostname.endswith(".web.app"):
    ...
```

unless this is purely a documented browser/runtime behavior that cannot be configuration-driven.

Prefer:

```text
DEPLOYMENT_ENV
PORTAL_TYPE
CAPABILITY_FLAGS
```

---

# 25. Dynamic Service Switching

The desired workflow:

```text
Current Render backend
        ↓
new backend service
        ↓
change environment variable / Infisical value
        ↓
deploy/rebuild
        ↓
SupremeAI uses new service
```

No application-source change.

Same for:

```text
n8n
storage
Redis
database
Langfuse
Sentry
AI proxy
```

---

# 26. Provider Endpoint Overrides

For each external provider support:

```text
canonical default
+
optional custom base URL
```

Example:

```text
OPENAI_BASE_URL
DEEPSEEK_BASE_URL
GROQ_BASE_URL
HF_BASE_URL
N8N_BASE_URL
LANGFUSE_HOST
```

Only create these when an actual proxy/self-host/private endpoint use case exists.

Do not flood configuration with unnecessary variables.

---

# 27. Dynamic Storage Configuration

Current project has multiple storage providers.

Use:

```text
STORAGE_PROVIDER=r2
```

and:

```text
R2_*
MINIO_*
APPWRITE_*
```

configuration.

Switch:

```text
STORAGE_PROVIDER
```

without changing application code.

---

# 28. Dynamic Messaging Configuration

Use:

```text
MESSAGING_PROVIDER
```

and channel policies.

Example:

```text
HITL_ALERT_CHANNEL=telegram
SECURITY_ALERT_CHANNEL=telegram
BILLING_CHANNEL=email
```

Do not hardcode provider selection in business logic.

---

# 29. Dynamic Automation

Use:

```text
AUTOMATION_PROVIDER=n8n
```

and workflow registry.

The workflow registry must contain logical names, not deployment-specific hostnames in business/domain code.

---

# 30. Dynamic Observability

Support:

```text
OTEL_ENABLED
LANGFUSE_ENABLED
SENTRY_ENABLED
POSTHOG_ENABLED
```

with endpoints/keys from deployment configuration.

No optional observability service should be required for application startup unless explicitly defined as mandatory.

---

# 31. Dynamic Worker Configuration

For the current 512 MB target:

```text
production → 1 worker
```

This is an operational policy.

Do not hardcode a Render URL or infrastructure-specific service name to enforce it.

A production worker policy can be:

```text
UVICORN_WORKERS=1
```

or a production-safe guard that rejects values >1.

---

# 32. Dynamic Caching / Redis

Use:

```text
REDIS_URL
CACHE_BACKEND
```

and feature flags.

If Redis is intentionally absent:

```text
bounded fallback
```

with configuration.

Do not hardcode a remote Redis host.

---

# 33. Health & Service Discovery

Create a central service registry:

```text
Service
Endpoint
Required?
Enabled?
Health path
Timeout
Fallback
```

Examples:

```text
database
redis
n8n
storage
LLM
Langfuse
Sentry
PostHog
```

Health checks consume this configuration.

---

# 34. Hardcoded URL Audit Tool

Create:

```text
scripts/ci/check_hardcoded_deployment_config.py
```

The script should fail CI for newly introduced patterns such as:

```text
.onrender.com
.web.app
.firebaseapp.com
.vercel.app
specific private hostnames
localhost production fallbacks
```

Allow explicit suppressions only for:

```text
tests
docs
provider canonical metadata
local-development fixtures
```

Every suppression must contain a reason.

---

# 35. Configuration Drift Detection

CI should compare:

```text
code expectations
+
.env.example
+
secrets_registry.yaml
+
Infisical documented keys
+
deployment config
```

Find:

```text
missing variable
unused variable
duplicate variable
wrong name
wrong environment
```

This is especially important because the project already has both configuration files and a secrets registry.

---

# 36. Production Config Contract

Create:

```text
docs/architecture/PRODUCTION_CONFIGURATION_CONTRACT.md
```

Document:

```text
Variable
Purpose
Required/Optional
Secret/Public
Allowed format
Example
Environment
Owner
Fallback
```

Do not include actual secret values.

---

# 37. Staging Verification

Before production:

```text
staging
   ↓
change backend URL in config only
   ↓
rebuild/deploy
   ↓
verify frontend connects
```

Repeat for:

```text
storage
n8n
Redis
LLM proxy
analytics
```

This proves the architecture is genuinely dynamic.

---

# 38. Vendor/Service Replacement Test

Perform at least one artificial provider replacement.

Example:

```text
Backend-A
   ↓
change USER_BACKEND_URL
   ↓
Backend-B
```

No source-code modification should be required.

Do the same conceptual test for:

```text
storage provider
n8n endpoint
LLM proxy
observability endpoint
```

---

# 39. Agent Execution Instructions

The AI coding agent MUST:

1. Audit current code before editing.
2. Search for hardcoded deployment/configuration values repository-wide.
3. Preserve canonical provider metadata where appropriate.
4. Move deployment-specific values to environment/Infisical.
5. Use centralized settings instead of scattered `os.getenv()`.
6. Never add production fallbacks that guess a service hostname.
7. Never expose secrets through `VITE_*`.
8. Never change portal backend routing into cross-portal failover.
9. Preserve CORS isolation.
10. Keep production fail-fast behavior for truly required configuration.
11. Treat optional AI-provider keys as optional.
12. Add tests for every changed configuration path.
13. Add CI protection against newly introduced hardcoded deployment URLs.
14. Update `.env.example` and the secrets registry for every new variable.
15. Never commit real production values.
16. Never weaken SHA-pinning or CI supply-chain controls while changing deployment config.
17. Verify a service can be replaced by changing configuration only.

---

# 40. Implementation Order

## P0 — Current Production Connectivity

```text
1. Identify canonical live backend URL from deployment configuration.
2. Fix Firebase/backend rewrite mismatch.
3. Fix frontend health path to canonical API path.
4. Verify user/admin CORS origins from environment.
5. Remove Render hostname fallback from frontend build.
6. Verify admin/user build outputs.
7. Run live frontend → backend smoke tests.
```

## P1 — Dynamic Configuration Foundation

```text
8. Centralize endpoint configuration.
9. Centralize service configuration.
10. Define production config contract.
11. Move hardcoded deployment values to Infisical/env.
12. Add environment validation.
13. Add config drift detection.
```

## P1 — Dynamic Service Boundaries

```text
14. Dynamic backend URLs.
15. Dynamic WebSocket URL.
16. Dynamic CORS.
17. Dynamic storage.
18. Dynamic messaging.
19. Dynamic n8n.
20. Dynamic observability.
```

## P2 — Enforcement

```text
21. Hardcoded deployment config CI scanner.
22. Service replacement tests.
23. Staging configuration-switch test.
24. Documentation update.
```

---

# 41. Definition of Done

The dynamic-configuration migration is complete when:

```text
[ ] No deployment-specific backend URL is hardcoded in application source.
[ ] No production domain is required by frontend source code.
[ ] Firebase backend rewrites are generated/configured dynamically.
[ ] Admin and user portals get their backend URLs from configuration.
[ ] WebSocket URL follows canonical configuration.
[ ] Production CORS comes from environment/Infisical.
[ ] Provider activation depends on configured keys.
[ ] Optional provider keys are not treated as failures.
[ ] Storage provider can be switched through configuration.
[ ] n8n endpoint can be changed through configuration.
[ ] Observability endpoints can be changed through configuration.
[ ] Redis/DB endpoints are configuration-driven.
[ ] Required config fails fast when missing.
[ ] Optional config fails gracefully.
[ ] Secrets never use VITE_*.
[ ] CI blocks newly introduced hardcoded deployment URLs.
[ ] Service replacement has been tested without source edits.
```

---

# 42. Golden Architecture

```text
                 SUPREMEAI CODE
                       |
              Project-owned interfaces
                       |
              Central Configuration
                       |
                Environment / Infisical
                       |
       +---------------+----------------+
       |               |                |
    Backend         Frontend        Integrations
       |               |                |
     DB/Redis       VITE_*          n8n/Storage/AI
```

The deployment flow becomes:

```text
Change service
    ↓
Update Infisical / environment
    ↓
Deploy/rebuild
    ↓
Same codebase
    ↓
New service
```

Not:

```text
Change service
    ↓
edit Python/TS
    ↓
edit firebase.json
    ↓
edit scripts
    ↓
edit CORS
    ↓
edit tests
    ↓
hope nothing was missed
```

---

# 43. Final Principle

> **No hardcoded deployment identity in application code.**

Allowed in source:

```text
protocol standards
logical route names
provider-neutral defaults
test fixtures
documented canonical public API metadata
```

Must be externalized:

```text
production URLs
service hostnames
domains
secrets
credentials
deployment-specific origins
provider activation
private endpoints
operational limits
```

This keeps SupremeAI portable across:

```text
Render
another VPS
another cloud
self-hosted infrastructure
different storage
different LLM gateway
different automation server
different observability stack
```

without rewriting the application.

---

# 44. Final Agent Command

> **Make SupremeAI deployment-agnostic. Audit the current codebase first. Remove or externalize deployment-specific hardcoded values. Use Infisical/environment variables as the production configuration source, centralized typed settings as the application interface, and project-owned adapters for external services. Preserve provider metadata, security boundaries, fail-fast behavior for required configuration, and graceful behavior for optional integrations. After implementation, prove that backend, storage, n8n, observability, and portal endpoints can be changed by configuration-only changes without source-code modification.**