# Heartbeat Protocol

Telemetry contract for agent liveness, task ownership, and orphan release in the
SupremeAI Federation. This protocol is SSOT'd in `api-schemas/heartbeat.schema.json`;
this document is the human-readable companion.

**Related:** issue #48 (`feat(telemetry): define task queue audit and heartbeat telemetry data contract`),
`docs/AGENT_LOOP_SPEC.md`, `AGENTS.md` §6 (heartbeat).

---

## 1. Purpose

Every running agent must emit periodic heartbeats to assert liveness on its
claimed task. The heartbeat server (or a fail-closed gate in the agent loop)
uses the TTL to detect orphaned tasks: if no heartbeat is received within
`ttl_seconds` from the agent's last timestamp, the task is released for
re-claim by another agent.

This prevents a dead/stuck agent from indefinitely holding a task slot — the
**duplicate-claim rejection** contract (#2596) depends on timely release.

## 2. Heartbeat Payload

Schema: `api-schemas/heartbeat.schema.json`

| Field           | Type    | Required | Description |
|-----------------|---------|----------|-------------|
| `agent_id`      | string  | yes      | Unique agent identifier matching `agent-[a-zA-Z0-9_-]{1,64}` (e.g. `agent-1`, `agent-coder`). |
| `task_id`       | string  | yes      | Identifier of the claimed task. Empty string when the agent is idle and holds no task. |
| `status`        | enum    | yes      | Current status: `alive` (responsive, on-task), `busy` (actively executing), `idle` (running, awaiting assignment). |
| `timestamp`     | string  | yes      | RFC 3339 / ISO 8601 UTC timestamp of emission (e.g. `2026-10-15T14:30:00Z`). |
| `ttl_seconds`   | integer | yes      | Lease duration (30–3600s, default 300). If no heartbeat arrives within this window from the last timestamp, the task is orphaned-eligible. |
| `task_group`    | string  | no       | VALID_GROUPS tag for the task (e.g. `agent-orchestration`, `quality`). Enables audit by group. |
| `heartbeat_seq` | integer | no       | Monotonic sequence number for ordering and gap detection. |

## 3. Timing Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Heartbeat interval | 90 s (recommended) | Must be < ttl_seconds; aligns with MCP Tower `agent_heartbeat` TTL of 300 s (#61). |
| Registry TTL | 300 s (5 min) | Default `ttl_seconds` in the schema. |
| Orphan release threshold | 30 min | Hard ceiling. Even if an agent's declared TTL is longer, the federation treats 30 minutes of silence as a lost heartbeat and releases the task. Prevents indefinite stale holds. |
| First heartbeat window | 90 s | An agent must emit its first heartbeat within 90 s of start, or the claim gate treats the reservation as stale. |

## 4. Orphan Release Procedure

When a task is detected as orphaned (no heartbeat ≥ ttl_seconds):

1. The claim marker for the orphaned task is cleared.
2. The task re-enters the claimable pool with `status:unclaimed`.
3. The `--pick-next` scan and any waiting agents may re-claim it immediately.
4. Any partial state written by the orphaned agent is logged for audit but not
   trusted — the task starts fresh from its declared contract.

## 5. Queue Audit Report Structure

The queue audit report (produced by `scripts/agents/continuous_agent_loop.py`
or a dedicated audit command) includes:

```json
{
  "generated_at": "2026-10-15T14:30:00Z",
  "agents": {
    "agent-1": {
      "task_id": "bridge-20261015-issue-114-pr-body-ssot",
      "status": "busy",
      "last_heartbeat": "2026-10-15T14:28:30Z",
      "ttl_seconds": 300,
      "orphan_eligible": false
    }
  },
  "orphaned_tasks": [],
  "claimable_pool_count": 27,
  "running_agents_count": 3
}
```

| Field | Description |
|-------|-------------|
| `generated_at` | UTC timestamp the report was produced. |
| `agents` | Map of `agent_id` → current task/status/last heartbeat. |
| `orphaned_tasks` | List of task IDs that have exceeded the orphan threshold. |
| `claimable_pool_count` | Number of tasks ready for `--pick-next`. |
| `running_agents_count` | Live agent count (excluding stale/orphaned). |

## 6. Integration Points

- **MCP Tower:** `agent_heartbeat` tool (§5 of `AGENTS.md`) — slot `agent-<N>`, TTL 300 s.
- **Agent Loop:** `continuous_agent_loop.py` emits a heartbeat on each cycle;
  the Merge Gate and claim gate read heartbeat state for freshness checks.
- **Claim Gate:** rejects claims on tasks held by a `busy` or `alive` agent with
  a fresh heartbeat; allows reclaim on orphaned tasks.
- **Audit:** `docs/AUDIT_2026-10-15.md` references heartbeat-based liveness as
  part of agent-orchestration group verification.

**Do not duplicate:** the `--pick-next` claimable scan already excludes
`mirror:private` issues (#122) and enforces single-PR-per-issue de-dup (#111);
the heartbeat protocol does not alter those rules — it only governs task release.
