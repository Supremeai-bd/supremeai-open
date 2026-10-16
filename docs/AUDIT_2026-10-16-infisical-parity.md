# AUDIT 2026-10-16 — Vault / Tower / Live-Services Parity

Auditor: zai-autonomous-contributor (Z.ai Code). Read-only probes; no secret values collected; identifiers redacted. Base: origin/main at 7f5f08a.

## Findings

**A1 HIGH — vault/deploy drift.** The control-plane bootstrap fails closed when the vault returns no production values, yet the deployed tower is healthy. Either the live deployment skips the bootstrap, or its vault identity has broader scope than the audit identity issued for this audit (the vault answers the audit identity with silent empty lists instead of a denial — masking misconfiguration).

**A2 HIGH — empty service registry.** The control tower health endpoint reports a service registry of zero while at least three federation services are documented and live.

**A3 HIGH — gateway breaks its own health contract.** The API gateway does not serve the no-auth health route its OpenAPI contract promises; every path variant returns 404 on the live host. Phase-0 Seq 0.1 (issue #401) targeted exactly this.

**A4 MED — dual source of truth.** Twenty-one deployment keys are provisioned outside the vault per the manifest, while the bootstrap silently lets vault values override the process environment at startup. No parity check or alert exists.

**A5 LOW — Studio has no health API surface.**

**A6 LOW — malformed live-URL links.** The README service table and the ecosystem map contain broken markdown links on the Studio row (a dropped leading character).

## Operator asks

1. Reconcile vault scope versus deploy; make denial or empty states loud instead of silent; surface the boot source and a names-only vault counter on the health endpoint.
2. Register the three live services with the heartbeat protocol (or document why the registry reads zero).
3. Add the no-auth health route to the gateway and close #401.
4. Pick one configuration source of truth; add a fingerprint parity check (hash prefixes only, never values).
5. Fix the two malformed links.
6. Fill the prod vault or drop the vault step from startup — as designed, an empty vault blocks the next deploy.

## Repro

Unauthenticated curl of the three documented live hosts' health endpoints reproduces every code above (full request/response evidence kept in the operator audit log, 2026-10-16T20:4xZ).

বাংলা: ভল্টে কোনো কী নেই অথচ টাওয়ার চলছে — স্কোপ বা ডিপ্লয়ে অমিল; গেটওয়ে নিজের OpenAPI হেলথ চুক্তি ভাঙছে; সার্ভিস রেজিস্ট্রি খালি। বিস্তারিত অপারেটর অডিট লগে।

*No secret values were read or transmitted; cited key names are public in the deployment manifest.*
