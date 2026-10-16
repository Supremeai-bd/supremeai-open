# AUDIT — 2026-10-16 last inline `workflow_dispatch` input interpolation (agent-loop step) vs the #155 env-passthrough doctrine

> **id:** audit-2026-10-16-agent-loop-dispatch-input-inline
> **title:** pipeline.yml agent-loop step interpolates `inputs.auto_pr` directly into the shell body — the one remaining member of the injection class #155 eliminated elsewhere
> **document_role:** audit
> **status:** active
> **canonical:** true
> **owner:** agent-orchestration (Auditor role, AGENT_RULES.md §3)
> **last_verified:** 2026-10-16
> **related_docs:** [INGRESS_SECURITY_POLICY.md](INGRESS_SECURITY_POLICY.md) · [AGENT_RULES.md](../AGENT_RULES.md) · [AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md](AUDIT_2026-10-16-stale-base-guard-frozen-base-sha.md)
> **source_issue:** filed via bridge (this document's own Work Order)

> **Auditor:** external autonomous contributor agent (zero-credential Pathway 1, AGENTS.md §2.1).
> **Method:** expression-injection sweep across both workflow files at main `8242d4e` — every
> `${{ }}` occurrence inside a `run:` block classified as env-passthrough (safe pattern,
> established by the #155 consolidation of landing.yml) vs inline shell interpolation.
> Severity **P3** (hardening / doctrine drift — no known external injection path today;
> severity honestly bounded below), **agent-orchestration** group.

## Finding — P3 · agent-orchestration · one remaining inline interpolation of a dispatch input

The sweep found exactly one inline (non-env) interpolation of event context that is not a
GitHub-controlled constant:

```yaml
- name: Start Continuous Agent Loop (existing dispatcher, one cycle)
  if: steps.board.outputs.has_work == 'true'
  run: |
    set -euo pipefail
    ARGS="--pick-next"
    if [ "${{ github.event_name }}" = "workflow_dispatch" ] && [ "${{ inputs.auto_pr }}" = "true" ]; then
      ARGS="$ARGS --auto-pr"
    fi
    python scripts/agents/continuous_agent_loop.py $ARGS
```

The repo's own doctrine (landing.yml, introduced by the #155 security consolidation) treats
workflow_dispatch inputs as hostile:

> workflow_dispatch inputs are free text and fated for a shell → pass through env, never
> interpolate into the shell body.

`DISPATCH_PR` is numerically validated and `EVENT_PR_TITLE` is env-passthrough ("Untrusted
event payload … pass through env, never interpolate into the shell body") — this step is the
remaining outlier: `inputs.auto_pr` is rendered inside a shell test's double quotes, where
any raw `"`-bearing value closes the quote and executes attacker shell.

### Honest severity bounds (why P3, not P1/P2)

- `auto_pr` is declared `type: boolean`; GitHub's dispatch API type-validates current
  tooling, and the MCP Tower's bridge intake dispatches with a **hard-coded**
  `inputs: { auto_pr: false }` boolean literal
  (`infrastructure/mcp-control-plane/src/events/bridge_intake.ts:175`) — no external-agent
  influence on this input exists today.
- Historical/legacy dispatch paths (older `gh` releases, hand-rolled API calls) sent raw
  strings for boolean-typed inputs before strict validation — the class #155 closed because
  the repo chose not to depend on GitHub's input coercion at all. This step still depends on
  it.
- `github.event_name` is a GitHub-controlled enum — safe to inline (noted, not filed).

## Verified fix — carried diff for an authorized lane (`.github/` is bridge-protected)

Same env-passthrough pattern as the #155-fixed steps. Behavior byte-identical for
true/false/empty coercions (the typed context renders `true`/`false`/empty exactly as the
inline form did).

```diff
--- a/.github/workflows/pipeline.yml
+++ b/.github/workflows/pipeline.yml
@@ -520,10 +520,15 @@
       - name: Start Continuous Agent Loop (existing dispatcher, one cycle)
         if: steps.board.outputs.has_work == 'true'
+        env:
+          EVENT_NAME: ${{ github.event_name }}
+          AUTO_PR: ${{ inputs.auto_pr }}
         run: |
           set -euo pipefail
           ARGS="--pick-next"
-          if [ "${{ github.event_name }}" = "workflow_dispatch" ] && [ "${{ inputs.auto_pr }}" = "true" ]; then
+          # #155 doctrine: dispatch inputs are free text and fated for a shell —
+          # pass through env, never interpolate into the shell body.
+          if [ "$EVENT_NAME" = "workflow_dispatch" ] && [ "$AUTO_PR" = "true" ]; then
             ARGS="$ARGS --auto-pr"
           fi
           python scripts/agents/continuous_agent_loop.py $ARGS
```

(Step line numbers from main `8242d4e`; the diff body is the authoritative artifact, not the
hunk offsets. The trailing unquoted `$ARGS` is intentional internal word-splitting of
self-constructed flags — not in scope.)

On landing, no doc changes required (INGRESS_SECURITY_POLICY.md does not cover this step's
dispatch plumbing; the #155 doctrine is already documented at its landing site in
landing.yml).

## U9 similar-problem sweep (inline-interpolation class, both workflows)

| Surface | Verdict |
|---|---|
| `pipeline.yml` agent-loop step `inputs.auto_pr` | **finding (this document)** — dispatch input inlined |
| `pipeline.yml` agent-loop step `github.event_name` | cleared — GitHub-controlled enum |
| `landing.yml` auto_merge / bridge-dispatch `${{ github.repository }}` inline | cleared — repo-slug constant (`Supremeai-bd/supremeai-open`), not event-derived |
| `landing.yml` EVENT_PR_TITLE / DISPATCH_PR / EVENT_PR_SHA family | cleared — already env-passthrough + numeric validation (#155) |
| All `env:`-block interpolations in both workflows | cleared — passthrough pattern by construction |

## Evidence record

| Check | Result |
|---|---|
| Sweep method | YAML-parsed both workflows; every `${{ }}` in `run:` blocks classified (inline vs env-assignment line) |
| Inline hits | 9 total → 8 cleared as GitHub-controlled constants, 1 finding |
| Tower dispatch input source | `bridge_intake.ts:175` — hard-coded `auto_pr: false` |
| Declared input type | `pipeline.yml` `workflow_dispatch.inputs.auto_pr` `type: boolean` |
| Audit base | main `8242d4e` |
