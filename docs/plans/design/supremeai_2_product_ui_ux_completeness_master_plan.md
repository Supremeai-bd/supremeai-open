---
target_scope: customer_facing

---

## 🌑 DARK-MODE DOCTRINE — RESOLVED (canonical, Wave 2.7 / issue #1244)

> **রায় (2026-09-25): DARK-FIRST হলো canonical।** SupremeAI-এর প্রাথমিক
> ভিজ্যুয়াল পরিচয় ডার্ক থিম ("Deep Space") — লাইট/সানসেট/ম্যাট্রিক্স থিম
> ব্যবহারকারীর ইচ্ছাধীন অপশন, ডিফল্ট নয়।

### Conflict history
| দাবি | উৎস | বর্তমান অবস্থা |
|---|---|---|
| "dark mode default" | এই মাস্টার প্ল্যান | ✅ **জিতেছে — canonical** |
| "dark mode default নয়, option থাকুক" | `docs/archive/plans/design/ux_ui_best_practices_and_interaction_guide.md` (archived) | ❌ বাতিল — archive-এই থাকবে, আর কোনো ক্যানোনিকাল মর্যাদা নেই |

### Code evidence (doctrine আগে থেকেই প্রয়োগ হয়ে আসছে)
1. `frontend/src/contexts/ThemeProvider.tsx` — `useState<Theme>('dark')` — ডিফল্ট Deep Space (dark)
2. `frontend/src/contexts/ThemeProvider.test.tsx` lines 37-41 — ডিফল্ট `'dark'` + `documentElement.classList` + `data-theme="dark"` পিন করা regression টেস্ট
3. `frontend/src/index.css` — `:root, .dark` selector + `body.dark` + `[data-theme="dark"]` blocks সব dark-first token সেট

### নিয়ম (এখান থেকে)
- নতুন UI component dark-first ডিজাইন হবে; লাইট/অন্য থিম ফলো-আপ অ্যাডাপ্টেশন
- থিম টোকেন পরিবর্তন `index.css`-এর `:root, .dark` block-এ হবে (এক সত্যের উৎস)
- `data-theme` attribute + ক্লাস দুটোই সেট থাকবে (আধুনিক CSS + লিগ্যাসি সিলেক্টর কভার)
- এই doctrine বদলাতে হলে আলাদা issue + CP06 owner-এর অনুমোদন লাগবে

**Wave 2.7 gate contribution:** doctrine conflict = ০ (canonical ঘোষিত + প্রমাণ লিঙ্কযুক্ত)

---

# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:supremeai_2_product_ui_ux_completeness_master_plan
subject: SUPREMEAI 2.0 — PRODUCT UI/UX + DASHBOARD COMPLETENESS MASTER PLAN
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SUPREMEAI 2.0 — PRODUCT UI/UX + DASHBOARD COMPLETENESS MASTER PLAN

Version: 1.0
Date: 2026-08-28
Repository: https://github.com/SaifulHaqueNiloy/supremeai
Primary frontend: `frontend/`
Design tokens: `packages/design-tokens/`
Status: Implementation Blueprint

---

## 0. Executive Decision

SupremeAI should NOT become a pure skeuomorphic, neumorphic, claymorphic, or “everything is glass” product.

The canonical visual direction is:

**70% Functional Minimalism + Bento**
**20% Liquid Glass + Spatial Depth**
**10% Controlled Cyber/Neon**

Product metaphor:

> **SupremeAI is a living AI operating environment.**

Two experiences share one shell:

- **Workspace** — user-facing creation, AI, projects, agents, automation.
- **Command Center** — admin-facing observability, governance, security, deployment, cost, and recovery.

Do not rewrite business logic or backend contracts just to achieve the new visual design. First build a reusable design system and migrate screens incrementally.

---

# 1. Current-Codebase Assessment

## 1.1 Existing strengths

The current frontend already contains substantial building blocks:

- Shared `DashboardLayout`, `Header`, and `Sidebar`.
- User dashboard with overview, feed, presets, chat, browser preview, mobile simulator, analytics, team, and security surfaces.
- Admin dashboard with live metrics, health, security/threat scan, CI/CD, deployment actions, and React Flow-based orchestrator topology.
- Simple/Advanced dashboard mode.
- Global command-palette trigger.
- User/Admin role switcher.
- Framer Motion.
- React Flow / XYFlow.
- Recharts.
- Monaco.
- Tailwind CSS.
- Shared `@supremeai/design-tokens`.
- Separate billing/usage pages and billing APIs.
- Audit log UI and security/audit backend pieces.
- Tenant-admin capabilities.

Useful source locations already identified:

- `frontend/src/components/admin/Dashboard.tsx`
- `frontend/src/components/admin/AethelCoreStyles.css`
- `frontend/src/components/customer/UserDashboard.tsx`
- `frontend/src/components/customer/UserDashboard.css`
- `frontend/src/components/dashboard/DashboardLayout.tsx`
- `frontend/src/components/core/Header.tsx`
- `frontend/src/components/core/Sidebar.tsx`
- `frontend/src/components/admin/AuditLogsPanel.tsx`
- `frontend/src/commandcenter/modules/secure/AuditExplorer.tsx`
- `frontend/src/commandcenter/modules/money/UsageBilling.tsx`
- `frontend/src/pages/BillingPage.tsx`
- `frontend/src/commandcenter/`
- `packages/design-tokens/`

## 1.2 Current UX problem

The main problem is visual/structural fragmentation, not missing technology.

Current code mixes:

- traditional SaaS layout,
- cyber/HUD visuals,
- heavy glass,
- neon terminal UI,
- separate light/simple dashboard,
- multiple dashboard-level tabs.

The redesign must consolidate those into one coherent language.

---

# 2. Dashboard Completeness — What Is Missing?

This section distinguishes between:

1. **Already present in code but not surfaced/coherently organized**
2. **Should be added to the product experience**
3. **Future/advanced capability that should not block the redesign**

---

## 2.1 USER WORKSPACE — Current gaps

### A. Stronger “Home / Continue Working” experience — REQUIRED

Current dashboard is more of a feature collection than a workflow-oriented home.

Add:

- Continue where you left off.
- Recent projects.
- Recent conversations.
- Recent agent jobs.
- Saved prompts / presets.
- Pinned projects.
- Last deployment/build.
- Quick create actions.

Goal:

> The user should be able to return to unfinished work in one click.

---

### B. Unified Project Hub — REQUIRED

Projects exist in current dashboard data structures, but they need a first-class workflow.

Project page should show:

- Overview
- Files
- Conversations
- Agents
- Deployments
- Usage/cost
- Activity
- Settings
- Team/access (if applicable)

Project-level navigation should be more important than generic dashboard cards.

---

### C. First-class Agent Center — REQUIRED

The codebase has agent/swarm concepts, but user-facing agent lifecycle should be explicit.

Required:

- Agent list
- Agent status
- Current task
- Progress
- Tool activity
- Input/output
- Pause / resume
- Retry
- Stop
- Run history
- Cost
- Errors
- Permissions/capabilities

A user should understand WHAT an agent is doing without opening logs.

---

### D. Context / Memory visibility — REQUIRED

AI Studio needs an explicit context layer.

Show:

- current model
- system instructions
- attached files
- tools
- memory status
- project context
- conversation context
- limits
- estimated usage/cost where possible

The goal is transparency, not exposing unsafe/internal secrets.

---

### E. Notifications / Inbox — REQUIRED

Current header has notifications, but this needs a stronger product model.

Create an Activity/Inbox surface for:

- agent completion
- build failure
- deployment success/failure
- collaboration mentions
- quota warnings
- security notices
- system incidents relevant to the user

Unread states should be persisted.

---

### F. Automation / Runs — HIGH PRIORITY

Automation queue capability already exists in the repo.

Expose a coherent user surface for:

- scheduled jobs
- recurring tasks
- queued jobs
- failed jobs
- retry
- execution history
- run details
- cancellation

A good model:

`Automation -> Runs -> Run Detail`

---

### G. Files / Knowledge — HIGH PRIORITY

AI products need a clear data layer.

Recommended user surface:

- Files
- folders/projects
- upload
- indexing status
- supported formats
- search
- knowledge sources
- attachment history
- deletion
- access visibility

This should integrate directly with AI Studio.

---

### H. Usage / Cost / Quota — HIGH PRIORITY

Billing infrastructure already exists.

Make usage visible where it matters:

- current usage
- quota
- estimated monthly cost
- token consumption
- model-level usage
- project-level usage
- warning threshold
- billing link

Avoid forcing users to discover billing from a detached page.

---

### I. Integrations — REQUIRED

Current sidebar has Integrations.

Expand it into:

- connected apps
- API/webhook integrations
- connection state
- reconnect
- revoke
- test connection
- scopes/permissions
- last sync
- error state

---

### J. Collaboration — REQUIRED FOR TEAM USE

Team exists as a concept in the current dashboard.

Need:

- members
- roles
- invitations
- project membership
- access level
- recent collaborator activity
- ownership transfer

Do not duplicate team management across many screens.

---

### K. Search / Command Center — REQUIRED

Existing CommandBar trigger is good.

It should become the central action surface:

- navigate
- search projects
- search conversations
- open agents
- run actions
- create project
- switch model
- open files
- start automation

Recommended mental model:

`Search + Navigate + Execute`

---

### L. Settings needs restructuring — MEDIUM PRIORITY

Settings should be grouped:

- Account
- Appearance
- Notifications
- AI preferences
- Privacy
- Security
- API/Developer
- Billing
- Workspace/Team

Do not put all settings into one long page.

---

# 2.2 ADMIN COMMAND CENTER — Current gaps

The current admin dashboard already contains strong telemetry/security/CI/deployment foundations. The problem is governance and operations need a complete control plane.

---

### A. Operations overview — REQUIRED

Top-level admin needs:

- platform health
- request rate
- latency
- error rate
- active agents
- queues/jobs
- deployments
- incidents
- cost
- capacity

A single executive “health” score should NEVER hide the underlying metrics.

---

### B. Incident Center — REQUIRED

This is one of the biggest missing product surfaces.

Need:

- active incidents
- severity
- affected services
- start time
- current status
- timeline
- owner
- actions
- mitigation
- resolution
- postmortem link

Statuses:

`Investigating -> Identified -> Mitigating -> Monitoring -> Resolved`

---

### C. Service / Infrastructure Explorer — REQUIRED

Admin should be able to drill from:

`Platform -> Service -> Instance/Subsystem`

Show:

- health
- latency
- throughput
- errors
- dependencies
- recent deploy
- recent incidents
- logs/telemetry links

React Flow topology should support this drill-down.

---

### D. Agent Swarm / Runtime Control — REQUIRED

Admin needs a dedicated control plane for:

- active agents
- queues
- stuck jobs
- concurrency
- failures
- resource consumption
- model/provider utilization
- kill/retry controls
- worker health

This is a critical differentiator for an AI orchestration platform.

---

### E. Cost & FinOps — REQUIRED

The repo already has billing/usage/cost tooling.

Admin should have:

- total spend
- spend trend
- cost by model/provider
- cost by tenant
- cost by project
- token usage
- budget
- forecast
- anomalies
- quota breaches
- top expensive workloads

Surface this in Command Center and keep deeper details in a dedicated Cost page.

---

### F. Tenant / Organization Control — REQUIRED

Tenant admin backend exists.

Surface:

- organizations/tenants
- users
- roles
- quotas
- plan
- usage
- status
- feature access
- suspension/restore
- audit trail

This should be RBAC protected and never visible to normal users.

---

### G. Identity / Access / RBAC — REQUIRED

Admin security should cover:

- users
- roles
- permissions
- sessions
- devices
- API keys
- service accounts
- access reviews
- privileged actions

Use least-privilege language.

---

### H. Audit Explorer — REQUIRED

Audit UI already exists.

Turn it into a first-class admin surface with:

- actor
- action
- target
- tenant
- timestamp
- request/correlation ID
- outcome
- severity
- source
- filter/search
- export where permitted

Important:

> Audit records are evidence, not decorative activity feed items.

---

### I. Security Center — REQUIRED

Existing threat scan should become one part of a broader security center:

- threat findings
- severity
- affected resource
- security posture
- policy violations
- auth anomalies
- dependency/security alerts
- remediation state
- security event history

---

### J. Deployment / Release Center — REQUIRED

Current deployment functionality exists.

Admin should have:

- current release
- release history
- commit
- build status
- environment
- deployment status
- rollback
- approvals
- deployment diff
- health after deploy

Emergency deployment should be visually distinct and require confirmation.

---

### K. Backup / Recovery / Disaster Readiness — REQUIRED

This is an important operations gap.

Admin needs visibility into:

- backup status
- last successful backup
- backup age
- restore points
- recovery tests
- database/storage health
- disaster recovery readiness

Actual restore actions must be protected and explicit.

---

### L. Feature Flags / Runtime Configuration — HIGH PRIORITY

Recommended:

- feature flags
- rollout percentage
- tenant targeting
- environment
- kill switch
- configuration history
- audit trail

Never expose raw secrets.

---

### M. API / Traffic / Rate Limit Control — HIGH PRIORITY

Admin should see:

- API traffic
- error rates
- top endpoints
- rate-limit events
- abusive clients
- latency distribution
- provider errors

Tenant rate-limiting infrastructure already exists; the UI should make it observable.

---

### N. Reliability / SLO view — HIGH PRIORITY

Add:

- uptime
- availability
- p95/p99 latency
- error budget
- SLO status
- trend
- service-level breakdown

This makes the dashboard useful for operations beyond “is it green?”

---

### O. Admin Notifications / Alert Rules — HIGH PRIORITY

Admins need alert configuration:

- trigger
- severity
- recipients
- channels
- cooldown
- acknowledgement
- escalation

---

# 3. Recommended Information Architecture

## 3.1 USER

```text
Workspace
├── Home
├── AI Studio
├── Projects
├── Agents
└── Activity

Discover
├── Skills
├── Integrations
└── Marketplace

Automation
└── Runs

Insights
├── Usage
└── Analytics

Settings
├── Account
├── AI
├── Notifications
├── Security
├── Developer
└── Billing
```

Avoid making Browser Preview, Mobile Simulator, Team, Security, etc. all equal-level top navigation entries.

They should be contextual or nested.

---

## 3.2 ADMIN

```text
Command Center
├── Overview
├── Topology
├── Services
└── Live Activity

Agents
├── Swarm
├── Jobs
└── Runtime

Security
├── Security Center
├── Threats
├── Audit Explorer
└── Access

Operations
├── Incidents
├── Deployments
├── Releases
└── Recovery

Organizations
├── Tenants
├── Users
├── Roles
└── Quotas

FinOps
├── Usage
├── Costs
├── Budgets
└── Forecast

Configuration
├── Feature Flags
├── Integrations
└── Runtime Config
```

---

# 4. Unified Shell

```text
┌────────────────────────────────────────────────────────────┐
│ ☰  SUPREMEAI     Search / Command ⌘K     Workspace Admin ● │
├──────────────┬─────────────────────────────────────────────┤
│              │ Breadcrumb                                  │
│ Navigation   │ Page Header                                 │
│              │                                             │
│ grouped      │ Main content                                │
│ sections     │                                             │
│              │                                             │
│              │                                             │
└──────────────┴─────────────────────────────────────────────┘
```

The shell must remain identical in structure across roles.

Only:

- accent,
- available navigation,
- permissions,
- contextual data

should change.

---

# 5. Visual Design System

## 5.1 Design language

**SUPREME SPATIAL UI 2.0**

Principles:

1. Intelligence over decoration.
2. Depth has meaning.
3. Glass is a material, not a default background.
4. Motion communicates state.
5. Complexity is adaptive.
6. Accessibility is built into primitives.

---

## 5.2 Base colors

```text
Ink              #06070B
Surface          #0B0F17
Raised           #111722
Text             #F8FAFC
Secondary        #94A3B8
Muted            #64748B
Border           rgba(255,255,255,0.08)
```

User accent:

```text
Primary          #A855F7
Secondary        #7C3AED
Glow             rgba(168,85,247,0.22)
```

Admin accent:

```text
Primary          #00F3FF
Secondary        #22D3EE
Glow             rgba(0,243,255,0.20)
```

Semantic:

```text
Success          #22C55E
Warning          #F59E0B
Danger           #F43F5E
Info             #38BDF8
```

---

## 5.3 Surfaces

```text
surface-0 = base
surface-1 = raised
surface-2 = glass
surface-3 = floating
surface-4 = focus/modal
```

Rules:

- large content surfaces -> low/no blur
- small floating surfaces -> stronger blur
- modals -> strongest controlled blur
- avoid nested blur layers

---

## 5.4 Radius

```text
xs     6px
sm     10px
md     14px
lg     18px
xl     24px
pill   999px
```

---

## 5.5 Shadow

```text
soft
float
glow
```

Do not allow component-specific shadow chaos.

---

## 5.6 Typography

```text
UI       Plus Jakarta Sans / Inter
Metrics  JetBrains Mono
Code     JetBrains Mono
```

Metrics use tabular numerals.

---

# 6. Component System

Build/standardize:

```text
Surface
GlassSurface
PageHeader
Breadcrumb
StatCard
Metric
StatusPill
ActivityFeed
CommandBar
NavRail
WorkspaceCard
AgentCard
AgentStatus
DataTable
EmptyState
ConfirmDialog
Drawer
Tooltip
KpiTrend
Timeline
FilterBar
```

Component states must include:

- loading
- empty
- success
- warning
- error
- disabled
- read-only
- permission denied

---

# 7. Motion System

Use Framer Motion already present in the project.

Standard timings:

```text
micro     120–160ms
normal    180–240ms
large     280–420ms
```

Allowed:

- opacity
- transform
- limited filter
- number transitions

Avoid:

- perpetual animations with no semantic meaning
- layout-jank animations
- giant spinning effects on every page

Respect `prefers-reduced-motion`.

---

# 8. Responsive Strategy

Desktop:

`NavRail + Main + optional Inspector`

Tablet:

`Collapsed NavRail + Main`

Mobile:

`Top Bar + Main + Bottom Action Dock`

Do not simply shrink desktop components.

---

# 9. Accessibility

Required:

- WCAG-conscious contrast
- keyboard navigation
- visible focus
- semantic HTML
- screen-reader labels
- aria-current
- status indicators not based on color alone
- reduced-motion behavior
- accessible dialogs/drawers
- proper form validation
- table semantics

---

# 10. Performance

Rules:

- Use `backdrop-filter` selectively.
- Limit large blur layers.
- Avoid dozens of animated shadows.
- Prefer transform/opacity.
- Lazy-load Monaco and heavy visualization modules.
- Virtualize long activity/log lists where needed.
- Preserve current lazy-loading strategy for heavy editor/visual modules.

---

# 11. Migration Plan

## Phase 0 — Audit / Guardrails

Before changing UI:

- inventory routes
- inventory dashboard components
- identify duplicate styles
- identify duplicate navigation
- verify permissions
- capture current screenshots
- capture current interaction tests
- establish visual regression baseline

Deliverable:

`docs/ui-ux/SUPREME_UI_2_MIGRATION_AUDIT.md`

---

## Phase 1 — Design Foundation

Build:

- tokens
- typography
- surface system
- buttons
- inputs
- cards
- status
- tables
- dialogs
- navigation primitives

Deliverable:

`packages/design-tokens/*`
`frontend/src/components/ui/*`

---

## Phase 2 — Shared Shell

Migrate:

- `DashboardLayout`
- `Header`
- `Sidebar`

Introduce:

- role switch
- command bar
- responsive rail
- unified breadcrumb
- page header

Do not break routes.

---

## Phase 3 — User Workspace

Order:

1. Home
2. AI Studio
3. Projects
4. Agents
5. Activity
6. Automation
7. Integrations
8. Usage
9. Team
10. Settings

---

## Phase 4 — Admin Command Center

Order:

1. Overview
2. topology
3. services
4. agents/swarm
5. security
6. audit
7. incidents
8. deployments
9. recovery
10. tenants
11. costs
12. configuration

---

## Phase 5 — Polish

- light mode
- reduced motion
- mobile refinement
- loading/empty/error states
- accessibility
- performance
- visual regression
- cleanup legacy CSS

---

# 12. Keep vs Replace

## KEEP

- React Flow / XYFlow topology
- Framer Motion
- Monaco
- Recharts
- command palette concept
- role switch concept
- design token package
- existing backend contracts
- billing/usage capability
- security/audit capability
- tenant capabilities
- current tests and test IDs where useful

## REWORK

- heavy Aethel/Cyber HUD visuals
- giant orbital core
- scanlines everywhere
- dense tab rows
- repeated card styling
- dashboard-level feature overload
- separate “simple mode” visual language

## REMOVE ONLY AFTER MIGRATION

- unused legacy dashboard styles
- duplicate visual primitives
- duplicate navigation components
- obsolete CSS tokens
- unused dashboard effects

---

# 13. Data/Permission Rules

UI redesign MUST NOT weaken authorization.

Rules:

- UI visibility is NOT authorization.
- Backend remains source of truth.
- Admin-only controls must be server-authorized.
- Privileged actions require explicit confirmation.
- Destructive actions require clear consequence text.
- Audit privileged operations.
- Never render secret/token values accidentally.
- Avoid exposing internal infrastructure details to unauthorized users.

---

# 14. Testing Plan

For every migrated screen:

## Functional

- route loads
- permissions work
- actions work
- API failures handled
- loading states handled
- empty states handled

## Visual

- dark mode
- light mode
- mobile
- tablet
- desktop
- hover/focus
- long content
- high-density data

## Accessibility

- keyboard
- focus order
- labels
- screen reader landmarks
- contrast
- reduced motion

## Regression

Do not remove existing test IDs unless replaced with equivalent stable selectors.

---

# 15. Definition of Done

A phase is done only when:

- design system primitives are reused instead of local CSS duplication
- no route regression
- existing API behavior remains intact
- permissions remain intact
- loading/error/empty states exist
- mobile is usable
- keyboard navigation works
- visual style matches SupremeAI 2.0
- no unjustified infinite animations
- no major console errors
- typecheck passes
- lint passes
- relevant tests pass

---

# 16. AI Agent Working Rules

Any AI coding agent working on this plan MUST follow these rules:

1. Inspect current code before changing it.
2. Search for existing components/services before creating new ones.
3. Reuse existing backend APIs where possible.
4. Do not invent endpoint contracts without evidence.
5. Do not duplicate utilities or contexts.
6. Keep changes incremental.
7. Prefer small cohesive commits.
8. Preserve working functionality.
9. Do not hide errors by swallowing exceptions.
10. Do not weaken authentication/authorization.
11. Do not place secrets in frontend code.
12. Do not replace a functioning component with a mock.
13. Run relevant tests/typecheck/lint after changes.
14. If a capability is missing from backend, document it rather than faking it.
15. Avoid full rewrites unless a measurable blocker exists.
16. Before deleting old UI/CSS, prove it is unused.
17. Keep existing test IDs when possible.
18. Make responsive behavior explicit.
19. Respect reduced motion.
20. Update documentation when architecture changes.

---

# 17. Priority Matrix

## P0 — Must have

- shared shell
- design tokens
- user home
- AI Studio
- projects
- agents
- admin Command Center
- security
- audit
- deployment
- tenant/access
- usage/cost visibility
- responsive/accessibility foundation

## P1 — High value

- activity/inbox
- automation/runs
- files/knowledge
- incidents
- recovery
- feature flags
- SLO/reliability
- admin alerts
- advanced FinOps

## P2 — Future

- deep spatial 3D
- richer WebGL
- adaptive AI UI personalization
- advanced visual simulations
- advanced agent decision visualization

Do not let P2 block P0/P1.

---

# 18. Final Product Vision

### User

**Workspace**

> “Help me build, understand, automate, and ship.”

### Admin

**Command Center**

> “Help me observe, control, govern, secure, and recover the platform.”

### Shared identity

> **SupremeAI — Spatial Intelligence Workspace**

The product should feel premium, intelligent, calm, and technically powerful.

Not:

> “A dashboard covered in neon.”

Instead:

> **“A living AI operating environment with depth, clarity, and control.”**