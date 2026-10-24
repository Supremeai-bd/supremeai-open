---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:repository_strict_file_hygiene_roadmap
subject: 🔥 SupremeAI Repository - STRICT File Organization Roadmap
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🔥 SupremeAI Repository - STRICT File Organization Roadmap

## 📊 Current State Summary

| Metric | Value | Status |
|--------|-------|--------|
| **Total Source Files** | 2,125 | 🔴 Too Many |
| **Files < 50 lines** | ~200+ | 🔄 Must Merge |
| **Files 500-1000 lines** | 110+ | ⚠️ Should Split |
| **Files > 1000 lines** | 17 | 🔴 Must Split |
| **Duplicate Patterns Found** | 104 `main()` functions | 🔄 Consolidate |

---

# 🎯 PHASE 1: MERGE SMALL FILES (Highest Priority)

## 1.1 SCRIPTS/DEVOPS - Merge 12 files → 3 modules

### ✅ ACTION: Create `scripts/devops/devops_audit_suite.py`
**Merge these 4 files (1,947 combined lines → ~1,500 lines):**

| Source File | Lines | Key Functions to Extract |
|------------|-------|-------------------------|
| `bug_prophet.py` | 704 | `BugProphet`, `predict_bugs()`, `analyze_code_smells()` |
| `refactor_wiz.py` | 637 | `RefactorWiz`, `suggest_refactors()`, `apply_refactor()` |
| `generate_modular_audits.py` | 625 | `ModularAuditGenerator`, `generate_audit_report()` |
| `run_local_audit.py` | 114 | `audit_file_with_ollama()`, `main()` |

**How to merge:**
```python
# devops_audit_suite.py structure:
class BugProphet:      # From bug_prophet.py
    """Predict potential bugs using AST analysis"""
    
class RefactorWiz:     # From refactor_wiz.py  
    """Suggest and apply code refactoring"""
    
class ModularAuditGenerator:  # From generate_modular_audits.py
    """Generate modular audit reports"""
    
def run_local_audit():        # From run_local_audit.py
    """Run single file audit via Ollama"""

# CLI entry point
def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command')
    
    # bug-prophet subcommand
    # refactor subcommand  
    # audit-generate subcommand
    # local-audit subcommand
```

---

### ✅ ACTION: Create `scripts/devops/devops_ai_scribe.py`
**Merge these 2 files (599 combined lines):**

| Source File | Lines | Key Functions |
|------------|-------|---------------|
| `ai_scribe_historian.py` | 481 | `AIScribeHistorian`, `generate_changelog()`, `analyze_commits()` |
| `ask_scribe.py` | 118 | `ask_scribe()`, `query_knowledge_base()` |

**How to merge:** Combine into single module with `historian` and `query` modes

---

### ✅ ACTION: Create `scripts/devops/devops_security_scan.py`
**Merge these 3 files (580 combined lines):**

| Source File | Lines | Key Functions |
|------------|-------|---------------|
| `fast_secret_scan.py` | 88 | `fast_secret_scan()`, `get_staged_files()` |
| `secret_scan_ci.py` | 330 | `CISecretScanner`, `scan_commit_range()` |
| `wire_error_bus.py` | 162 | `process_file()`, `fix_wire_format()` |

---

### ✅ ACTION: Keep Separate (Already Well-Sized)
These files are already good size - keep as-is:

| File | Lines | Reason to Keep |
|------|-------|----------------|
| `superai_config_validator.py` | 1038 | Complex standalone tool - SPLIT instead (see Phase 2) |
| `cloud_watchman.py` | 454 | Distinct responsibility |
| `todo_manager.py` | 238 | Self-contained utility |

**DELETE after merging:** `bug_prophet.py`, `refactor_wiz.py`, `generate_modular_audits.py`, `run_local_audit.py`, `ai_scribe_historian.py`, `ask_scribe.py`, `fast_secret_scan.py`, `secret_scan_ci.py`, `wire_error_bus.py`

---

## 1.2 SCRIPTS/SECURITY - Already Partially Merged, Complete It

### Current State (After partial merge):
```
✅ security_scanners.py     (1418 lines) - Merged from auto_vulnerability_scanner.py
✅ security_secrets.py       (756 lines) - Merged from auto_secret_rotate.py  
✅ security_audit.py         (859 lines) - Merged from audit_log_analyzer.py
```

### ✅ ACTION: Split `security_scanners.py` (1418 lines is TOO LARGE)

**Split into:**
```python
# security_vuln_scanner.py (~600 lines)
class VulnerabilityScanner:
    """Scan for CVEs, dependencies issues"""
    
# security_blindspot_finder.py (~500 lines)  
class BlindspotFinder:
    """Find security blindspots in code"""
    
# security_dependency_checker.py (~400 lines)
class DependencyChecker:
    """Check dependency health"""
```

**Also merge remaining small files if they exist:**
- `check_dependencies.py` → into `security_dependency_checker.py`
- `find_dead_code.py` → into new `security_code_analyzer.py`
- `auto_find_blindspots.py` → MERGE into `security_blindspot_finder.py`

---

## 1.3 SCRIPTS/AI - Already Merged, But Need Splitting

### Current State:
```
✅ ai_memory.py      (286 lines) - GOOD SIZE, keep
✅ ai_models.py     (1176 lines) - TOO LARGE, split
✅ ai_tools.py       (720 lines) - Borderline, can keep or split
```

### ✅ ACTION: Split `ai_models.py` (1176 lines)

**Split into:**
```python
# ai_version_manager.py (~400 lines)
class ModelVersionManager:
    """Track model versions, rollbacks"""

# ai_drift_detector.py (~400 lines)
class ModelDriftDetector:
    """Detect model drift over time"""
    
# ai_bias_detector.py (~376 lines)  
class BiasDetector:
    """Detect bias in model outputs"""
```

---

## 1.4 SCRIPTS/BACKUP - Merge 7 files → 2 modules

### ✅ ACTION: Create `scripts/backup/backup_providers.py`
**Merge these 4 files (1,866 combined lines):**

| Source File | Lines | Key Classes/Functions |
|------------|-------|----------------------|
| `superai_backup_manager.py` | 1171 | `SuperAIBackupManager` - MAIN class |
| `auto_firestore_backup.py` | 256 | `FirestoreBackupProvider` |
| `auto_cross_cloud_replicate.py` | 324 | `CrossCloudReplicator` |

**Structure:**
```python
# backup_providers.py
class BackupConfig:           # Shared config
class BackupManifest:         # Shared manifest
    
class SuperAIBackupManager:   # Main orchestrator
    def __init__(self):
        self.firestore_provider = FirestoreBackupProvider()
        self.cross_cloud = CrossCloudReplicator()

class FirestoreBackupProvider:
    """Handle Firestore backups"""
    
class CrossCloudReplicator:
    """Cross-cloud replication logic"""
```

### ✅ ACTION: Create `scripts/backup/backup_telegram.py`
**Merge these 3 files (914 combined lines):**

| Source File | Lines | Key Functions |
|------------|-------|---------------|
| `telegram_backup_vault.py` | 219 | `TelegramBackupVault` |
| `telegram_code_backup.py` | 611 | `TelegramCodeBackup` |
| `restore_from_telegram.py` | 84 | `restore_from_telegram()` |

### Keep Separate:
- `create_desktop_backup.py` (444 lines) - Different target (local desktop)

**DELETE after merging:** All source files above

---

## 1.5 SCRIPTS/MONITORING - Already Merged, Needs Splitting

### Current State:
```
✅ monitoring_core.py   (2324 lines) - WAY TOO LARGE
✅ monitoring_logs.py   (1757 lines) - TOO LARGE
```

### ✅ ACTION: Split `monitoring_core.py` (2324 lines)

**Split into:**
```python
# monitoring_sla.py (~600 lines)
class SLATracker:
    """Track SLA compliance"""

# monitoring_cost.py (~600 lines)  
class CostAnalyzer:
    """Analyze infrastructure costs"""
    
# monitoring_capacity.py (~600 lines)
class CapacityPlanner:
    """Plan capacity needs"""
    
# monitoring_shared.py (~524 lines)
# Shared utilities, base classes
```

### ✅ ACTION: Split `monitoring_logs.py` (1757 lines)

**Split into:**
```python
# log_analyzer.py (~700 lines)
class SuperAILogAnalyzer:
    """Analyze application logs"""

# cpu_monitor.py (~600 lines) 
class SuperAICPUMonitor:
    """Monitor CPU usage"""
    
# log_shared.py (~457 lines)
# Shared parsing utilities
```

---

## 1.6 SCRIPTS/TESTING - Merge 11 files → 4 modules

### ✅ ACTION: Create `scripts/testing/test_security.py`
**Merge these 2 files (531 combined lines):**

| Source File | Lines | Content |
|------------|-------|---------|
| `security_audit.py` | 254 | Security audit runner |
| `security_penetration_test.py` | 277 | Penetration testing |

### ✅ ACTION: Create `scripts/testing/test_performance.py`
**Merge these 2 files (1,482 combined lines):**

| Source File | Lines | Content |
|------------|-------|---------|
| `performance_benchmark.py` | 890 | Performance benchmarks |
| `_gen_services.py` | 899 | Service generation for tests |

### ✅ ACTION: Create `scripts/testing/test_runners.py`
**Merge these 2 files (1,189 combined lines):**

| Source File | Lines | Content |
|------------|-------|---------|
| `integration_test_runner.py` | 597 | Integration test runner |
| `superai_smoketest.py` | 596 | Smoke test suite |

### Keep Separate (already good size):
- `api_contract_validator.py` (1077 lines) → SPLIT in Phase 2
- `alert_manager.py` (746 lines) → Keep
- `log_anomaly_detector.py` (712 lines) → Keep
- `mutation_testing.py` (698 lines) → Keep
- `auto_test_generator.py` (592 lines) → Keep

---

## 1.7 SCRIPTS/RESOURCE_COLLECTION - Merge 10 files → 2 modules

### ✅ ACTION: Create `scripts/resource_collection/scrapers.py`
**Merge these 6 files (549 combined lines):**

| Source File | Lines | Content |
|------------|-------|---------|
| `base_scraper.py` | 182 | Base scraper class |
| `awesome_python.py` | 45 | Python awesome list scraper |
| `awesome_go.py` | 45 | Go awesome list scraper |
| `awesome_selfhosted.py` | 45 | Self-hosted awesome list |
| `ossinsight/client.py` | 169 | OSS Insight client |
| `ossinsight/test.py` | 22 | Tests |

### ✅ ACTION: Create `scripts/resource_collection/api_clients.py`
**Merge these 2 files (179 combined lines):**

| Source File | Lines | Content |
|------------|-------|---------|
| `base_api_client.py` | 178 | Base API client |
| `run_all_collectors.py` | 1 | Just imports (delete) |

### Delete:
- `run_all.py` (69 lines) - Move logic to scrapers.py `main()`
- `__init__.py`, `run_all_collectors.py` - Unnecessary

---

## 1.8 TINY UTILITY FILES - Merge or Delete

### ✅ DELETE These (Useless/Archive):
```
scripts/_archive/*           (9 files - Already archived, remove from main)
scripts/cost_guard_monitor.py (19 lines - Incomplete stub)
scripts/ai_query_optimizer.py (17 lines - Stub)
scripts/one-off/fix_dups.py  (20 lines - One-off, should be in _archive)
scripts/one-off/fix_docs.py  (22 lines - One-off, should be in _archive)
```

### ✅ Merge Into Parent Modules:
```
scripts/maintenance/notify.py     (45 lines) → Into scripts/maintenance/__init__.py
scripts/orchestrator/auto_budget_guardian.py → scripts/orchestrator.py
scripts/diagnostics/superai_console_detective.py → Keep but SPLIT (909 lines)
scripts/health/cleanup_duplicate_health_scripts.sh → Run once, then delete
```

---

# 🔧 PHASE 2: SPLIT LARGE FILES (Critical)

## 2.1 ABSOLUTE MUST-SPLIT Files (>1000 lines)

### 🔴 File 1: `tools/tool_knowledge_injector.py` (2,044 lines)

**Current Structure:**
```python
class ToolKnowledgeCard:          (lines 48-104)    56 lines
def build_knowledge_cards():      (lines 105-1790) 1685 lines ← PROBLEM
class ToolKnowledgeInjector:      (lines 1791-1979) 188 lines
def main():                       (lines 1980-2044)  64 lines
```

**Split Into:**
```python
# tools/knowledge/cards.py (~200 lines)
class ToolKnowledgeCard:
    """Data class for knowledge cards"""
    
# tools/knowledge/card_builder.py (~800 lines)  
def build_python_tool_cards():    # ~200 lines
def build_js_tool_cards():        # ~200 lines
def build_infra_tool_cards():     # ~200 lines
def build_ml_tool_cards():        # ~200 lines

# tools/knowledge/injector.py (~300 lines)
class ToolKnowledgeInjector:
    """Inject knowledge into tools"""

# tools/knowledge/cli.py (~70 lines)
def main():
    """CLI entry point"""
```

---

### 🔴 File 2: `tests/test_mcp_servers_integration.py` (1,987 lines)

**Split By Test Category:**
```python
# tests/mcp/test_mcp_connection.py     (~400 lines)
class TestMCPConnection: ...

# tests/mcp/test_mcp_tools.py          (~500 lines)
class TestMCPTools: ...

# tests/mcp/test_mcp_memory.py         (~500 lines)
class TestMCPMemory: ...

# tests/mcp/test_mcp_errors.py         (~587 lines)
class TestMCPErrors: ...
```

---

### 🔴 File 3: `scripts/devops/superai_config_validator.py` (1,038 lines)

**Current Structure:**
```python
class Severity:              (lines 51-58)    8 lines
class ValidationResult:      (lines 59-83)   25 lines
class ConfigValidationReport:(lines 84-170)  86 lines
class SuperAIConfigValidator:(lines 171-986) 815 lines ← PROBLEM
def main():                  (lines 987-1038) 51 lines
```

**Split Into:**
```python
# devops/config/models.py (~120 lines)
class Severity, ValidationResult, ConfigValidationReport

# devops/config/validators.py (~500 lines)
class SuperAIConfigValidator:
    # Core validation logic only

# devops/config/rules.py (~300 lines)
# Individual validation rules
# Security rules, performance rules, etc.

# devops/config/cli.py (~60 lines)
def main()
```

---

### 🔴 File 4: `.github/scripts/ci_summary_v2.py` (1,346 lines)

**Split Into:**
```python
# github/scripts/collectors.py (~400 lines)
def collect_test_results(): ...
def collect_coverage_data(): ...
def collect_deploy_status(): ...

# github/scripts/formatters.py (~400 lines)
def format_summary_table(): ...
def format_trend_chart(): ...
def format_alert_message(): ...

# github/scripts/notifiers.py (~300 lines)
def send_slack_notification(): ...
def send_email_report(): ...
def update_github_status(): ...

# github/scripts/main.py (~246 lines)
def main(): ...
```

---

### 🔴 File 5: `frontend/src/components/admin/CIDashboard.tsx` (1,297 lines)

**Current Exports (from analysis):**
```typescript
// Internal components that should be extracted:
function Badge({})            (line 282)  83 lines
function ScoreCircle({})      (line 297)  32 lines  
function AnimatedStatus({})   (line 329)  16 lines
function ProgressBar({})      (line 345)  20 lines
function InsightCard({})      (line 365)  41 lines
function JobRow({})           (line 406)  71 lines
function EmptyState({})       (line 477)  14 lines
export function CIDashboard   (line 503)  771 lines ← MAIN
function convertToCSV()       (line 1274) 23 lines
```

**Split Into:**
```typescript
// admin/ci/Badge.tsx                    (~90 lines)
// admin/ci/ScoreCircle.tsx              (~40 lines)
// admin/ci/ProgressBar.tsx              (~30 lines)
// admin/ci/InsightCard.tsx              (~50 lines)
// admin/ci/JobRow.tsx                   (~80 lines)
// admin/ci/CIDashboard.tsx              (~850 lines) - Main orchestrator
// admin/ci/types.ts                     (~80 lines) - All interfaces
// admin/ci/utils.ts                     (~30 lines) - Helper functions
```

---

### 🔴 File 6: `frontend/src/components/admin/CrownJewelBrowser.tsx` (1,168 lines)

**Split Into:**
```typescript
// admin/data/BrowserTab.tsx             Interfaces
// admin/data/CrownJewelBrowser.tsx      Main component (~800 lines)
// admin/data/CrownJewelUtils.ts         Utility functions (~150 lines)
```

---

## 2.2 SHOULD-SPLIT Files (500-1000 lines) - Top Priority

| File | Lines | Suggested Split |
|------|-------|-----------------|
| `backend/services/smart_model_router.py` | 967 | Split: Router + Selector + Cache |
| `scripts/benchmark/superai_load_tester.py` | 939 | Split: Generator + Runner + Reporter |
| `backend/tools/security_tools/multi_account_rotator.py` | 914 | Split: Rotator + Validator + Sync |
| `scripts/diagnostics/superai_console_detective.py` | 909 | Split: Parser + Analyzer + Reporter |
| `backend/memory/mcp_server.py` | 895 | Split: Server + Handlers + Transport |
| `backend/database/supabase_client.py` | 886 | Split: Client + Queries + Realtime |
| `backend/services/auto_healer.py` | 864 | Split: Detector + Healer + Verifier |
| `backend/core/auto_healer.py` | 864 | ⚠️ DUPLICATE - choose one, delete other |
| `backend/services/llm/llm_router.py` | 847 | Split: Router + Fallback + LoadBalancer |
| `scripts/security/security_audit.py` | 859 | Split: Collector + Analyzer + Reporter |

---

# 📁 PHASE 3: REORGANIZE DIRECTORY STRUCTURE

## 3.1 Frontend Admin Components (CRITICAL)

### Problem: 47 TSX files in flat `admin/` directory

### Solution: Feature-Based Subdirectories

```
admin/
├── ci/                              CI/CD Components
│   ├── CIDashboard.tsx             (1297→850 after extract)
│   ├── CICDVisualizer.tsx          (172)
│   ├── GitHubCIWidget.tsx           (need to find)
│   ├── Badge.tsx                   (extracted)
│   ├── ScoreCircle.tsx             (extracted)
│   ├── JobRow.tsx                  (extracted)
│   └── types.ts
│
├── data/                            Data Browsing Components
│   ├── CrownJewelBrowser.tsx       (1168→800 after extract)
│   ├── MemoryBrowser.tsx
│   ├── AuditLogsPanel.tsx
│   └── utils.ts
│
├── security/                        Security Components
│   ├── SecurityDashboard.tsx       (245)
│   ├── ThreatDetection.tsx
│   ├── RateLimitManager.tsx        (363)
│   └── RulesEnginePanel.tsx        (234)
│
├── infra/                           Infrastructure Components
│   ├── ServiceHealthMonitor.tsx    (514)
│   ├── CloudOrchestrator.tsx
│   ├── DeploymentModal.tsx         (324)
│   ├── HealthMap.tsx
│   └── SystemUptimeWidget.tsx      (134)
│
├── auth/                            Authentication Components
│   ├── AdminLogin.tsx             (272)
│   ├── AdminAuthenticated.tsx     (159)
│   └── ConsentMatrixModal.tsx     (161)
│
├── shared/                          Reusable Admin Components
│   ├── ActionCard.tsx             (162)
│   ├── DynamicPanel.tsx
│   ├── HealthReportWidget.tsx
│   ├── AdminAlertsTab.tsx         (156)
│   └── ScreencastViewer.tsx       (196)
│
├── Dashboard.tsx                   (783) - Main dashboard
├── AdminDashboardHome.tsx          (393)
├── AdminConsole.tsx                (keep here - main entry)
├── AdminTopNav.tsx                 (navigation)
└── index.ts                        (barrel exports)
```

---

## 3.2 Backend Tests Directory (413 files - REDUCE)

### Problem: Too many scattered test files

### Solution: Consolidate by Module

```
tests/
├── conftest.py                      Shared fixtures
├── test_suites/
│   ├── core_test_suite.py          Merge: tests/core/*.py (34 files)
│   ├── tools_test_suite.py         Merge: tests/tools/*.py (28 files)
│   ├── services_test_suite.py      Merge: tests/services/*.py (12 files)
│   ├── api_test_suite.py           Merge: tests/api/*.py (7 files)
│   └── agents_test_suite.py        Merge: tests/agents/*.py
├── integration/
│   └── test_mcp_integration.py     Split from 1987-line file
└── performance/
    └── test_load.py                Performance tests
```

---

# 📋 EXECUTION CHECKLIST

## Week 1: Quick Wins (MERGE phase)

- [ ] **Day 1-2**: Merge `scripts/devops/` (12→4 files)
- [ ] **Day 2-3**: Merge `scripts/backup/` (7→2 files)  
- [ ] **Day 3-4**: Merge `scripts/resource_collection/` (10→2 files)
- [ ] **Day 4-5**: Merge `scripts/testing/` (11→6 files)
- [ ] **Day 5**: Delete `_archive/` and stub files

**Expected Result:** ~60 fewer files

## Week 2: Medium Effort (SPLIT phase)

- [ ] **Day 1-2**: Split `tool_knowledge_injector.py` (2044→4 files)
- [ ] **Day 2-3**: Split `test_mcp_servers_integration.py` (1987→4 files)
- [ ] **Day 3-4**: Split `superai_config_validator.py` (1038→4 files)
- [ ] **Day 4-5**: Split `CIDashboard.tsx` (1297→8 files)
- [ ] **Day 5**: Split `CrownJewelBrowser.tsx` (1168→3 files)

**Expected Result:** ~5 fewer huge files, ~20 new well-sized files

## Week 3: Structure & Cleanup

- [ ] **Day 1-2**: Reorganize `admin/` into subdirectories
- [ ] **Day 2-3**: Split `monitoring_core.py` and `monitoring_logs.py`
- [ ] **Day 3-4**: Split `ai_models.py` and `security_scanners.py`
- [ ] **Day 4-5**: Consolidate `tests/` directory
- [ ] **Day 5**: Update all imports and verify tests pass

**Expected Result:** Clean, maintainable structure

---

# ⚠️ CRITICAL WARNINGS

## DO NOT Merge These (Different Concerns):

| Files | Reason |
|-------|--------|
| `backend/services/auto_healer.py` + `backend/core/auto_healer.py` | DUPLICATES - delete one, don't merge |
| `backend/evolution/temporal_system.py` + `backend/core/evolution/temporal_system.py` | DUPLICATES - choose canonical location |
| Any test file with production code | Tests must stay separate |
| JS files with Python files | Different runtimes |

## Import Path Updates Required:

After any merge/split, update:
1. All `import` statements referencing moved functions
2. `__init__.py` barrel exports
4. CI/CD configurations referencing script paths
5. Documentation examples

## Testing Requirements:

After each merge/split:
```bash
# Run full test suite
pytest backend/tests/ --cov=backend/

# Check for import errors
python -c "import scripts.devops.devops_audit_suite"

# Verify CLI still works
python scripts/devops/devops_audit_suite.py --help
```

---

# 📊 EXPECTED FINAL STATE

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Total Files | 2,125 | ~1,650 | ↓ 22% |
| Avg File Size | 162 lines | 280 lines | ↑ 73% |
| Files > 1000 lines | 17 | 3-5 | ↓ 75% |
| Files < 50 lines | 200+ | ~30 | ↓ 85% |
| Max File Size | 2,044 | ~900 | ↓ 56% |
| Directories (flat) | Many | Organized | ↑ Maintainability |

---

*Roadmap Version: 1.0*
*Generated: Deep Analysis*
*Repository: https://github.com/SaifulHaqueNiloy/supremeai*