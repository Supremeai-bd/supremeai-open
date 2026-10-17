# supremeai-browser — Agent Governance Constitution

## Superadmin Authority Mandate

This satellite is governed by the Superadmin Authority Mandate: the human
superadmin (via the supremeai-command control plane) holds final authority
over every push, merge, and runtime action performed inside this repository.
Autonomous agents are delegated workers; they never outrank the mandate.

## Two-Tier Ingress Invariant

Work enters this repository through exactly two gates, in strict order:

1. **No Claim → No Branch.** An agent must hold a verified claim (label plane
   `status:claimed` or an atomic-claim comment per S0.1 / Invariant #430) on
   an open work-order issue BEFORE creating any branch.
2. **No Branch → No Push.** A branch may only be pushed when it is bound to
   that claimed issue (TaskIssue token in the work order body), and only
   through the Bridge submission lane — never by direct credential push.

Violations are constitutional breaches, not style issues.

## Boundary Limits

- **Stdlib-only core.** `runtime/` imports the standard library only; heavy
  dependencies (playwright, lxml) are OPTIONAL execution-tier extras guarded
  by capability probes. Offline verification must always succeed.
- **No network in tests.** The verification battery is fully offline. Any
  test that dials out is defective by definition.
- **No real browser launches in CI.** Session lifecycle is exercised via
  capability probes and CDP endpoint validation only.
- **Fail-closed everywhere.** Missing capabilities, empty allowlists, and
  unknown inputs raise precise errors; nothing silently degrades.
- **Walled-garden discipline.** The cookie bridge starts with an EMPTY
  allowlist; domains are operator-approved, values are redacted in logs.
- **No banned driver strings.** The stealth normalization table carries
  standard vendor/renderer shapes only; the reflection grep must stay at
  zero hits inside `runtime/`.
- **Secret hygiene.** No credentials in code, config, or logs; env-only
  configuration; redacted reprs for anything sensitive.
