# SupremeAI 2.0 — 100% Test Coverage Implementation Plan
**Target:** 100% Backend Monorepo Unit Test Coverage
**Current Status:** 43/43 Pass (Targeted Core Coverage: 68%, Total Monorepo: 18%)

---

## Information Gathered

### Existing Test Infrastructure:
- **Test Framework:** pytest with pytest-asyncio, pytest.mark.anyio
- **Mock Strategy:** monkeypatch, unittest.mock (MagicMock, AsyncMock, patch), respx for network
- **Conftest:** Global mock modules (slowapi, chromadb, nats, docker, firebase), environment isolation, test database setup
- **Existing Coverage:**
  - Core: test_circuit_breaker.py (comprehensive), test_auth_middleware.py (89 lines), test_rbac.py (good), test_prompt_firewall.py (good), test_honeypot_middleware.py (comprehensive), test_guardian_ai.py (comprehensive), test_compliance_bot.py (partial)
  - Missing: test_redis_cache.py, test_security_firewall.py (comprehensive), test_origin_validator.py

### Key Modules to Test:

#### Phase A: Core Resilience & Security
1. **core/cache/redis_manager.py** - SecureRedisManager, IdempotencyLock
2. **core/resilience/circuit_breaker.py** - Already tested (52 tests), needs edge cases
3. **core/security/auth_middleware.py** - Already tested (12 tests), needs JWT rotation tests
4. **core/security/rbac.py** - Already tested, needs UserContext expiry edge cases
5. **core/security/honeypot_middleware.py** - Already tested (6 tests)
6. **core/security/prompt_firewall.py** - Already tested (10 tests)
7. **core/security/input_sanitizer.py** - Needs comprehensive tests
8. **core/security/guardian_ai.py** - Already tested (comprehensive)
9. **core/security/compliance_bot.py** - Needs more tests
10. **core/security/origin_validator.py** - Needs tests
11. **core/security/secret_vault.py** - Needs tests
12. **core/security/audit_logger.py** - Needs tests
13. **core/security/autonoguard_middleware.py** - Needs tests

#### Phase B: API Gateway Routes
14. **api/routes/admin.py** - Needs analytics/business metrics tests
15. **api/routes/analytics.py** - DAU/MAU analytics tests
16. **api/routes/swarm.py** - Swarm stream persister tests
17. **api/routes/billing.py** - Free-tier token quota tests
18. **api/routes/email.py** - Transaction receipt tests
19. **api/routes/websocket_agent.py** - Token handshake tests
20. **api/routes/websocket_voice.py** - Voice WS tests

#### Phase C: Data Persistence
21. **memory/unified_db_manager.py** - Multi-DB atomic writes
22. **memory/chromadb_store.py** - Vector store operations
23. **memory/rag_pipeline.py** - RAG pipeline tests
24. **memory/sliding_window.py** - Sliding window tests
25. **memory/supabase_store.py** - Supabase adapter tests
26. **memory/cloud_postgres_store.py** - Cloud Postgres tests
27. **memory/sqlite_store.py** - SQLite store tests

#### Phase D: AI Tools
28. **tools/mcp/mcp_cloud_deploy.py** - MCP Cloud deploy tests
29. **tools/mcp/mcp_github_cicd.py** - GitHub CICD tests
30. **tools/mcp/mcp_workspace.py** - Workspace tests
31. **tools/knowledge/knowledge_base_indexer.py** - KB indexer tests
32. **tools/knowledge/codebase_exporter.py** - Codebase export tests
33. **tools/knowledge/local_search_rag.py** - Local RAG tests
34. **tools/learning/skill_recommender.py** - Skill recommender tests
35. **tools/learning/style_learner.py** - Style learner tests
36. **tools/learning/domain_adapter.py** - Domain adapter tests
37. **tools/media/multilingual_tts.py** - TTS tests
38. **tools/media/voice.py** - Voice tests
39. **tools/media/image_generator.py** - Image gen tests
40. **tools/security_tools/vpn_switcher.py** - VPN tests
41. **tools/security_tools/multi_account_rotator.py** - Account rotator tests
42. **tools/security_tools/vulnerability_predictor.py** - Vuln predictor tests

---

## Plan

### Phase A: Core Resilience & Security Suite (Priority 1)

#### A.1 Auth & JIT OTP Defense (`tests/core/test_auth_security.py`)
- [ ] Test `_decode_jwt` with missing jwt_secret (fail-closed)
- [ ] Test `_decode_jwt` with expired token
- [ ] Test `_decode_jwt` with invalid signature
- [ ] Test `_is_public_path` with various paths
- [ ] Test `_send_json_response` call count and content
- [ ] Test `AuthMiddleware` with valid JWT token
- [ ] Test `AuthMiddleware` with expired JWT token
- [ ] Test `AuthMiddleware` with invalid JWT token
- [ ] Test `AuthMiddleware` with non-admin role
- [ ] Test `verify_admin_session_fail_closed` with valid master_admin
- [ ] Test `verify_admin_session_fail_closed` with missing headers
- [ ] Test `verify_admin_session_fail_closed` with malformed headers
- [ ] Test JWT secret rotation scenarios

#### A.2 Cache & Redis Engine (`tests/core/test_redis_cache.py`)
- [ ] Test `SecureRedisManager` initialization
- [ ] Test `_ensure_connected` with valid URL
- [ ] Test `_ensure_connected` with no URL (fail-closed)
- [ ] Test `get_client_async` returns None when no URL
- [ ] Test `client` property sync fallback
- [ ] Test `close` method
- [ ] Test `set` success and failure (Redis error)
- [ ] Test `get` success and failure
- [ ] Test `delete` success and failure
- [ ] Test `set_cache` / `get_cache` aliases
- [ ] Test `set_json` / `get_json` serialization
- [ ] Test `_AcquireIdempotencyLockContext` acquire/release
- [ ] Test `_AcquireIdempotencyLockContext` fail-closed raises IdempotencyUnavailableError
- [ ] Test `acquire_idempotency_lock` context manager
- [ ] Test concurrent lock acquisition safety

#### A.3 Unified CircuitBreaker (`tests/test_circuit_breaker_edge.py`)
- [ ] Test decorator with sync functions
- [ ] Test decorator with async functions  
- [ ] Test `allow_request` when HALF_OPEN and recovery in progress
- [ ] Test `allow_request` when HALF_OPEN and no recovery in progress
- [ ] Test `mark_success` when CLOSED
- [ ] Test `mark_failure` when already OPEN (no state change)
- [ ] Test `mark_failure` at threshold exactly
- [ ] Test `_should_attempt_recovery` edge cases (opened_at manipulation)
- [ ] Test `call` with OSError (recoverable)
- [ ] Test `acall` with OSError (recoverable)
- [ ] Test `call` with CircuitBreakerOpenError re-raise
- [ ] Test `acall` with CircuitBreakerOpenError re-raise
- [ ] Test `get_metrics` state values: CLOSED=0, HALF_OPEN=1, OPEN=2
- [ ] Test `reset` clears all state
- [ ] Test thread safety with concurrent `mark_failure`/`mark_success`
- [ ] Test recovery timeout with `time.monotonic()` simulation

#### A.4 Security & Prompt Firewall (`tests/core/test_security_firewall.py`)
- [ ] Test `PromptFirewall.validate_agent_response` with mixed content
- [ ] Test `PromptFirewall.validate_agent_response` with whitespace-only
- [ ] Test `PromptFirewall._check_local_patterns` with all categories
- [ ] Test `PromptFirewall._check_local_patterns` case insensitivity
- [ ] Test `constitutional_filter` with local pattern hit (no LLM call)
- [ ] Test `constitutional_filter` with connection error (graceful skip)
- [ ] Test `constitutional_filter` with value error (graceful skip)
- [ ] Test `pre_flight_scan` with blocked pattern
- [ ] Test `classify_intent` coding keywords
- [ ] Test `classify_intent` reasoning keywords
- [ ] Test `classify_intent` creative keywords
- [ ] Test `classify_intent` general fallback
- [ ] Test `enforce_bengali_rules` idempotency
- [ ] Test `InputSanitizer.strip_pii` with all patterns (email, IP, phone)
- [ ] Test `InputSanitizer.detect_ambiguity` results
- [ ] Test `InputSanitizer.validate_scope` forbidden patterns
- [ ] Test `InputSanitizer.extract_constraints` budget/time patterns
- [ ] Test `InputSanitizer.sanitize` full pipeline
- [ ] Test `HoneypotMiddleware` with blocked IP (RulesMutator)
- [ ] Test `HoneypotMiddleware` non-HTTP scope
- [ ] Test `HoneypotMiddleware` query string injection
- [ ] Test `HoneypotMiddleware` threat intel persistence
- [ ] Test `OriginValidator.TrustedOriginMiddleware` with origin
- [ ] Test `OriginValidator.TrustedOriginMiddleware` without origin
- [ ] Test `OriginValidator.TrustedOriginMiddleware` OPTIONS preflight
- [ ] Test `OriginValidator.TrustedOriginMiddleware` public path bypass
- [ ] Test `OriginValidator.TrustedOriginMiddleware` host header validation
- [ ] Test `SecretVault` cache TTL expiry
- [ ] Test `SecretVault` fetch with Infisical client
- [ ] Test `SecretVault` fetch_async wrapper
- [ ] Test `SecretVault` fallback to env
- [ ] Test `SecretVault` invalidate cache
- [ ] Test `SecretVault` exponential backoff retry
- [ ] Test `SecretVault` fail-closed in production
- [ ] Test `AuditLogger.log_security_event` Redis pipeline
- [ ] Test `AuditLogger.log_security_event` without Redis
- [ ] Test `ComplianceBot` GDPR data minimization
- [ ] Test `ComplianceBot` DSA data localization
- [ ] Test `ConsentManager` record/withdraw/get status
- [ ] Test `DataRetentionPolicy` enforce retention
- [ ] Test `AutonoGuardMiddleware` dispatch flow
- [ ] Test `AutonoGuardMiddleware` sensitive path enforcement

### Phase B: API Gateway & Router Endpoint Suite (Priority 2)

#### B.1 Admin & Analytics Routes (`tests/api/test_admin_analytics.py`)
- [ ] Test admin dashboard metrics endpoint
- [ ] Test analytics business endpoint
- [ ] Test DAU/MAU analytics computation
- [ ] Test analytics with no data

#### B.2 Swarm & Orchestration Routes (`tests/api/test_swarm_routes.py`)
- [ ] Test swarm stream persister
- [ ] Test halt/resume execution state
- [ ] Test swarm status endpoint

#### B.3 Billing & Email Agent Routes (`tests/api/test_billing_email.py`)
- [ ] Test free-tier token quota audit
- [ ] Test transaction receipt generation
- [ ] Test billing plan upgrade/downgrade

#### B.4 WebSocket Security Token Routes (`tests/api/test_websocket_routes.py`)
- [ ] Test WebSocket agent token handshake
- [ ] Test WebSocket voice token handshake
- [ ] Test message payload validation
- [ ] Test token expiry rejection

### Phase C: Data Persistence & Multi-DB (Priority 3)

#### C.1 Unified Multi-DB Manager (`tests/memory/test_unified_db.py`)
- [ ] Test simultaneous atomic write across SQLite, Supabase, Postgres, ChromaDB
- [ ] Test write failure rollback
- [ ] Test read from multiple DBs

#### C.2 Vector & RAG Pipeline (`tests/memory/test_rag_memory.py`)
- [ ] Test ChromaDB store CRUD
- [ ] Test RAG pipeline retrieval
- [ ] Test sliding window context management
- [ ] Test semantic similarity search

#### C.3 Cloud Storage & DB Adapters (`tests/memory/test_storage_adapters.py`)
- [ ] Test Supabase store operations
- [ ] Test Cloud Postgres store operations
- [ ] Test SQLite store operations
- [ ] Test connection fallback

### Phase D: AI Tools & Agent Modules Suite (Priority 4)

#### D.1 DevOps & Deployment MCP Tools (`tests/tools/test_mcp_devops.py`)
- [ ] Test MCP cloud deploy
- [ ] Test MCP GitHub CICD pipeline
- [ ] Test MCP workspace management

#### D.2 Knowledge & RAG Indexing Tools (`tests/tools/test_knowledge_tools.py`)
- [ ] Test knowledge base indexer
- [ ] Test codebase exporter
- [ ] Test local search RAG

#### D.3 Learning & Adaptive Engine (`tests/tools/test_learning_engine.py`)
- [ ] Test skill recommender
- [ ] Test style learner
- [ ] Test domain adapter

#### D.4 Media & Voice Tools (`tests/tools/test_media_voice.py`)
- [ ] Test multilingual TTS
- [ ] Test voice processing
- [ ] Test image generator

#### D.5 Security Rotator & VPN Tools (`tests/tools/test_security_rotators.py`)
- [ ] Test VPN switcher
- [ ] Test multi-account rotator
- [ ] Test vulnerability predictor

### Phase E: CI Integration (Priority 5)

- [ ] Configure `--cov-fail-under=80` in CI pipeline
- [ ] Generate auto test cases for zero-coverage files
- [ ] Integrate coverage reports with PR checks

---

## First Focus: Phase A - Core Security Tests

Create new test files:
1. `backend/tests/core/test_redis_cache.py` - Redis Cache & Idempotency Lock
2. `backend/tests/core/test_security_firewall.py` - Security Firewall (comprehensive)  
3. `backend/tests/core/test_secret_vault.py` - Secret Vault
4. `backend/tests/core/test_audit_logger.py` - Audit Logger
5. `backend/tests/core/test_origin_validator.py` - Origin Validator
6. `backend/tests/core/test_autonoguard_middleware.py` - AutonoGuard Middleware
7. `backend/tests/core/test_input_sanitizer.py` - Input Sanitizer (independent)
8. `backend/tests/test_circuit_breaker_edge.py` - Circuit Breaker Edge Cases
9. `backend/tests/core/test_auth_security_extension.py` - Auth Security Extension

---

## Dependent Files to be Edited
- No existing files need modification
- All new test files will be created
- CI config may need `.coveragerc` update

## Follow-up Steps
1. ✅ Run existing tests to ensure baseline passes
2. Create new test files in priority order
3. Run coverage report after each phase
4. Verify `--cov-fail-under=80` in CI
5. Update TODO.md with progress tracking
