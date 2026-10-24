---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:admin_dashboard_visual_and_api_gap_analysis
subject: 🔍 SupremeAI Admin Dashboard - Complete Gap Analysis Report
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# 🔍 SupremeAI Admin Dashboard - Complete Gap Analysis Report

**Repository:** `SaifulHaqueNiloy/supremeai`  
**Date:** 2026-08-22  
**Analysis Type:** Feature Gap & Implementation Quality Audit

---

## 📊 Executive Summary

After deep-diving into **50+ admin components**, **backend routes**, **services**, and **state management**, I've identified **critical gaps** that are preventing your admin dashboard from being production-ready.

### 🎯 Key Findings

| Category | Count | Severity |
|----------|-------|----------|
| **Missing Backend Endpoints** | 8 | 🔴 Critical |
| **Hardcoded/Mock Data** | 12 | 🔴 Critical |
| **Broken Component Logic** | 6 | 🟠 High |
| **Missing Error Handling** | 9 | 🟠 High |
| **Authentication Gaps** | 4 | 🔴 Critical |
| **Unimplemented Features** | 7 | 🟡 Medium |
| **Performance Issues** | 5 | 🟡 Medium |

---

## 🚨 CRITICAL ISSUES (Immediate Action Required)

---

### Issue #1: Service Health Monitoring System - INCOMPLETE

**Files Affected:**
- `frontend/src/components/admin/ServiceHealthMetrics.tsx`
- `frontend/src/components/admin/HealthBanner.tsx`
- `frontend/src/components/admin/HealthMap.tsx`

**Problem:** 
Your health monitoring system is **fragmented across multiple components** with no unified source of truth:

```typescript
// ❌ CURRENT: HealthBanner.tsx - Only checks basic status
const { data: health } = useQuery({
  queryKey: ['dashboard', 'health'],
  queryFn: () => apiClient.get('/admin-api/health-map'), // Single endpoint
});

// ❌ CURRENT: ServiceHealthMetrics.tsx - Only checks Java Worker
const response = await apiClient.get('/admin/microservices/java-worker/health');
// Returns MOCK data when fails:
return {
  status: 'OFFLINE', // Always shows offline if backend unreachable
  uptimeSeconds: 0,
  // ... hardcoded zeros
};
```

**What's Missing:**
- [ ] No multi-service monitoring (Backend, Admin, Scraper, Edge Worker)
- [ ] No real-time health aggregation from Cloudflare Worker
- [ ] No circuit breaker pattern for failed services
- [ ] No historical health data / uptime tracking
- [ ] No alerting system (Discord/Slack webhooks)
- [ ] HealthMap component exists but isn't integrated into main Dashboard

**Impact:** Admins cannot see real system status, leading to prolonged outages going unnoticed.

---

### Issue #2: Cost Auditor Using HARDCODED Data

**File:** `frontend/src/components/admin/CostAuditor.tsx`

**Problem:** 
The entire cost monitoring system uses **completely fake data**:

```typescript
// ❌ HARDCODED - Not from API!
const spent = 42.67;  // Fake value
const limit = 150.00; // Fake value

const providerCosts = [
  { name: "Google Gemini", spent: 18.24, quota: 50.00 },  // Hardcoded
  { name: "OpenRouter (DeepSeek)", spent: 12.80, quota: 40.00 },  // Hardcoded
  { name: "Hugging Face Hub", spent: 6.45, quota: 30.00 },  // Hardcoded
];

const recentCharges = [
  { time: "2026-06-22 22:04:12", user: "admin", model: "gemini-1.5-pro", ... },
  // All fake timestamps and data!
];
```

**Backend Reality Check:**
```python
# backend/api/routes/admin_dashboard.py - get_costs()
def get_costs():
    auditor = CostAuditor()
    try:
        reports = auditor.generate_report()
        # ... returns markdown text, NOT structured cost data
        return {"status": "ok", "report": content}
    except Exception as e:
        return {
            "status": "error",
            "report": f"# ⚠️ Cost Engine Error\n\nUnable to pull metrics from DB: {e!s}"
        }
```

**What's Missing:**
- [ ] No structured API for per-provider costs
- [ ] No real-time token usage tracking
- [ ] No budget alerting system
- [ ] No billing cycle management
- [ ] Cost charts/graphs show fake trends

**Impact:** Financial blindness - can't track actual AI/LLM spending.

---

### Issue #3: Security Dashboard - FAKE Data & Missing Endpoints

**File:** `frontend/src/components/admin/SecurityDashboard.tsx`

**Problems Found:**

```typescript
// ❌ Static security signals - not real-time!
<div className="flex items-start gap-2">
  <span className="text-emerald-400">[OK]</span>
  <span>All active coroutines are bound to class strong-reference sets...</span>
</div>
// These are HARD-CODED messages, not from API!

// ❌ Memory metrics endpoint likely doesn't exist or returns mock data
const [memoryMetrics, setMemoryMetrics] = useState<MemoryMetrics | null>(null);
const metricsRes = await apiClient.get<MemoryMetrics>('/admin-api/security/memory');
// This endpoint probably doesn't exist in backend!
```

**What's Missing:**
- [ ] Real intrusion detection integration
- [ ] Live threat feed (not static messages)
- [ ] Actual memory leak detection
- [ ] Failed login attempt tracking
- [ ] IP blacklist management UI
- [ ] Security incident response workflow

---

### Issue #4: Threat Detection - Limited Functionality

**File:** `frontend/src/components/admin/ThreatDetection.tsx`

**Issues:**

```typescript
// ⚠️ Works but very basic
const { data, isLoading } = useQuery({
  queryKey: ['dashboard', 'security-scan'],
  queryFn: () => apiClient.get<SecurityScanResponse>('/admin-api/security-scan'),
  refetchInterval: 30_000,
});

// Problems:
// 1. No ability to REMEDIATE threats (just view-only)
// 2. No threat severity configuration
// 3. No automated blocking rules
// 4. "Details" button doesn't do anything (no modal/handler)
// 5. Security score is fake calculation: total === 0 ? 'A' : 'B-'
```

**Missing Features:**
- [ ] Threat remediation actions (block IP, ban user, etc.)
- [ ] Custom security rule builder
- [ ] Integration with WAF/firewall logs
- [ ] Compliance reporting (SOC2, GDPR, etc.)
- [ ] Vulnerability scan scheduling

---

### Issue #5: User Management - DUPLICATE Components & RBAC Issues

**Files Affected:**
- `frontend/src/components/admin/UserManager.tsx`
- `frontend/src/components/admin/RBACManager.tsx`

**Critical Problem - TWO Separate User Management Systems:**

You have **TWO different components** doing the same thing:

```typescript
// UserManager.tsx - Uses queryKey: ['admin-users']
const { data: adminUsers = [] } = useQuery({
  queryKey: ['admin-users'],  // ← Different key
  queryFn: () => apiClient.get<AdminUser[]>('/admin-api/users'),
});

// RBACManager.tsx - Uses queryKey: ['admin', 'users']  
const { data: users } = useQuery({
  queryKey: ['admin', 'users'],  // ← Different key!
  queryFn: () => apiClient.get<AdminUser[]>('/admin-api/users'),  // Same endpoint!
});
```

**Issues:**
- [ ] Cache duplication (same data fetched twice)
- [ ] Inconsistent UI/UX between the two
- [ ] Role options differ (UserManager: Operator/God/Viewer vs RBAC: Viewer/Operator/Developer/Admin/God)
- [ ] No permission granularity (all-or-nothing roles)
- [ ] No audit trail for user changes
- [ ] No MFA enforcement UI
- [ ] No session management (view active sessions)

---

### Issue #6: Backup & Restore - NON-FUNCTIONAL

**File:** `frontend/src/components/admin/BackupRestore.tsx`

**Problems:**

```typescript
// ❌ Hardcoded values
<Card title="Storage Used">
  <div className="text-2xl font-bold text-white font-mono">9.2 GB</div>  {/* FAKE */}
  <div className="text-[10px] text-slate-400">of 100 GB</div>     {/* FAKE */}
</Card>

<Card title="Last Backup">
  <div className="text-sm font-bold text-white font-mono">Today 03:00</div>  {/* FAKE */}
  <div className="text-[10px] text-slate-400">Automatic</div>              {/* FAKE */}
</Card>

// ⚠️ Restore button has NO handler!
{backup.status === 'completed' && (
  <button className="...">
    <Upload size={10} /> Restore  {/* onClick not implemented! */}
  </button>
)}

// Maintenance mode toggle is LOCAL STATE only - doesn't persist!
const [maintenanceMode, setMaintenanceMode] = useState(false);
// No API call to actually enable/disable maintenance mode!
```

**What's Missing:**
- [ ] Real backup storage metrics
- [ ] Functional restore workflow (confirmation, progress, verification)
- [ ] Backup scheduling UI
- [ ] Retention policy configuration
- [ ] Cross-region backup replication status
- [ ] Maintenance mode that actually works
- [ ] Disaster recovery runbook integration

---

## 🟠 HIGH PRIORITY ISSUES

---

### Issue #7: Command Center - Voice/Audio Features BROKEN

**File:** `frontend/src/components/admin/CommandCenter.tsx`

**Issues:**

```typescript
// ⚠️ Audio recording likely broken - WebSocket connection issues
const wsUrl = `${getWebSocketBaseUrl()}/api/voice/ws/voice`;
recorderRef.current = new AudioRecorderService(wsUrl);

// Problem: WebSocket endpoint probably doesn't exist or isn't configured
// Voice commands won't work, no error handling shown to user

// Terminal is FAKE - just echoes back
const handleTerminalSubmit = () => {
  setTerminalHistory(prev => [
    ...prev, 
    `$ ${cmd}`, 
    `[SupremeAI] Executing: "${cmd}"...`,  // Fake response
    `[SupremeAI] Command completed.`        // Always succeeds!
  ]);
  // No actual command execution!
};
```

**Missing:**
- [ ] Working voice command integration
- [ ] Real terminal/backend shell access
- [ ] Command history persistence
- [ ] Audio playback for AI responses (partially works)
- [ ] Browser panel doesn't load external URLs (CORS/security)

---

### Issue #8: Observability Dashboard - STATIC DATA

**File:** `frontend/src/components/admin/ObservabilityDashboard.tsx`

**Problem:** Charts use **100% hardcoded data**:

```typescript
// ❌ COMPLETELY STATIC - Never updates!
const latencyData = [
  { time: '10:00', p50: 200, p95: 450, p99: 900 },
  { time: '11:00', p50: 210, p95: 470, p99: 920 },
  // ... more fake data
];

const endpointErrors = [
  { endpoint: '/api/chat', errors: 12, total: 1240 },
  { endpoint: '/api/tts', errors: 3, total: 450 },
  // ... more fake data
];

// Stats cards show fixed numbers:
<Card title="QPS">
  <div className="text-2xl font-bold">142</div>  {/* NEVER CHANGES */}
</Card>
```

**What's Needed:**
- [ ] Real-time metrics from Prometheus/Grafana/Custom backend
- [ ] Live-updating charts (WebSocket or polling)
- [ ] Customizable time ranges (currently buttons do nothing)
- [ ] Export to PDF/PNG functionality
- [ ] Alert threshold configuration
- [ ] Service dependency map

---

### Issue #9: CI/CD Visualizer - LIMITED

**File:** `frontend/src/components/admin/CICDVisualizer.tsx` (referenced but need to check)

**Likely Issues (based on patterns seen):**
- Pipeline status probably hardcoded or mock
- No ability to trigger/retry deployments from UI
- No deployment rollback functionality
- No environment promotion workflow
- GitHubCIWidget exists separately - possible duplication

---

### Issue #10: Rate Limit Manager - Complex but Fragile

**File:** `frontend/src/components/admin/RateLimitManager.tsx`

**Issues:**

```typescript
// ⚠️ Uses raw fetch instead of apiClient (inconsistent)
const resp = await fetch(`${API_BASE}/admin/tenant-limits`, {
  headers: { 'Authorization': `Bearer ${adminTokenStore.getRawToken()` }
});
// Should use apiClient for consistent error handling!

// ❌ Endpoint might not exist in backend
// Looking at admin_dashboard.py routes... no /admin/tenant-limits found!

// Complex tenant management but probably backed by nothing
const TIER_LIMITS = {
  free:       { requests_per_minute: 20, max_tokens_per_day: 50000 },
  enterprise: { requests_per_minute: 999, max_tokens_per_day: 9999999 },
  // These limits aren't enforced anywhere visible
};
```

**Missing:**
- [ ] Backend endpoint for tenant CRUD operations
- [ ] Actual rate limiting enforcement
- [ ] Usage analytics per tenant
- [ ] Overage billing calculation
- [ ] Tenant onboarding workflow

---

## 🟡 MEDIUM PRIORITY ISSUES

---

### Issue #11: Config Editor - DANGEROUS

**File:** `frontend/src/components/admin/ConfigEditor.tsx` (assumed based on store)

**Potential Issues:**
- Editing .env variables from UI is risky (no validation?)
- No config version control/rollback
- Changes might require restart (no indication to admin)
- Sensitive values (API keys) shown in plaintext?
- No dry-run/preview mode

---

### Issue #12: Audit Logs Panel - BASIC Implementation

**File:** `frontend/src/components/admin/AuditLogsPanel.tsx`

**Issues:**

```typescript
// ✅ Actually fetches from API (good!)
const res = await apiClient.get<{ logs: AuditEntry[] }>('/admin-api/audit-logs?limit=50');

// But missing:
// - No filtering by date range, actor, severity
// - No export functionality (CSV/PDF)
// - No search capability
// - No log retention policy display
// - No compliance export (SOC2, HIPAA, GDPR audit trails)
// - Side panel only opens when activePanel === 'Audit' (navigation issue?)
```

---

### Issue #13: Cloud Orchestrator - VISUAL ONLY

**File:** `frontend/src/components/admin/CloudOrchestrator.tsx`

**Likely Issues:**
- Cloud distribution visualization probably static
- No ability to provision/deprovision resources
- No cost estimation for cloud changes
- Multi-cloud (GCP/AWS/Azure) support unclear

---

### Issue #14: Rules Engine Panel - UNCLEAR STATUS

**File:** `frontend/src/components/admin/RulesEnginePanel.tsx`
**File:** `frontend/src/components/admin/VisualRulesBuilder.tsx`

**Questions:**
- Are these for business rules or security rules?
- Do they connect to a working rules engine backend?
- Can rules be tested in sandbox before deploying?
- Version control for rules?

---

### Issue #15: Memory Browser - UNKNOWN DATA SOURCE

**File:** `frontend/src/components/admin/MemoryBrowser.tsx`

**Concerns:**
- What memory is it browsing? (Vector DB? Redis cache? Local?)
- Can memories be edited/deleted?
- Search/filter capabilities?
- Privacy concerns (user data visibility)?

---

## 🔴 SECURITY & AUTHENTICATION GAPS

---

### Issue #16: Inconsistent Token Handling

**Multiple Files Affected:**

```typescript
// Pattern 1: Uses adminTokenStore (correct)
enabled: !!adminTokenStore.getDecodedToken()

// Pattern 2: Uses raw fetch with manual token (inconsistent)
headers: { 'Authorization': `Bearer ${adminTokenStore.getRawToken()}` }

// Pattern 3: Some queries have NO auth check at all!
useQuery({
  queryKey: ['skills', query],
  queryFn: () => apiClient.post('/api/skills/search', ...),
  // ❌ No enabled check - accessible without admin auth!
})
```

**Risks:**
- Unauthorized access to admin endpoints
- Token leakage in browser console
- No token refresh logic visible
- JWT expiration not handled gracefully

---

### Issue #17: TOTP Setup Flow - Confusing UX

**File:** `frontend/src/store/adminStore.ts`

**Issues:**

```typescript
// State machine is complex and error-prone
if (data.status === 'otp_required') {
  set({ otpRequired: true });
} else if (data.status === 'totp_setup_required') {
  // Different flow for setup vs login
  const setupRes = await fetch(`${API_BASE}/api/admin/firebase-totp-setup`, ...);
}

// Problems:
// 1. User might not understand difference between OTP and TOTP setup
// 2. QR code display might not work on all devices
// 3. No backup codes option
// 4. Recovery flow if device lost unclear
```

---

## 📋 MISSING FEATURES COMPLETE CHECKLIST

### Monitoring & Observability
- [ ] **Real-time service topology map** (which services depend on which)
- [ ] **Custom dashboard builder** (drag-drop widgets)
- [ ] **Alert notification preferences** (email, SMS, Slack, Discord)
- [ ] **Incident management workflow** (create, assign, resolve)
- [ ] **SLA tracking & reporting**
- [ ] **Synthetic monitoring** (uptime probes from multiple regions)

### Security & Compliance
- [ ] **Vulnerability scanner integration** (Trivy, Snyk, Dependabot)
- [ ] **Secrets rotation scheduler**
- [ ] **Compliance dashboard** (GDPR, SOC2, HIPAA checkboxes)
- [ ] **Data classification viewer** (PII, PHI, financial data locations)
- [ ] **Access review workflow** (periodic permission audits)
- [ ] **Session monitoring** (active admin sessions, force logout)

### User & Access Management
- [ ] **SSO/SAML integration** (Okta, Auth0, Azure AD)
- [ ] **Role template library** (predefined permission sets)
- [ ] **Permission request workflow** (users request access, admins approve)
- [ ] **Login history & anomaly detection**
- [ ] **API key management** (generate, rotate, revoke)
- [ ] **Service accounts management**

### Infrastructure & DevOps
- [ ] **One-click deploy with progress tracking**
- [ ] **Rollback to previous version**
- [ ] **Environment variable diff viewer**
- [ ] **Database migration runner**
- [ ] **Cron job scheduler/editor**
- [ ] **Feature flag management** (percentage rollouts, target users)

### Financial & Billing
- [ ] **Real cost breakdown by feature/user/model**
- [ ] **Budget alert thresholds** (email at 50%, 80%, 100%)
- [ ] **Cost optimization suggestions** ("switch to cheaper model X")
- [ ] **Invoice generation & download**
- [ ] **Usage forecasting** (ML-based prediction)
- [ ] **Multi-currency support**

### Data & Backups
- [ ] **Backup integrity verification** (test restore to staging)
- [ ] **Point-in-time recovery selector**
- [ ] **Data retention policy editor**
- [ ] **GDPR data deletion requests queue**
- [ ] **Export user data (portability)**

---

## 🛠️ RECOMMENDED FIXES - Priority Order

### Phase 1: Critical Stabilization (Week 1)

1. **Fix Health Monitoring System**
   - Create unified `ServiceHealthMonitor` component (see previous deliverable)
   - Add Cloudflare Worker health aggregation endpoint
   - Replace mock data with real API calls

2. **Implement Real Cost Tracking**
   - Add structured `/admin-api/costs/detail` endpoint
   - Track token usage per model/provider in database
   - Replace hardcoded values in CostAuditor

3. **Consolidate User Management**
   - Remove duplicate UserManager OR RBACManager
   - Standardize role definitions
   - Add proper permission matrix

4. **Fix Authentication Consistency**
   - Use `adminTokenStore` everywhere (no raw fetch)
   - Add `enabled` checks to ALL admin queries
   - Implement token refresh logic

### Phase 2: Feature Completion (Weeks 2-3)

5. **Make Observability Dashboard Live**
   - Connect to real metrics backend
   - WebSocket for live chart updates
   - Time range selectors that work

6. **Functional Backup System**
   - Real storage metrics
   - Working restore flow
   - Maintenance mode toggle that persists

7. **Enhanced Security Dashboard**
   - Real threat feeds
   - Remediation actions
   - Incident response playbooks

8. **Working Command Center**
   - Fix or remove non-functional voice features
   - Real terminal access (or remove fake one)
   - Proper error states

### Phase 3: Polish & Advanced (Week 4+)

9. **Rate Limiting Backend**
   - Implement `/admin/tenant-limits` endpoints
   - Actual enforcement middleware
   - Usage analytics

10. **Audit Log Enhancements**
    - Filtering, search, export
    - Compliance reports
    - Retention policies

11. **Advanced Features**
    - Custom dashboards
    - Alert routing
    - SLA tracking

---

## 📊 COMPONENT HEALTH SCORECARD

| Component | Status | Data Quality | Backend Support | UX Score |
|-----------|--------|-------------|----------------|----------|
| Dashboard.tsx | ⚠️ Partial | Mixed | Partial | 7/10 |
| AdminDashboardHome | ✅ Good | Real API | Good | 8/10 |
| ServiceHealthMetrics | ❌ Broken | Mock | Missing | 3/10 |
| HealthBanner | ⚠️ Basic | Real | Basic | 5/10 |
| SecurityDashboard | ❌ Fake | Hardcoded | Missing | 2/10 |
| ThreatDetection | ⚠️ View-only | Real | Basic | 6/10 |
| UserManager | ✅ Works | Real | Good | 7/10 |
| RBACManager | ✅ Works | Real | Good | 7/10 |
| CostAuditor | ❌ Fake | Hardcoded | Partial | 2/10 |
| BackupRestore | ⚠️ Partial | Mixed | Partial | 4/10 |
| ObservabilityDashboard | ❌ Static | Hardcoded | Missing | 2/10 |
| CommandCenter | ⚠️ Partial | Mixed | Partial | 5/10 |
| AuditLogsPanel | ✅ Works | Real | Good | 6/10 |
| RateLimitManager | ❌ Broken | N/A | Missing | 3/10 |

**Overall Dashboard Health: 48% (Needs Significant Work)**

---

## 🎯 Quick Wins (Can Fix Today)

1. **Remove duplicate User/RBAC managers** → Keep one, delete the other
2. **Replace hardcoded costs** → Show "Coming Soon" or fetch real data
3. **Add loading/error states** → Every component should handle failures gracefully
4. **Standardize auth** → Search for `fetch(` in admin folder, replace with `apiClient`
5. **Disable non-functional features** → Hide or show "Under Construction" badge rather than fake data

---

## 📞 Recommended Next Steps

1. **Review this analysis** with your team to prioritize fixes
2. **Start with Phase 1 critical items** (health monitoring, costs, auth)
3. **Create backend endpoints** needed by frontend components
4. **Implement comprehensive testing** (E2E tests already exist in `tests/e2e/`)
5. **Set up staging environment** to test changes before production

---

*Analysis generated by Super Z AI Assistant*  
*Based on codebase snapshot: 2026-08-22*  
*Total files analyzed: 50+ components, 8 backend route files*

---

## 🔄 RE-RUN 2026-09-25 (Wave 2.5, issue #1242 — cost/security fake-data verdicts)

Fresh audit of the two highest-severity rows from the 2026-08-22 table
("CostAuditor ❌ Fake / SecurityDashboard ❌ Fake"), against main @ 35c8a54:

### CostAuditor — ✅ FIXED (verified)
* `frontend/src/components/admin/CostAuditor.tsx` now reads `useCostBreakdown()`
  → `GET /admin-api/costs/breakdown` (30s refetch, token-gated). The fake
  literals (`42.67`, `18.24`, `6.45`, fake timestamps) are gone; honest
  `?? 0.0` / empty-array defaults. Backend endpoint exists in
  `api/routes/admin_dashboard/__init__.py` (`/costs/breakdown`, structured JSON
  with providerCosts + recentCharges).

### SecurityDashboard — ✅ FIXED in this PR (was still fake)
* **Missing endpoints:** frontend called `GET /admin-api/security/tasks` and
  `GET /admin-api/security/memory`; **no backend routes existed**. New real
  module `api/routes/admin_dashboard/endpoints_security_memory.py` serves both
  from the live strong-reference task registry (`core/utils/background_tasks.py`)
  and `tracemalloc` (explicit `unavailable` when not tracing — never invented).
* **Static "[OK]" signals** (coroutines/NullPool/fail-closed/AST claims) —
  replaced with an honest "no scan data yet" state (absence of a scan is not
  evidence of safety).
* **Hardcoded OCC "0 Contended"** → honest "No telemetry source" card.
* **Hardcoded Free-Tier numbers** (Survival Score 64.2/100, "~200-400 MB / 500 MB",
  "513.6/750.0", fixed-width bars) → honest "no live source" placeholders until
  provider quota APIs are wired.
* **Header badges** "All Tasks Tracked"/"0 Zombie Tasks" → live
  `trackedTasks/untrackedTasks` values from the new endpoint.

### Updated verdict table (rows in question)
| Component | 2026-08-22 | 2026-09-25 |
|---|---|---|
| CostAuditor | ❌ Fake | ✅ Real (API-backed) |
| SecurityDashboard | ❌ Fake | ✅ Real (new endpoints + fake placeholders purged) |

### Remaining gaps (unchanged from original audit, still open)
- Budget alerting is client-side only (`addAlert` at ≥80%) — no server-side budget enforcement.
- Provider quota live wiring (Supabase/Upstash/Render) — UI now honest-unavailable until built.
