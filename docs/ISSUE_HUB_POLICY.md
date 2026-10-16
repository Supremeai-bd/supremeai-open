---
id: issue-hub-policy
title: "Single Pane of Glass — supremeai-open as the Federation Unified Work Hub (issue #374)"
document_role: policy
status: active
canonical: true
owner: coder
last_verified: 2026-10-16
governing_issue: 374
related_docs:
  - ECOSYSTEM_MAP.md
  - docs/ZERO_ADMIN_GUIDE.md
  - docs/FEDERATED_CI_WATCHER.md
  - AGENTS.md
  - docs/AGENT_LOOP_SPEC.md
---

# Single Pane of Glass — supremeai-open as the Federation Unified Work Hub (#374)

> **Policy:** every active task of the SupremeAI federation — feature request,
> bug report, agent task, or Bridge Work Order — lives on **exactly one board**:
> [`Supremeai-bd/supremeai-open`](https://github.com/Supremeai-bd/supremeai-open).
> Satellite repositories stay issue-free (§3); failures reach the hub
> automatically (§4); no human sweeps notification streams (§1).

## 1. Purpose and Zero-Admin alignment

In alignment with the Zero-Admin Policy (manual admin effort budget ≤ 0.01%,
AGENTS.md §2.1) and the federation design in `ECOSYSTEM_MAP.md`, this document
formalizes the **Single Pane of Glass** policy the issue #374 declares.

Scattering issues across the 14 federation repositories listed in
`ECOSYSTEM_MAP.md` §2 causes three measurable harms:

1. **Context fragmentation** — an autonomous agent working one board cannot see
   work registered on another; the anti-duplicate and claim-gate machinery
   (`scripts/agents/continuous_agent_loop.py`, claim lifecycle per #222) is
   board-scoped and cannot gate what it cannot list.
2. **Loop starvation** — `pick_next_issue()` fetches claimable issues from the
   hub only (issue #88 selection policy); tasks filed on satellites are
   invisible to the loop and rot unclaimed.
3. **Admin monitoring cost** — each extra notification stream is exactly the
   manual human attention the Zero-Admin Policy removes from the critical path
   (docs/ZERO_ADMIN_GUIDE.md §1).

## 2. The Single Hub Policy (federation standard)

All active tasks live on `Supremeai-bd/supremeai-open`:

- Feature requests, bug reports, agent tasks, and Bridge Work Orders targeting
  **any** federation repository (`supremeai`, `supremeai-skills`,
  `supremeai-browser`, `supremeai-api`, `supremeai-studio`, …) are created
  **exclusively on the hub**.
- Routing to the target repository is declarative, not spatial: the issue
  templates carry a `target_repo` selector —
  `.github/ISSUE_TEMPLATE/agent-task.yml` (dropdown `target_repo`, "Primary
  Group (Target Repository)") and `.github/ISSUE_TEMPLATE/bridge-work-order.yml`
  (dropdown `target_repo`) — and the bridge dispatch
  (#346, `.github/workflows/landing.yml`) routes merged work by `repo:*` labels
  and touched paths to the owning satellite, always keeping the monorepo in
  sync.
- **Corollary:** a task's location on GitHub and its implementation target are
  independent axes. "Filed on the hub" never means "implemented on the hub".

## 3. Satellite Issue-Free Invariant (and strict exceptions)

Satellite repositories must not host individual bug reports, feature requests,
or scattered discussions. Two strict exceptions only:

1. **Foundational repository epics / blueprints** — a satellite's own
   architecture charter (precedent: `Supremeai-bd/supremeai-skills#1`).
2. **Automated local CI/CD failure alerts** — issues generated directly by
   GitHub Actions when a build or test run fails on that repository's `main`
   (§4 gives these a mandatory sync path back to the hub).

Enforcement material for satellite maintainers — install this
`.github/ISSUE_TEMPLATE/config.yml` in each satellite to redirect issue
creators to the hub (blank issues disabled, hub links surfaced):

```yaml
blank_issues_enabled: false
contact_links:
  - name: 🎯 SupremeAI Unified Work Hub (file ALL tasks here)
    url: https://github.com/Supremeai-bd/supremeai-open/issues/new/choose
    about: This repository hosts no individual tasks — the federation Single Hub Policy (issue #374) routes everything to the hub; the hub templates' target_repo selector addresses work back here.
  - name: 🗺️ Federation Ecosystem Map
    url: https://github.com/Supremeai-bd/supremeai-open/blob/main/ECOSYSTEM_MAP.md
    about: Repository directories, boundary classifications, and federation policies.
  - name: 📜 AGENTS.md Constitution
    url: https://github.com/Supremeai-bd/supremeai-open/blob/main/AGENTS.md
    about: 8-step autonomous task cycle, work submission pathways, and bridge rules.
```

This mirrors the hub's own `config.yml` shape (blank-issues-off +
contact_links), so the fleet stays uniform.

## 4. Cross-Repository CI Failure Sync Mechanism (§3 of issue #374)

A satellite CI failure on `main` must reach the hub **without a human copying
anything**. Two complementary transports, one event contract:

| Transport | Surface | Lands where | Best for |
|---|---|---|---|
| **Push-based reusable action** (this delivery) | `.github/actions/sync-ci-failure/action.yml` | Any satellite workflow `if: failure()` step | Satellites without org-level webhook wiring; per-workflow opt-in |
| **Webhook-based watcher** (landed, issue #199) | `src/events/federated_ci_watcher.ts` in `infrastructure/mcp-control-plane` + hub webhook | Every `workflow_run` failure org-wide | Fleet-wide default once the webhook subscription exists |

### 4.1 Shared event contract (both transports)

Both emit the machine-readable report `federated-ci-failure/v1`
(`api-schemas/federated-ci-failure.schema.json`, Draft 2020-12) and share the
idempotency anchor:

```
eventKey = ci-failure:<repo>:<workflowName>:<runId>:<runAttempt>
```

A re-run of the same run id under a **new attempt** is a NEW failure signal
(#199 dedupe doctrine). Reports are advisory: emission before enrichment
(`failedJobs: []` is conformant), and a failed report never masks the original
build failure — the next failing run re-triggers.

### 4.2 Board-issue payload (issue #374 §3 "Sync Payload Specification")

| Field | Value |
|---|---|
| Repository | `Supremeai-bd/supremeai-open` |
| Title | `[CI Failure] <satellite-repo>: <workflow_name> failed on run #<run_id>` |
| Labels | `bridge:ci-failure`, `target:<satellite-repo>`, `P1-high` |
| Body context | Run URL, head SHA (full 40-hex), failed step log excerpt, actionable repro command, plus the fenced `federated-ci-failure/v1` JSON block |

Label governance: `target:<slug>` must pre-exist on the hub or creation 422s —
retry without it and note the drop (same governance the #199 watcher applies to
`repo:<slug>` labels); triage relabels (e.g. `repo:supremeai-open` →
`repo:open`). Idempotent sync: before creating, search the hub for the open
issue carrying the `eventKey`; found → append a re-observation comment, never
a duplicate issue.

### 4.3 Continuous Agent Loop precedence (issue #374 §4.4)

No loop-code change is required to give `bridge:ci-failure` issues high
precedence — by construction the payload spec **mandates `P1-high`**, and the
loop's selection policy (`pick_next_issue()`, issue #88) ranks by
**labels only** (`P0 > P1 > P2 > P3 > unlabeled`, oldest-first tie-break), so a
`P1-high` failure report enters tier 1 immediately and can only be outranked by
a `P0`. Two deployment notes for the maintainers:

1. If fresh breakage should outrank **ordinary** P1 work, mint a `P0`
   variant in the sync payload — the #88 map already implements that precedence
   with zero code change (`p0` label tier 0).
2. The `bridge:ci-failure` label itself is a routing/filtering affordance for
   tooling and dashboards; the loop stays deliberately label-map-simple (#88
   docstring: "prose in titles can no longer outrank a real priority label").

## 5. Implementer verification checklist

1. Hub templates carry the `target_repo` dropdown
   (`.github/ISSUE_TEMPLATE/agent-task.yml`, `.github/ISSUE_TEMPLATE/bridge-work-order.yml`).
2. Satellite `config.yml` matches §3 (blank issues off; hub redirect first link).
3. A satellite workflow invoking `.github/actions/sync-ci-failure` on a failing
   `main` run produces exactly one hub issue per `<runId>:<runAttempt>` whose
   body embeds a schema-valid `federated-ci-failure/v1` report
   (validate: `python scripts/validate_schemas.py` + `jsonschema` against
   `api-schemas/federated-ci-failure.schema.json`).
4. Re-invoking the action for the same `eventKey` appends a re-observation
   comment and creates no duplicate issue.
5. Withholding `issues:write` scope produces a loud, advisory skip
   (`[CI_FAILURE_SYNC]` step-summary line) — never a masked original failure.
6. The opened issue carries `P1-high` (or the ladder-dropped remainder) so the
   #88 label-priority loop picks it up at tier 1.
7. Both transports agree on `eventKey` shape and on advisory/no-mask semantics.

## 6. Folding anchors (for the canonical docs' next revision)

To materialize deliverable §4.1 of issue #374 inside the existing canonical
documents, insert:

- **`ECOSYSTEM_MAP.md` §2** (after the repository directory table): *"Single
  Hub Policy (issue #374): all active federation tasks are filed on
  `supremeai-open` only; the issue templates' `target_repo` selector and the
  bridge dispatch (#346) route each task to its owning repository. Satellites
  stay issue-free except foundational epics and automated CI failure alerts —
  see docs/ISSUE_HUB_POLICY.md."*
- **`docs/ZERO_ADMIN_GUIDE.md`** (§1 table, one row): *"Task discovery across
  the fleet" replaced by "Single Hub Policy + cross-repo CI failure sync
  (reusable action #374 / webhook watcher #199)" enforced at
  `.github/actions/sync-ci-failure` and `src/events/federated_ci_watcher.ts`.*

## 7. Related documents

- `ECOSYSTEM_MAP.md` — §2 federation repository directory (14 repositories).
- `docs/ZERO_ADMIN_GUIDE.md` — the zero-human-landing doctrine this policy serves.
- `docs/FEDERATED_CI_WATCHER.md` — the webhook transport's canonical reference (issue #199).
- `api-schemas/federated-ci-failure.schema.json` — the shared emission contract.
- `AGENTS.md` §2.1 (Zero-Admin), §3 (8-step loop); docs/AGENT_LOOP_SPEC.md §4 (verify tiers).

## Appendix A — the reusable action, ready to commit (lane hand-off)

The bridge lane **refuses automatic writes to `.github/`** ("protected paths"
rejection — workflow files are executable infrastructure, so the lane
fail-closes them by design). The reusable action of §4 is therefore handed off
here: the block below is the complete, battery-tested
`.github/actions/sync-ci-failure/action.yml` — byte-identical to the artifact
this document's battery executed end-to-end (mocked-curl functional suite, 5
scenarios). Commit it as-is at that path and the §5 checklist applies verbatim.

```yaml
# =============================================================================
# Reusable composite action — Single-Hub CI failure sync (issue #374, §4.3)
# =============================================================================
# Emits the §3 "Sync Payload Specification" issue to the unified hub
# (Supremeai-bd/supremeai-open) when a satellite workflow run fails, so the
# Continuous Agent Loop can claim and patch the breakage without any human
# repository sweep (Zero-Admin Policy, AGENTS.md §2.1).
#
# Push-based transport, complementary to the webhook-based control-plane
# watcher (issue #199, docs/FEDERATED_CI_WATCHER.md): satellites without
# org-level webhook wiring embed this step directly in their workflows.
# Both transports share the dedupe key
#   ci-failure:<repo>:<workflow>:<runId>:<runAttempt>
# and both treat the report as ADVISORY (#199 doctrine): the original job has
# already failed, so this action never masks that failure and never hard-fails
# on its own API errors — every terminal path writes a loud [CI_FAILURE_SYNC]
# line to the job step summary. No silent success, no silent skip.
#
# SECURITY: every input reaches the shell only through env — never interpolated
# into the run body (workflow inputs are free text and fated for a shell, same
# rule as .github/actions/gitleaks-scan). Every JSON payload (report, issue
# body, comment) is built by jq with --arg/--argjson — no input text is ever
# passed through shell expansion or a heredoc into JSON.
#
# PLACEMENT: invoke on failure, typically main-only —
#   jobs:
#     notify-hub:
#       needs: [build]
#       if: failure() && github.ref == 'refs/heads/main'
#       steps:
#         - uses: Supremeai-bd/supremeai-open/.github/actions/sync-ci-failure@main
#           with:
#             token:         ${{ secrets.HUB_ISSUE_TOKEN }}   # needs issues:write on the hub
#             repro_command: "gh run view ${{ github.run_id }} --repo ${{ github.repository }} --log-failed"
#             failed_steps:  "install-dependencies
#                             tower-tests"
#             log_excerpt:   "first failing lines of the job log"
# =============================================================================

name: "Sync CI Failure to Unified Hub"
description: "Open (or re-observe) the [CI Failure] issue on the unified hub for this failed workflow run — payload per issue #374 §3, machine block per federated-ci-failure/v1"

inputs:
  report_repo:
    description: "Unified hub repository that receives the failure issue (#374 Single Hub Policy)"
    required: false
    default: "Supremeai-bd/supremeai-open"
  token:
    description: "Token with issues:write on report_repo. The default github.token can only reach THIS repository — cross-repo issue creation needs a fine-grained PAT or App token scoped to the hub."
    required: false
    default: ${{ github.token }}
  repro_command:
    description: "Actionable repro command quoted verbatim in the issue body (#374 §3 Body Context)"
    required: false
    default: ""
  failed_steps:
    description: "Optional newline-separated failing step names (best-effort enrichment). Empty is allowed: emission before enrichment (#199) — the report itself must still go out."
    required: false
    default: ""
  log_excerpt:
    description: "Optional short failing-log excerpt for the issue body (#374 §3 Body Context)"
    required: false
    default: ""

runs:
  using: composite
  steps:
    - name: Sync CI failure issue to the unified hub
      shell: bash
      env:
        REPORT_REPO: ${{ inputs.report_repo }}
        GH_TOKEN: ${{ inputs.token }}
        REPRO_COMMAND: ${{ inputs.repro_command }}
        FAILED_STEPS: ${{ inputs.failed_steps }}
        LOG_EXCERPT: ${{ inputs.log_excerpt }}
        SRC_REPO: ${{ github.repository }}
        WORKFLOW_NAME: ${{ github.workflow }}
        RUN_ID: ${{ github.run_id }}
        RUN_ATTEMPT: ${{ github.run_attempt }}
        RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        HEAD_SHA: ${{ github.sha }}
        HEAD_BRANCH: ${{ github.ref_name }}
        JOB_NAME: ${{ github.job }}
      run: |
        set -uo pipefail

        SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-/dev/null}"
        note() { printf '%s\n' "$*" >> "$SUMMARY_FILE" 2>/dev/null || printf '%s\n' "$*" >&2; }

        if ! command -v jq >/dev/null 2>&1; then
          note "[CI_FAILURE_SYNC] ABORT (misconfig): jq is required on the runner but was not found — no report emitted."
          exit 1
        fi
        if [ -z "${GH_TOKEN:-}" ]; then
          note "[CI_FAILURE_SYNC] SKIP (fail-closed): no token supplied — cross-repo issue creation is impossible. Pass \`token\` with issues:write on ${REPORT_REPO}."
          exit 0
        fi

        # ---- §3 Sync Payload Specification ---------------------------------
        # Title:  [CI Failure] <satellite-repo>: <workflow_name> failed on run #<run_id>
        # Labels: bridge:ci-failure, target:<satellite-repo>, P1-high
        # (target:<slug> label must pre-exist on the hub; on 422 we retry
        #  without it and note the drop — same governance the #199 watcher
        #  applies to repo:<slug> labels.)
        TARGET_SLUG="${SRC_REPO##*/}"
        TITLE="[CI Failure] ${SRC_REPO}: ${WORKFLOW_NAME} failed on run #${RUN_ID}"
        EVENT_KEY="ci-failure:${SRC_REPO}:${WORKFLOW_NAME}:${RUN_ID}:${RUN_ATTEMPT}"
        NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        API="https://api.github.com"
        AUTH=(-sS -H "Authorization: Bearer ${GH_TOKEN}" -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28")

        # ---- machine-readable report (federated-ci-failure/v1) -------------
        # Conformant to api-schemas/federated-ci-failure.schema.json
        # (Draft 2020-12, additionalProperties:false). failedJobs=[] when no
        # enrichment was supplied — explicit "emission before enrichment" (#199).
        if [ -n "${FAILED_STEPS}" ]; then
          STEPS_JSON="$(printf '%s' "${FAILED_STEPS}" | jq -Rs 'split("\n") | map(select(length > 0))')"
          JOBS_JSON="$(jq -n --arg name "${JOB_NAME}" --argjson steps "${STEPS_JSON}" '[{ name: $name, steps: $steps }]')"
        else
          JOBS_JSON="[]"
        fi
        REPORT="$(jq -n --arg repo "${SRC_REPO}" --arg wf "${WORKFLOW_NAME}" --arg runUrl "${RUN_URL}" --arg branch "${HEAD_BRANCH}" --arg sha "${HEAD_SHA}" --arg eventKey "${EVENT_KEY}" --arg reportedAt "${NOW}" --argjson runId "${RUN_ID}" --argjson attempt "${RUN_ATTEMPT}" --argjson failedJobs "${JOBS_JSON}" '{ schema: "federated-ci-failure/v1", repo: $repo, workflowName: $wf, runId: $runId, runAttempt: $attempt, runUrl: $runUrl, headBranch: $branch, headSha: $sha, conclusion: "failure", failedJobs: $failedJobs, eventKey: $eventKey, reportedAt: $reportedAt }')"

        # ---- issue body (#374 §3 Body Context), jq-built: injection-safe ----
        if [ -n "${REPRO_COMMAND}" ]; then REPRO_LINE="$(printf '%s' "${REPRO_COMMAND}" | jq -Rs '.')"; else REPRO_LINE='"_(not supplied)_"'; fi
        if [ -n "${LOG_EXCERPT}" ]; then EXCERPT_LINE="$(printf '%s' "${LOG_EXCERPT}" | jq -Rs '.')"; else EXCERPT_LINE='"_(not supplied)_"'; fi
        BODY="$(jq -rn --arg repo "${SRC_REPO}" --arg wf "${WORKFLOW_NAME}" --arg runUrl "${RUN_URL}" --arg branch "${HEAD_BRANCH}" --arg sha "${HEAD_SHA}" --arg eventKey "${EVENT_KEY}" --arg now "${NOW}" --argjson repro "${REPRO_LINE}" --argjson excerpt "${EXCERPT_LINE}" --argjson report "${REPORT}" '(
          "## CI failure report — Single Hub Policy (issue #374)\n\n" +
            "| Field | Value |\n|---|---|\n" +
            "| Source repository | \($repo) |\n" +
            "| Workflow | \($wf) |\n" +
            "| Run | \($runUrl) |\n" +
            "| Head branch | \($branch) |\n" +
            "| Head SHA | `\($sha)` |\n" +
            "| Dedupe key | `\($eventKey)` |\n" +
            "| Reported at | \($now) |\n\n" +
            "### Actionable repro command (issue #374 §3)\n\n```bash\n\($repro)\n```\n\n" +
            "### Failed step log excerpt (issue #374 §3)\n\n```\n\($excerpt)\n```\n\n" +
            "### Machine-readable report (`federated-ci-failure/v1`)\n\n" +
            "```json\n\($report | tostring)\n```\n\n" +
            "Same emission contract as the webhook-based control-plane watcher\n" +
            "(docs/FEDERATED_CI_WATCHER.md, issue #199). Autonomous agents: claim this\n" +
            "task only after verifying the run is still failing — a re-run may have\n" +
            "already healed it.")')"

        # ---- idempotency: re-observe instead of duplicate -------------------
        # Same event-key doctrine as the #199 watcher's 24 h dedupe TTL: one open
        # board issue per ci-failure:<repo>:<workflow>:<runId>:<runAttempt>; a new
        # attempt on the same run id is a NEW failure signal.
        SEARCH_CODE="$(curl "${AUTH[@]}" -o /tmp/hub_search.json -w '%{http_code}' -G "${API}/search/issues" --data-urlencode "q=\"${EVENT_KEY}\" in:body state:open type:issue repo:${REPORT_REPO}" || echo curl-error)"
        EXISTING="$(jq -r '.items[0].number // empty' /tmp/hub_search.json 2>/dev/null || true)"

        if [ -n "${EXISTING}" ]; then
          COMMENT_BODY="$(jq -n --arg now "${NOW}" --arg attempt "${RUN_ATTEMPT}" --arg runUrl "${RUN_URL}" --arg eventKey "${EVENT_KEY}" '{ body: ("Re-observed at " + $now + " — attempt #" + $attempt + " of the same failure signal.\nRun: " + $runUrl + "\nDedupe key: `" + $eventKey + "`\n\n_(no duplicate issue opened; original report stays canonical — #374 §3 idempotent sync)_") }')"
          CODE="$(curl "${AUTH[@]}" -o /tmp/hub_comment.json -w '%{http_code}' -X POST "${API}/repos/${REPORT_REPO}/issues/${EXISTING}/comments" -d "${COMMENT_BODY}" || echo curl-error)"
          case "${CODE}" in
            2*) note "[CI_FAILURE_SYNC] OK (re-observe): appended attempt note to existing hub issue #${EXISTING} for ${EVENT_KEY} (HTTP ${CODE})." ;;
            *)  note "[CI_FAILURE_SYNC] SKIP (advisory): re-observe comment on issue #${EXISTING} failed (HTTP ${CODE}) — original report remains on the hub; the next failing run re-triggers." ;;
          esac
          exit 0
        fi

        # ---- create the issue (best-effort label ladder on 422) -------------
        # Ladder mirrors the #199 watcher's repo:<slug> governance: a missing
        # label on the hub 422s the creation, so we retry without it and note
        # the drop in the step summary — triage can relabel.
        post_issue() {
          jq -n --arg title "${TITLE}" --arg body "${BODY}" --argjson labels "$1" '{title:$title, body:$body, labels:$labels}' | curl "${AUTH[@]}" -o /tmp/hub_issue.json -w '%{http_code}' -X POST "${API}/repos/${REPORT_REPO}/issues" -d @- || echo curl-error
        }

        CODE="$(post_issue "[\"bridge:ci-failure\", \"target:${TARGET_SLUG}\", \"P1-high\"]")"
        if [ "${CODE}" = "422" ]; then
          note "[CI_FAILURE_SYNC] note: label target:${TARGET_SLUG} rejected (422) — retrying without it (drop noted here; triage may relabel)."
          CODE="$(post_issue "[\"bridge:ci-failure\", \"P1-high\"]")"
        fi
        if [ "${CODE}" = "422" ]; then
          note "[CI_FAILURE_SYNC] note: hub label set rejected again (422) — final retry with no labels."
          CODE="$(post_issue "[]")"
        fi

        case "${CODE}" in
          2*)
            NUM="$(jq -r '.number // empty' /tmp/hub_issue.json 2>/dev/null || true)"
            note "[CI_FAILURE_SYNC] OK: hub issue ${REPORT_REPO}#${NUM} opened for ${EVENT_KEY} (HTTP ${CODE}) — the Continuous Agent Loop's label-only priority policy (#88) ranks the mandatory P1-high label at tier 1."
            ;;
          401|403)
            note "[CI_FAILURE_SYNC] SKIP (fail-closed, advisory): token lacks issues:write on ${REPORT_REPO} (HTTP ${CODE}). The failure stays visible on the run page; the next failing run re-triggers. Grant the token hub scope or wire the #199 webhook watcher instead."
            ;;
          *)
            note "[CI_FAILURE_SYNC] SKIP (advisory): issue creation failed (HTTP ${CODE}) — the failure stays visible on the run page; the next failing run re-triggers."
            ;;
        esac
        exit 0
```
