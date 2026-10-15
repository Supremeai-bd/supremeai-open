# Event-Driven Bridge Intake (#69)

Webhook → workflow-dispatch wake-up path that replaces high-frequency **polling**
latency with **event-driven** intake for the SupremeAI agent loop.

- **Problem:** the agent loop only ran every 30 minutes (cron in the unified
  `pipeline.yml`), so a new Bridge Work Order / PR waited up to a
  full interval before any agent picked it up. Scheduled runs also burned
  Actions minutes on empty boards.
- **Solution:** the already-deployed MCP Control Tower `/webhooks/github` route
  (signature-verified, normalized, gateway-dispatched) now additionally arms a
  **bridge intake listener** that dispatches the existing polling workflow via
  the GitHub `workflow_dispatch` API the moment relevant work appears.
- **No second event bus, no duplicate endpoint** — this extends
  `src/events/normalizer.ts` + `src/events/gateway.ts` with one listener
  (`src/events/bridge_intake.ts`).

```
GitHub webhook ──► /webhooks/github (HMAC sha256 over raw body, prod)
                      │
                      ▼
              EventNormalizer ──► EventGateway ──► BridgeIntakeService
                                                     │  decide (repo/action/bot filter)
                                                     │  dedupe (X-GitHub-Delivery + event key, 30-min TTL)
                                                     │  outbox append (durable JSONL, sync & O(1))
                                                     ▼  async
                                     POST /repos/{repo}/actions/workflows/{workflow}/dispatches
                                                     │
                                                     ▼
                             pipeline.yml runs immediately (--pick-next)
```

## Activation (owner-side, one time)

1. **Repo webhook** on `Supremeai-bd/supremeai-open` →
   URL `https://<tower-host>/webhooks/github`,
   content type `application/json`,
   secret = the value deployed as `GITHUB_WEBHOOK_SECRET`,
   events: **Issues**, **Pull requests** (Issue comment optional).
2. **Env on the Tower deployment:**

   | Variable | Default | Meaning |
   |---|---|---|
   | `BRIDGE_INTAKE_ENABLED` | `false` | **fail-closed master switch** |
   | `BRIDGE_INTAKE_REPO` | `Supremeai-bd/supremeai-open` | repo owning the workflow |
    | `BRIDGE_INTAKE_WORKFLOW` | `pipeline.yml` | dispatch target |
   | `BRIDGE_INTAKE_REF` | `main` | dispatch ref |
   | `BRIDGE_INTAKE_MIN_INTERVAL_MS` | `60000` | min spacing between dispatches |
   | `BRIDGE_INTAKE_MAX_ATTEMPTS` | `5` | retry ceiling → dead-letter |
   | `BRIDGE_INTAKE_OUTBOX_PATH` | `var/bridge-intake-outbox.jsonl` | durable outbox |
   | `GITHUB_TOKEN` | — | server-side token **with `workflow` scope** on the target repo |

3. **Boot check:** the Tower logs either
   `[BRIDGE_INTAKE] armed → <repo>/<workflow>@<ref>` or
   `[BRIDGE_INTAKE] disabled (set BRIDGE_INTAKE_ENABLED=true …)`.

## Safety properties (each covered by `test_bridge_intake.ts`)

- **Signature** — HMAC over the **raw request body**, constant-time compare,
  fail-closed on missing secret/header (`src/lib/webhook_signature.ts`).
- **Filtering** — only `issues` (`opened`/`reopened`/`labeled`),
  `pull_request` (`opened`/`reopened`/`synchronize`),
  `issue_comment` (`created`); wrong repo, bot senders, other actions and
  non-GitHub sources are dropped with a reason. Events **cannot** bypass
  claiming, scope gates, review or merge governance — they only start the
  existing dispatcher, which enforces all of that.
- **Idempotency** — duplicate deliveries collapse by delivery id *and* by
  event key inside a 30-minute TTL window.
- **Fast ack** — the HTTP 200 never waits on GitHub: accept + outbox append
  are synchronous O(1); the API call is asynchronous.
- **Durability** — every accepted event is persisted **before** dispatch;
  pending entries are replayed on boot (`replayPending()`) and retried with
  exponential backoff (5 s → 15 min cap) up to `maxAttempts`, then
  dead-lettered **visibly** (log + outbox status).
- **Rate limit** — dispatches spaced ≥ `BRIDGE_INTAKE_MIN_INTERVAL_MS`;
  extras queue in the outbox instead of hammering the API.
- **Least privilege** — only the server-side token is used; nothing from the
  payload (and no secret) is ever logged or persisted.
- **Reconciliation tick** — `service.tick()` drains whatever is due without a
  new webhook (usable from an external cron/job).

## Measured latency

Every successful dispatch records `latencyMs` (enqueue → GitHub API 2xx) in the
outbox entry and the `[BRIDGE_INTAKE] dispatched … (NNms)` log line. Test
evidence: `npm run test:bridge-intake` → `ALL BRIDGE INTAKE TESTS PASSED (#69)`.
Note the honest boundary: this measures **webhook-to-dispatch**. End-to-end
**webhook-to-agent-start** additionally includes the runner start time and must
be measured in deployment logs (`agent-loop` job start vs `[BRIDGE_INTAKE]`).

## Rollout & cron retirement criteria

The 30-minute cron in `pipeline.yml` **stays** as the
reconciliation fallback during rollout. Retire (or lower) it only after **all**
of:

1. ≥ 7 consecutive days with webhook-dispatched runs and no missed-issue
   reconciliation (cron no-op evidence absent while issues existed);
2. zero dead-lettered outbox entries over that window;
3. the Support-ticketed `workflow_dispatch` scheduler defect (see
   `docs/OPS_ACTIONS_QUOTA_RUNBOOK.md`) is confirmed resolved for this repo.

## Recovery procedure

1. Inspect the outbox: `cat var/bridge-intake-outbox.jsonl | jq -s 'group_by(.status)'`.
2. Dead-lettered entries: fix the root cause (token scope, scheduler freeze),
   then reset `"status": "pending"`, `"attempts": 0` and restart the Tower —
   boot replay redelivers them. Re-dispatch is safe (workflow is idempotent:
   one `--pick-next` cycle).
3. Manual drain without restart: call `tick()` from an operator console.
