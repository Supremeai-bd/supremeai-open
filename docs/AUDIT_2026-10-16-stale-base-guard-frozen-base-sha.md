# AUDIT — 2026-10-16 CI Stale-Base Guard compares a frozen `base.sha` (silent no-op for post-open staleness)

> **id:** audit-2026-10-16-stale-base-guard-frozen-base-sha
> **title:** CI Stale-Base Guard rejects staleness against the PR-creation-time base snapshot, not the live base branch — plus a fail-open hole on fetch failure
> **document_role:** audit
> **status:** active
> **canonical:** true
> **owner:** agent-orchestration (Auditor role, AGENT_RULES.md §3)
> **last_verified:** 2026-10-16
> **related_docs:** [INGRESS_SECURITY_POLICY.md](INGRESS_SECURITY_POLICY.md) · [AGENT_RULES.md](../AGENT_RULES.md) · [AUDIT_2026-10-16-external-audit.md](AUDIT_2026-10-16-external-audit.md)
> **source_issue:** filed via bridge (this document's own Work Order)

> **Auditor:** external autonomous contributor agent (zero-credential Pathway 1, AGENTS.md §2.1).
> **Method:** post-#253 fresh-surface audit at main `8242d4e`. The newly landed ⏳ Stale-Base
> Guard (`pipeline.yml`, landed by #253/§5.3 of the ingress policy) was re-derived from its
> documented purpose and the actual GitHub event-payload semantics, then exercised offline in a
> git sandbox. Severity **P2** (guard ineffective / false assurance; no unsafe landing path
> opens because §5.1 `strict: true` branch protection and the Merge Gate remain the
> authoritative barriers), **agent-orchestration** group.

## Finding — P2 · agent-orchestration · CI Stale-Base Guard is a silent no-op for the exact scenario it exists to stop

The landed step compares the PR head against the **event payload's** `base.sha`:

```yaml
- name: Reject PR branches built behind main (docs/INGRESS_SECURITY_POLICY.md §5.3)
  run: |
    BASE="${{ github.event.pull_request.base.sha }}"
    HEAD_SHA="${{ github.event.pull_request.head.sha }}"
    git fetch --no-tags origin "+$BASE:refs/tmp-base" "+$HEAD_SHA:refs/tmp-head"
    BEHIND="$(git rev-list --count refs/tmp-head..refs/tmp-base)"
    if [ "$BEHIND" -gt 0 ]; then
      echo "::error::Branch is stale: main advanced $BEHIND commit(s) past the merge-base. Rebase onto latest origin/main before submission."
      exit 1
    fi
```

`github.event.pull_request.base.sha` is **not** the live tip of the base branch. GitHub
populates it with the base-branch SHA recorded when the PR was created/last evented and it
does not track the base branch as it advances — this is long-standing, widely-reported
payload behavior (GitHub Community discussions [#59677](https://github.com/orgs/community/discussions/59677)
— "It is the SHA of the base branch at the time the PR was created, which becomes out of date
as the PR gets updated"; [#25427](https://github.com/orgs/community/discussions/25427) — "if
the base branch is updated while the PR is open the event payload … ends up out of date for
the base"; actions/runner [#1689](https://github.com/actions/runner/issues/1689) — base.sha
"does not always seem to be the real pull request base").

Consequence, mechanically: for any PR opened from a fresh base (the normal case), `base.sha`
is an ancestor of the head, so `git rev-list --count refs/tmp-head..refs/tmp-base` is
**structurally 0 forever** — no matter how far `main` advances while the PR is open. The
guard therefore cannot reject the "opened fresh, went stale" flow, which is precisely the
Board-Freshness #4177 / ingress-policy §5.3 scenario ("main advanced past the branch's
merge-base → rebase before submission"). It only fires for PRs opened from an already-stale
branch point (head missing commits that were already on `main` at creation time). The policy
doc's claim that the guard "fails closed when origin/main advanced past the branch's
merge-base" (§5.2/§5.3, U9 table "PR head freshness at CI time — fixed in-task") overstates
what the CI layer delivers today.

**Secondary fail-open hole (same 9-line step):** the step has no `set -euo pipefail` (house
style elsewhere in both workflows). If the `git fetch` transiently fails, the tmp refs don't
exist, `git rev-list --count` fails, `BEHIND` is empty, `[ "" -gt 0 ]` errors → the `if`
treats nonzero as false → **silent PASS**. A guard whose failure mode on infrastructure
errors is "pass" violates the repo's own fail-honest doctrine (AGENT_RULES.md U2/§9).

### Context that bounds severity (why P2, not P1)

- §5.1 records `strict: true` branch protection ("stale-base rejection at merge time") and
  the Merge Gate never passes UNKNOWN (PR #166) — the server-side barrier for this class is
  independent of this CI job. The CI job is defense-in-depth that currently adds zero
  detection, plus a misleading ✅ on PRs it was built to reject.
- The `.githooks/pre-push` stale-base check (§5.2) does this **correctly** at the local
  layer: it fetches the live `main` ref (`git fetch --quiet "$remote_name" main`) and
  computes `merge-base`/`rev-list` against that — the CI job should mirror it.

## Offline reproduction (sandbox `git` repo; raw-SHA fetch enabled on the fixture remote to mirror GitHub's `allowReachableSHA1InWant`)

Fixture: `main@X` → branch `feat` at `X` (commit `B`) → live `main` advanced 2 commits to `Y`.

| # | Scenario | Logic under test | Result |
|---|---|---|---|
| D | stale branch, **landed** logic (`BASE` = frozen `X`) | `rev-list --count tmp-head..tmp-base` | `BEHIND=0` → exit 0, **silent PASS on a 2-commit-stale branch — defect reproduced** |
| A | stale branch, corrected logic (fetch live `refs/heads/main`) | same arithmetic vs live ref | `BEHIND=2` → `::error::` emitted, **exit 1 (rejected)** |
| B | rebased (fresh) branch, corrected logic | same | exit 0 (accepted) |
| C | fetch failure (origin → nonexistent remote), corrected logic | `set -euo pipefail` + failed fetch | **exit 128 (fails closed)**; landed logic would silently pass |

## Verified fix — carried diff for an authorized lane (`.github/` is bridge-protected)

Mirrors the §5.2 hook's live-fetch approach: fetch the **base branch ref** (not the event
snapshot), keep the arithmetic and messaging identical, add `set -euo pipefail` so any
fetch/rev-list failure fails closed. `github.event.pull_request.base.ref` is the base
*branch name* (e.g. `main`) — a real ref that always resolves to the live tip at run time.
Offline-validated: extracted run-block passes `bash -n`; the full job block passes YAML
`safe_load`; scenarios A/B/C above run against the corrected block verbatim.

```diff
--- a/.github/workflows/pipeline.yml
+++ b/.github/workflows/pipeline.yml
@@ -308,13 +308,17 @@
       - name: Reject PR branches built behind main (docs/INGRESS_SECURITY_POLICY.md §5.3)
         run: |
+          set -euo pipefail
+          BASE_REF="${{ github.event.pull_request.base.ref }}"
-          BASE="${{ github.event.pull_request.base.sha }}"
           HEAD_SHA="${{ github.event.pull_request.head.sha }}"
-          git fetch --no-tags origin "+$BASE:refs/tmp-base" "+$HEAD_SHA:refs/tmp-head"
-          BEHIND="$(git rev-list --count refs/tmp-head..refs/tmp-base)"
+          git fetch --no-tags origin "+refs/heads/$BASE_REF:refs/tmp-base" "+$HEAD_SHA:refs/tmp-head"
+          BEHIND="$(git rev-list --count refs/tmp-head..refs/tmp-base)"
           if [ "$BEHIND" -gt 0 ]; then
-            echo "::error::Branch is stale: main advanced $BEHIND commit(s) past the merge-base. Rebase onto latest origin/main before submission."
+            echo "::error::Branch is stale: main advanced $BEHIND commit(s) past the merge-base. Rebase onto latest origin/$BASE_REF before submission."
             exit 1
           fi
```

On landing, update `docs/INGRESS_SECURITY_POLICY.md` §5.3 to the applied form (the artifact
block there is already the byte-identical landed job; its prose gains the live-ref fetch
wording) — that doc edit is NOT included here to keep this patch single-purpose.

## U9 similar-problem sweep (frozen-SHA class, whole-workflow)

| Surface | Verdict |
|---|---|
| `pipeline.yml` stale_base_guard | **defect (this document)** — needs a live ref, uses the frozen event snapshot |
| `landing.yml:294-295,341` `EVENT_PR_BASE_SHA` / `.base.sha` / `.baseRefOid` | **cleared** — post-merge *diff anchor* for patch-branch extraction; a recorded historical base is the correct semantics there (authors documented the reasoning at the REST fallback); empirically sound across dozens of correctly-scoped bridge landings |
| `.githooks/pre-push` stale-base check | **cleared** — already fetches the live `main` ref (the pattern this fix adopts) |
| `pipeline.yml` duplicate/issue-reference/branch-naming guards | cleared — no base-SHA arithmetic |

## Verified no-actionable-finding surfaces this pass (AGENT_RULES §10)

- Whole-tree at `8242d4e`: `py_compile` all `.py` PASS; YAML `safe_load` all `.yml` PASS;
  `bash -n` all tracked `.sh` PASS (incl. the hook); `pyflakes` full scan → 2 hits only
  (`Sequence` NameError — already WO'd and bridge-queued via #257; one unused import in
  `infrastructure/mcp-control-plane/scripts/runtime/infisical_bootstrap.py` — cosmetic,
  patch WO filed separately by the same lane).
- Offline battery independently re-run: dispatcher `--verify-only` 8-tier PASS
  (`CONTRACT_VERSION=agent-loop-contract/1`); parity checker tiers 1..8, 7 guards PASS;
  releaser `--self-test` PASS; boundary `--check` 222 files / 0 violations; schema
  test-suite 15/15; hook `--self-test` 5/5 + exec bit; doc relative-link sweep 46/46 resolve;
  §5.3 artifact ↔ landed job byte-parity confirmed.

## Evidence record

| Check | Result |
|---|---|
| Sources for `base.sha` snapshot semantics | GitHub Community #59677, #25427; actions/runner #1689 (URLs inline above) |
| Defect repro (scenario D) | sandbox: `BEHIND=0`, exit 0 on 2-commit-stale branch |
| Corrected logic (scenarios A/B/C) | reject-stale exit 1; accept-fresh exit 0; fetch-failure exit 128 |
| `bash -n` corrected run-block | PASS |
| YAML `safe_load` corrected job block | PASS |
| Audit base | main `8242d4e` (PR #253 landed) |
