---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:render_production_runtime_error_cleanup_plan
subject: SupremeAI — Render Production Error & Warning Cleanup Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Render Production Error & Warning Cleanup Plan

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Target:** Current production runtime on Render  
**Principle:** Fix real failures, classify expected optional configuration as informational, and keep logs actionable.

---

# 1. Current Production Log Verdict

The latest Render log shows the service becomes live, but there is at least **one genuine runtime code error**:

```text
cannot import name 'VectorStore'
from 'core.ai_memory.vector_store'
```

This occurs from:

```text
core/memory_manager.py
    → _aggressive_cleanup()
```

The error is caught/logged, so Render remains live, but the memory cleanup path is not correct. fileciteturn87file0L29-L37

There are also expected/degraded configuration messages that should not be treated as production failures:

```text
Rate limiter Redis unavailable, falling back to in-memory
```

and:

```text
[Mock Analytics]
```

The `/api/v1/health/live` endpoint returns 200, so the service is alive. The root `HEAD /` returns 405, which should be reviewed because a platform probe is hitting it. fileciteturn87file0L37-L52

---

# 2. Core Principle for Warnings

SupremeAI should not treat every missing optional dependency/key as a warning.

Use capability-aware classification:

```text
CRITICAL
    ↓
Core functionality broken or unsafe

ERROR
    ↓
Feature expected to work but currently fails

WARNING
    ↓
Configured capability is degraded or unsafe

INFO
    ↓
Optional capability is simply not configured

DEBUG
    ↓
Normal absence / diagnostic detail
```

---

# 3. LLM Provider Key Philosophy

This is a mandatory architecture rule:

> **The system must not complain about a specific provider API key being absent when that provider is optional and another usable provider is configured.**

Example:

```text
OPENAI_API_KEY      missing
DEEPSEEK_API_KEY    missing
HF_API_KEY          missing
GEMINI_API_KEY      present
```

Correct:

```text
✅ LLM capability available
ℹ️ Optional providers not configured: openai, deepseek, huggingface
```

Incorrect:

```text
⚠️ OPENAI_API_KEY missing
⚠️ DEEPSEEK_API_KEY missing
⚠️ HF_API_KEY missing
```

The user should see only actionable information.

---

# 4. Capability-Based Startup Validation

Current `StartupValidator` already checks that at least one LLM provider key exists, which is the correct high-level rule. It currently creates a warning only when **all** LLM provider keys are absent. fileciteturn90file0

Keep this behavior.

Improve it so the validator reports:

```text
LLM_CAPABILITY = available
ACTIVE_PROVIDERS = [gemini, groq]
OPTIONAL_PROVIDERS_UNCONFIGURED = [...]
```

Do NOT emit warning for each missing provider.

---

# 5. Optional Key Classification

Create an explicit configuration taxonomy.

## Required for Core

Examples:

```text
JWT secret
database URL
required encryption material
```

Missing → `ERROR` or startup failure where truly required.

## Optional Provider

Examples:

```text
OPENAI_API_KEY
DEEPSEEK_API_KEY
HF_API_KEY
GROQ_API_KEY
NVIDIA_API_KEY
MOONSHOT_API_KEY
TOGETHER_API_KEY
OPENROUTER_API_KEY
GEMINI_API_KEY
```

Missing → `INFO` only.

## Optional Feature

Examples:

```text
Langfuse
n8n
Appwrite
Sentry
Ollama
```

Missing → `INFO` / `DEBUG`.

## Configured but Broken

Example:

```text
GEMINI_API_KEY present
API returns 401
```

→ `WARNING` / `ERROR` depending on impact.

This distinction is essential.

---

# 6. Provider Registry Behavior

Current provider registry already has:

```text
ACTIVE
DEGRADED
DISABLED_TEMPORARY
DISABLED_PERMANENT
NOT_CONFIGURED
UNKNOWN
```

This is good.

Do not convert:

```text
NOT_CONFIGURED
```

into an application-wide warning when other providers are active.

Instead:

```text
NOT_CONFIGURED
= provider unavailable by configuration
```

and:

```text
ALL_PROVIDERS_UNAVAILABLE
= actual system-level warning/error
```

The registry already discovers providers by API-key environment variable and marks providers `NOT_CONFIGURED` when their individual key is absent. fileciteturn94file0

---

# 7. Critical Fix — `VectorStore` Import Failure

Current Render logs show:

```text
ImportError:
cannot import name 'VectorStore'
from core.ai_memory.vector_store
```

This is a real code defect.

## Required investigation

Inspect:

```text
backend/core/ai_memory/vector_store.py
backend/core/memory_manager.py
```

Determine:

```text
Does VectorStore actually exist?
Was it renamed?
Was the import path changed?
Is cleanup using an obsolete API?
```

## Fix options

### If the class was renamed

Update the caller to the canonical current class.

### If the module provides functions instead

Update cleanup to use the actual interface.

### If the cleanup is obsolete

Remove the invalid import and replace the cleanup operation with the current memory subsystem's supported cleanup method.

### Do NOT

- create a fake empty `VectorStore` just to suppress the import error;
- catch the ImportError and permanently ignore it;
- disable memory cleanup entirely without measuring the effect.

---

# 8. Memory Manager Cleanup Must Be Safe

The current error happens in:

```text
_aggressive_cleanup()
```

Therefore aggressive cleanup must follow:

```text
supported memory API
        ↓
safe cleanup
        ↓
verify
```

not:

```text
try random imports
        ↓
catch exception
        ↓
continue
```

Add a dedicated test for the aggressive cleanup path.

---

# 9. Rate Limiter Redis Message

Render log:

```text
Rate limiter Redis unavailable, falling back to in-memory
```

appears as `WARNING`. fileciteturn87file0L37-L38

But the current code deliberately has an in-memory fallback when Redis is unavailable. fileciteturn93file0

If your free-tier production architecture intentionally runs without Redis, this should be classified differently.

## Correct behavior

### Redis intentionally disabled / free-tier mode

```text
INFO:
Redis not configured; rate limiter using bounded in-memory mode.
```

### Redis configured but unexpectedly unreachable

```text
WARNING:
Configured Redis unavailable; temporarily using bounded fallback.
```

### Redis required for production policy

```text
ERROR:
Required Redis unavailable.
```

The log severity must depend on configuration and operational intent.

---

# 10. Rate-Limiter Fallback Safety

Current fallback cache can hold up to:

```text
10,000 keys
```

The fallback is bounded, which is good, but for a constrained free-tier process this should be reviewed.

Add:

```text
RATE_LIMIT_FALLBACK_MAX_KEYS
```

with a conservative production value.

Also verify:

```text
per-user / per-IP isolation
TTL cleanup
memory footprint
```

Do not let the fallback become an unbounded memory sink.

---

# 11. Mock Analytics in Production

Render logs show:

```text
[Mock Analytics] User: anonymous_api_user | Event: api_request
```

This is clearly not useful as routine production INFO traffic. fileciteturn87file0L38-L43

## Required behavior

If analytics provider is intentionally disabled:

```text
DEBUG:
Analytics disabled; using no-op provider.
```

or:

```text
INFO:
Analytics provider disabled.
```

Do NOT emit a full pseudo-analytics event for every request.

## Better

Use:

```text
NoOpAnalyticsProvider
```

instead of a noisy "Mock Analytics" logger.

---

# 12. Anonymous API User Logging

Current mock analytics includes:

```text
anonymous_api_user
```

Every health/API request can therefore create noisy log entries.

Remove routine request analytics logging from the main production log stream.

If request analytics is needed:

```text
metrics/telemetry
```

should handle it, not application INFO logs.

---

# 13. Root `HEAD /` → 405

Render log shows:

```text
HEAD / HTTP/1.1
405 Method Not Allowed
```

while:

```text
GET / HTTP/1.1
200 OK
```

works. fileciteturn87file0L38-L52

Because this endpoint appears during Render probing, verify which health/probe URL is configured.

## Preferred

Point Render health checks directly at:

```text
/api/v1/health/live
```

which already returns:

```text
200 OK
```

fileciteturn87file0L40-L43

If a generic platform probe still requires `/`, consider supporting `HEAD /` cleanly rather than returning 405.

---

# 14. Health Endpoint Rules

Separate:

```text
Liveness
Readiness
Deep health
```

Recommended:

```text
/live
    → process alive

/ready
    → core dependencies ready

/health
    → detailed diagnostic state
```

Optional integrations such as:

```text
n8n
Langfuse
Sentry
Ollama
```

must not make liveness fail.

---

# 15. Startup Validation — Fix Message Semantics

Current startup validator says:

```text
No LLM API keys configured
```

only if zero providers are configured, which is correct. fileciteturn90file0

Improve output to:

```text
LLM providers configured: 2
LLM providers unavailable by configuration: 7
```

Only warn when:

```text
configured usable providers = 0
```

---

# 16. Optional Provider Health

Provider health should be exposed separately:

```text
Gemini       ACTIVE
Groq         ACTIVE
OpenAI       NOT_CONFIGURED
DeepSeek     NOT_CONFIGURED
HuggingFace  NOT_CONFIGURED
```

Admin UI should not show `NOT_CONFIGURED` in red as if it is a failure.

Suggested UI:

```text
🟢 Active
🟡 Degraded
🔴 Error
⚪ Not configured
```

---

# 17. API-Key Discovery and Infisical

Current secret configuration uses batched secret loading and caches secrets in memory. fileciteturn91file0

Before changing provider validation:

- [ ] Verify environment variables and vault names match.
- [ ] Verify `HF_API_KEY` naming.
- [ ] Verify `DEEPSEEK_API_KEY` naming.
- [ ] Verify all optional provider aliases.
- [ ] Verify an absent optional key returns empty/None safely.
- [ ] Verify no missing optional key causes startup failure.
- [ ] Verify no individual missing key produces warning spam.

---

# 18. Memory Crisis Connection

The `VectorStore` import error is directly related to the earlier memory-crisis work.

Do not close the memory warning task until:

```text
memory manager
    ↓
standard cleanup
    ↓
aggressive cleanup
```

all execute without exceptions.

The current Render log proves the aggressive cleanup path is still broken. fileciteturn87file0L29-L36

---

# 19. Logging Policy

Introduce a consistent rule:

```text
ERROR
actual failure requiring intervention

WARNING
unexpected degradation

INFO
normal operation / optional feature state

DEBUG
expected absence / diagnostic detail
```

Examples:

```text
Missing DeepSeek key
→ INFO

Missing HF key
→ INFO

No LLM provider at all
→ ERROR

Configured Redis unavailable
→ WARNING

Redis intentionally disabled
→ INFO

Ollama not installed on user device
→ DEBUG/INFO

Ollama was explicitly selected but unavailable
→ WARNING
```

---

# 20. Tests

Add/update tests for:

## Startup validator

```text
0 LLM keys → warning/error
1 LLM key  → success
2 LLM keys → success
optional keys missing → no warning spam
```

## Provider registry

```text
missing key → NOT_CONFIGURED
valid key → normal health path
invalid key → failure state
```

## Memory manager

```text
standard cleanup
aggressive cleanup
VectorStore dependency path
cleanup exception
memory threshold
```

## Rate limiter

```text
Redis configured + healthy
Redis configured + down
Redis intentionally disabled
fallback bounded
```

## Analytics

```text
provider configured
provider disabled
no-op path produces no noisy event logs
```

## Health

```text
GET /health/live → 200
HEAD / if needed → expected status
readiness rules
optional dependency failure does not break liveness
```

---

# 21. Production Verification

After implementation:

```text
Deploy
  ↓
Watch startup logs
  ↓
Check /api/v1/health/live
  ↓
Check /api/v1/health/ready
  ↓
Exercise one LLM request
  ↓
Exercise provider fallback
  ↓
Exercise memory cleanup
  ↓
Check Redis state
  ↓
Check analytics behavior
  ↓
Check logs
```

Expected production logs should contain:

```text
✅ server started
✅ health checks
✅ configured providers
```

but should NOT contain recurring:

```text
❌ VectorStore ImportError
⚠️ Missing HF key
⚠️ Missing DeepSeek key
⚠️ Missing every optional provider key
ℹ️ Mock Analytics event for every request
```

---

# 22. Acceptance Criteria

## Critical

- [ ] `VectorStore` import error eliminated.
- [ ] Aggressive memory cleanup works.
- [ ] No hidden memory cleanup exception.
- [ ] Core LLM capability works with any one valid provider.
- [ ] Missing optional provider keys do not break startup.
- [ ] Redis fallback behavior matches configured architecture.

## Warning quality

- [ ] Optional missing key = INFO/DEBUG.
- [ ] Unexpected dependency outage = WARNING.
- [ ] Core capability broken = ERROR.
- [ ] Warning logs are throttled where repetitive.

## Production noise

- [ ] No mock analytics spam.
- [ ] No repeated rate-limiter fallback warnings when fallback is intentional.
- [ ] No 405 health-probe noise if avoidable.

---

# 23. Implementation Order

```text
P0-1  Fix VectorStore import/cleanup path
P0-2  Test aggressive memory cleanup
P0-3  Confirm at least one LLM provider works end-to-end

P0-4  Change startup/provider messaging to capability-based severity
P0-5  Reclassify Redis fallback based on configured intent
P0-6  Remove Mock Analytics request-by-request production logging
P0-7  Verify Render health endpoint configuration

P1-1  Improve provider health representation
P1-2  Bound/audit rate-limit fallback memory
P1-3  Add startup/provider regression tests
P1-4  Add production log classification tests

P2-1  Improve admin integration status UI
P2-2  Add log/health dashboards
```

---

# 24. Agent Rules

The coding agent must:

1. Fix the real `VectorStore` error before changing log severity.
2. Never hide exceptions with broad `except: pass`.
3. Never classify a real outage as INFO merely to make Render logs look clean.
4. Never require all AI provider keys.
5. Never make a missing optional API key a startup failure.
6. Preserve provider failover.
7. Preserve free-tier operation without optional services.
8. Keep Redis optional if the deployment policy intentionally allows in-memory fallback.
9. Keep user-local Ollama optional and separate from backend infrastructure.
10. Add tests for every changed warning/error path.
11. Compare pre/post production logs.
12. Do not remove health checks just to eliminate 405 output.
13. Do not suppress Python warnings globally.
14. Do not weaken security checks to reduce log noise.

---

# 25. Final Desired Production State

```text
                  SUPREMEAI PRODUCTION

Core:
  ✅ Database
  ✅ Authentication
  ✅ At least one LLM provider
  ✅ Agent runtime
  ✅ Memory
  ✅ Security/HITL

Optional:
  ⚪ DeepSeek not configured
  ⚪ HF not configured
  ⚪ OpenAI not configured
  ⚪ n8n disabled
  ⚪ Langfuse disabled
  ⚪ Ollama unavailable on user device

No problem.

Configured provider fails:
  ↓
WARNING
  ↓
fallback provider

All providers fail:
  ↓
ERROR
  ↓
user-visible degraded state

Redis intentionally absent:
  ↓
INFO
  ↓
bounded in-memory rate limiting

Redis unexpectedly fails:
  ↓
WARNING
  ↓
bounded fallback

Memory cleanup:
  ↓
must never throw ImportError

Health:
  ↓
liveness remains green
  ↓
readiness reflects actual core dependency state
```

> **Golden rule: A missing optional capability is not a failure. A broken promised capability is a failure.**
