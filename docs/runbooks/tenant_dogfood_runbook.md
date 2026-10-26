# Tenant Dogfood Runbook (#1343)

**Goal:** convert tenant isolation from "designed but never exercised" into a
tested invariant before the first real customer touches it.

## Why
`tenant_list` returns 0 tenants; every interactive client runs on
`tenant_default`. AIQ-075 (P0) requires cross-tenant access + privilege
escalation tests **before scale**. The first customer onboarding must not be
the first-ever isolation test.

## Week 0 — provision (operator, ~30 min)
1. Create two internal tenants via the admin lane:
   - `staging-admin` (admin/customer role pair kept internal)
   - `staging-customer` (role: customer)
   Tools: `tenant_create` (returns per-tenant admin token — store in Infisical, never in chat).
2. Record both tenant IDs in this file's Evidence table.
3. Rotate the customer admin token once via `tenant_rotate_admin_token` to prove rotation works.

## Week 1 — dogfood
1. Point one studio workspace profile at the **customer** tenant.
2. Route **at least one full agent work-order lifecycle** through it
   (claim → implement → submit → verdict) using only the customer tenant's
   credentials.
3. Each day: run the negative battery
   (`SUPREMEAI_API_URL=... CUSTOMER_TOKEN=... python scripts/ci/tenant_negative_battery.py`)
   and paste the JSON report into the Evidence table.

## Evidence table

| Date | Battery result | Work-order lifecycle step | Notes |
|------|----------------|---------------------------|-------|
| — | — | — | (fill during dogfood week) |

## Exit criteria (all must hold)
- [ ] `tenant_list` shows ≥1 active non-default tenant with its own rotated admin token
- [ ] Negative battery: 0 cross-tenant successes across ≥5 runs on ≥3 days
- [ ] One full work-order lifecycle completed inside the customer tenant
- [ ] Any isolation hole → file a P0 follow-up work order referencing #1343

## Rollback
Tenants are soft-state: `tenant_suspend` + `tenant_activate` reverse any dogfood
state; nothing here touches `tenant_default` clients.
