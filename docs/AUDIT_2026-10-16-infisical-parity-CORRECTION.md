# AUDIT CORRECTION 2026-10-16 — Infisical Vault Findings Revised

Supersedes finding A1 of the same-day parity audit (issue #437). Root cause of the error: this auditor queried the structured secrets endpoint, which returns a silent empty list because of the vendor blind-index defect reported in the operator ops notice. No vault data was ever absent — the wrong route simply answers zero rows.

## Corrected facts

- The vault is fully populated. Raw-route counts: prod 204, staging 11, dev 25 secrets (read-only audit identity).
- The control-plane bootstrap already reads the raw route; the earlier boot paradox is dissolved. No deploy drift, no identity mis-scope.
- Deploy-manifest parity, measured: 16 of 21 manifest keys are present in the prod vault. Five are vault-absent: INFISICAL_PROJECT_ID and INFISICAL_TOKEN (bootstrap recursion — acceptable by design), plus TOWER_AUTH_TOKEN, GH_TOKEN, GITHUB_TOKEN (runtime-critical keys that live only in the platform dashboard — rotation and audit cannot see them).

## Findings that stand (re-verified live, 2026-10-16T21:0xZ)

- A2 stands: the tower health endpoint reports a service registry of zero while at least three federation services are live.
- A3 stands: the gateway serves no health route on any path variant (404) against its OpenAPI contract; an independent work-order probe recorded the same no-server routing state.
- A5 and A6 stand unchanged.

## Updated asks

1. Vault audit tooling must read the raw route; the structured route stays unusable until the vendor defect clears. The ops notice cites issue #434 for this defect, but public issue #434 is an unrelated work order — please reconcile the reference.
2. Mirror the three runtime-critical dashboard-only keys (TOWER_AUTH_TOKEN, GH_TOKEN, GITHUB_TOKEN) into the vault, or document their dashboard-only status in the deployment manifest so rotation covers them.
3. The operator vault tooling (synthetic vault check, credential bootstrap and manager scripts, integration guide, identity scope doc) is not on public main; when publishable, a public pointer would help external auditors use the raw route correctly.
4. Original asks of #437 remain for A2, A3, A5, A6.

বাংলা: আগের A1 ভুল ছিল — ভল্ট খালি নয়; raw রুটে prod-এ ২০৪টা সিক্রেট আছে (structured রুট vendor-defect-এ ০ দেয়)। আসল অমিল: ৫টা ম্যানিফেস্ট কী vault-এ নেই — তার মধ্যে TOWER_AUTH_TOKEN, GH_TOKEN, GITHUB_TOKEN শুধু ড্যাশবোর্ডে বাস করে, রোটেশন/অডিট দেখতে পায় না। A2/A3 পুনঃযাচাইকৃত — টাওয়ার রেজিস্ট্রি এখনো ০, গেটওয়ে হেলথ রুট এখনো 404।

*No secret values read or transmitted; identifiers redacted; audit identity read-only.*
