---
id: software-engineering-excellence-plan
subject: "Software Engineering Excellence Plan — SupremeAI engineering practices"
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: active
canonical: false
evidence_state: partial
last_verified: 2026-09-25
target_scope: supremeai_internal
---

# SupremeAI — Software Engineering Excellence Master Plan

**Version:** 1.0.0  
**Status:** Active  
**Scope:** `supremeai_internal` + `customer_facing`  
**Last Updated:** 2026-09-19

---

## 1. DRY Principle & Code Reusability (ডipolar পুনরাবৃত্তি)

### 1.1 Current State Analysis

#### 🔴 Critical Violations

| Area | Duplication | Files Affected | Lines |
|------|-------------|----------------|-------|
| **Config System** | 12+ overlapping config files with re-declared schemas, validators, and defaults | `config_validator.py`, `env_validator.py`, `config.py`, `config_fields.py`, `config_secrets.py`, `config_validation.py`, `config_classification.py`, `config_control_plane.py`, `config_cache.py`, `config_proxy.py`, `config_registry.py`, `config_service.py` | ~3,500 |
| **Backend URL Resolution** | 4 separate implementations of backend URL resolution with same env var fallback chain | `frontend/src/utils/api.ts`, `scripts/deploy/generate_firebase_config.py`, `frontend/src/shared/supremeShared.ts`, `frontend/src/services/supremeShared.ts` | ~120 |
| **HTTP Request Layer** | 3 parallel implementations: circuit breaker + retry, throttled fetch + auth, global fetch override | `frontend/src/utils/api.ts`, `frontend/src/services/apiClient.ts`, `frontend/src/utils/apiInterceptor.ts` | ~950 |
| **Secret Lists** | 5 overlapping but unsynchronized secret key lists | `secret_vault.py`, `config_secrets.py`, `env_validator.py` | ~80 |
| **CORS Parsing** | 4 separate CORS origin parsing implementations in backend | `config_fields.py`, `config_validation.py` (2 validators + 2 helpers) | ~120 |
| **Frontend Config Objects** | 3 separate config sources for backend URL | `frontend/src/shared/supremeShared.ts`, `frontend/src/utils/api.ts`, `frontend/src/config/constants.ts` | ~90 |

### 1.2 DRY Refactoring Plan

#### Phase 1 — Single Source of Truth for Configuration

```
BEFORE (12 files, ~3,500 lines):
config/
├── config.py                    # Pydantic Settings singleton
├── config_fields.py             # Field declarations
├── config_secrets.py            # Secret properties + _CORE_SECRET_KEYS
├── config_validator.py          # Boot-time schema validation
├── env_validator.py             # Alternative env validator
├── config_validation.py         # Pydantic validators
├── config_classification.py     # 1,243 lines of ConfigSpec metadata
├── config_control_plane.py      # Health snapshot
├── config_cache.py              # TTL cache with DEFAULT_CONFIGS
├── config_proxy.py              # Tenant-specific proxy
├── config_registry.py           # ConfigDefinition + REGISTRY
└── config_service.py            # L1-L4 config service

AFTER (4 files, ~1,500 lines):
config/
├── config_registry.py           # ← SINGLE SOURCE OF TRUTH
│   ├── ConfigSpec (name, type, default, validation, aliases, classification)
│   ├── REGISTRY: dict[str, ConfigSpec]
│   ├── generate_pydantic_fields() → config_fields.py (generated)
│   ├── generate_validation_schema() → config_validator.py (generated)
│   └── get_health_snapshot() → config_control_plane.py (runtime)
├── config.py                    # Settings singleton (imports from registry)
├── config_cache.py              # TTL cache (uses registry defaults)
└── config_service.py            # L1-L4 service (uses registry)
```

**Action Items:**
1. **Merge** `config_validator.py` + `env_validator.py` → auto-generated from `config_registry.py`
2. **Unify** secret lists: `OPTIONAL_SECRETS` + `HARD_REQUIRED_SECRETS` + `_CORE_SECRET_KEYS` → single `SECRET_CLASSIFICATION` in `secret_vault.py`
3. **Eliminate** `config_classification.py` hand-written entries — generate from `config_registry.py` at build time
4. **Remove** duplicate CORS validators — keep one canonical parser in `config_registry.py`

#### Phase 2 — Unified Frontend HTTP Layer

```typescript
// BEFORE (3 files, ~950 lines):
frontend/src/
├── utils/
│   ├── api.ts                   # Circuit breaker + retry + URL resolution
│   └── apiInterceptor.ts        # Global window.fetch override
└── services/
    └── apiClient.ts             # Throttled fetch + auth + idempotency

// AFTER (2 files, ~500 lines):
frontend/src/
├── utils/
│   └── api.ts                   # URL resolution + types
└── services/
    └── apiClient.ts             # ← SINGLE HTTP BOUNDARY
        ├── fetchWithTimeout()
        ├── fetchWithRetry()
        ├── FrontendCircuitBreaker
        ├── requestQueue (p-queue)
        ├── getAuthHeaders()
        ├── handleResponse()
        └── apiClient.get/post/put/patch/delete/performSensitiveAction
```

**Action Items:**
1. **Move** `FrontendCircuitBreaker` + `fetchWithRetry` from `utils/api.ts` → `services/apiClient.ts`
2. **Delete** `utils/apiInterceptor.ts` global `window.fetch` override (security risk, breaks non-API calls)
3. **Extract** `normalizeBackendUrl()` to `shared/` package, used by both frontend and `generate_firebase_config.py`

#### Phase 3 — Frontend Config Unification

```typescript
// BEFORE (3 config sources):
frontend/src/
├── shared/supremeShared.ts      # CONFIG object (throws if missing)
├── utils/api.ts                 # USER_BACKEND_URL, ADMIN_BACKEND_URL
└── config/constants.ts          # AppDefaults

// AFTER (1 source):
frontend/src/
└── utils/api.ts                 # ← SINGLE SOURCE
    ├── getApiBaseUrl(path?)
    ├── getBackendUrl(path?)
    ├── USER_BACKEND_URL
    ├── ADMIN_BACKEND_URL
    ├── SCRAPER_BACKEND_URL
    └── isAdminContextPath()
```

**Action Items:**
1. **Delete** `frontend/src/shared/supremeShared.ts` CONFIG object — use `getApiBaseUrl()` everywhere
2. **Remove** duplicate WS_URL logic — keep `getWebSocketBaseUrl()` in `api.ts` only
3. **Update** all imports across frontend to use `getApiBaseUrl()`

### 1.3 Reusability Patterns

#### Pattern: Registry-Driven Code Generation

```python
# config_registry.py — define once, generate everywhere
REGISTRY: dict[str, ConfigSpec] = {
    "JWT_SECRET": ConfigSpec(
        name="JWT_SECRET",
        type=SecretStr,
        default=None,
        required=True,
        min_length=JWT_SECRET_MIN_LENGTH,
        validation_regex=r".{64,}",
        sources=["env", "vault"],
        scopes=["backend"],
    ),
    # ... 100+ more
}

# Auto-generated at build time:
# - Pydantic fields (config_fields.py)
# - Boot-time validator (config_validator.py)
# - Frontend config types (frontend/src/config/generated.ts)
# - CI contract checker (scripts/ci/validate_config_registry.py)
```

#### Pattern: Composition Over Inheritance

```python
# BEFORE: Multiple mixins with overlapping concerns
class Settings(BaseSettings, SettingsFieldsMixin, SettingsSecretsMixin, 
               SettingsValidationMixin, SettingsCacheMixin):
    ...

# AFTER: Single composition with clear responsibilities
class Settings(BaseSettings):
    fields: SettingsFields = SettingsFields()
    secrets: SettingsSecrets = SettingsSecrets()
    validation: SettingsValidation = SettingsValidation()
    
    @property
    def jwt_secret(self) -> str:
        return self.secrets.get("JWT_SECRET")
```

---

## 2. Modular Architecture & Separation of Concerns (SoC)

### 2.1 Current Architecture Issues

| Problem | Evidence | Impact |
|---------|----------|--------|
| **Circular imports** | `config_secrets.py` → `secret_vault.py` → `event_bus.py` → `config_secrets.py` (via settings) | Startup hangs, import errors |
| **Mixed concerns in core/** | `core/` contains config, security, caching, messaging, optimization | Unclear module boundaries |
| **Fat services** | `apiClient.ts` handles auth, retry, circuit breaking, idempotency, telemetry | Hard to test, hard to reuse |
| **God objects** | `Settings` class has 150+ fields + 50+ properties + 20+ validators | Single Responsibility Principle violated |

### 2.2 Proposed Module Boundaries

```
supremeai/
├── backend/
│   ├── core/
│   │   ├── config/
│   │   │   ├── registry.py          # ← Single source of truth
│   │   │   ├── settings.py          # Pydantic Settings singleton
│   │   │   ├── cache.py             # TTL config cache
│   │   │   └── service.py           # L1-L4 config service
│   │   ├── security/
│   │   │   ├── vault.py             # Secret fetching + classification
│   │   │   ├── policy.py            # Secret strength rules
│   │   │   ├── auth.py              # JWT, OTP, session
│   │   │   └── cors.py              # CORS policy
│   │   ├── gateway/
│   │   │   ├── router.py            # Model router
│   │   │   ├── providers.py         # Provider adapters
│   │   │   └── fallback.py          # Fallback chain logic
│   │   ├── messaging/
│   │   │   ├── event_bus.py         # In-process events
│   │   │   └── error_bus.py         # Error tracking
│   │   └── utils/
│   │       ├── time_utils.py
│   │       ├── http.py              # HTTP client utilities
│   │       └── retry.py             # Retry strategies
│   ├── services/
│   │   ├── config_service.py        # Config L1-L4 service
│   │   ├── scraper/
│   │   │   ├── security.py          # SSRF protection
│   │   │   ├── fetcher.py           # Scrape logic
│   │   │   └── parser.py            # Content extraction
│   │   └── ...
│   └── api/
│       ├── routes/
│       │   ├── config.py            # Config endpoints
│       │   ├── auth.py              # Auth endpoints
│       │   └── ...
│       └── middleware/
│           ├── auth.py
│           ├── cors.py
│           └── rate_limit.py
├── frontend/
│   ├── src/
│   │   ├── config/
│   │   │   ├── registry.ts          # Navigation, commands, permissions
│   │   │   └── constants.ts         # App-wide constants
│   │   ├── services/
│   │   │   ├── apiClient.ts         # ← SINGLE HTTP BOUNDARY
│   │   │   ├── tokenStorage.ts      # Token management
│   │   │   └── queryClient.ts       # React Query client
│   │   ├── store/
│   │   │   ├── authStore.ts         # Auth state
│   │   │   ├── uiStore.ts           # UI state
│   │   │   └── workspaceStore.ts    # Workspace state
│   │   └── components/
│   │       ├── shell/               # Global shell components
│   │       ├── auth/                # Auth components
│   │       └── features/            # Feature-specific components
│   └── ...
└── shared/
    ├── contracts/                   # TypeScript types shared across packages
    ├── utils/                       # Shared utilities
    └── config/                      # Shared config resolution
```

### 2.3 Dependency Rules (No Circular Imports)

```python
# ALLOWED dependency directions:
# core/ → services/ → api/
# core/config/ → core/security/ → core/utils/
# frontend/services/ → frontend/store/ → frontend/components/

# FORBIDDEN:
# services/ → core/ (use core interfaces)
# api/ → services/ (use service interfaces)
# components/ → store/ → components/ (circular)
```

**Enforcement:** Add `ruff` rule + custom pre-commit hook to detect circular imports.

---

## 3. Type Safety & Static Typing (টাইপ সেফটি)

### 3.1 Backend Python Type Safety

#### Current State
- ✅ Pydantic v2 models for settings and API schemas
- ✅ `pyright` / `mypy` configured in some modules
- ❌ ~30% of codebase lacks type hints
- ❌ `Any` type overused in config service, dynamic proxy
- ❌ No strict mode enforcement in CI

#### Action Items

| Priority | Action | Tool | Command |
|----------|--------|------|---------|
| P0 | Enable `mypy --strict` for `backend/core/` | mypy | `mypy --strict backend/core/` |
| P0 | Add `from __future__ import annotations` to all new files | PEP 563 | `ruff check --select ANN` |
| P1 | Replace `Any` with TypedDict/Protocol in config service | mypy | `mypy --disallow-any-expr` |
| P1 | Add typed `@dataclass(frozen=True)` for all config specs | mypy | `ruff check --select PYI` |
| P2 | Generate TypeScript types from Pydantic models | pydantic2ts | `pydantic2ts backend/core/config_registry.py` |

### 3.2 Frontend TypeScript Type Safety

#### Current State
- ✅ Strict TypeScript config (`tsc --noEmit` passes)
- ✅ React 19 + TypeScript 5.x
- ❌ `any` type used in 50+ places (apiClient, stores, components)
- ❌ No `satisfies` operator usage for config objects
- ❌ Missing return types on 30% of functions

#### Action Items

| Priority | Action | Tool | Command |
|----------|--------|------|---------|
| P0 | Enable `@typescript-eslint/no-explicit-any` | ESLint | `eslint --rule '@typescript-eslint/no-explicit-any: error'` |
| P0 | Add return types to all exported functions | TypeScript | `tsc --noImplicitAny` |
| P1 | Use `satisfies` for config objects | TypeScript 5.0 | `const CONFIG = { ... } satisfies ConfigSchema` |
| P1 | Generate API types from backend OpenAPI | openapi-typescript | `openapi-typescript http://localhost:8080/openapi.json` |
| P2 | Add Zod validation for runtime type checking | Zod | `zod schemas + TypeScript inference` |

### 3.3 Shared Type Contracts

```typescript
// shared/contracts/config.ts — generated from backend config_registry.py
export interface ConfigSpec {
  name: string;
  type: 'string' | 'integer' | 'boolean' | 'secret' | 'url';
  default?: unknown;
  required: boolean;
  minLength?: number;
  pattern?: string;
  aliases?: string[];
}

// shared/contracts/api.ts — generated from OpenAPI
export interface HealthResponse {
  status: 'alive' | 'dead';
  role: 'core' | 'worker' | 'scraper';
  checks: Record<string, unknown>;
}
```

---

## 4. Static Code Analysis & Linting (স্ট্যাটিক অ্যানালিসিস)

### 4.1 Backend Python

#### Current State
- ✅ `ruff` configured (format + check)
- ✅ 1,844 files linted in CI
- ❌ No `mypy` in CI
- ❌ No `bandit` for security scanning
- ❌ No `pylint` for complexity analysis

#### Proposed CI Lint Gate

```yaml
# .github/workflows/lint.yml
name: Lint Gate
on: [push, pull_request]

jobs:
  backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install ruff mypy bandit pylint
      - run: ruff check backend/ --fix
      - run: ruff format backend/ --check
      - run: mypy backend/core/ --strict --fail-on-error
      - run: bandit -r backend/core/ -ll
      - run: pylint backend/core/ --fail-under=8.0
```

#### Pre-commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.0
    hooks:
      - id: mypy
        args: [--strict, backend/core/]
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.9
    hooks:
      - id: bandit
        args: [-r, backend/core/, -ll]
```

### 4.2 Frontend TypeScript/React

#### Current State
- ✅ `eslint.config.js` configured
- ✅ `tsc --noEmit` passes
- ❌ No `eslint-plugin-react-hooks` exhaustive-deps enforcement
- ❌ No `eslint-plugin-import` for circular dependency detection
- ❌ No `eslint-plugin-perfectionist` for import sorting

#### Proposed ESLint Config

```javascript
// eslint.config.js
export default [
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/explicit-function-return-type': 'error',
      'react-hooks/exhaustive-deps': 'error',
      'import/no-circular-dependencies': 'error',
      'import/no-duplicates': 'error',
      'perfectionist/sort-imports': 'error',
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    }
  }
];
```

### 4.3 Cross-Cutting Concerns

| Tool | Purpose | Integration |
|------|---------|-------------|
| **Semantic Release** | Automated versioning + changelog | GitHub Actions |
| **Renovate** | Dependency update automation | GitHub Actions |
| **Dependabot** | Security dependency updates | GitHub native |
| **CodeQL** | Security vulnerability scanning | GitHub native |
| **Snyk** | Open source vulnerability scanning | GitHub Actions |

---

## 5. Centralized Environment & State Management

### 5.1 Current State

| Layer | Current Approach | Problems |
|-------|------------------|----------|
| **Backend Env** | 12+ config files + Pydantic Settings | Duplication, no single source |
| **Frontend Env** | Vite env vars + 3 config objects | Inconsistent resolution |
| **State Management** | 8+ Zustand stores + React Context | No clear ownership |
| **Secret Management** | Infisical + env vars + hardcoded defaults | Multiple fallback chains |

### 5.2 Proposed Architecture

#### Backend: Single Config Registry

```python
# backend/core/config_registry.py
from dataclasses import dataclass, field
from enum import StrEnum

class ConfigClass(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    SECRET = "secret"
    PUBLIC = "public"

class ConfigSource(StrEnum):
    ENV = "env"
    VAULT = "vault"
    BUILD = "build"
    CODE_DEFAULT = "code_default"

@dataclass(frozen=True)
class ConfigSpec:
    name: str
    type: type | tuple[type, ...]
    default: Any
    classes: frozenset[ConfigClass]
    sources: frozenset[ConfigSource]
    aliases: tuple[str, ...] = ()
    min_value: float | None = None
    max_value: float | None = None
    pattern: str | None = None
    description: str = ""

REGISTRY: dict[str, ConfigSpec] = {
    "JWT_SECRET": ConfigSpec(
        name="JWT_SECRET",
        type=str,
        default=None,
        classes=frozenset({ConfigClass.REQUIRED, ConfigClass.SECRET}),
        sources=frozenset({ConfigSource.ENV, ConfigSource.VAULT}),
        aliases=("SUPREMEAI_JWT_SECRET",),
        min_length=JWT_SECRET_MIN_LENGTH,
        description="JWT signing secret (min 64 chars)",
    ),
    # ... 100+ more
}
```

#### Frontend: Single Config Resolution

```typescript
// frontend/src/utils/config.ts
export interface FrontendConfig {
  backendUrl: string;
  adminBackendUrl: string;
  wsUrl: string;
  env: 'local' | 'development' | 'production';
  features: {
    selfHealing: boolean;
    costGuard: boolean;
  };
}

export async function loadConfig(): Promise<FrontendConfig> {
  // Single resolution path — no duplicate logic
  const backendUrl = getApiBaseUrl();
  const adminBackendUrl = getApiBaseUrl('/admin-api');
  
  // Fetch runtime overrides from /api/config/public
  const runtime = await apiClient.get<PublicConfig>('/api/config/public');
  
  return {
    backendUrl,
    adminBackendUrl,
    wsUrl: getWebSocketBaseUrl(),
    env: import.meta.env.VITE_ENV as FrontendConfig['env'],
    features: {
      selfHealing: runtime.self_healing ?? true,
      costGuard: runtime.cost_guard ?? true,
    },
  };
}
```

#### State Management: Clear Ownership

```
frontend/src/store/
├── authStore.ts           # Auth state (user, admin, tokens)
├── uiStore.ts             # UI state (theme, sidebar, modals)
├── workspaceStore.ts      # Workspace state (projects, agents)
├── configStore.ts         # Config state (loaded once, cached)
└── index.ts               # Combined store (Zustand)
```

**Rules:**
1. Each store owns ONE domain
2. No cross-store subscriptions — use events
3. Config store is read-only after initial load
4. Auth store is the only source of truth for user identity

---

## 6. Dependency Injection & Design Patterns (ডিজাইন প্যাটার্ন)

### 6.1 Current Patterns

| Pattern | Current Usage | Issues |
|---------|---------------|--------|
| **Singleton** | `Settings()`, `get_secret_vault()`, `config_cache` | Hard to test, hidden dependencies |
| **Factory** | `InfisicalClient()` creation in `_init_infisical_client()` | Scattered across codebase |
| **Strategy** | Model router provider chain | Good — should be formalized |
| **Observer** | `event_bus`, `error_bus` | Good — should be standardized |
| **Repository** | `SystemConfig` queries | Inconsistent — some use direct DB, some use service |

### 6.2 Proposed Pattern Enforcement

#### Pattern 1: Protocol-Based DI (Python)

```python
# backend/core/ports/secret_port.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class SecretVaultProtocol(Protocol):
    def fetch_secret(self, name: str, default: str | None = None) -> str: ...
    def fetch_all_secrets(self) -> dict[str, str]: ...
    def invalidate_cache(self, name: str | None = None) -> None: ...

# backend/core/security/secret_vault.py
class ProductionSecretVault(SecretVaultProtocol):
    ...

# backend/core/config_secrets.py
class SettingsSecretsMixin:
    def __init__(self, vault: SecretVaultProtocol | None = None):
        self._vault = vault or get_secret_vault()
    
    def _get_cached_secret(self, key: str) -> str:
        return self._vault.fetch_secret(key, default="")

# Usage in tests:
class MockSecretVault(SecretVaultProtocol):
    def fetch_secret(self, name: str, default=None) -> str:
        return f"mock-{name}"
```

#### Pattern 2: Factory Pattern for Providers

```python
# backend/core/gateway/provider_factory.py
class ProviderFactory:
    _builders: dict[str, type[BaseProvider]] = {}
    
    @classmethod
    def register(cls, name: str, builder: type[BaseProvider]) -> None:
        cls._builders[name] = builder
    
    @classmethod
    def create(cls, name: str, config: ProviderConfig) -> BaseProvider:
        if name not in cls._builders:
            raise ValueError(f"Unknown provider: {name}")
        return cls._builders[name](config)

# Registration (app startup):
ProviderFactory.register("openai", OpenAIProvider)
ProviderFactory.register("gemini", GeminiProvider)
ProviderFactory.register("groq", GroqProvider)

# Usage:
provider = ProviderFactory.create("gemini", config)
```

#### Pattern 3: Repository Pattern

```python
# backend/core/repositories/config_repository.py
class ConfigRepository:
    def __init__(self, db: AsyncSession, cache: ConfigCache):
        self._db = db
        self._cache = cache
    
    async def get(self, key: str) -> Any:
        # L1: Cache
        if value := self._cache.get(key):
            return value
        # L2: Database
        if value := await self._get_from_db(key):
            self._cache.set(key, value)
            return value
        # L3: Registry default
        return REGISTRY[key].default
```

### 6.3 Anti-Patterns to Eliminate

| Anti-Pattern | Current Example | Fix |
|--------------|-----------------|-----|
| **God Object** | `Settings` with 150+ fields | Split into `SettingsFields`, `SettingsSecrets`, `SettingsValidation` |
| **Hidden Dependencies** | `get_secret_vault()` called inside property getter | Inject via constructor |
| **Service Locator** | `from core.logging_config import logger` everywhere | Use structlog with context |
| **Singleton Abuse** | Module-level `settings = Settings()` | Use dependency injection container |
| **Tight Coupling** | `config_secrets.py` directly imports `infisical_client` | Use `SecretVaultProtocol` |

---

## 7. Automated Testing Suite (অটোমেটেড টেস্টিং)

### 7.1 Current Test Coverage

| Layer | Framework | Coverage | Gap |
|-------|-----------|----------|-----|
| **Backend Unit** | pytest | ~30% | Missing: config, security, gateway |
| **Backend Integration** | pytest + httpx | ~15% | Missing: E2E flows |
| **Frontend Unit** | vitest | ~60% (544/544 pass) | Missing: stores, hooks |
| **Frontend E2E** | Playwright | 4 specs | Missing: admin flows |
| **Mission Tests** | pytest | 62/62 pass | Good — expand to 100+ |

### 7.2 Testing Strategy

#### Backend Testing Pyramid

```
        /\
       /  \     E2E Tests (Playwright + pytest)
      /____\    - Full user journeys
     /      \   - Admin flows
    /________\  Integration Tests (pytest + test DB)
   /          \ - API contract tests
  /____________\ Unit Tests (pytest + mocks)
```

#### Test Organization

```
backend/tests/
├── unit/
│   ├── core/
│   │   ├── test_config_registry.py
│   │   ├── test_secret_vault.py
│   │   ├── test_gateway_router.py
│   │   └── test_security_policy.py
│   ├── services/
│   │   ├── test_scraper_security.py
│   │   └── test_config_service.py
│   └── utils/
│       ├── test_retry.py
│       └── test_time_utils.py
├── integration/
│   ├── test_api_config.py
│   ├── test_api_auth.py
│   └── test_api_health.py
├── missions/                    # Existing — good, expand
│   ├── test_reliability.py
│   ├── test_failure_modes.py
│   └── test_security_hardening.py
├── contracts/
│   ├── test_api_contract.py     # OpenAPI contract tests
│   ├── test_config_contract.py  # Config schema contract
│   └── test_nav_contract.py     # Frontend nav contract
└── fixtures/
    ├── conftest.py
    ├── db_fixture.py
    └── secret_vault_fixture.py
```

#### Frontend Testing Pyramid

```
frontend/src/
├── __tests__/
│   ├── unit/
│   │   ├── utils/
│   │   │   ├── api.test.ts
│   │   │   └── cn.test.ts
│   │   ├── services/
│   │   │   ├── apiClient.test.ts
│   │   │   └── queryClient.test.ts
│   │   └── store/
│   │       ├── authStore.test.ts
│   │       └── uiStore.test.ts
│   ├── integration/
│   │   ├── components/
│   │   │   ├── GlobalHeader.test.tsx
│   │   │   └── RoleAwareNavRail.test.tsx
│   │   └── hooks/
│   │       ├── useAuth.test.ts
│   │       └── useApi.test.ts
│   └── e2e/
│       ├── auth.spec.ts
│       ├── chat.spec.ts
│       └── admin.spec.ts
```

### 7.3 Test Contracts

```python
# backend/tests/contracts/test_api_contract.py
from contracts import ContractChecker

def test_health_endpoint_contract():
    checker = ContractChecker("http://localhost:8080")
    response = checker.get("/api/v1/health/live")
    assert response.status == 200
    assert "status" in response.json
    assert response.json["status"] == "alive"

def test_config_validation_contract():
    checker = ContractChecker("http://localhost:8080")
    response = checker.get("/api/config/public")
    assert response.status == 200
    # Ensure no secrets leak
    assert "JWT_SECRET" not in response.json
    assert "SUPREMEAI_JWT_SECRET" not in response.json
```

### 7.4 CI Test Matrix

```yaml
# .github/workflows/test.yml
jobs:
  backend-unit:
    runs-on: ubuntu-latest
    steps:
      - run: pytest backend/tests/unit/ -v --cov=core --cov-report=xml

  backend-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
    steps:
      - run: pytest backend/tests/integration/ -v

  backend-missions:
    runs-on: ubuntu-latest
    steps:
      - run: pytest backend/tests/missions/ -v

  frontend-unit:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm test -- --coverage

  frontend-e2e:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm exec playwright test

  contract-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest backend/tests/contracts/ -v
```

---

## 8. API Contract & Centralized Documentation (API কন্ট্র্যাক্ট)

### 8.1 Current State

| Component | Documentation | Gap |
|-----------|---------------|-----|
| **Backend API** | OpenAPI auto-generated at `/api/v1/openapi.json` | No versioning, no examples |
| **Frontend API** | `apiClient.ts` + `api.ts` | No generated types |
| **Config API** | `docs/plans/001-dynamic-production-configuration/` | Out of sync with code |
| **Navigation** | `navigationRegistry.ts` + `commandRegistry.ts` | No validation against actual routes |
| **Deployment** | `docs/deployment/*.md` | Scattered, some outdated |

### 8.2 Proposed: Contract-First API Design

#### Step 1: Define Contracts in OpenAPI

```yaml
# backend/contracts/openapi.yaml
openapi: 3.1.0
info:
  title: SupremeAI Core API
  version: 1.0.0
  description: |
    Governed, model-agnostic task-execution API.
    
    ## Authentication
    All endpoints require Bearer JWT unless marked public.
    
    ## Rate Limiting
    - Free tier: 60 requests/minute
    - Pro tier: 600 requests/minute
    - Premium tier: 1200 requests/minute

paths:
  /api/v1/health/live:
    get:
      tags: [Health]
      summary: Liveness probe
      security: []
      responses:
        '200':
          description: Service is alive
          content:
            application/json:
              schema:
                type: object
                required: [status]
                properties:
                  status:
                    type: string
                    enum: [alive]
                  role:
                    type: string
                    enum: [core, worker, scraper]
                  timestamp:
                    type: string
                    format: date-time

  /api/v1/config/public:
    get:
      tags: [Config]
      summary: Public configuration (no secrets)
      security: []
      responses:
        '200':
          description: Public config
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/PublicConfig'
```

#### Step 2: Generate Code from Contracts

```bash
# Generate TypeScript types
openapi-typescript backend/contracts/openapi.yaml \
  -o frontend/src/contracts/api.ts

# Generate Python types
datamodel-codegen backend/contracts/openapi.yaml \
  -o backend/core/contracts/api_schema.py

# Generate API client
openapi-generator-cli generate \
  -i backend/contracts/openapi.yaml \
  -g typescript-fetch \
  -o frontend/src/services/generated/
```

#### Step 3: Contract Validation in CI

```python
# backend/tests/contracts/test_api_contract.py
import pytest
from openapi_spec_validator import validate_spec

def test_openapi_spec_valid():
    """Ensure OpenAPI spec is valid YAML/JSON."""
    spec = yaml.safe_load(open("backend/contracts/openapi.yaml"))
    validate_spec(spec)

def test_contract_matches_implementation():
    """Ensure every path in spec has a corresponding route."""
    spec = yaml.safe_load(open("backend/contracts/openapi.yaml"))
    app = create_app()
    registered_paths = {str(r.path) for r in app.routes}
    
    for path in spec["paths"]:
        assert path in registered_paths, f"Contract path {path} not implemented"
```

### 8.3 Documentation Structure

```
docs/
├── api/
│   ├── openapi.yaml              # ← Single source of truth for API
│   ├── README.md                 # API overview
│   ├── auth.md                   # Authentication guide
│   ├── errors.md                 # Error code reference
│   └── contracts/                # Contract tests
├── architecture/
│   ├── OVERVIEW.md               # High-level architecture
│   ├── config.md                 # Config system (references registry)
│   ├── security.md               # Security architecture
│   └── data-flow.md              # Key data flows
├── deployment/
│   ├── render.md                 # Render deployment
│   ├── firebase.md               # Firebase Hosting
│   ├── env.md                    # Environment variables (auto-generated)
│   └── runbook.md                # Incident response
├── guides/
│   ├── contributing.md           # Contribution guide
│   ├── testing.md                # Testing guide
│   └── debugging.md              # Debugging guide
└── generated/
    ├── STATUS_PROOF.md           # Auto-generated status
    ├── CONFIG_REFERENCE.md       # Auto-generated from registry
    └── API_REFERENCE.md          # Auto-generated from OpenAPI
```

### 8.4 Auto-Generated Documentation

```python
# scripts/docs/generate_config_reference.py
from core.config_registry import REGISTRY

def generate_config_reference():
    lines = ["# Configuration Reference\n", "Auto-generated from `config_registry.py`.\n"]
    for name, spec in sorted(REGISTRY.items()):
        lines.append(f"## `{name}`\n")
        lines.append(f"- **Type:** {spec.type.__name__}")
        lines.append(f"- **Default:** {spec.default}")
        lines.append(f"- **Required:** {'Yes' if spec.required else 'No'}")
        if spec.pattern:
            lines.append(f"- **Pattern:** `{spec.pattern}`")
        lines.append(f"- **Description:** {spec.description}\n")
    
    with open("docs/generated/CONFIG_REFERENCE.md", "w") as f:
        f.write("\n".join(lines))
```

---

## 9. Git Branching Strategy & Strict Code Review (কঠোর কোড রিভিউ)

### 9.1 Branching Model

```
main (production)
  │
  ├── develop (integration)
  │     │
  │     ├── feature/config-dry-refactor
  │     ├── feature/api-contract-generation
  │     └── feature/typing-enforcement
  │
  ├── release/v1.2.0
  │     │
  │     └── hotfix/prod-critical-fix
  │
  └── hotfix/security-patch-2026-09-19
```

### 9.2 Branch Naming Convention

```
<type>/<issue-number>-<short-description>

Types:
- feature/     — New feature (from issue)
- fix/         — Bug fix
- hotfix/      — Production emergency fix
- chore/       — Maintenance, dependencies
- docs/        — Documentation only
- refactor/    — Code refactoring (no behavior change)
- test/        — Test additions/fixes

Examples:
- feature/542-jwt-secret-min-length
- fix/587-firebase-rewrite-contract
- hotfix/prod-memory-leak
- chore/update-dependencies
- refactor/config-dry-consolidation
```

### 9.3 Commit Message Convention

```
<type>(<scope>): <subject>

<body>

<footer>

Types:
- feat:     New feature
- fix:      Bug fix
- docs:     Documentation
- style:    Formatting (no code change)
- refactor: Code restructuring
- test:     Adding tests
- chore:    Maintenance
- perf:     Performance improvement
- ci:       CI/CD changes
- revert:   Revert previous commit

Scopes:
- backend:  Backend Python code
- frontend: Frontend TypeScript/React
- config:   Configuration
- ci:       CI/CD pipelines
- infra:    Infrastructure
- docs:     Documentation

Examples:
- feat(backend): add dynamic LLM provider pool ($0..N)
- fix(frontend): prevent spurious logout on background 401
- refactor(config): merge config_validator into config_registry
- docs(api): generate OpenAPI contract from config_registry
```

### 9.4 Pull Request Requirements

| Requirement | Enforcement |
|-------------|-------------|
| **Linked Issue** | PR description must include `Fixes #<id>` or `Relates to #<id>` |
| **CI Green** | All jobs must pass: lint, typecheck, tests, contract |
| **Code Review** | Minimum 1 approval from CODEOWNERS |
| **Branch Up-to-Date** | Must be rebased on target branch |
| **No Merge Conflicts** | Must resolve conflicts before merge |
| **Contract Tests** | New features must include contract tests |
| **Coverage** | New code must have tests (coverage threshold enforced) |
| **Size Limit** | PR > 400 lines requires tech lead approval |

### 9.5 CODEOWNERS

```
# .github/CODEOWNERS

# Backend core
backend/core/* @supremeai/backend-team
backend/core/config* @supremeai/config-team
backend/core/security/* @supremeai/security-team

# Frontend
frontend/src/services/* @supremeai/frontend-team
frontend/src/store/* @supremeai/frontend-team
frontend/src/components/* @supremeai/frontend-team

# Infrastructure
infrastructure/* @supremeai/infra-team
.github/workflows/* @supremeai/infra-team

# Documentation
docs/* @supremeai/docs-team
README.md @supremeai/tech-leads

# Config & Secrets
config/* @supremeai/config-team
scripts/deploy/* @supremeai/infra-team
```

### 9.6 Branch Protection Rules

```yaml
# .github/branch-protection.yml
branches:
  main:
    protection:
      required_status_checks:
        strict: true
        contexts:
          - lint-backend
          - lint-frontend
          - typecheck-backend
          - typecheck-frontend
          - test-backend
          - test-frontend
          - contract-tests
          - security-scan
      required_pull_request_reviews:
        required_approving_review_count: 1
        dismiss_stale_reviews: true
        require_code_owner_reviews: true
      restrictions:
        users: []  # No direct pushes
        teams: [supremeai/tech-leads]
```

### 9.7 Review Checklist

```markdown
## Code Review Checklist

### DRY & Reusability
- [ ] No duplicated logic — extracted to shared utility?
- [ ] No hardcoded values — uses config registry?
- [ ] No new config without adding to `config_registry.py`

### Architecture
- [ ] Follows module boundaries (no circular imports)
- [ ] Uses dependency injection (not hidden singletons)
- [ ] Single Responsibility Principle observed

### Type Safety
- [ ] All functions have return types
- [ ] No `Any` type without justification
- [ ] New API endpoints have OpenAPI spec

### Security
- [ ] No secrets in code or logs
- [ ] Input validation present
- [ ] Authorization checks in place

### Testing
- [ ] Unit tests added for new logic
- [ ] Contract tests added for new API endpoints
- [ ] All tests pass locally

### Documentation
- [ ] Docstrings on public functions
- [ ] README updated if needed
- [ ] CHANGELOG entry added
```

---

## 10. Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

| Week | Focus | Deliverables |
|------|-------|--------------|
| 1 | Config DRY | Merge `config_validator.py` + `env_validator.py` into `config_registry.py` |
| 1 | Type Safety | Enable `mypy --strict` for `backend/core/` |
| 2 | HTTP Layer | Unify `apiClient.ts` + `api.ts` into single module |
| 2 | Secret Lists | Unify `OPTIONAL_SECRETS` + `_CORE_SECRET_KEYS` |
| 3 | Linting | Add `mypy`, `bandit`, `pylint` to CI |
| 3 | Contracts | Add OpenAPI contract tests |
| 4 | Testing | Add 50 unit tests for config system |

### Phase 2: Enforcement (Weeks 5-8)

| Week | Focus | Deliverables |
|------|-------|--------------|
| 5 | DI Patterns | Refactor `Settings` to use protocol-based DI |
| 5 | State Management | Audit and document Zustand store ownership |
| 6 | Type Contracts | Generate TypeScript types from OpenAPI |
| 6 | Pre-commit | Add comprehensive pre-commit hooks |
| 7 | Documentation | Auto-generate config reference from registry |
| 7 | CI Gates | Add coverage gates, size limits |
| 8 | Review | Full codebase review against checklist |

### Phase 3: Maturity (Weeks 9-12)

| Week | Focus | Deliverables |
|------|-------|--------------|
| 9 | Architecture | Document and enforce module boundaries |
| 10 | Design Patterns | Formalize factory, repository, strategy patterns |
| 11 | Testing | Expand mission tests from 62 → 100+ |
| 12 | Audit | Final DRY/SoC/Type-safety audit |

---

## 11. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| **Config Files** | 12 | 4 | Count of `backend/core/config*.py` |
| **Config Lines** | ~3,500 | ~1,500 | Lines of config code |
| **Backend Lint Pass** | ✅ | ✅ | `ruff check backend/` |
| **Backend Typecheck** | ❌ | ✅ | `mypy --strict backend/core/` |
| **Frontend Typecheck** | ✅ | ✅ | `tsc --noEmit` |
| **Test Coverage (Backend)** | ~30% | ≥70% | `pytest --cov` |
| **Test Coverage (Frontend)** | ~60% | ≥80% | `vitest --coverage` |
| **Contract Tests** | 0 | 20+ | `pytest tests/contracts/` |
| **PR Review Time** | Unknown | <4 hours | GitHub PR metrics |
| **Circular Imports** | Unknown | 0 | `pydeps backend/core/` |

---

## 12. Governance

### 12.1 Plan Ownership

| Domain | Owner | Review Cadence |
|--------|-------|----------------|
| Config System | Config Circle | Weekly |
| Frontend Architecture | Frontend Circle | Weekly |
| Testing Strategy | QA Circle | Bi-weekly |
| Security | Security Circle | Weekly |
| Documentation | Docs Circle | Bi-weekly |

### 12.2 Amendment Process

1. Propose amendment via GitHub Issue with label `plan-amendment`
2. Discuss in relevant Circle
3. Update this document via PR
4. Merge requires 1 approval from affected Circle

### 12.3 Living Document

This plan is a **living document**. It should be updated as:
- New patterns are established
- Old patterns are deprecated
- Metrics show improvement or regression
- Architectural decisions are made

**Last Reviewed:** 2026-09-19  
**Next Review:** 2026-09-26
