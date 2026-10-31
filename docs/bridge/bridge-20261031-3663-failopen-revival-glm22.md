# P0 #3663 fail-open class REVIVED by the #4249 restore — machine verdict exit 2

**Agent:** GLM Agent 22 (Job 486813) · **Cycle 13 (2026-10-31 16:2x+08)** ·
report-only, no claim, no Closes — the security decision is owner/HITL lane.

## Premise (live-verified this cycle)

- Owner landing `d23a82e` (**#4249** "restore mcp control tower default
  pre-production role to admin (#762)") deliberately rolled the tower's
  default role back to admin. glm16 r10 (#4254) recorded the era flip as
  "RBAC ERA ENDED". **No receipt yet records the security consequence at the
  wire.** This receipt is that record.
- Correlated wire state (anonymous streamable session, this cycle):
  `tools/list` roster **158 descriptors** (was 20 under the purge),
  `system_summary` **21/21 services** (was 12/12).

## Machine verdict — `scripts/tower/p0_3663_acceptance_probe.py`

```
[INDETERMINATE] 1_identity_not_admin: own ctx not observable (only third-party
                principals: role='core-api'; 'async-worker'; 'browser-scraper';
                'mcp-control')
[      EXPOSED] 2_client_list_is_error: anonymous session listed 100 client
                rows (PII plane open)
[      EXPOSED] 3_destructive_tools_hidden: destructive surface visible
                anonymously: autonomy_kill_switch, github_list_secrets,
                tenant_create
P0 #3663 FAIL-OPEN STILL LIVE (2/3 criteria exposed) — pre-deploy expected
state; owner redeploy pending
exit code: 2
```

- The probe's aggregation treats EXPOSED as the only fail-open trigger (the
  Cycle-3 false-alarm fix), so exit 2 here is a clean, deliberate verdict:
  **the exact class #3663 fixed is live again at the wire.**

## Guard chain — the #3959 note has now fired in both directions

"#3959" guard note: *any toolset change must keep the #3663 probe green.*

| Toolset change | Probe result | Meaning |
| - | - | - |
| Cycle 8: roster purge (158→20) | exit 3, NO EXPOSURE | purge was RBAC-safe |
| Cycle 13: restore #4249 (20→158, admin default) | **exit 2, EXPOSED 2/3** | restore re-opened the fail-open class |

The guard is therefore demonstrated as a real two-way tripwire, not prose:
it stayed green through a safe change and went red through an unsafe one.

## Impact ledger (what is open vs what still holds)

- Open anonymously (as of this cycle): full tool roster incl. destructive
  class (kill switch, secrets listing, tenant create), client_list PII plane
  (100 rows), 21-service system summary.
- Still holding: the bridge front door (work_claim / bridge_submit /
  bridge_work_queue authenticated reads — this receipt itself is submitted
  through them), the loop's 9-tier verify, all local guards, and the
  #4132 gate's honest dark-note semantics (github.list_prs is still absent
  from the roster even at 158 — PR-plane stays dark and the auto-revive
  correctly has not fired).

## Decision framing (owner lane)

#4249's own message says the restore is deliberate pre-production posture;
whether that trade is acceptable before the next production deploy is an
owner/HITL call, not an agent's. What this receipt adds: the probe is a
one-command deploy-window gate (`exit 0/3 = safe to proceed; exit 2 = the
#3663 class is live`), so the decision can be armed mechanically rather
than argued.

## Reflection Evidence

- **why:** the guard note existed precisely for this moment; a toolset
  change landed, the probe went red, and the only durable response is a
  machine-verifiable ledger row — not a chat note that evaporates.
- **alternatives_rejected:** re-filing/reopening #3663 itself (closed
  completed with an owner-landed fix; the new state is a deliberate
  post-fix restore — a NEW decision, not the old issue); agent-side
  mitigation of the exposure (none exists client-side; the wire is the
  owner's plane); staying silent because the restore was intentional
  (intent does not make the wire safe — recording it does).
