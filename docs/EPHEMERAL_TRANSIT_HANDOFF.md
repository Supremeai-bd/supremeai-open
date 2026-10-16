# Ephemeral Transit Pipeline — operator hand-off (#416, The Ephemeral Mailbox Model)

Task ID: `bridge-20261016-ephemeral-transit-prune-r1` · Agent: `zai-autonomous-contributor`
Base: `9fc5d47` (current main tip) · Lane: **pure-new-file** (the only lane that survives
bridge v1's private-main apply — measured across WO #370 landed, #393/#394/#417 in-gates
vs the #377/#378/#388/#396/#415 rejection wave).

## Problem census

- Bridge patches land in `supremeai-open/patches/` and stay there **permanently**.
  Current inventory: `patches/bridge-20261016-kaggle-meta-cognition.patch` (PR #407).
- Consequences: repository bloat, historical noise, and **proprietary code residue on
  public GitHub history** (a patch carrying core-class logic never leaves the public
  repo even after the satellite dispatch landed it privately).
- `git grep -n "auto-prune" .github/workflows/landing.yml` today: **0 hits** — the
  doctrine's cleanup stage does not exist anywhere in the federation.

## §1 Doctrine contract (the 5-stage lifecycle)

1. **Submission** — contributor/agent submits `patches/<task-id>.patch` here.
2. **Validation & landing** — CI guards evaluate fail-closed; merge gate auto-merges.
3. **Satellite dispatch** — landing.yml routes the landed change to its target repo.
4. **Monorepo synchronization** — satellite syncs into the central monolith.
5. **Auto-prune (THIS order)** — upon **verified** dispatch, remove the transit patch
   and keep the host pristine: `git rm patches/<task-id>.patch` + one doctrine commit.

**Fail-closed prune rule:** a patch is removed ONLY with structural dispatch evidence —
`{task_id, target_repo, dispatch_commit, dispatched_at}` — where the task-id matches the
patch filename (identity binding), the target is a known federation repo, the commit is
a hex sha, and the timestamp parses. **No evidence = hold, with explicit auditable
reasons.** The mailbox prefers residue over data loss: a pruned-but-undispatched patch
silently destroys the only public copy of that work.

## §2 Shipped files (4 NEW paths — zero bytes on existing files)

| Path | Kind | Purpose |
| --- | --- | --- |
| `scripts/ci/transit_prune.py` | NEW pure core | Vocabulary (14 dispatch targets from landing.yml), task-id parsing, evidence contract, fail-closed `build_prune_plan`, sweep `select_prunable_patches`, byte-exact commit-message builder. Zero I/O. |
| `scripts/ci/transit_prune_cli.py` | NEW I/O wrapper | Executable entry for the workflow step: scans inbox, loads evidence JSON, writes plan JSON. The CLI never deletes anything — execution stays in the workflow. |
| `tests/test_transit_prune.py` | NEW battery | Dual-mode (pytest + plain runner) offline suite: parsing, fail-closed zoo, byte-exact message, sweep partition, determinism, CLI end-to-end (tempdir), **doc-conformance** (§3.1 YAML asserted against the code contract). |
| `docs/EPHEMERAL_TRANSIT_HANDOFF.md` | NEW doc | This hand-off. |

### Module API (`scripts/ci/transit_prune.py`)

| Symbol | Kind | Contract |
| --- | --- | --- |
| `DEFAULT_DISPATCH_TARGETS` | frozenset | 14 federation targets, SSOT = landing.yml on public main |
| `parse_task_id(patch_ref)` | pure | → `(task_id, reasons)`; stem of `<task-id>.patch` (stems may contain dots/dashes) |
| `validate_dispatch_evidence(evidence, expected_task_id, known_targets=None)` | pure | 4-field contract: `task_id` identity binding, `target_repo` known, `dispatch_commit` hex sha 7-40, `dispatched_at` ISO-8601; every failure returns explicit reasons |
| `build_prune_plan(patch_ref, evidence, known_targets=None, now=None)` | pure | → `(plan, hold_reasons)`; plan None = HOLD (fail-closed); plan carries `commit_message` + evidence snapshot |
| `build_prune_commit_message(task_id)` | pure | byte-exact doctrine message (below) |
| `select_prunable_patches(patch_refs, evidence_by_task, known_targets=None, now=None)` | pure | inbox sweep → `{"prunable": [plans], "held": [{patch, reasons}]}`; absent evidence = hold |

The doctrine-mandated cleanup commit message, byte-exact:
`chore(bridge): auto-prune transit patch <task-id> after successful satellite dispatch`

The three scope surfaces named by the issue (`.github/workflows/landing.yml`,
`ECOSYSTEM_MAP.md`, `AGENTS.md`) are existing paths — mechanically unbridgeable here
(`.github/` hard-block, measured; doc hunks die on private-main drift, measured ×2 in
#377/#415). Their content ships below as byte-exact §3 blocks, operator-applied.

## §3 Operator application blocks

### §3.1 `.github/workflows/landing.yml` — append this job (Reflection Check target)

After apply, the issue's Reflection Check must pass:
`git grep -n "auto-prune" .github/workflows/landing.yml` → matches the job/step names below.

```yaml
jobs:
  auto-prune-transit-patches:
    # Ephemeral Transit Pipeline (#416): the mailbox is transit, not storage.
    # Fail-closed via scripts/ci/transit_prune.py — patches are selected for
    # removal ONLY with verified dispatch evidence. Dry-run by default.
    name: auto-prune transit patches (Ephemeral Mailbox #416)
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    runs-on: ubuntu-latest
    env:
      PRUNE_DRY_RUN: "true"
    steps:
      - name: Check out host repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Select prunable patches (fail-closed core)
        id: select
        run: |
          python3 scripts/ci/transit_prune_cli.py \
            --patches-dir patches \
            --evidence patches/dispatch-evidence.json \
            --out prune-plan.json
          echo "prunable_count=$(jq '.prunable | length' prune-plan.json)" >> "$GITHUB_OUTPUT"

      - name: Report dry-run prune plan
        if: env.PRUNE_DRY_RUN == 'true'
        run: |
          echo "DRY-RUN auto-prune plan (nothing removed):"
          cat prune-plan.json

      - name: Execute auto-prune (git rm + doctrine commit)
        # Commit message contract (byte-exact, emitted by the pure core):
        #   chore(bridge): auto-prune transit patch <task-id> after successful satellite dispatch
        if: env.PRUNE_DRY_RUN == 'false' && steps.select.outputs.prunable_count != '0'
        run: |
          jq -r '.prunable[].patch' prune-plan.json | xargs -r git rm
          git config user.name "supremeai-bot"
          git config user.email "bot@supremeai.local"
          MSG="$(jq -r '.prunable[0].commit_message' prune-plan.json)"
          git commit -m "$MSG"
          git push origin main
```

Dispatch evidence convention: when the dispatch stage completes for a task, automation
(or an operator) appends to `patches/dispatch-evidence.json`:

```json
{
  "bridge-20261016-kaggle-meta-cognition": {
    "task_id": "bridge-20261016-kaggle-meta-cognition",
    "target_repo": "Supremeai-bd/supremeai",
    "dispatch_commit": "<sha of the dispatch commit>",
    "dispatched_at": "<ISO-8601>"
  }
}
```

Absent file or absent entry = hold (`no dispatch evidence`) — the verified default.

### §3.2 `ECOSYSTEM_MAP.md` — append to the host-repository policy section

```markdown
**Ephemeral Mailbox doctrine (#416).** `supremeai-open/patches/` is an ephemeral transit
inbox, not storage: patches land, dispatch to their federation target, and are then
auto-pruned by the `auto-prune-transit-patches` job with verified-dispatch evidence
(fail-closed — no evidence, no prune). The host repository stays pristine and
zero-residue; permanent records live in the target repositories and the archive.
```

### §3.3 `AGENTS.md` — append to the contributor etiquette section

```markdown
- `patches/` is a TRANSIT INBOX (Ephemeral Mailbox, #416): submit
  `patches/<task-id>.patch`, and after verified satellite dispatch the file is
  auto-removed by CI. Never treat a patch file here as a permanent artifact; the
  durable copies live in the target repository (and the archive keeps history).
```

### §3.4 `scripts/ci/boundary_sanitization_guard.py` — NO change

The issue's Boot Smoke (`python3 scripts/ci/boundary_sanitization_guard.py --check`)
targets an existing guard; this order ships no edit to it. Post-apply, re-run the smoke
to confirm the added job introduces no boundary violation.

## §4 Verification (3-tier, per the issue)

1. **Reflection Check** — post-apply: `git grep -n "auto-prune" .github/workflows/landing.yml`
   (pre-apply, the same contract is asserted offline by the battery's doc-conformance
   group against the §3.1 block).
2. **Boot Smoke** — `python3 scripts/ci/boundary_sanitization_guard.py --check` (unchanged guard).
3. **Test Suite (dry-run mode)** — `pytest tests/test_transit_prune.py` OR
   `python3 tests/test_transit_prune.py`: N groups incl. CLI end-to-end dry-run
   (plan emitted, nothing deleted) and the fail-closed hold of no-evidence patches.
   The workflow itself runs `PRUNE_DRY_RUN: "true"` by default — flip to `"false"`
   only after a green dry-run window.

Rollback: delete the 4 NEW paths and remove the §3 blocks; no schema, no workflow side
effects from this order itself.

## §5 Non-goals

- No retroactive pruning decisions in this order: the current resident patch
  (`bridge-20261016-kaggle-meta-cognition`) is held until its dispatch evidence entry
  exists — an admin/operator supplies it when the private landing sha is known.
- No changes to the dispatch stage itself (landing.yml routing) — prune is strictly
  downstream of dispatch.
- No expansion of the evidence contract beyond the four required fields; any future
  grace-window policy gets its own order (the core's `now` parameter is reserved).
