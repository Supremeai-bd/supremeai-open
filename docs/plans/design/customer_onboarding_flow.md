---
id: customer-onboarding-flow
subject: "Customer Onboarding Flow — Zero-Complexity First Experience"
document_role: architecture
planning_authority: Customer Experience Circle + Frontend Face
status: proposed
target_scope: customer_facing
canonical: candidate
evidence_state: unverified
disposition: retain
last_verified: 2026-09-17
depends_on:
  - docs/plans/features/customer_api_spec.md
  - docs/plans/features/mode3_zero_password_experience.md
  - docs/plans/features/tenant_workspace_architecture.md
  - docs/plans/design/intelligent_chat_plan.md
implements:
  - Step-by-step customer onboarding journey from signup to first agent task
  - Progressive disclosure of capabilities without technical configuration
  - First-run guidance with sample projects and pre-built agent templates
supersedes: []
superseded_by: []
---

> ⚠️ **CONFLICT NOTE (2026-09-25):** এই প্ল্যানটি সঠিক, কিন্তু আসল কোড
> (`frontend/src/components/Onboarding/OnboardingWizard.tsx`) প্ল্যানের বিপরীত।
> প্ল্যান বলে "zero-config, 60s, কোনো API key না" কিন্তু কোড = `StepApiKey →
> StepModelSelect → StepFirstChat` (প্রথম ধাপেই API key চায়)।
>
> **সমাধান:** কোড fix করতে হবে প্ল্যান অনুযায়ী (আলাদা Issue, code PR)।
> এই প্ল্যানটি archive করা হয়নি কারণ প্ল্যান সঠিক — কোড ভুল।
>
> দর্শন: [CP06 Decoupled 3-Layer Topology](../../plan-network/core-plans/CP06_DECOUPLED_THREE_LAYER_TOPOLOGY.md)


# Customer Onboarding Flow

**Status:** proposed  
**Scope:** End-user onboarding experience from first visit to first successful agent execution

---

## 1. Purpose

Guide new customers from signup to their first successful agent task in under 60 seconds, without requiring technical configuration, API key setup, or documentation reading.

---

## 2. Onboarding Stages

### Stage 1: Landing (0–10 seconds)

- Value proposition headline: "Describe what you want to build"
- Single input field: project name + description
- CTA: "Start Building" (no account required for demo)

### Stage 2: Mode 3 Auth (10–20 seconds)

- Email magic link or "Continue with Google"
- No password, no username creation
- Session token issued automatically

### Stage 3: First Project Creation (20–40 seconds)

- Auto-create default project from landing input
- Show project dashboard with one-click templates:
  - "Build a REST API"
  - "Scrape a Website"
  - "Automate a Workflow"

### Stage 4: First Agent Task (40–60 seconds)

- Pre-filled prompt based on selected template
- Real-time progress indicator
- Success state with shareable result link

---

## 3. Progressive Disclosure

| Stage | Visible UI | Technical Exposure |
|-------|-----------|-------------------|
| Landing | Logo, headline, input, CTA | None |
| Auth | Provider buttons | None |
| Project | Dashboard, templates | None |
| Task Execution | Progress, result | Agent name only |
| Post-Onboarding | Full dashboard | Capabilities revealed gradually |

---

## 4. Fallback & Edge Cases

- **Slow network:** Show optimistic UI with background sync
- **Provider failure:** Graceful degradation with "Try again" and cached suggestions
- **Abandoned session:** Email recovery link with pre-filled context

---

## 5. Acceptance Criteria

- [ ] New user completes first task in < 60 seconds (measured)
- [ ] Zero technical configuration required before first execution
- [ ] Onboarding completion rate > 80%
- [ ] No password fields in customer-facing onboarding flow

---

## 6. Out of Scope

- Admin onboarding (Layer 1 concern)
- Enterprise SSO setup (handled post-onboarding)
- Billing configuration (deferred to first paid action)
