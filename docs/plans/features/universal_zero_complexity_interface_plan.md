---
target_scope: customer_facing
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto-universal_zero_complexity_interface_plan
subject: "SupremeAI: Universal Zero-Complexity Interface — Final Corrected Plan"
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI: Universal Zero-Complexity Interface — Final Corrected Plan
### All 14 corrections incorporated | Implementation-ready baseline

---

## Core Philosophy (6 Principles + 5 New)

### Original 6 Principles (Confirmed)
1. Customer dashboard — শুধু সে যা ব্যবহার করে তাই দেখায়
2. Progressive disclosure — "Add" করলে তবেই নতুন জিনিস দেখায়
3. Admin sees everything within their authorized scope
4. Default = safe, minimal, clean
5. Advanced settings → Settings page-এ, main dashboard-এ নয়
6. Same backend, different scoped views

### 5 New Principles (Added from review)
7. **Capability > Module** — User capability দেখে, module নয়
8. **Intent > Technical Configuration** — "আমি কী চাই" বলবে, "কীভাবে" বলবে না
9. **Authorization before Execution** — সব কাজের আগে verify
10. **Reuse before Creating** — নতুন file/module আগে existing search করো
11. **One simple UX, Modular Backend** — সহজ UI ≠ একটা বিশাল backend function

---

## Correction 1: One SPA, Two Experiences (Not Two Apps)

### ❌ আগের ভুল wording
> "2 Completely Separate Dashboards"
> App.tsx → CustomerDashboard / AdminDashboard separately

### ✅ সঠিক
```
ONE SPA
ONE Auth
ONE Identity
ONE Session
ONE Backend
ONE Capability Registry
ONE Control Plane
         │
         ├── Customer Experience  → CustomerDashboard component
         └── Admin Experience    → AdminControlPanel component
```

**Wording:**
> "Two role-specific experiences inside one unified application"

Current codebase-এ already unified frontend/route graph আছে। আলাদা architectural split করলে সেটাই undo হবে।

---

## Correction 2: Role Change ≠ Privilege Escalation

### ❌ আগের ভুল ধারণা
> User dashboard থেকে role change করতে পারবে

### ✅ সঠিক — Backend-Authoritative Context Selection

```
Identity (authenticated)
         ↓
Backend returns: Authorized Contexts for this user
         ↓
User selects from AVAILABLE contexts only
```

**User দেখবে:**
```
Your Access

● Personal Workspace       ← currently active
○ Team Workspace
○ Admin Workspace          ← only visible IF backend authorizes it
```

### Customer পারবে:
- ✅ Authorized workspace/context switch করতে
- ✅ Permitted execution mode switch করতে
- ✅ নিজের allowed capabilities enable/disable করতে

### Customer পারবে না:
- ❌ নিজেকে Admin বানাতে
- ❌ নিজে permission grant করতে
- ❌ অন্য tenant access করতে
- ❌ অন্য user-এর role modify করতে

### Admin পারবে:
- ✅ অন্য user-এর role/context change করতে
- ✅ Tenant access policy change করতে
- ✅ Execution mode per-user control করতে

---

## Correction 3: Admin Sees Everything — Within Their Scope

### ❌ আগের অতি-broad statement
> "Admin-এর কাছে কিছু hidden নয়। সব visible।"

### ✅ সঠিক — Scoped Admin Visibility

```
Super Admin        → All tenants, all users, all capabilities
Tenant Admin       → Only their assigned tenant(s)
Workspace Admin    → Only their assigned workspace
```

"Admin dashboard = unrestricted access" would be a security design flaw।

---

## Correction 4: Universal UX + Modular Backend Connection Engine

### ❌ আগের ভুল
```
POST /api/v1/connections/add  ← সব business logic এখানে
```

### ✅ সঠিক — UI সহজ, Backend Modular

**UI (Customer দেখবে):**
```
[ Paste URL or describe what you need ]
[ Connect ]
```

**Backend (Customer দেখবে না):**
```
Universal Add Intent
         ↓
Connection Engine (router)
         ↓
Provider / Protocol Detector
   ├── MCP → MCPAdapter
   ├── OAuth → OAuthAdapter
   ├── REST → RESTAdapter
   ├── GitHub → GitHubAdapter
   └── ...
         ↓
Canonical ConnectionContract
         ↓
Validation → Health Check → Capability Discovery
         ↓
Capability Registry
```

**Endpoints (modular):**
```
POST /api/v1/connections/detect   ← type detect করো
POST /api/v1/connections/mcp/register
POST /api/v1/connections/oauth/initiate
POST /api/v1/connections/credential/save
```
Simple UI, modular backend। এগুলো internal — customer `/connections/add` UI দেখে।

---

## Correction 5: Capability-Focused Customer UX

### Critical Architectural Distinction

```
Connection = HOW we reach something
Capability = WHAT the user can DO with it
```

**Example:**
```
GitHub Connection
       ↓
 ┌──────────────────┐
 │  Capabilities    │
 ├──────────────────┤
 │ Read repository  │
 │ Search code      │
 │ Create issue     │
 │ Review PR        │
 └──────────────────┘

MCP Server
    ↓
20 discovered tools
    ↓
12 safe capabilities
    ↓
5 available to this user
```

**Customer Dashboard-এ দেখায়: Capabilities**
```
Research        🟢 Ready    [Use]
Web Access      🟢 Ready    [Use]
Code Review     🟢 Ready    [Use]
```

**Admin Dashboard-এ দেখায়:**
```
Connections + Capabilities + Providers + Protocols + Health + Policies
```

---

## Correction 6: Intent-First Add Wizard (Not Category Selection)

### ❌ আগের approach (Category-heavy)
```
🤖 Connect an AI
🌐 Enable web browsing
📁 File & storage access
⚡ Create automation
```

### ✅ সঠিক — Intent First, Structure Second

```
What do you want to add?

[ Tell us what you need...                     ]

Examples:
• "I want to connect my GitHub"
• "I need access to my Google Drive"
• "I want to add a custom AI tool"
• "I want to automate my daily report"

─────── or ───────

Common options:
[ Connect a service ]  [ Create automation ]  [ Add a tool ]
```

**Backend:** Intent parse করে → correct connection type detect করে → right form দেখায়।

User category জানতে হয় না।

---

## Correction 7: API Keys Are Advanced, Not Default

### ❌ আগের wording
> "URL, OAuth, or API key দিয়ে"

### ✅ সঠিক — Normal Path vs Advanced

**Normal path (customer দেখে):**
```
[ Paste URL or search for a service ]
[ Connect ]
↓
Auto-detection → OAuth / Secure flow
```

**Advanced (শুধু দরকার হলে):**
```
[ Advanced / Manual setup ]
  → API Key input
```

**Security rule:** API keys কখনো frontend state/localStorage-এ stored হবে না। Backend secret broker-এ যাবে।

---

## Correction 8: Reuse-First File Creation Strategy

### ❌ আগের ভুল — সরাসরি অনেক নতুন file list

### ✅ সঠিক — Before creating any file:

```
New file needed?
       ↓
Search existing capability
       ↓
Can existing component/service do it?
   ├── YES → extend/reuse
   └── NO  → create new
```

**Existing components যা check করতে হবে আগে:**
- `frontend/src/components/customer/UserDashboard.tsx` — enhance করা যায়?
- `frontend/src/pages/user/IntegrationsManager.tsx` — reuse/refactor করা যায়?
- `frontend/src/components/plugins/MCPConnector.tsx` — extend করা যায়?
- `backend/adaptive_engine/capability_registry.py` — already solid
- `infrastructure/mcp-control-plane/src/` — already has adapters, registry, policy

---

## Correction 9: Universal Manage Model

প্রতিটি item (capability, connection, automation) same interaction pattern follow করবে:

```
GitHub                    ← name
🟢 Ready                  ← status (human-readable)

[Use]  [Manage]

─── Manage expands to ───

Status:    Connected · Healthy
Last used: 2 hours ago
Capabilities: 4 active

[Configure]  [Pause]  [Remove]
```

**Same model for everything:**
```
Research AI      🟢 Ready     [Use] [Manage]
Daily Report     🟢 Active    [Run] [Manage]
Web Browser      🟡 Idle      [Use] [Manage]
GitHub           🟢 Ready     [Use] [Manage]
```

---

## Correction 10: "Explain Why" — Human-Readable Errors

### Customer দেখবে:
```
This feature isn't available yet.

Why:
Your workspace doesn't have access to this capability.

[Request Access]  [Learn more]

─── Advanced details (collapsed) ───
```

### Admin দেখবে:
```
Why unavailable?

Capability disabled for this workspace.
Required permission: capability:browser:use
Policy: tenant_default_safe

[Enable for workspace]  [Edit policy]

─── Technical details ───
Error: RBAC_CAPABILITY_DISABLED | tenant: t-123
```

---

## Correction 11: Capability Policy Layer — Correct Execution Flow

### ✅ Correct Universal Pipeline

```
USER INTENT
       ↓
CAPABILITY DISCOVERY
       ↓
CAPABILITY REGISTRY
       ↓
AUTHORIZATION
       ↓
POLICY ENGINE
       ↓
MCP CONTROL PLANE
       ↓
GOVERNED EXECUTOR
       ↓
AUDIT / MEMORY / OBSERVABILITY
       ↓
RESULT → USER (human-readable)
```

**NOT:**
```
User → Connection → Tool (shortcut — too shallow)
```

This pipeline answers: **"Can this user do X?"** BEFORE **"Which tool does X?"**

---

## System Architecture Diagram

```
                         SUPREMEAI
                             │
              ┌──────────────▼──────────────┐
              │          USER INTENT         │
              │   (natural language or click) │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      CAPABILITY DISCOVERY    │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      CAPABILITY REGISTRY     │
              │  (backend/adaptive_engine/)  │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │   AUTHORIZATION + POLICY    │
              │   (tenant-scoped RBAC)      │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      MCP CONTROL PLANE       │
              │   (infrastructure/src/)      │
              └──────────────┬──────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
   MCP / Tools           Services             Agents
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │      GOVERNED EXECUTOR       │
              └──────────────┬──────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  AUDIT / MEMORY / OBSERVE    │
              └──────────────┬──────────────┘
                             │
                    RESULT (human-readable)
```

**Customer দেখে (top surface only):**
```
┌─────────────────────────────────────┐
│ What do you need?                   │
│ [_______________________________] →  │
│                                     │
│ Research      🟢 Ready     [Use]    │
│ Web Access    🟢 Ready     [Use]    │
│ GitHub        🟢 Ready     [Use]    │
│                                     │
│ [+ Add something]                   │
└─────────────────────────────────────┘
```

---

## Corrected File Creation Plan

### Reuse-first check before any new file:

| Before creating... | Check first... |
|---|---|
| `AddNewWizard.tsx` | `IntegrationsManager.tsx` refactor করা যায়? |
| `CapabilityMatrix.tsx` | `SkillCatalog.tsx` extend করা যায়? |
| `AdminControlPanel` | `pages/admin/AdminShell.tsx` enhance করা যায়? |
| Connection Engine | `mcp-control-plane/src/` existing adapters reuse? |

### Likely New (after reuse-check):
| File | Why new |
|---|---|
| `frontend/src/types/contracts/` (4 files) | Type contracts — no equivalent exists |
| `frontend/src/components/customer/AddNewWizard.tsx` | Intent-first flow — existing wizards are category-based |
| `frontend/src/components/common/ManageItem.tsx` | Universal manage model — no reusable equivalent |
| `frontend/src/components/common/CapabilityUnavailableExplainer.tsx` | "Explain why" — no equivalent |
| `backend/api/v1/connections/detect.py` | Protocol detection — new capability |
| `backend/api/v1/access/set_mode.py` | Execution mode — new capability |

### Likely Modify (not replace):
| File | Change |
|---|---|
| `UserDashboard.tsx` | State-based rendering: show only what user HAS |
| `IntegrationsManager.tsx` | Simplified + intent-first Add flow |
| `governed_executor.py` | HITL + policy + audit wired in |
| `App.tsx` | Context-aware routing, no architectural split |

---

## Complete Acid Tests (13)

### Customer Tests
```
Test 1: New user → Dashboard open
Expected: Intent input + simple "get started" → NO MCP, NO GitHub visible

Test 2: User with only Research AI
Expected: Only Research AI shown. Nothing else.

Test 3: User wants to add something
Expected: Intent-first wizard → describe need → system detects type → Done

Test 4: User switches workspace context
Expected: Backend authorizes → allowed contexts shown → user selects → capabilities update

Test 5: User tries to get Admin access
Expected: Backend rejects → "This access level isn't available to you" (human-readable)

Test 6: Capability unavailable
Expected: "Why?" → human-readable reason → [Request Access] option
```

### Admin Tests
```
Test 7: Tenant Admin → see another tenant's data
Expected: Rejected — only authorized tenant visible

Test 8: Super Admin → sees all tenants
Expected: Full visibility within system scope

Test 9: Admin enables capability system-wide
Expected: Toggle → backend policy update → all affected users see it
```

### Architecture Tests
```
Test 10: One URL MCP connect
Expected: URL → Detect → Validate → Discover → Health → Register → Show capabilities (no protocol config by user)

Test 11: Same capability, different connection
Expected: User asks "web research" → System finds authorized capability →
User doesn't care if it's Browser, MCP, or internal service

Test 12: Feature request → reuse check
Expected: New feature request → existing capability searched → if found, reused → no duplicate module created

Test 13: Connection failure explanation
Expected: Human-readable error + retry option + technical details collapsed
```

---

## 6 Major Changes Summary

| Previous Plan | Corrected Plan |
|---|---|
| Two completely separate dashboards | **Two experiences inside one SPA** |
| User can change role | **User switches only authorized context (backend-authoritative)** |
| Admin sees everything | **Admin sees everything within authorized scope** |
| Universal `/connections/add` | **Universal UX + modular backend Connection Engine** |
| Connection-focused customer UX | **Capability-focused customer UX** |
| Many new files immediately | **Reuse-first; create only when no existing capability** |

---

## Status: Ready for Implementation

This corrected plan is the implementation baseline.

**Next step after approval:**
1. Reuse-check against existing codebase
2. Phase 0: Type contracts
3. Phase 1: Backend endpoints (modular)
4. Phase 2: UserDashboard state-based rendering
5. Phase 3: AddNewWizard (intent-first)
6. Phase 4: Universal Manage model
7. Phase 5: Admin scoped view
8. Phase 6: Acid tests