---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:single_frontend_role_based_auth_migration_roadmap
subject: SupremeAI — Single Frontend Role-Based Migration Roadmap
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI — Single Frontend Role-Based Migration Roadmap

**Version:** 1.0.0  
**Status:** Implementation Roadmap  
**Target:** One frontend application/build for User + Admin  
**Source of truth:** Current `main` codebase and `docs/ui-ux/SUPREME_UI_DASHBOARD_MASTER.md`

---

## 1. Objective

Move SupremeAI from the current partially split User/Admin frontend architecture to:

> **One frontend build → one shared application shell → one canonical identity/session → runtime role-based experiences → backend-enforced authorization.**

The goal is **not** to merge every User/Admin component into one giant module. The goal is to eliminate duplicated application infrastructure while preserving clean separation of role-specific business functionality.

### Target

```text
                    SUPREMEAI FRONTEND
                         ONE BUILD
                            │
                     Canonical Auth
                            │
              ┌─────────────┴─────────────┐
              │                           │
         USER CONTEXT                ADMIN CONTEXT
              │                           │
         /workspace                    /admin/*
              │                           │
              └─────────────┬─────────────┘
                            │
                    UNIFIED APP SHELL
                            │
             Header / Navigation / Command
             Theme / Notifications / Status
                            │
                  Role + Permission Guards
                            │
                    Shared API Client
                            │
                   SupremeAI Backend
                            │
                  Backend RBAC / Policy
```

---

# 2. Current-State Findings

The current codebase already contains important pieces of the target architecture.

## 2.1 `App.tsx`

Current `frontend/src/App.tsx` already has:

- React Router
- shared providers
- global error boundary
- `ProtectedRoute` / `GuestRoute`
- lazy-loaded heavy User/Admin pages
- `/admin/*`
- `/workspace/*`
- global `CommandBar`

However, it still contains:

```ts
const PORTAL_TYPE = import.meta.env.VITE_PORTAL_TYPE || 'user';
```

and uses this value to branch the complete route tree.

### Decision

**P0:** remove build-time portal identity.

The same frontend must contain both User and Admin route definitions.

---

## 2.2 `WorkspaceLayout`

Current `WorkspaceLayout` contains:

- UserSidebar
- grouped navigation
- collapsible sidebar
- DashboardLayout
- Dynamic Action Dock
- HITL modal
- drag/drop context

This is useful infrastructure and should be **refactored**, not discarded.

### Decision

Promote the structural parts into the shared application shell while keeping User-specific navigation data separate.

---

## 2.3 `DashboardLayout`

Current `DashboardLayout` already provides:

- full-screen shell
- optional header
- animated collapsible sidebar
- main content viewport

### Decision

Use it as the low-level foundation for the unified shell.

Do not introduce a second competing layout framework.

---

## 2.4 Admin Architecture

Current Admin architecture includes:

- `AdminShell`
- `AdminConsole`
- admin authentication state
- admin role state
- OTP/TOTP flow
- admin-specific operational state

### Decision

Preserve required admin security, but converge identity/session ownership with the canonical authentication system.

Do **not** weaken OTP/TOTP or privileged-operation protection simply to simplify architecture.

---

## 2.5 Authentication

`AuthGuards.tsx` already provides a reusable authenticated/guest guard.

### Decision

Extend this architecture with:

```text
ProtectedRoute
      ↓
RoleGuard
      ↓
PermissionGuard
      ↓
Optional StepUpGuard
      ↓
Page
```

The backend remains the real authorization boundary.

---

# 3. Non-Negotiable Architecture Rules

1. One frontend application.
2. One production frontend build.
3. No `VITE_PORTAL_TYPE` controlling application identity.
4. One canonical identity/session authority.
5. User and Admin remain separate runtime contexts.
6. Backend authorization is authoritative.
7. Admin step-up security remains intact.
8. No duplicate global shells.
9. No duplicate command bars.
10. No duplicate notification systems.
11. No duplicate authentication authorities for the same identity.
12. Role-specific modules may remain separate.
13. Heavy modules remain lazy-loaded.
14. Unauthorized UI must not be presented as available functionality.
15. Frontend role state must never grant privileges.
16. Existing functionality must be preserved unless explicitly deprecated.
17. New components must reuse existing infrastructure whenever possible.
18. Do not reduce source-file count artificially; reduce runtime duplication and unclear ownership.
19. No portal-specific deployment just because the role differs.
20. Every migration step must be testable and reversible.

---

# 4. Roadmap Overview

| Phase | Objective | Priority | Exit Condition |
|---|---|---:|---|
| 0 | Inventory & freeze duplication | P0 | Ownership map complete |
| 1 | Remove portal split | P0 | One route graph/build |
| 2 | Unify identity/session | P0 | One canonical auth authority |
| 3 | Build unified shell | P0 | User/Admin share shell |
| 4 | Add role/permission guards | P0 | RBAC route contract tested |
| 5 | Integrate Admin into shell | P1 | `/admin/*` uses shared shell |
| 6 | Consolidate navigation | P1 | One navigation registry |
| 7 | Preserve lazy loading/performance | P1 | Bundle/performance budget passes |
| 8 | Testing & security hardening | P0/P1 | Full User/Admin matrix passes |
| 9 | Remove legacy split infrastructure | P2 | Old split architecture removed |
| 10 | Production rollout & observation | P0 | Stable production validation |

---

# 5. Phase 0 — Inventory & Freeze Duplication

**Priority:** P0  
**Goal:** Understand the existing frontend before changing architecture.

## Tasks

### 5.1 Entry points

Inventory:

- `main.tsx`
- `App.tsx`
- Vite configuration
- build scripts
- Firebase deployment configuration
- frontend Docker/deployment configuration
- CI frontend jobs
- environment variables

### 5.2 Authentication inventory

Map:

- `authStore`
- `adminStore`
- Firebase auth
- backend auth
- token handling
- OTP/TOTP
- login/logout flows
- session persistence
- role resolution

### 5.3 UI infrastructure inventory

Map:

- layouts
- headers
- sidebars
- command bars
- notification systems
- theme providers
- error boundaries
- loading states
- modal systems
- toast systems

### 5.4 Role inventory

Create a matrix:

| Feature | User | Admin | Shared | Backend Permission |
|---|---:|---:|---:|---|
| Workspace | ✓ | ✓/optional | — | workspace.read |
| Admin Console | — | ✓ | — | admin.* |
| Profile | ✓ | ✓ | ✓ | profile.read |
| Settings | ✓ | ✓ | ✓ | settings.* |
| System Health | — | ✓ | — | system.health |
| Billing | ✓ | ✓/oversight | — | billing.* |
| Deploy | — | ✓ | — | deployment.trigger |

Do not assume permissions from frontend visibility.

### Exit Criteria

- [ ] Full frontend entry-point inventory.
- [ ] Auth ownership documented.
- [ ] Admin/user state ownership documented.
- [ ] Duplicate infrastructure identified.
- [ ] No new shell/auth infrastructure created during inventory.

---

# 6. Phase 1 — Remove Portal Split

**Priority:** P0

## Current problem

```text
VITE_PORTAL_TYPE=admin
        ↓
Admin-only route tree

VITE_PORTAL_TYPE=user
        ↓
User route tree
```

This creates two logical frontend products inside one repository.

## Target

```text
ONE BUILD
   ↓
ONE ROUTE GRAPH
   ↓
Runtime authentication + role
   ↓
User/Admin experience
```

## Tasks

### 6.1 Remove

Remove `VITE_PORTAL_TYPE` from application identity decisions.

### 6.2 Keep one route graph

Both must exist in the same build:

```text
/login
/register
/workspace/*
/projects/*
/agents/*
/integrations/*
/settings/*
/profile
/admin/*
```

### 6.3 Default landing

Use runtime state:

```text
Guest
  → /login

Authenticated User
  → /workspace

Authenticated Admin
  → configured admin/user landing context
```

Do not use environment variables to decide role.

### 6.4 Preserve deep links

Examples:

```text
/admin/overview
/admin/security
/workspace/agent
/workspace/ide
```

must survive refresh and direct navigation.

### Exit Criteria

- [ ] `VITE_PORTAL_TYPE` no longer controls routing.
- [ ] One production build contains User + Admin routes.
- [ ] User deep links work.
- [ ] Admin deep links work.
- [ ] No portal-specific build artifact exists.

---

# 7. Phase 2 — Unify Identity & Session Authority

**Priority:** P0

## Target model

```text
Canonical Auth
├── identity
├── session
├── authStatus
├── role
├── permissions
└── adminStepUp
```

## Tasks

### 7.1 Canonical identity

Use the existing authentication authority as the source for:

- user identity
- session
- authenticated status

### 7.2 Role

Role should be resolved from trusted authenticated/backend state.

Never trust the following for authorization:

```text
localStorage.role
URL role
UI pill state
client-only admin flag
```

### 7.3 Admin step-up

Represent Admin verification as:

```text
Authenticated
    ↓
Admin role
    ↓
Step-up required?
    ├── no → Admin
    └── yes
          ↓
      OTP/TOTP
          ↓
       Admin
```

### 7.4 Admin store

Refactor `adminStore` carefully.

It may retain **admin-specific UI state**, such as:

- admin filters
- admin tab
- operational action status

but should not become a second independent identity/session authority.

### Exit Criteria

- [ ] One canonical identity.
- [ ] One canonical session.
- [ ] Role resolved from trusted state.
- [ ] Admin step-up preserved.
- [ ] Logout clears relevant contextual state.
- [ ] No client-only role elevation path.

---

# 8. Phase 3 — Build Unified Application Shell

**Priority:** P0

## Target component structure

```text
UnifiedAppShell
├── GlobalHeader
│   ├── Brand
│   ├── CommandBar trigger
│   ├── Role Context
│   ├── Notifications
│   └── Profile
│
├── RoleAwareNavRail
│
└── MainViewport
    ├── Breadcrumb
    ├── PageHeader
    └── Route Content
```

## Tasks

### 8.1 Reuse

Use:

- `DashboardLayout`
- existing `WorkspaceLayout` infrastructure
- existing `CommandBar`
- existing theme system
- existing error boundary

### 8.2 Create only missing shared primitives

Potential components:

```text
UnifiedAppShell
GlobalHeader
RoleAwareNavRail
RoleContext
PermissionContext
GlobalStatus
```

### 8.3 Shared header

Header must be structurally identical across User/Admin.

Only contextual content changes.

### 8.4 Shared sidebar

Sidebar content is role-aware.

Do not create two complete application shells.

### Exit Criteria

- [ ] One shared shell exists.
- [ ] User renders inside it.
- [ ] Admin renders inside it.
- [ ] Header structure is shared.
- [ ] Sidebar structure is shared.
- [ ] Existing command bar still works.
- [ ] Existing theme behavior works.

---

# 9. Phase 4 — Role & Permission Guards

**Priority:** P0

## Route model

Introduce route metadata where practical:

```ts
{
  path: '/admin/resources',
  requiredRole: 'admin',
  requiredPermission: 'resource.read',
  requiresStepUp: true
}
```

## Guard hierarchy

```text
GuestRoute
   ↓
ProtectedRoute
   ↓
RoleGuard
   ↓
PermissionGuard
   ↓
StepUpGuard
   ↓
Page
```

## Security tests

### Normal User

```text
/workspace       → allowed
/admin           → denied
/admin/security  → denied
/admin/deploy    → denied
```

### Admin

```text
/workspace       → allowed
/admin           → allowed
/admin/security  → allowed after required step-up
```

### Critical rule

Frontend guards improve UX. They do **not** replace backend authorization.

### Exit Criteria

- [ ] Route-level role checks.
- [ ] Permission checks.
- [ ] Admin step-up checks.
- [ ] Backend authorization remains active.
- [ ] URL manipulation cannot elevate privileges.
- [ ] Local state manipulation cannot elevate privileges.

---

# 10. Phase 5 — Integrate Admin Console Into Shared Shell

**Priority:** P1

Current:

```text
AdminShell
   ↓
AdminConsole
```

Target:

```text
UnifiedAppShell
   ↓
RoleAwareNavRail
   ↓
/admin/*
   ↓
Admin page modules
```

## Tasks

- Preserve AdminConsole business functionality.
- Move shell responsibility upward.
- Reuse shared PageHeader.
- Reuse shared StatCard.
- Reuse shared tables/dialogs.
- Reuse global notifications.
- Preserve Admin error isolation.
- Preserve admin login/step-up UX.

Admin-specific business components may remain independent.

### Exit Criteria

- [ ] Admin uses shared shell.
- [ ] Admin functionality preserved.
- [ ] No duplicate global header.
- [ ] No duplicate global navigation framework.
- [ ] Admin-specific business components remain modular.

---

# 11. Phase 6 — Consolidate Navigation

**Priority:** P1

Create one navigation registry.

```text
NAVIGATION_REGISTRY
├── public
├── authenticated
├── shared
├── user
└── admin
```

Each item should support:

- path
- label
- icon
- required role
- required permission
- feature flag
- availability
- badge
- priority

## Audit current navigation targets

Current user navigation contains targets such as:

```text
/projects
/activity
/marketplace
/runs
/usage
/settings
```

Every target must be verified against the actual route registry.

Classify missing targets as:

```text
Implemented
Planned
Deprecated
Broken
```

Do not silently leave dead navigation.

### Exit Criteria

- [ ] One navigation registry.
- [ ] User navigation generated from it.
- [ ] Admin navigation generated from it.
- [ ] Shared navigation generated from it.
- [ ] No duplicate navigation definitions.
- [ ] Every visible target is valid.

---

# 12. Phase 7 — Performance & Bundle Strategy

**Priority:** P1

Single frontend does **not** mean single giant bundle.

Continue route-level lazy loading.

## Target

```text
Initial bundle
├── Auth
├── Shell
├── Routing
├── Core UI
└── minimal shared state

Lazy modules
├── Admin
├── Agent Workspace
├── IDE
├── Swarm
├── Evolution Forge
└── other heavy capabilities
```

## Rules

- Admin-heavy code must not be eagerly loaded for normal users.
- Browser-heavy libraries must not enter root bundle unnecessarily.
- AI-heavy modules must remain lazy.
- Measure bundle size before/after migration.
- Do not create duplicate dependencies for User/Admin.

### Exit Criteria

- [ ] Build succeeds.
- [ ] Bundle size has an explicit budget.
- [ ] Admin code remains lazy.
- [ ] Heavy user modules remain lazy.
- [ ] No unnecessary root-level heavy imports.

---

# 13. Phase 8 — Testing & Security Hardening

**Priority:** P0/P1

## Build tests

```text
One build
One artifact
User + Admin route graph
```

Test that no portal-specific build is generated.

## Authentication matrix

| Scenario | Expected |
|---|---|
| Guest → `/workspace` | Login |
| Guest → `/admin` | Login |
| User → `/workspace` | Allow |
| User → `/admin` | Deny |
| Admin → `/workspace` | Allow |
| Admin → `/admin` | Allow |
| Admin without step-up → sensitive page | Step-up |
| Logout | Session/context cleared |

## Security matrix

Attempt:

```text
Change URL
Change localStorage
Change client role
Modify route state
Replay stale UI state
Directly call admin API
```

Expected:

```text
No privilege escalation
```

## UX matrix

Verify:

- desktop
- tablet
- mobile
- collapsed sidebar
- expanded sidebar
- direct URL
- browser refresh
- back/forward navigation
- role switch
- logout/login
- expired session

## Regression matrix

### User

- Workspace
- AI Studio
- Agent
- IDE
- Skills
- Integrations
- Swarm
- Evolution Forge
- Billing
- Profile

### Admin

- Overview
- Health
- Skills
- Checkpoints
- Cost
- Rules
- Deployment
- User administration
- Security
- operational controls

### Exit Criteria

- [ ] Full auth matrix passes.
- [ ] Full RBAC matrix passes.
- [ ] User regression passes.
- [ ] Admin regression passes.
- [ ] Security escalation tests pass.
- [ ] Responsive tests pass.

---

# 14. Phase 9 — Remove Legacy Split Infrastructure

**Priority:** P2

Only begin after production validation.

Remove:

- obsolete portal-specific build scripts
- obsolete portal-specific deployment config
- duplicate shell implementations
- duplicate global auth infrastructure
- obsolete documentation
- unused environment variables
- dead role-switch logic

## CI protection

Add a CI rule that fails if future code reintroduces:

```text
VITE_PORTAL_TYPE
portal-specific production builds
duplicate shell registration
duplicate global navigation
duplicate auth authority
```

### Exit Criteria

- [ ] Legacy split infrastructure removed.
- [ ] CI prevents regression.
- [ ] Documentation updated.
- [ ] No orphaned deployment target remains.

---

# 15. Phase 10 — Production Rollout

**Priority:** P0

Do not cut over everything simultaneously.

## Stage 1 — Internal validation

Validate:

```text
Guest
User
Admin
Admin step-up
Role switching
Deep links
Refresh
Logout
```

## Stage 2 — Admin validation

Test:

- system operations
- deployment controls
- health
- security
- user administration
- evolution controls

## Stage 3 — User validation

Test:

- workspace
- AI Studio
- agents
- IDE
- integrations
- skills
- billing
- profile

## Stage 4 — Production

Monitor:

- frontend errors
- API 401/403 rates
- route failures
- bundle loading failures
- authentication failures
- Admin authorization failures
- backend API latency
- memory/network impact

Keep the previous frontend artifact available until the new architecture has passed the observation window.

---

# 16. Role Switching Specification

Role switching is optional and only appears when the authenticated identity is authorized for multiple contexts.

## User without admin

```text
[ User ]
```

No Admin option.

## Admin

```text
[ Admin ▼ ]

Admin Console
User Workspace
```

## Switching process

```text
Click role
   ↓
Check authorized context
   ↓
Update runtime context
   ↓
Navigate
   ↓
Rebuild role-aware navigation
   ↓
Load required lazy module
```

Never implement:

```text
click Admin
   ↓
set role='admin'
   ↓
gain privilege
```

---

# 17. State Ownership Policy

## Global state

Only truly global state:

```text
auth
session
role/context
theme
locale
notifications
server connectivity
feature flags
```

## User state

```text
workspace
projects
chat
agent interaction
user preferences
```

## Admin state

```text
system filters
deployment status
admin investigations
operational dashboards
admin-specific UI state
```

**Unified architecture ≠ unified everything.**

---

# 18. File/Module Ownership Target

Recommended conceptual ownership:

```text
frontend/src/
│
├── app/
│   ├── App.tsx
│   ├── routes/
│   └── routeRegistry/
│
├── auth/
│   ├── authStore
│   ├── role
│   ├── permissions
│   └── guards
│
├── components/
│   ├── shell/
│   │   ├── UnifiedAppShell
│   │   ├── GlobalHeader
│   │   └── RoleAwareNavRail
│   │
│   ├── ui/
│   ├── core/
│   └── shared/
│
├── pages/
│   ├── user/
│   ├── admin/
│   └── shared/
│
├── stores/
│   ├── auth
│   ├── user
│   └── admin
│
└── services/
    ├── api
    ├── auth
    └── ...
```

This is a target ownership model, not a requirement to rename everything immediately.

---

# 19. CI/CD Acceptance Gates

## Gate A — Single frontend

Fail if:

```text
VITE_PORTAL_TYPE
admin-only production build
user-only production build
```

is detected.

## Gate B — RBAC

Automated tests must verify:

```text
User cannot access Admin
Admin can access Admin
Admin can access User
```

## Gate C — Security

Fail on client-only admin authorization.

## Gate D — Navigation

Detect:

- duplicate route definitions
- duplicate navigation IDs
- invalid navigation targets
- unauthorized navigation exposure

## Gate E — Bundle

Track:

```text
initial JS
initial CSS
largest chunks
Admin chunk
User heavy chunks
```

against defined budgets.

---

# 20. Definition of Done

The migration is complete only when:

### Architecture

- [ ] One frontend application.
- [ ] One production frontend build.
- [ ] One route graph.
- [ ] No portal-type build branching.
- [ ] One shared application shell.

### Authentication

- [ ] One canonical identity.
- [ ] One canonical session.
- [ ] Runtime role resolution.
- [ ] Admin step-up preserved.
- [ ] No client-side privilege escalation.

### UI

- [ ] Shared header.
- [ ] Shared navigation framework.
- [ ] Shared command bar.
- [ ] Shared theme infrastructure.
- [ ] Shared notification/status infrastructure.
- [ ] Role-aware navigation.

### Routing

- [ ] User routes work.
- [ ] Admin routes work.
- [ ] Deep links work.
- [ ] Refresh works.
- [ ] Role guards work.
- [ ] Permission guards work.

### Performance

- [ ] Heavy modules lazy-loaded.
- [ ] Admin bundle not eagerly loaded for users.
- [ ] User heavy modules not eagerly loaded unnecessarily for admins.
- [ ] Bundle budget passes.

### Security

- [ ] URL manipulation cannot elevate role.
- [ ] localStorage manipulation cannot elevate role.
- [ ] UI role switching cannot elevate role.
- [ ] Backend RBAC remains authoritative.
- [ ] Sensitive Admin actions retain step-up requirements.

### Operations

- [ ] CI validates single-build architecture.
- [ ] CI validates RBAC.
- [ ] Production smoke tests cover User + Admin.
- [ ] Previous deployment remains rollback-capable during rollout.
- [ ] Legacy split infrastructure removed only after validation.

---

# 21. Recommended Commit Sequence

Do **not** implement all phases in one large change.

```text
Commit 1
docs: inventory current frontend architecture

Commit 2
refactor(auth): establish canonical role/session contract

Commit 3
refactor(routes): remove portal-type route branching

Commit 4
feat(shell): introduce unified application shell

Commit 5
feat(rbac): add role and permission guards

Commit 6
refactor(admin): render admin experience inside shared shell

Commit 7
refactor(nav): consolidate role-aware navigation registry

Commit 8
test(frontend): add user/admin authentication and RBAC matrix

Commit 9
perf(frontend): validate lazy loading and bundle budgets

Commit 10
ci(frontend): prevent portal-split regression

Commit 11
chore(frontend): remove obsolete split infrastructure
```

Each commit should be independently reviewable and preferably independently testable.

---

# 22. Rollback Strategy

At every phase:

```text
Current stable frontend
        │
        ├── migration change
        │
        └── validation
             │
        ┌────┴────┐
        │         │
      PASS      FAIL
        │         │
     continue   rollback
```

Do not remove old authentication or deployment infrastructure until the replacement has been validated.

---

# 23. Future AI Agent Instructions

Any AI agent modifying SupremeAI frontend must follow:

1. Read this roadmap before changing frontend architecture.
2. Inspect existing components before creating new ones.
3. Never reintroduce `VITE_PORTAL_TYPE`.
4. Never create a second frontend for Admin.
5. Never create a second frontend for User.
6. Never create a second authentication authority without explicit architectural approval.
7. Never use frontend role state as authorization.
8. Preserve backend RBAC.
9. Preserve Admin OTP/TOTP/step-up security.
10. Prefer shared shell + role-specific pages.
11. Prefer lazy loading over separate builds.
12. Keep role-specific business logic modular.
13. Do not merge modules merely to reduce file count.
14. Add tests for every routing/auth architecture change.
15. Do not remove legacy infrastructure until replacement validation passes.
16. Record architectural regressions in the project's tracking documents.
17. Never claim the migration is complete based only on a successful frontend build.
18. Validate real User and Admin journeys.

---

# 24. Final Architecture Principle

> **One SupremeAI frontend. One shared shell. One canonical identity. Multiple authorized experiences.**

The application should feel like one coherent product while still giving each role the correct capabilities:

```text
ONE PRODUCT
   │
   ├── User Experience
   │      └── Workspace / Agents / Projects / Skills / Automation
   │
   └── Admin Experience
          └── System / Security / Resources / Users / Evolution
```

The shell, identity, routing infrastructure, design system, command system and global UX should be shared.

The business capabilities should remain role-aware.

The backend should remain the final authority.