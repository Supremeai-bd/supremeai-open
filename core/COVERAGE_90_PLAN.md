# Coverage 100% Plan

> **বাংলা মন্তব্য:** এই প্ল্যানটি পুনর্গঠন করা হয়েছে। লক্ষ্যমাত্রা ৯০% থেকে আপগ্রেড করে **১০০% লাইন কভারেজ** নির্ধারণ করা হয়েছে।
> **Last Updated:** 2026-07-23

---

## Current State (Baseline)

| Metric | Value |
|--------|-------|
| **Line Coverage** | **57.87%** |
| **Branch Coverage** | **42.88%** |
| Covered Lines | 17,556 / 28,648 |
| Missing Lines | 11,092 |
| Test Files | ~200+ |

### Per-Package Breakdown

| Package | Coverage | Lines Covered | Target |
|---------|----------|---------------|--------|
| `models` | **90.41%** | 745/824 | 100% |
| `core` | **67.98%** | 8,170/12,018 | 100% |
| `tools` | **58.51%** | 4,891/8,359 | 100% |
| `services` | **51.37%** | 563/1,096 | 100% |
| `api` | **50.18%** | 3,187/6,351 | 100% |

---

## 🎯 Target: 100% Line Coverage

| Metric | Current | Target | Gap |
|--------|---------|--------|-----|
| Line Coverage | 57.87% | **100%** | **+42.13%** |
| Branch Coverage | 42.88% | **100%** | **+57.12%** |
| Lines to Add | 17,556 | 28,648 | **+11,092 lines** |

> [!IMPORTANT]
> ১০০% কভারেজ মানে প্রতিটি executable লাইন অন্তত একটি টেস্টে রান হতে হবে।
> `# pragma: no cover` শুধুমাত্র physically-unreachable বা platform-specific কোডের জন্য ব্যবহারযোগ্য।

---

## Phase 1: Eliminate 0% Coverage Files

**Goal: +35 lines → reach ~58.0%**

| File | Lines | Strategy |
|------|-------|----------|
| `tools/cache_cleanup.py` | 35 | Test cleanup triggers, TTL expiry, cache invalidation |

**Quick action:**
```bash
# tests/test_cache_cleanup.py তৈরি করুন
poetry run pytest tests/test_cache_cleanup.py -v --cov=tools/cache_cleanup
```

---

## Phase 2: Demolish Largest Gaps (< 50% Coverage)

**Goal: +5,500 lines → reach ~77%**

| Priority | File | Missing Lines | Current % | Test Strategy |
|----------|------|--------------|-----------|---------------|
| **P1** | `api/routes/admin_dashboard.py` | 387 | 22.13% | Mock DB, test all 20+ endpoints, chart aggregation, pagination |
| **P2** | `api/routes/__init__.py` | 199 | 38.20% | Test every router registration, middleware injection, error handlers |
| **P3** | `tools/learning/skill_recommender.py` | 149 | 45.82% | Test scoring algorithms, filtering, cold-start, recommendation loop |
| **P4** | `core/evolution/daily_learner.py` | 143 | 35.87% | Test learning cycle scheduling, experience aggregation, persistence |
| **P5** | `tools/sso_integrator.py` | 139 | 24.04% | Test OAuth flows, token exchange, SAML, provider integration |
| **P6** | `tools/parallel_agent_executor.py` | 131 | 40.45% | Test parallel execution, result aggregation, timeout, cancellation |
| **P7** | `api/routes/tenant_admin.py` | 124 | 43.38% | Test tenant CRUD, user provisioning, quota enforcement |
| **P8** | `api/routes/billing_api.py` | 124 | 34.39% | Test billing flows, invoice generation, Stripe webhooks |
| **P9** | `api/routes/evolution.py` | 120 | 37.17% | Test evolution endpoints, agent breeding, fitness scoring |
| **P10** | `core/cache/multi_layer_cache.py` | 116 | 42.00% | Test L1/L2/L3 cache layers, invalidation, TTL, eviction |
| **P11** | `tools/code/diagram_to_architecture.py` | 105 | 45.60% | Test diagram parsing, AST extraction, architecture generation |
| **P12** | `tools/checkpoint_manager.py` | 105 | 45.03% | Test checkpoint save/restore, rollback, corruption handling |
| **P13** | `services/memory_service.py` | 99 | 35.29% | Test memory CRUD, semantic search, context windowing |
| **P14** | `tools/knowledge/local_search_rag.py` | 99 | 25.00% | Test RAG pipeline, embedding indexing, hybrid retrieval |
| **P15** | `tools/meta_architect.py` | 98 | 8.41% | Test architecture planner, code structure analysis, output |
| **P16** | `api/routes/websocket_agent.py` | 97 | 19.17% | Test WebSocket handshake, message streaming, disconnection |
| **P17** | `api/routes/api_keys.py` | 96 | 38.06% | Test key CRUD, rotation, validation, scope enforcement |
| **P18** | `tools/code/image_to_code.py` | 93 | 48.04% | Test vision-to-code pipeline, OCR, template matching |
| **P19** | `services/video_to_code_pipeline.py` | 92 | 42.14% | Test video frame extraction, code generation per frame |
| **P20** | `api/routes/websocket_voice.py` | 90 | 19.64% | Test voice WebSocket streaming, audio chunking, STT |
| **P21** | `tools/self_planner.py` | 88 | 20.00% | Test goal decomposition, task scheduling, re-planning |
| **P22** | `core/evolution/performance_oracle.py` | 85 | 37.50% | Test performance prediction, metric correlation |
| **P23** | `tools/api_gateway.py` | 85 | 32.54% | Test request proxying, rate limiting, auth injection |
| **P24** | `tools/seed_database.py` | 85 | 15.00% | Test seed data generation, idempotency, rollback |
| **P25** | `core/microvm_sandbox.py` | 83 | 45.03% | Test sandbox spawn, isolation, resource limits, cleanup |
| **P26** | `tools/security_tools/vulnerability_predictor.py` | 83 | 20.95% | Test CVE lookup, risk scoring, remediation suggestions |
| **P27** | `core/skills/integrations.py` | 82 | 19.61% | Test skill integration hooks, dependency resolution |
| **P28** | `api/routes/meta_ai.py` | 76 | 47.22% | Test meta-AI coordination, model selection, fallback |
| **P29** | `api/routes/websocket_hitl.py` | 76 | 22.45% | Test HITL approval flow, WebSocket approval events |
| **P30** | `tools/collaborative_editor.py` | 75 | 48.28% | Test OT/CRDT operations, conflict resolution, sync |

---

## Phase 3: Push 50–80% Files to 100%

**Goal: +3,500 lines → reach ~89%**

| Priority | File | Missing | Current % | Strategy |
|----------|------|---------|-----------|----------|
| **P31** | `core/llm_router.py` | 162 | 56.91% | Test all routing strategies, provider failover, load balancing |
| **P32** | `tools/security_tools/multi_account_rotator.py` | 147 | 68.59% | Test account rotation, credential refresh, rate limiting |
| **P33** | `tools/code/code_smell_detector.py` | 137 | 58.10% | Test all code smell patterns, severity scoring |
| **P34** | `core/queue/task_queue_enhanced.py` | 135 | 56.59% | Test queue FIFO/priority, retries, dead-letter, persistence |
| **P35** | `api/routes/browser.py` | 111 | 62.24% | Test all browser automation endpoints |
| **P36** | `api/routes/admin_routes.py` | 102 | 57.32% | Test all admin route handlers, auth guards |
| **P37** | `core/tier8/self_improvement_agent.py` | 100 | 50.00% | Test self-improvement loop, metric tracking, model update |
| **P38** | `tools/learning/style_learner.py` | 96 | 53.40% | Test style adaptation, preference learning, A/B tracking |
| **P39** | `tools/comment_thread_ai.py` | 86 | 54.74% | Test AI comment analysis, sentiment, suggestion generation |
| **P40** | `core/tier8/swarm_coordination_agent.py` | 81 | 61.61% | Test swarm consensus, agent communication, task distribution |
| **P41** | `core/evolution/agent_breeder.py` | 81 | 54.24% | Test crossover, mutation, selection pressure |
| **P42** | `core/orchestration/crew_departments.py` | 76 | 58.47% | Test department routing, skill matching, workload balancing |
| **P43** | `core/tier8/skill_marketplace_curator.py` | 74 | 62.44% | Test skill discovery, curation, ranking, deprecation |
| **P44** | `core/evolution/auto_skill_creator.py` | 71 | 56.44% | Test skill generation, validation, packaging |
| **P45** | `core/security/secret_hunter.py` | 66 | 57.14% | Test secret pattern matching, entropy detection |
| **P46** | `services/rider_tracker.py` | 66 | 50.75% | Test location tracking, ETA calculation, status updates |
| **P47** | `core/evolution/fitness_engine.py` | 63 | 57.14% | Test fitness function computation, comparison, normalization |
| **P48** | `core/llm/token_deductor.py` | 62 | 52.67% | Test token accounting, budget deduction, overflow handling |
| **P49** | `api/middleware.py` | 62 | 51.18% | Test every middleware handler, request/response mutation |
| **P50** | `core/evolution/evolution_engine.py` | 59 | 69.59% | Test full evolution cycles, convergence, early stopping |

---

## Phase 4: Complete Remaining Files to 100%

**Goal: +2,057 lines → reach ~100%**

- All remaining files not covered in Phase 2 & 3 that are below 100%
- Systematically run `coverage report --show-missing` after each phase
- Push every file from current % to 100% using the pattern below:

```bash
# কোন লাইনগুলো miss হচ্ছে দেখুন
poetry run coverage report --show-missing -m --include="<file>"
```

---

## Phase 5: Branch Coverage to 100%

**Goal: Branch Coverage 42.88% → 100%**

For every conditional block, cover both branches:

```python
# if/else উভয় branch
async def test_condition_true(): ...  # truthy path
async def test_condition_false(): ...  # falsy path


# try/except উভয় branch
async def test_success_path(): ...  # no exception
async def test_exception_path(): ...  # exception raised


# None guard
async def test_none_input(): ...  # None value
async def test_valid_input(): ...  # valid value


# Empty collection guard
async def test_empty_list(): ...  # []
async def test_populated_list(): ...  # [item]
```

**Tool to find uncovered branches:**
```bash
poetry run coverage report --branch --show-missing --include="path/to/file.py"
```

---

## Implementation Pattern (Per File)

```python
# tests/test_<module>_full.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ১. Happy path (primary functionality)
async def test_success_path():
    result = await module.function(valid_input)
    assert result.status == "success"


# ২. Error path (exceptions, invalid inputs)
async def test_invalid_input_raises():
    with pytest.raises(ValueError, match="invalid"):
        await module.function(bad_input)


# ৩. Edge case (empty, boundary, None)
async def test_empty_state():
    result = await module.function([])
    assert result == []


async def test_none_input():
    result = await module.function(None)
    assert result is None  # or raises


# ৪. Async paths
async def test_async_timeout():
    with patch("asyncio.sleep"):
        result = await module.long_running()
    assert result is not None


# ৫. External dependency mocking
@patch("module.redis_client")
@patch("module.supabase_client")
async def test_with_mocks(mock_supabase, mock_redis):
    mock_redis.get.return_value = None
    mock_supabase.table.return_value.select.return_value.execute.return_value = {"data": []}
    result = await module.function()
    assert result == expected
```

---

## Progress Tracking

| Phase | Target Coverage | Est. Lines Added | Status |
|-------|----------------|------------------|--------|
| Phase 1: Eliminate 0% | 58.0% | +35 | ⬜ Pending |
| Phase 2: < 50% Gaps | 77% | +5,500 | ⬜ Pending |
| Phase 3: 50–80% Push | 89% | +3,500 | ⬜ Pending |
| Phase 4: Remaining Files | 98% | +2,000 | ⬜ Pending |
| Phase 5: Branch Coverage | **100%** | +57 | ⬜ Pending |
| **Total** | **100%** | **+11,092** | ⬜ |

### Lines Needed Per % Point (at 28,648 total lines)

| From | To | Lines Needed |
|------|----|-------------|
| 57.87% | 65% | +2,043 |
| 65% | 70% | +1,432 |
| 70% | 75% | +1,432 |
| 75% | 80% | +1,432 |
| 80% | 85% | +1,432 |
| 85% | 90% | +1,432 |
| 90% | 95% | +1,432 |
| 95% | 100% | +1,432 |

---

## Automation: Batch Coverage Runner

```bash
# সমস্ত টেস্ট রান করে coverage রিপোর্ট করুন
poetry run pytest tests/ \
  --cov=. \
  --cov-report=term-missing \
  --cov-branch \
  --tb=no \
  -q 2>&1 | tee coverage_report.txt

# কোন ফাইলগুলো ১০০% থেকে দূরে তা খুঁজুন
poetry run coverage report --show-missing | grep -v "100%"
```

---

## Risk Factors & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Complex async WebSocket code | High | Use `anyio` + `websockets` test client |
| External deps (Redis, Supabase, Firestore) | High | Comprehensive `MagicMock` / `AsyncMock` per dependency |
| Physically unreachable code | Medium | Use `# pragma: no cover` only for dead-code branches |
| Global state / hardcoded configs | Medium | Inject via fixtures, use `monkeypatch` |
| Platform-specific code (Windows/Linux paths) | Low | Conditional `# pragma: no cover` per platform |

---

## ✅ Success Criteria (100% Definition of Done)

- [ ] `tools/cache_cleanup.py` — 0% → 100%
- [ ] All packages reach 100% line coverage
- [ ] Line coverage ≥ **100%**
- [ ] Branch coverage ≥ **100%**
- [ ] Zero files with 0% coverage
- [ ] All tests pass (`pytest` exit code 0)
- [ ] No untested `if`, `else`, `try`, `except`, `match` branch

```bash
# Final verification command
poetry run pytest tests/ --cov=. --cov-report=term-missing --cov-branch -q
# Expected: TOTAL 100%  100%
```
