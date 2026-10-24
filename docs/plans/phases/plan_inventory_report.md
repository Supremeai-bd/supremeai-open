---
id: plan-inventory-report
subject: "Plan inventory report — generated registry-vs-filesystem reconciliation"
document_role: audit
planning_authority: Architecture Governance / Planning Circle
status: historical
evidence_state: unverified
last_verified: 2026-09-25
target_scope: supremeai_internal
---

# docs/plans/ Inventory & Governance Report

> Generated: 2026-09-25 by `scripts/governance/lint_plans.py` (report-only mode)  
> Machine cache: `docs/plans/plan_registry.json` · Source of truth: per-file YAML frontmatter

## Totals

- Documents scanned: **183**
- With valid frontmatter: **181**
- Findings: **0 errors / 14 warnings**

## Family distribution (content-derived)

| Family | Documents |
|---|---|
| control-tower-mcp | 45 |
| unclassified | 28 |
| execution-phases | 28 |
| free-tier-federation | 23 |
| frontend-product-ux | 16 |
| unified-architecture | 12 |
| browser-automation | 9 |
| ci-cd-pipeline | 7 |
| intelligence-evolution | 6 |
| dynamic-configuration | 4 |
| production-readiness | 3 |
| security-defense | 1 |
| deployment-render | 1 |

## Competing plan sets (same subject + role, unlinked)

- None detected among frontmatter-classified documents.

## Findings

### `missing-frontmatter` (2)

- [WARNING] missing-frontmatter    supremeai/docs/plans/SOFTWARE_ENGINEERING_EXCELLENCE_PLAN.md: no YAML frontmatter — registry cannot classify this plan (inferred family: frontend-product-ux)
- [WARNING] missing-frontmatter    supremeai/docs/plans/phases/plan_inventory_report.md: no YAML frontmatter — registry cannot classify this plan (inferred family: free-tier-federation)

### `unverified-claim` (6)

- [WARNING] unverified-claim       supremeai/docs/plans/architecture/dynamic_ai_architecture_zero_downtime.md: L1251: confident claim without evidence marker — `Runs locally, no API keys needed, 100% uptime`
- [WARNING] unverified-claim       supremeai/docs/plans/features/antihacking_security_defense_framework.md: L353: confident claim without evidence marker — `- **Availability SLA**: 99.9% uptime guaranteed`
- [WARNING] unverified-claim       supremeai/docs/plans/features/superai_competitor_playbook.md: L286: confident claim without evidence marker — `└── Our Opportunity: 99.9% Uptime guarantee`
- [WARNING] unverified-claim       supremeai/docs/plans/implementation_plan.md: L203: confident claim without evidence marker — `Enterprise targets such as 99.99% uptime or sub-100ms P95 are **future targets**, not current guarantees.`
- [WARNING] unverified-claim       supremeai/docs/plans/phases/phase4_optimization.md: L115: confident claim without evidence marker — `- 99.9% uptime achieved`
- [WARNING] unverified-claim       supremeai/docs/plans/phases/yearly_strategic_roadmap_2026.md: L57: confident claim without evidence marker — `- **Reliability**: 99.9% uptime`

### `versioned-filename` (6)

- [WARNING] versioned-filename     supremeai/docs/plans/architecture/dynamic_ai_architecture_zero_downtime.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section
- [WARNING] versioned-filename     supremeai/docs/plans/features/evolution_patch_implementation_plan.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section
- [WARNING] versioned-filename     supremeai/docs/plans/features/free_tier_federation_missing_services_analysis.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section
- [WARNING] versioned-filename     supremeai/docs/plans/infrastructure/SUPREMEAI_CONFIGURATION_CONTROL_REGISTRY.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section
- [WARNING] versioned-filename     supremeai/docs/plans/infrastructure/free_tier_federation_master_plan.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section
- [WARNING] versioned-filename     supremeai/docs/plans/infrastructure/production_upgrade_implementation_plan_v2.md: filename uses banned versioning pattern (_v2/_final/_latest/…); changes belong in this living plan's evolution section

