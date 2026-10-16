---
id: tower-health-runbook
title: "Tower Health Triage Runbook — status semantics, degraded/expired investigation, alerting thresholds"
document_role: runbook
status: active
canonical: true
owner: governance
last_verified: 2026-10-16
related_docs:
  - docs/HEARTBEAT_PROTOCOL.md
  - docs/OPS_ACTIONS_QUOTA_RUNBOOK.md
  - AGENTS.md
source_issue: 252
source_pr: null
supersedes: []
superseded_by: []
---

# Tower Health Triage Runbook

One findable operational record for classifying and triaging non-healthy states
reported by the MCP Tower `system_health` / `system_summary` / `agent_status`
snapshots. Filed against the 2026-10-16 triage snapshot (**issue #252**).
Zero secrets in this document — probe URLs and env refs are names only.

**Evidence snapshot (live recheck, 2026-10-16T01:39 UTC):** `system_health`
reported **29/30 healthy, 0 degraded, 0 unreachable, 1 unconfigured**;
`agent_status` reported 13 agents, `onlineAutonomous: 0`,
`onlineInteractive: 7`. The three findings of issue #252 are each resolved in
§3–§5 with this evidence.

---

## 1. Status semantics (read before triaging)

Tower health probes (SSOT:
`infrastructure/mcp-control-plane/src/tools/system.tools.ts`) emit exactly four
service states; the agent registry emits two agent states. Treating a state
with the wrong severity is the #1 triage error.

| State | Meaning | Incident? |
|---|---|---|
| `healthy` | Probe succeeded within latency budget. | No. |
| `degraded` | Probe succeeded but slow / partial (e.g. Redis read-write check latency spike). Investigate; may be transient. | Only if persistent (§6). |
| `unreachable` | Probe failed (network/5xx/auth). | Yes — treat as outage until proven transient. |
| `unconfigured` | Required credential/env **not provisioned in tower env** — the integration is intentionally disabled, not broken. | No (informational). See §5. |

Agent states (`agent_status`):

| State | Meaning | Incident? |
|---|---|---|
| `online` | Heartbeat within registry TTL (default 300 s). | No. |
| `expired` | No heartbeat within TTL — session ended without explicit deregistration, or agent died. Stale record until TTL cleanup. | Only if the slot should be live right now (§4). |

`unconfigured` is **by design** for optional integrations: e.g. WhatsApp
reports `unconfigured` when `WHATSAPP_ACCESS_TOKEN` or `WHATSAPP_WEBHOOK_URL`
is missing from the tower env (`system.tools.ts` WhatsApp probe: *"WHATSAPP_ACCESS_TOKEN
or WHATSAPP_WEBHOOK_URL missing in tower env"*). Unconfigured ≠ unreachable.

---

## 2. Investigation workflow (decision tree)

For every non-healthy finding, run the read-only MCP checks **in this order**
and record outputs before touching anything:

1. **Re-probe immediately** — `system_health` + `system_summary`. Many
   `degraded` findings are single-probe latency spikes on shared platforms
   (Render, Upstash, Cloudflare, Supabase). If the re-probe is `healthy`,
   classify **transient**, attach both probe outputs, done.
2. **Identify the affected service** by `id` (e.g. `redis-primary`,
   `whatsapp-primary`) and check the `displayName`: Tower annotates provider
   failover in the name (e.g. `Upstash Redis (Cache + Queue
   [auto-rotated: tertiary])`) — auto-rotation already contained the fault.
3. **Classify** with the table in §1:
   - `unconfigured` → verify which env var gate produced it (§5), document
     expected state, close as informational.
   - `degraded` persistent across ≥3 probes / ≥15 min → escalate per §6.
   - `unreachable` → escalate immediately per §6.
4. **For agent findings** (`expired`, 0 online builders): cross-check
   `agent_status` (registry entry, `clientId`, `lastHeartbeat`, `ageSeconds`)
   against `slot_status(name=<slot>)`. If the slot registry answers
   `Slot not found`, the record is a **stale heartbeat from an ended session**
   — nothing to restore (§4).
5. **Attach evidence** (probe outputs, timestamps, latency values) to the
   tracking issue. No secrets, no tokens, no raw env dumps.

---

## 3. Finding 2026-10-16 — Redis `redis-primary` degraded (~796 ms / 1598 ms)

**Symptom (2026-10-16 snapshot):** `redis-primary` reported `degraded` with
latency ~796 ms; follow-up sweep measured 1598 ms after auto-rotation.

**Root cause:** upstream Upstash regional latency spike on the primary
endpoint. Tower's provider auto-rotation failed over cache+queue to the
tertiary endpoint (visible in `displayName`: `[auto-rotated: tertiary]`), so
cache and queue operations continued throughout.

**Impact:** brief elevated read/write latency; no data loss; no queue outage.

**Recheck evidence (2026-10-16T01:39 UTC):** `redis-primary` → `status:
healthy`, `latencyMs: 5`. **Resolved as transient.**

**Relation to other tracking:** systemic high probe latency (1.5–2.5 s average
across all 30 endpoints) is a separate, pre-existing concern tracked in
issue #256 — do not re-file Redis latency there or vice versa.

---

## 4. Finding 2026-10-16 — autonomous builder `agent-1` expired, 0 online builders

**Symptom:** `agent_status` showed `agent-1` (kind `autonomous_builder`,
source `mcp-tower`, clientId `named_zai-open-agent-render-logs-fix`) with
`lastHeartbeat 2026-10-15T13:38:37Z`, `ageSeconds: 43268` (~12 h), state
`expired`; `onlineAutonomous: 0`.

**Root cause:** the heartbeat record belongs to the **render-logs-fix agent
session that finished on 2026-10-15** and ended without an explicit
deregistration call. Per [HEARTBEAT_PROTOCOL.md](HEARTBEAT_PROTOCOL.md) the
registry TTL is 300 s and the orphan-release threshold is 30 min — `expired`
is the protocol's correct terminal classification for that stale record.

**Cross-check:** `slot_status(name: "agent-1")` → `Slot not found: agent-1`.
The named-slot registry no longer contains the slot; only the aged heartbeat
entry remains. **There is nothing to restore.**

**Impact:** none. Autonomous builders register on demand when a named session
starts heartbeating; `onlineAutonomous: 0` is the steady state between
sessions. Interactive assistant lanes were unaffected (7 online at recheck).

**Decision:** no restore action; document as expected lifecycle.

**Hardening follow-up (owning production repo):** agents should call
deregister/clear on shutdown so ended sessions do not leave `expired` records
in the registry for up to the retention window. Not implementable from this
public repo — tracked here for the Tower maintainers.

---

## 5. Finding 2026-10-16 — `whatsapp-primary` unconfigured

**Symptom:** `whatsapp-primary` ("WhatsApp Alerts Bot") reported
`status: unconfigured`, `latencyMs: null`.

**Root cause / expected state:** the WhatsApp probe requires
`WHATSAPP_ACCESS_TOKEN` + `WHATSAPP_WEBHOOK_URL` (plus phone-id/recipient for
the Meta Cloud API path — see
`infrastructure/mcp-control-plane/src/adapters/notify/actions.ts`) in the
tower env. None are provisioned; the notify adapter reports the integration
as unavailable instead of failing.

**Decision:** **intentional unconfiguration**, not an incident. Alert routing
runs through the other configured notify channels. To enable: provision the
WhatsApp env refs in the tower env (secret values stay in the vault, never in
repo/docs) and re-probe; expected result is `healthy` with measured latency.

---

## 6. Alerting guidance (when to page, when to document)

| Condition | Severity | Action |
|---|---|---|
| Any `unreachable` on a core lane (render-primary, github-*, mcp-control) | High | Open incident immediately; attach probe output; check provider status page. |
| `degraded` persisting ≥3 consecutive probes or ≥15 min | Medium | Investigate per §2; check provider auto-rotation annotation; file tracking issue if provider-side. |
| Single-probe `degraded` that clears on re-probe | Informational | Attach both probe outputs to the triage issue; no incident. |
| Agent `expired` while its slot still exists AND work was expected | Medium | Re-register/heartbeat or reassign the task; check orphan release per HEARTBEAT_PROTOCOL §4. |
| Agent `expired` with `Slot not found` (stale record) | Informational | Document; no action (this case). |
| `unconfigured` on an integration with no provisioning contract | Informational | Document expected state (§5). |
| `unconfigured` on an integration that SHOULD be live | Medium | Provision env refs; re-probe; confirm `healthy`. |

**Re-probe cadence for triage:** immediately, +5 min, +15 min. Two consecutive
healthy re-probes close a transient finding.

**Evidence template** (attach to the issue, redact everything secret):

```
probe: system_health @ <RFC3339Z>
summary: <X>/30 healthy, N degraded, N unreachable, N unconfigured
finding: <service-id> status=<state> latencyMs=<n> note=<auto-rotation/etc>
recheck: system_health @ +5min → <result>
recheck: system_health @ +15min → <result>
classification: transient | persistent | expected-unconfigured | stale-record
```

---

## 7. Verification & change log

- 2026-10-16: initial runbook filed from issue #252 triage. Live recheck
  evidence: 29/30 healthy; `redis-primary` healthy @ 5 ms (transient
  resolved); `whatsapp-primary` unconfigured (expected); `agent-1` expired =
  stale record from ended 2026-10-15 session, slot registry empty for that
  slot, `onlineAutonomous: 0` steady-state. All claims in this document are
  reproducible with the read-only MCP tools `system_health`, `system_summary`,
  `agent_status`, `slot_status`.
