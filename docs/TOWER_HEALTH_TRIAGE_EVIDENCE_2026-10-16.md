# MCP Tower Health Triage Evidence — 2026-10-16 (Issue #252)

- Author: zai-autonomous-contributor (Z.ai Code autonomous contributor agent)
- Task ID: `bridge-20261016-tower-health-triage-252`
- Base: Supremeai-bd/supremeai-open main `8242d4e`
- Lane: zero-credential Pathway 1 (bridge WO, patch = this evidence doc)
- Trigger: issue #252 "[MCP Tower Audit] Investigate degraded Redis health and expired autonomous-builder heartbeats"
- U2 note: this lane cannot comment on issues or read private Render logs; every claim below carries a verbatim sanitized snapshot and an explicit "cannot verify" boundary where one exists.

## Findings and root-cause classification

### F1 — Redis degraded (RESOLVED: transient, self-recovered)

| Time (UTC, 2026-10-16) | Source | Observation |
|---|---|---|
| ~01:17 | #252 audit snapshot | `redis-primary` status `degraded`, latency ~796 ms |
| 01:37:27 | this lane, `system_health` | `29 healthy · 0 degraded · 0 unreachable · 1 unconfigured (of 30)` |
| 02:03:15 | this lane, `system_health` | `redis-primary` → `status: healthy`, `latencyMs: 2`; `35 healthy · 0 degraded · 0 unreachable · 1 unconfigured (of 36)` |

Classification: **transient Upstash latency spike, fully self-recovered within ~20 minutes; no configuration or credential fault, no outage.** The current service entry reads `Upstash Redis (Cache + Queue [auto-rotated: tertiary])` — the tower's automatic instance-rotation annotation is present, consistent with a failover/rotation having absorbed the instability. No code or config change is required from the public repo (the runtime lives in the tower's own Render deployment, outside this repository). Impact while degraded: none attributable — no bridge WO in the 01:15–01:40 window failed on a Redis-dependent step (queue operations and issue creation continued throughout; the two submission failures in that window were independently root-caused by the submitting agent as GitHub issue-title length limits, not Redis).

### F2 — Autonomous builder slot `agent-1` expired (AWAITING OPERATOR; not restorable from this lane)

Verbatim `agent_status` record (02:00:24.186Z, sanitized — no tokens present):

```json
{
  "kind": "autonomous_builder", "slot": "agent-1", "agentId": "agent-1",
  "source": "mcp-tower", "clientId": "named_zai-open-agent-render-logs-fix",
  "updatedAt": "2026-10-15T13:38:37.915Z",
  "ageSeconds": 44506, "state": "expired"
}
```

- Counts at 02:00:24Z: `autonomousBuilders: 1, onlineAutonomous: 0, interactiveAssistants: 12, onlineInteractive: 11`.
- The builder last heartbeated 2026-10-15 13:38:37 UTC and has been expired ~12.4 h. Its registration name (`named_zai-open-agent-render-logs-fix`) indicates it was working a render-logs fix; whether that work completed before shutdown cannot be verified from the public lane (the builder operates against the private codebase).
- Consistency observation: `slot_status(name="agent-1")` now returns `Slot not found: agent-1` while `agent_status` still lists the expired agent record — the slot registry and the agent registry have diverged (the slot entry appears to have been de-registered while the historical agent record persists). Documented here so the owner knows both views were checked, per the issue's task list.
- Restoration path: per the tower's own guidance (`bridge_guide` → escalation; `infrastructure/mcp-control-plane/PROVIDER_NEUTRAL_CONNECTIONS.md`), claim/heartbeat/complete for the agent role requires an operator-issued bearer token via the admin-protected `/clients` endpoint. **A zero-credential external agent cannot and must not attempt to re-register the builder.** State recorded as intentional-await-operator.
- Owner recommendation: either re-register the builder slot (and confirm the render-logs-fix work item is covered — no public WO carries that slug) or document the shutdown as intentional in the runbook.

### F3 — WhatsApp unconfigured (documented expected-unknown; not an incident)

- `whatsapp-primary` ("WhatsApp Alerts Bot") is the only unconfigured service: `1 unconfigured (of 36)` at 02:03:15Z, `latencyMs: null`.
- Repo-wide markdown search for `whatsapp`: **0 references** — the public repository documents no expected configured state for this integration, so "intentional" cannot be confirmed from the public lane (honest limit). Following the issue's own framing ("triage issue, not a claim that Redis or the agent is definitively down"), this is treated as **not-an-incident**.
- Follow-up: the owner should record the expected state once; the natural home is the health-triage runbook being filed separately (sibling WO #267, `docs/TOWER_HEALTH_RUNBOOK.md`) — not duplicated here per U4.

## Issue #252 task mapping

| #252 checklist item | Resolution |
|---|---|
| Inspect Redis probe details / transient vs config vs outage | F1 — transient, self-recovered; three-snapshot evidence above |
| Verify builder slot should run; restore or document | F2 — expired 12.4 h; restoration requires operator token (documented path); recorded as intentional-await-operator |
| Confirm WhatsApp intentional; document expected state | F3 — unconfigured, no public doc of expected state; not-an-incident; owner confirmation recommended |
| Add/update alerting/runbook guidance | Covered by sibling WO #267 (`docs/TOWER_HEALTH_RUNBOOK.md`) — referenced, not duplicated (U4) |
| Re-run health and agent-status checks; attach evidence | Done — snapshots at 01:37:27Z, 02:00:24Z, 02:03:15Z embedded above |
| Follow-up fixes in owning production repo | Redis/WhatsApp/builder runtime is tower-internal (Render + Upstash), not this repo; nothing to patch here beyond this record |

## Evidence log (sanitized)

- 01:37:27Z `system_health`: `29 healthy · 0 degraded · 0 unreachable · 1 unconfigured (of 30)`.
- 02:00:24Z `agent_status`: agent-1 expired record (verbatim above); 11/12 interactive online.
- 02:03:15Z `system_health`: `redis-primary` healthy 2 ms; `whatsapp-primary` unconfigured null; `35 healthy · 0 degraded · 0 unreachable · 1 unconfigured (of 36)`.
- 02:0x `slot_status(name="agent-1")`: `Slot not found: agent-1`.
- No secrets or tokens appear in any captured output (tower health/agent snapshots carry service ids, latencies, and registration names only).

## U9 sweep report

similar found: 0 | fixed in-task: 0 | filed follow-up: 0 — runbook guidance already owned by sibling WO #267; CI-side fixes already owned by sibling WOs #266/#270/#271/#272; no additional follow-ups discovered during this triage.

## References

- Issue #252 (this triage's source) · WO #267 (health runbook, sibling) · WOs #266/#270/#271/#272 (CI fixes, siblings)
- `infrastructure/mcp-control-plane/PROVIDER_NEUTRAL_CONNECTIONS.md` (operator token path) · `docs/HEARTBEAT_PROTOCOL.md` (heartbeat lifecycle)
