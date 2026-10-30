# Bridge Receipt — P0 #3663 post-deploy acceptance probe (report-only tooling)

- **taskId:** `bridge-20261031-3663-acceptance-probe-glm22`
- **agent:** GLM Agent 22 (Job 486813), cron cycle 2026-10-31 03:2x+08
- **base:** main @ `957119c` · claim taken: **NONE** (owner-lane row; report-only)
- **kind:** report-only tooling — no auth change, no Closes, no claim, no closure ask

## Premise (re-verified on HEAD 957119c, 2026-10-30T19:3xZ)

- `infrastructure/mcp-control-plane/src/http_server.ts` still carries the fail-open
  default at all three fallback sites: L988 `slotRole ?? refreshedClient?.role ?? role ?? "admin"`,
  L1020 `role ?? "admin"`, L1119 `sessionRole = slotRole ?? refreshedClient?.role ?? role ?? "admin"`.
  L1119 remains the third site the issue text (which names only L988/L1020) does not enumerate —
  the eventual fix must cover it or a fail-open path survives.
- Issue #3663 labels: `P0-critical`, `security`, `status:unclaimed`. 21 open PRs —
  none touches the control plane or references #3663. Receipt WOs #3670/#3672/#3676 are
  report-only corroborations; no solver is in flight (idempotency check per Universal Invariant 5).
- Filer directive (verbatim): *"needs owner's guest-role-set decision + deploy window …
  not an agent patch"* — honored here.

## New artifact: `scripts/tower/p0_3663_acceptance_probe.py`

The issue's acceptance criteria existed only as prose. Every fresh agent re-derived the
exposure anatomy by hand (the same re-derivation treadmill the stale-incident demotion
removed for CI rows). This tool makes the criteria machine-checkable, for the owner's
deploy window AND for every later cycle:

1. **Fresh anonymous session → `!ctx.isGlobalAdmin && ctx.role != "admin"`** — honest
   INDETERMINATE unless a session-scoped identity plane answers; infra summaries list
   third-party principals and prove nothing about own-ctx (misclassification guard).
2. **`client.list` returns isError** — anonymous `client_list scope="*"` returning rows
   is the fail-open signature; 88-row/PII plane measured.
3. **`tools/list` omits `autonomy_kill_switch` / `tenant_create` / `github_list_secrets`** —
   fragment-based matching so naming drift cannot defuse the tripwire; top-level
   JSON-RPC method with legacy-envelope tolerance.

Safety envelope: allowlist of exactly three read-only calls (`system_summary`,
`client_list`, `tools/list`) enforced before the wire — destructive tools are
unreachable from this code path; no credentials read or stored; URL resolution is
SSOT-imported from `scripts/agents/mcp_tower_client.py` (no hardcoded endpoint).
Offline `--self-test`: 12/12 PASS (classifier matrix incl. third-party-role
misclassification and allowlist refusal).

## Live run (2026-10-30T19:33Z, pre-deploy expected state)

```
[INDETERMINATE] 1_identity_not_admin: own ctx not observable (only third-party principals)
[      EXPOSED] 2_client_list_is_error: anonymous session listed 88 client rows (PII plane open)
[      EXPOSED] 3_destructive_tools_hidden: autonomy_kill_switch, github.list_secrets, tenant_create
P0 #3663 FAIL-OPEN STILL LIVE (2/3 criteria exposed) — owner redeploy pending
```

Exit codes for scripting: 0 fail-closed (remediated) / 2 fail-open / 1 indeterminate —
so the owner can wire it into the redeploy window as a gate, and cron agents get a
one-command fresh-evidence run instead of hand-built probes each cycle.

## Reflection Evidence

- **why:** the P0 holds the entire cadence (pick: "no clean pick — P0 drain hold") while
  its only remedy is owner-lane; four receipts already agree on the anatomy. The missing
  piece was not a fifth opinion — it was making the issue's own acceptance criteria
  executable so the owner's redeploy can be verified mechanically and future agents stop
  re-deriving the same probe by hand (root cause of the cycle-cost, not another symptom note).
- **alternatives_rejected:** (1) landing the L988/L1020/L1119 `?? "viewer"` flip myself —
  explicitly forbidden by the filer's blast-radius judgment, concurred by receipts
  #3670/#3672/#3676; this receipt does not override recorded consensus. (2) a fifth
  report-only corroboration — duplicate of #3670/#3672/#3676, zero new information.
  (3) relaxing `has_open_p0_blocker()` for content-level owner-lane P0s — routing-policy
  change above agent lane; the label SSOT must not be gamed by body-text parsing.
- **rollback:** delete `scripts/tower/p0_3663_acceptance_probe.py` — single additive file,
  no imports point at it, no CI wiring, runtime dep is `requests` (already required by
  the imported client module).

## Post-redeploy verification (2026-10-31 06:2x+08 cycle, HEAD f1677a5) — probe r2

- **The fix landed and the live tower was redeployed**: all three fallback sites now read
  `?? DEFAULT_GUEST_ROLE // #3663 fail-closed (was ?? "admin")` — including L1119, the
  third site this receipt flagged (issue text enumerated only L988/L1020). Loop preflight
  at 06:2x+08: "zero open P0 architectural blockers on the live board" — the P0 gate lifted.
- **Probe r2 (two defects found and fixed by its own first real verdict):**
  1. aggregation bug — the else-branch fired on any non-uniform verdict set, so the
     post-redeploy mixed state (fail-closed + indeterminate, zero exposed) was mislabeled
     "FAIL-OPEN STILL LIVE" — a false alarm that would have kept the fleet believing the
     redeploy never happened. `aggregate()` is now a pure function; exposure is the ONLY
     fail-open trigger; exit 3 = "no exposure observed, acceptance incomplete".
  2. criterion-2 classifier gap — the redeploy's deny arrives as plain prose inside the
     content envelope ("Forbidden: … default-deny RBAC"), not a JSON-RPC error plane or
     isError JSON; deny-marker recognition added (self-test 12/12 → 17/17 PASS).
- **Live acceptance run 06:3x+08 (exit 3):**
  `[INDETERMINATE]` criterion 1 — own-ctx still not observable via system_summary
  (honest; no identity tool on the anonymous 20-tool surface);
  `[FAIL-CLOSED]` criterion 2 — client_list answers deny prose (default-deny RBAC);
  `[FAIL-CLOSED]` criterion 3 — anonymous tools/list = 20 descriptors (was 158),
  zero matches kill_switch/tenant_create/list_secrets; bridge front door intact
  (work_claim/bridge_submit/bridge_work_queue all still reachable — matches the
  Cycle-1 deploy-window matrix prediction that only the github read family degrades).
- **Acceptance status:** 2/3 fail-closed + 1/3 indeterminate = positive redeploy
  evidence; full 3/3 closure needs a session-scoped identity observable (owner option:
  a whoami-class viewer tool would let the probe assert criterion 1 mechanically).
- Same cycle, dispatch hygiene: pick served CI-incident tracker #3858 (PR #3534 parity
  guard) but its feedback plane shows a LIVE claim (contributor-agent 22:25:18Z, TTL 30m
  — minutes old at 06:3x+08) → skip-with-evidence, no stampede; the row belongs to its
  active solver.
