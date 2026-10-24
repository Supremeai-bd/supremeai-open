---
target_scope: combined_ecosystem
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:plan_reconciliation_register
subject: Plan Reconciliation Register
document_role: roadmap
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# Plan Reconciliation Register

> Status: active
> Owner: Architecture Governance
> Last verified: 2026-09-15
> Canonical role: reconciliation register
> Supersedes: `docs/plans/PLAN_RECONCILIATION_REGISTER.md`

This first pass classifies overlapping plan families without deleting or moving protected files. A later pass may add archive indexes after all cross-references are verified.

## Canonical hierarchy

- Global implementation source: [`implementation_plan.md`](../implementation_plan.md)
- Architecture source: [`architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md`](../architecture/SUPREMEAI_MASTER_PLAN_CANONICAL.md)
- Lifecycle rules: [`PLAN_LIFECYCLE_POLICY.md`](../PLAN_LIFECYCLE_POLICY.md)
- Evidence map: [`PLAN_TO_CODE_TRACEABILITY_MATRIX.md`](../PLAN_TO_CODE_TRACEABILITY_MATRIX.md)

## Reconciliation groups

| Group | Canonical direction | Existing files to reconcile | First-pass disposition |
|---|---|---|---|
| Architecture blueprints | Unified ecosystem architecture | `architecture/*master*`, `full_system_architecture_map.md`, `supremeai_*blueprint*`, `crown_jewel_*` | Preserve; mark competing versions and link to root architecture |
| Control Tower/MCP | Unified control plane and capability federation | `architecture/unified_fastmcp_control_tower_multitenant_master_plan_bn.md`, `features/mcp_gateway_dynamic_hub_plan.md`, `features/personal_mcp_gateway_multitenant_hub_plan.md`, `features/orphan_components_wiring_master_plan.md` | Preserve; reconcile contracts before any move |
| Dynamic configuration | Runtime configuration and provider abstraction | `architecture/dynamic_configuration_zero_hardcode_roadmap.md`, `architecture/dynamic_control_plane_zero_hardcode_plan_bn.md`, `features/runtime_dynamic_configuration_zero_hardcode_plan.md`, `architecture/vendor_independent_integration_architecture_plan.md` | Preserve; establish one domain index next pass |
| Production hardening | Release gates and production readiness | `PRODUCTION_UPGRADE_PLAN.md`, `infrastructure/production_upgrade_implementation_plan_v2.md`, `features/production_hardening_and_p1_p2_roadmap_2026_09_11.md`, `features/production_readiness_final_stretch_plan_bn.md`, `features/risk_remediation_and_hardening_execution_plan_bn.md` | Keep current roadmap active; label older execution records historical/superseded after evidence review |
| Free-tier/federation | Policy-compliant cost and capacity management | root `FREE_TIER_*`, `infrastructure/free_tier_*`, `features/free_tier_*`, multi-cloud plans | Preserve; do not treat experimental free-tier workers as production dependencies |
| Intelligence/self-evolution | Governed proposal, evaluation, promotion, rollback | `features/zero_cost_autonomous_self_evolution_plan.md`, `living_autonomous_intelligence_master_plan.md`, `self_assembling_need_supply_intelligence_plan.md`, `self_tracing_and_bounded_black_box_architecture.md`, `Plan_01`, `Plan_03`, `Plan_19`–`Plan_21`, `Plan_24` | Preserve; consolidate only after runtime evidence and safety boundaries are mapped |
| Data/memory lifecycle | Tenant-safe storage, memory, retention | `Plan_09`, `Plan_17`, `design/knowledge_acquisition_plan.md`, infrastructure Supabase plan | Preserve; use schema and migration evidence as authority |
| Frontend/product UX | Customer/admin experience and API mapping | `design/complete_frontend_master_plan_bn.md`, `supremeai_2_product_ui_ux_completeness_master_plan.md`, dashboard/chat/mission plans | Preserve; add API-to-screen mapping before merge |
| Execution phases | Current release train | `phases/phase1_*` through `phase4_*`, Q1/yearly roadmaps, milestone trackers | Treat as historical planning lineage until reconciled with current release gates |
| Historical/reference records | Evidence only | `phases/historical_status_snapshot*`, deployment records, troubleshooting records, reference guides | Preserve; do not use as implementation source |

## 2026-09-17 automated pass (Phase 2 — canonical registry)

Tooling: `scripts/governance/lint_plans.py` · Machine cache: [`plan_registry.json`](../plan_registry.json) · Inventory: [`plan_inventory_2026-09-17.md`](./plan_inventory_2026-09-17.md)

- Frontmatter conformance sweep executed: canonical governance plan self-conformance fixed (`document_role: policy`, `supersedes: []` with prose moved to comments), PLAN_001–004 colon-bearing prose values quoted, missing `document_role`/`id`/`planning_authority` backfilled on the free-tier v4.1 analysis and scaling constitution (their `canonical:` self-path fields re-typed as boolean + `source_file`, dead `supersedes` targets documented as no-longer-in-repository), and root canonical docs (lifecycle policy, traceability matrix, implementation index, README, unified/master architecture, roadmaps, CI consolidation) received full canonical frontmatter.
- Scanner state after sweep: **0 errors / 143 warnings / 2 active competing sets** — down from 17 errors on first inventory.
- Competing-set detection now follows PLAN_LIFECYCLE_POLICY single-active-execution discipline: only `status: active` documents compete; `proposed` candidates are queued, not competing.
- Registry totals: 157 documents, frontmatter-classified growing pass over pass (family distribution in the JSON `totals.families`).

## Known drift to resolve

1. `phases/cross_module_dependency_matrix.md` must be checked against actual current services before being authoritative.
2. Root and infrastructure free-tier plans have versioned duplicates and need a single policy index.
3. Several “master blueprint” documents overlap and lack explicit supersession metadata.
4. Completion claims must be matched to code, tests, and runtime evidence.
5. The catalog contains legacy file URLs; repository-relative links are preferred.

## 2026-09-17 Phase 5 — controlled archive & lineage record

Executed the move that `docs/plans/phases/README.md` had already planned but never carried out:

| File | Disposition | Destination | Cross-reference handling |
|---|---|---|---|
| `docs/plans/phases/historical_status_snapshot_2026_05_10.md` | archive (historical lineage — pre-pivot Spring Boot/Firebase/Flutter architecture snapshot; evidence only) | `docs/archive/plans/phases/historical_status_snapshot_2026_05_10.md` | **Redirect stub** left at the old path (frontmatter `status: historical`, `disposition: redirect`, `superseded_by` link) so all inbound links keep resolving. Inbound refs found: `phases/README.md` (already pointed at the archive destination), this register's evidence rows, generated registry (regenerates). |

Archive protocol applied (per CANONICAL_PLANNING…PLAN.md §7 Phase 5): content preserved verbatim (git mv), no deletion, cross-reference scan executed before the move, redirect stub created, lineage recorded here.

## Next reconciliation pass

1. Add metadata headers to the canonical root and active domain plans.
2. Build a current dependency matrix from actual imports, routes, schemas, and deployment configuration.
3. Add `superseded_by` links only after reading each candidate’s references.
4. Create archive indexes without deleting files.
5. Validate all internal links and update `README.md` counts/links.