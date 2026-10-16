---
id: federated-ci-watcher
title: "Federated CI Failure Watcher — Auto-Issue Reporter & Cross-Repo Task Normalizer (#199)"
document_role: reference
status: active
canonical: true
owner: coder
last_verified: 2026-10-16
related_docs:
  - AGENTS.md
  - docs/AGENT_LOOP_SPEC.md
  - api-schemas/federated-ci-failure.schema.json
---

# Federated CI Failure Watcher (#199)

Automated ecosystem self-healing: the moment any federation repository's GitHub
Actions run fails, an **actionable, standardized issue** opens on the control
plane (`Supremeai-bd/supremeai-open`) so autonomous agents can claim and patch
the breakage in seconds instead of waiting for a human sweep.

Implemented as `src/events/federated_ci_watcher.ts` in
`infrastructure/mcp-control-plane` — a **gateway listener on the existing
normalizer→EventGateway pipeline**. No second event bus, no new webhook
endpoint (same doctrine as the #69 bridge intake).

## How it listens

```
GitHub webhook (workflow_run.completed) ──► POST /webhooks/github
  └─ signature check → EventNormalizer.normalizeGitHubEvent
       └─ globalEventGateway.dispatch(NormalizedEvent)
            └─ FederatedCiWatcherService.handle(event)      ← this module
                 ├─ decide()       pure relevance policy
                 ├─ dedupe ×2      deliveryId + eventKey (TTL)
                 ├─ rate cap       rolling issues/hour ceiling
                 └─ queue → jobs enrichment → create issue on reportRepo
```

The generic `/webhooks/github` route already forwards **every** event type
through the normalizer, so no routing change is needed. Deployment requirement:
the repository/org webhook must **subscribe to `workflow_run` events** (same
place the `issues`/`pull_request` subscriptions for bridge intake are set).

## Relevance policy (fail-closed)

An event produces a report only when ALL hold:

1. `source === "github"` and `type === "workflow_run"`;
2. `payload.action === "completed"`;
3. `payload.workflow_run.conclusion === "failure"` — **strict**: v1 ignores
   `startup_failure`/`timed_out`/`cancelled` (contract bump required to extend);
4. the repository passes the federation scope check:
   - if `FEDERATED_CI_WATCHER_REPOS` is set → explicit allowlist (case-insensitive);
   - otherwise the **same-org default**: any repo owned by the same owner as
     `FEDERATED_CI_WATCHER_REPORT_REPO` (the fleet is org-scoped; a hardcoded
     14-repo list would drift);
5. `workflow_run.id` is present (the dedupe/anchor key requires it).

Everything else is dropped with a machine-readable reason
(`[CI_WATCHER] skip (<reason>)`).

## Anti-spam Poka-yoke (a bug here could spam the board)

Three independent gates, in order:

| Gate | Key | Default |
|---|---|---|
| Delivery idempotency | `X-GitHub-Delivery` header | TTL 24 h |
| Event-key dedupe | `ci-failure:<repo>:<workflow>:<runId>:<runAttempt>` | TTL 24 h |
| Global rate cap | rolling 1-hour emission window | 6 issues/hour |

Notes: a re-run of the same run id under a **new attempt** is a new failure
signal and re-reports. A rate-capped report is dropped **loudly** (logged) and
its event key is still marked seen — the failure remains visible on the run
page and the next failing run re-triggers; this prevents queued-retry storms.

## Emission contract (the cross-repo task normalizer)

The report shape is schema `federated-ci-failure/v1`
(`api-schemas/federated-ci-failure.schema.json`, Draft 2020-12 — metaschema-
validated in CI by the `validate_schemas.py` glob over `api-schemas/`).

Derived board issue:

- **Title:** `fix(ci): workflow failure in <repo-name> (<workflow-name> #<run_id>)`
- **Labels:** `P1-high`, `handoff:coder`, `area:ci` + best-effort `repo:<slug>`.
  Per the implicit claimable lifecycle (#222) no `status:unclaimed` is emitted.
  If the board does not have the `repo:<slug>` label yet, the Issues API 422s;
  the watcher retries without the repo label and notes the drop inside the
  body (triage can relabel, e.g. `repo:supremeai-open` → `repo:open`).
- **Body:** the standardized agent-task contract — Primary Group (failing
  repo), Sub-Group/Area `ci`, Priority `P1-high`, Topological Layer 2, Task
  Group `agent-orchestration`, mission (run URL, head branch/SHA, failing
  jobs/steps), Touching Files (workflow path first suspect), and the 3-Tier
  Verification Contract.

**Emission before enrichment:** failed-job details come from
`GET /repos/{repo}/actions/runs/{runId}/jobs?filter=latest` best-effort; a
jobs-API blip degrades the body (explicit "details unavailable" note) and never
loses the report.

## Retry semantics

In-memory bounded retry (default 3 attempts, exponential backoff 5 s → 15 min
cap) with a dead-letter state surfaced in `getStatus()`. There is **no durable
outbox** (unlike #69 bridge intake): the reporter is advisory, GitHub
redelivery and the next failing run provide natural reconciliation. Missing
server-side `GITHUB_TOKEN` fails closed at the service level and dead-letters
visibly — no silent success is possible.

## Configuration (env, fail-closed defaults)

| Variable | Default | Meaning |
|---|---|---|
| `FEDERATED_CI_WATCHER_ENABLED` | `false` | Master switch — must be `true` to arm |
| `FEDERATED_CI_WATCHER_REPORT_REPO` | `Supremeai-bd/supremeai-open` | Board that receives failure issues |
| `FEDERATED_CI_WATCHER_REPOS` | _(empty)_ | Comma-separated explicit allowlist; empty → same-org policy |
| `FEDERATED_CI_WATCHER_MAX_PER_HOUR` | `6` | Global rolling issues-per-hour cap |
| `FEDERATED_CI_WATCHER_DEDUPE_TTL_MS` | `86400000` | Event-key/delivery dedupe TTL |
| `FEDERATED_CI_WATCHER_MAX_ATTEMPTS` | `3` | Retry ceiling before dead-letter |
| `GITHUB_TOKEN` / `GITHUB_API_TOKEN` | — | Server-side token with issue-create scope on the report repo |

Arming checklist: set `FEDERATED_CI_WATCHER_ENABLED=true`, ensure the webhook
subscription includes `workflow_run`, ensure the token can open issues on the
report repo. When disabled, boot logs one actionable line
(`[CI_WATCHER] disabled (…)`).

## Scope and wiring

- Registered in `src/index.ts` next to `registerBridgeIntake()` (armed before
  the server accepts webhook traffic; idempotent).
- Config block in `src/lib/env.ts` (`env.federatedCiWatcher`).
- Offline test suite: `test_federated_ci_watcher.ts`, wired as
  `test:federated-ci-watcher` and appended to `test:unit` and the
  credentials-free `test:tower-ci` CI chain (wiring-guard doctrine #116: a
  test file that no script references is silent rot).

## Verification (3-tier, per issue #199)

1. `python scripts/ci/boundary_sanitization_guard.py --check` — 0 violations
2. `npm --prefix infrastructure/mcp-control-plane run typecheck` — clean
3. `python scripts/agents/continuous_agent_loop.py --verify-only` — 8-tier pass

Plus the module suite: `npm run test:federated-ci-watcher` (40 checks,
offline/deterministic — fake clock, injected backends, stubbed `fetch`).
