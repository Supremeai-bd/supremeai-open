---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:file_organization_and_cleanup_action_plan
subject: ✅ SupremeAI - COMPLETE File Organization Action Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# ✅ SupremeAI - COMPLETE File Organization Action Plan

## 🎯 Master Checklist: Original Roadmap + New Findings Combined

---

# 🔴 PHASE 0: ELIMINATE DUPLICATES (Do This First!)

## Quick Wins - Zero Risk, Immediate Impact

### 0.1 Triple auto_healer.py 🚨
```
KEEP:   backend/services/auto_healer.py (864 lines) - CANONICAL
DELETE: backend/agents/devops/auto_healer.py
DELETE: backend/core/auto_healer_service.py
```
**Time: 5 minutes | Risk: None**

### 0.2 Double temporal_system.py
```
KEEP:   backend/evolution/temporal_abstraction/temporal_system.py (905 lines)
DELETE: backend/core/evolution/temporal_abstraction/temporal_system.py
```
**Time: 2 minutes | Risk: None**

### 0.3 Double tom_system.py
```
KEEP:   backend/evolution/theory_of_mind/tom_system.py (830 lines)
DELETE: backend/core/evolution/theory_of_mind/tom_system.py
```
**Time: 2 minutes | Risk: None**

### 0.4 Investigate browser routes
```bash
diff backend/api/routes/browser.py backend/api/routes/browser_routes.py
# If >60% similar, delete one
```
**Time: 10 minutes | Risk: Low**

### 0.5 Investigate mobile home_screen.dart
```bash
diff apps/mobile/lib/screens/home_screen.dart apps/mobile/lib/src/theme/home_screen.dart
# Determine if duplicate or different screens
```
**Time: 5 minutes | Risk: None**

---

# 🔴 PHASE 1: SPLIT CRITICAL LARGE FILES (>1000 lines)

## Infrastructure (NEW! Not in Original)

### 1.1 Split `infrastructure/firebase_functions_v1/index.js` (709 lines)
```
CREATE:
├── middleware/cors.js (~40 lines)
├── middleware/auth.js (~60 lines)
├── handlers/scheduled_tasks.js (~200 lines)
├── handlers/api_routes.js (~200 lines)
├── handlers/firestore_triggers.js (~169 lines)
REDUCE index.js to: ~100 lines (entry point only)
```

### 1.2 Split `infrastructure/cloudflare/enhanced-worker-v2.js` (595 lines)
```
CREATE:
├── worker-modules/router.js (~150 lines)
├── worker-modules/cache-handler.js (~150 lines)
├── worker-modules/auth-checker.js (~100 lines)
├── worker-modules/response-builder.js (~100 lines)
REDUCE enhanced-worker-v2.js to: ~150 lines
```

### 1.3 Split `infrastructure/firebase_functions_v1/src/scrapeEngine.ts` (542 lines)
```
CREATE:
├── scrapeEngine/core.ts (~200 lines)
├── scrapeEngine/parsers.ts (~170 lines)
├── scrapeEngine/storage.ts (~172 lines)
```

## Backend API Routes (NEW!)

### 1.4 Split `backend/api/routes/admin_dashboard.py` (1,176 lines)
```
CREATE: api/routes/admin/
├── __init__.py (~20 lines)
├── dashboard_stats.py (~300 lines)
├── user_management.py (~300 lines)
├── system_config.py (~300 lines)
├── activity_logs.py (~256 lines)
```

## Backend Services (NEW!)

### 1.5 Split `backend/services/smart_model_router.py` (967 lines)
```
CREATE: services/model_selectors/
├── smart_model_router.py (~350 lines) - Main orchestrator
├── cost_based_selector.py (~200 lines)
├── performance_selector.py (~200 lines)
├── capability_selector.py (~217 lines)
```

## From Original Roadmap (Still Pending)

### 1.6 Split `tools/tool_knowledge_injector.py` (2,044 lines) → 4 files
### 1.7 Split `tests/test_mcp_servers_integration.py` (1,987 lines) → 4 files
### 1.8 Split `scripts/devops/superai_config_validator.py` (1,038 lines) → 4 files
### 1.9 Split `.github/scripts/ci_summary_v2.py` (1,346 lines) → 4 files
### 1.10 Split `frontend CIDashboard.tsx` (1,297 lines) → 8 files
### 1.11 Split `frontend CrownJewelBrowser.tsx` (1,168 lines) → 3 files

---

# 🟢 PHASE 2: MERGE SMALL FILES

## Scripts Directory (From Original)

### 2.1 Merge scripts/devops/ (12→3 files) ✓
- [ ] devops_audit_suite.py (merge 4 files)
- [ ] devops_ai_scribe.py (merge 2 files)
- [ ] devops_security_scan.py (merge 3 files)

### 2.2 Merge scripts/backup/ (7→2 files) ✓
- [ ] backup_providers.py (merge 3 files)
- [ ] backup_telegram.py (merge 3 files)

### 2.3 Merge scripts/resource_collection/ (10→2 files) ✓
- [ ] scrapers.py (merge 6 files)
- [ ] api_clients.py (merge 2 files)

### 2.4 Merge scripts/testing/ (11→6 files) ✓
- [ ] test_security.py (merge 2 files)
- [ ] test_performance.py (merge 2 files)
- [ ] test_runners.py (merge 2 files)

## NEW: Backend Core/Security Consolidation

### 2.5 Merge backend/core/security/ (28→16 files) ⭐ NEW
```
CONSOLIDATE INTO:
├── injections/
│   ├── sql_prevention.py (merge from sql_injection_prevention.py)
│   └── xss_protection.py (extract if exists)
├── scanning/
│   ├── ast_scanner.py (MERGE: ast_sandbox_scanner + enhanced_ast_scanner)
│   ├── secret_scanner.py (MERGE: secret_hunter + related)
│   └── vulnerability_scanner.py
├── authentication/
│   ├── auth_middleware.py (keep)
│   ├── rbac.py (keep)
│   └── session_manager.py (extract if exists)
├── protection/
│   ├── ssrf_protection.py (keep)
│   ├── prompt_firewall.py (keep)
│   └── honeypot.py (from honeypot_middleware)
├── audit/
│   ├── security_auditor.py (keep)
│   └── compliance_bot.py (keep)
└── intelligence/
    ├── guardian_ai.py (keep)
    └── behavioral_analyzer.py (keep)
```

## NEW: Root Scripts Cleanup

### 2.6 Move root scripts to proper locations ⭐ NEW
```bash
mv generate_secrets.py scripts/security/
mv fix_eslint_any.py scripts/devops/
mv fix_mypy.py scripts/devops/
mv fetch_logs.py scripts/monitoring/
mv cleanup.py scripts/maintenance/
```

---

# 🔵 PHASE 3: REORGANIZE DIRECTORIES

## Frontend (From Original + New)

### 3.1 Reorganize frontend/src/components/admin/ (56 files → 6 subdirs) ⭐
```
admin/
├── ci/         (8 files) - CI/CD components
├── data/       (4 files) - Data browsers
├── security/   (4 files) - Security panels
├── infra/      (5 files) - Infrastructure
├── auth/       (3 files) - Authentication
└── shared/     (5 files) - Reusable components
```

### 3.2 Split Frontend Store ⭐ NEW
```
SPLIT: useSupremeStore.ts (523 lines) → 5 files
├── useSupremeStore.ts (~100 lines)
└── slices/
    ├── userSlice.ts (~120 lines)
    ├── workspaceSlice.ts (~120 lines)
    ├── uiSlice.ts (~100 lines)
    └── apiSlice.ts (~83 lines)
```

## Backend (NEW)

### 3.3 Consolidate backend/tests/ (413 files) ⭐ NEW
```
tests/
├── conftest.py
├── test_suites/
│   ├── core_test_suite.py (merge 34 files)
│   ├── tools_test_suite.py (merge 28 files)
│   ├── services_test_suite.py (merge 12 files)
│   ├── api_test_suite.py (merge 7 files)
│   └── agents_test_suite.py (merge remaining)
├── integration/
└── performance/
```

---

# 📋 EXECUTION TIMELINE (Updated)

## Week 1: Quick Wins & Duplicates (Day 1-2)
- [x] **Day 1 Morning**: Eliminate all duplicates (Phase 0) - **2 hours**
- [x] **Day 1 Afternoon**: Move root scripts (Phase 2.6) - **30 minutes**
- [ ] **Day 2**: Split infrastructure files (Phase 1.1-1.3) - **6 hours**

## Week 2: Critical Splits (Day 3-5)
- [ ] **Day 3**: Split backend large files (Phase 1.4-1.5) - **6 hours**
- [ ] **Day 4**: Split original roadmap large files (Phase 1.6-1.8) - **6 hours**
- [ ] **Day 5**: Split frontend large files (Phase 1.9-1.11) - **6 hours**

## Week 3: Merges & Consolidation (Day 6-8)
- [ ] **Day 6**: Merge scripts directories (Phase 2.1-2.4) - **6 hours**
- [ ] **Day 7**: Merge security directory (Phase 2.5) - **4 hours**
- [ ] **Day 8**: Reorganize frontend admin (Phase 3.1) - **4 hours**

## Week 4: Final Polish (Day 9-10)
- [ ] **Day 9**: Reorganize tests & split store (Phase 3.2-3.3) - **4 hours**
- [ ] **Day 10**: Update imports, run tests, fix issues - **8 hours**

**Total Estimate: ~55 hours of work over 2 weeks (part-time)**

---

# 📊 FINAL METRICS

## Before vs After Complete Action Plan:

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Total Files** | 2,125 | ~1,570 | ↓ 26% reduction |
| **Files > 1000 lines** | 19 | ~5 | ↓ 74% |
| **Max File Size** | 2,044 | ~900 | ↓ 56% |
| **Duplicate Files** | 6+ instances | 0 | ✅ Eliminated |
| **Flat Directories** | 3+ (admin, tests, etc.) | 0 | ✅ Organized |
| **Avg File Size** | 162 lines | ~280 lines | ↑ 73% better |

---

# 🚨 RISK MITIGATION

## After Each Phase:
```bash
# 1. Run Python import checks
python -c "import backend; import scripts"

# 2. Run TypeScript compilation
cd apps/desktop && npm run build
cd frontend && npm run build

# 3. Run test suite
pytest backend/tests/ -x --tb=short

# 4. Check for broken imports
grep -r "from.*import" backend/ --include="*.py" | grep -v "__pycache__"
```

## Rollback Plan:
```bash
# If anything breaks:
git checkout -b "file-reorg-$(date +%Y%m%d)"
# Make changes
git add -A
git commit -m "File reorganization phase X"

# To rollback:
git revert HEAD
```

---

# ✅ SUCCESS CRITERIA

- [ ] No duplicate files remain
- [ ] No file exceeds 1,000 lines (except migration files)
- [ ] All imports resolve correctly
- [ ] Full test suite passes
- [ ] Build succeeds for all apps (desktop, mobile, frontend)
- [ ] Documentation updated with new structure

---

*Complete Action Plan v1.0*
*Combines: Original Strict Roadmap + Additional Findings*
*Repository: https://github.com/SaifulHaqueNiloy/supremeai*