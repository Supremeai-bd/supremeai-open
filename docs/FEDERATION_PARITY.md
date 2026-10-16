# Federation Parity — Studio Drift Audit & Upstream Sync Handoff (#399)

```yaml
id: federation-parity-studio-drift-audit
title: Automated parity and drift detection between monorepo frontend/ and supremeai-studio
document_role: handoff
status: ready-to-apply
canonical: true
owner: agent-orchestration
last_verified: 2026-10-17
related_docs:
  - AGENTS.md
  - docs/INGRESS_SECURITY_POLICY.md
  - docs/CONSUMERS.md
  - ECOSYSTEM_MAP.md
source_issue: "https://github.com/Supremeai-bd/supremeai-open/issues/399"
```

## Related Documents

- [`AGENTS.md`](../AGENTS.md) — Two-Tier Ingress Invariant (§1.4), submission pathways (§2.1).
- [`docs/INGRESS_SECURITY_POLICY.md`](./INGRESS_SECURITY_POLICY.md) — the fail-honest degradation
  doctrine the auditor inherits ("never blocks what it cannot verify; never claims verification
  it did not do").
- [`ECOSYSTEM_MAP.md`](../ECOSYSTEM_MAP.md) — 12-repo routing matrix; `repo:studio` domain.

---

## Purpose

The federation maintains a standalone frontend repository
(`Supremeai-bd/supremeai-studio`, Vercel production host) while the central
monorepo (`Supremeai-bd/supremeai`) carries the mirror surface `frontend/`.
Independent commits on either side (Vercel deployment adjustments, environment
configurations, hotfixes applied directly in one tree) silently diverge the two
copies — code drift with no detector.

This handoff closes that gap with the issue's declared scope, exactly:

| Scope file (issue #399) | Status on `main` | Delivery lane in this handoff |
|---|---|---|
| `.github/workflows/upstream-sync.yml` | absent (NEW) | **Appendix A** below (protected-lane byte-exact handoff — `.github/` is admin-review-only for the zero-credential bridge) |
| `scripts/audit/verify_studio_parity.sh` | absent (NEW) | **delivered as a real file** by the same bridge submission (pure-new-file lane) |
| `docs/FEDERATION_PARITY.md` | absent (NEW) | this document (pure-new-file lane) |
| *(supporting)* `scripts/ci/boundary_sanitization_guard.py` APPROVED_SUBTREES registry | pre-existing | **Appendix B** content-anchored hunk — the guard's own documented expansion process ("registry changes ride a PR that references the governing issue"); `scripts/audit/` must become an approved subtree for the file above to pass the Layer-3 surface guard |

Why one appendix and not a direct file: the bridge's protected-path contract
(`.github/` → admin review) is unchanged, and the public repo's "Federation
Workflow Diet — public boundary 5 → 2 workflows" doctrine
(`.github/workflows/landing.yml` header) forbids re-introducing public
workflows. The audit workflow therefore belongs to the **private monorepo**,
where the byte-exact content below is applied by hand — the same
proven lane used for the `pipeline.yml` guard handoff (#392, landed via
PR #235 + commit `ee1cb19`).

## 1. Host-Repository Analysis (why the monorepo hosts the workflow)

| Host candidate | Reads | Token required | Verdict |
|---|---|---|---|
| **Private monorepo** (`Supremeai-bd/supremeai`) | `frontend/` in-workspace; clones the **public** studio repo | none (public clone) | **RECOMMENDED** — zero credentials, `frontend/` SSOT is local |
| `Supremeai-bd/supremeai-studio` | clones the **private** monorepo | PAT with private-repo scope | REJECTED — private credential material in a public-repo Actions context |
| `Supremeai-bd/supremeai-open` | clones both | none for reads | REJECTED — violates the public workflow diet (2-workflow boundary doctrine) |

The auditor script itself is host-agnostic (explicit `--monorepo-root` /
`--studio-root`), so the maintainer retains the final placement decision; the
recommendation is encoded in Appendix A's checkout order.

## 2. Parity Surface & Exclusions

**Mirror surface:** every file under monorepo `frontend/` ↔ the same relative
path at the studio checkout root (`frontend/<rel>` ↔ `<rel>`).

**Default exclusions** (basename or glob, overridable via repeatable
`--exclude PAT`; the secret guard applies *regardless* of any override):

| Class | Patterns | Rationale |
|---|---|---|
| Repo plumbing | `.git`, `.github` | repo-specific, not product surface |
| Build outputs | `node_modules`, `.next`, `dist`, `build`, `coverage`, `.vercel`, `.nuxt`, `out` | generated, never mirrored |
| **Secrets** | `.env*`, `*.env`, plus an absolute guard for `*.pem`, `*.key`, `*.p12`, `*credential*` | **never hashed, never read, never reported** — divergence in secrets is invisible to the auditor by design (secret hygiene) |
| Deploy config | `vercel.json` | deployment-target-specific |
| Lockfiles | `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lockb` | cross-repo byte-parity of lockfiles is meaningless; dependency *alignment* is owned by the dependency plane |
| `package.json` | `package.json` | `name`/`scripts` fields legitimately differ; alignment is owned by the dependency plane (never byte-judged) |

## 3. Auditor Contract — `scripts/audit/verify_studio_parity.sh`

Dependency-free POSIX sh (git + coreutils; one optional python3-assisted plane
that reports `SKIPPED` honestly when python3 is absent). Read-only: never
mutates either tree, never clones, never touches the network — the workflow
owns all IO.

```
sh scripts/audit/verify_studio_parity.sh \
     --monorepo-root /path/to/monorepo \
     --studio-root   /path/to/supremeai-studio \
     [--report parity-report.md] [--json parity-summary.json] \
     [--exclude pattern] ... [--self-test]
```

**Exit contract** (machine-readable, asserted by Appendix A):

| Code | Verdict | Meaning |
|---|---|---|
| `0` | `PARITY` | every executed plane clean; skipped planes recorded with reasons — a skipped plane never masks drift |
| `1` | `DRIFT` | at least one executed plane found divergence |
| `2` | `ERROR` | operational failure (missing roots, unreadable files) — **UNVERIFIABLE is never clean** |

**Three audit planes:**

1. **Byte/hash parity** — per-file sha256 across the surface; classes
   `DRIFTED` / `MONOREPO_ONLY` / `STUDIO_ONLY` / `UNREADABLE`. `STUDIO_ONLY`
   rows flow studio → monorepo, `MONOREPO_ONLY`/`DRIFTED` rows flow
   monorepo → studio (**bi-directional**, per the issue's requirement 2).
2. **Dependency-map parity** — `dependencies` + `devDependencies` name→version
   maps of both `package.json` files; classes `VERSION_MISMATCH`,
   `MISSING_IN_STUDIO`, `MISSING_IN_MONOREPO`. Honest degradation: python3
   absent or JSON unparseable ⇒ `SKIPPED` with the reason printed in the
   report (advisory, never silently clean).
3. **Design-token alignment** — filtered view of the byte plane for
   `*tokens*.{json,css,js,ts,cjs,mjs}` paths; unpaired or drifted token files
   surface in a dedicated table (issue's requirement 3).

**Report:** deterministic markdown (no timestamps by default; opt-in
correlation via `PARITY_RUN_ID` env), row-capped at 200/plane with an explicit
`+N more` truncation note, plus an optional machine-readable `--json` summary
(`verdict` + per-plane counts). `--self-test` runs a 20-assertion offline
fixture suite asserting the full exit contract (guard-the-guard, house style
of `.githooks/pre-push --self-test`).

## 4. Appendix A — `.github/workflows/upstream-sync.yml` (byte-exact handoff)

> **Application note (maintainer):** copy the YAML block below verbatim into
> `Supremeai-bd/supremeai/.github/workflows/upstream-sync.yml` in the private
> monorepo. The engine file `scripts/audit/verify_studio_parity.sh` and this
> document arrive through the bridge as real files — no manual step for them.

```yaml
# =============================================================================
# Upstream Sync — Studio Parity Drift Audit (#399)
# =============================================================================
# Scheduled + on-demand parity audit between the monorepo mirror surface
# (`frontend/`) and the standalone Supremeai-bd/supremeai-studio repository.
#
# Engine: scripts/audit/verify_studio_parity.sh (read-only, dependency-free,
# exit contract 0=PARITY / 1=DRIFT / 2=ERROR — docs/FEDERATION_PARITY.md §3).
#
# Alert doctrine (fail-loud, never fail-spam, never fail-merge):
#   - DRIFT (exit 1) -> open or update ONE tracking issue with the report,
#     upload the report artifact, and fail the job when fail_on_drift is
#     true (default). Bi-directional: monorepo->studio AND studio->monorepo.
#   - ERROR (exit 2) -> ::error:: annotation + red job only. Transient
#     operational failures (network, clone) must never spam the tracker
#     (degradation policy, landing.yml-house: fail-loud not fail-spam).
#   - PARITY (exit 0) -> green run; report still uploaded for transparency.
#
# Host analysis (docs/FEDERATION_PARITY.md §1): this workflow belongs in the
# private monorepo (frontend/ SSOT side) — cloning the PUBLIC studio repo
# needs no token there. Hosting it in supremeai-studio would require a PAT
# with private-repo scope to read the monorepo — rejected (credential
# exposure). Apply verbatim to .github/workflows/upstream-sync.yml.
# =============================================================================

name: Upstream Sync — Studio Parity Drift Audit

on:
  schedule:
    - cron: "23 3 * * *" # daily 03:23 UTC — off-peak minute, away from the top-of-hour Actions herd
  workflow_dispatch:
    inputs:
      fail_on_drift:
        description: "Fail the job when drift is detected (false = report-only run)"
        required: false
        default: "true"

permissions:
  contents: read
  issues: write

concurrency:
  group: upstream-sync-studio-parity
  cancel-in-progress: false

jobs:
  studio-parity-audit:
    name: "🔁 Studio Parity Drift Audit (#399)"
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - name: Checkout monorepo (parity SSOT side)
        uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - name: Clone public studio mirror (shallow, read-only, no token)
        run: |
          git clone --depth 1 https://github.com/Supremeai-bd/supremeai-studio.git /tmp/supremeai-studio

      - name: Run parity auditor (exit contract 0=PARITY, 1=DRIFT, 2=ERROR)
        id: parity
        env:
          PARITY_RUN_ID: "${{ github.run_id }}-${{ github.run_attempt }}"
        run: |
          CODE=0
          sh scripts/audit/verify_studio_parity.sh \
            --monorepo-root "$GITHUB_WORKSPACE" \
            --studio-root /tmp/supremeai-studio \
            --report /tmp/parity-report.md \
            --json /tmp/parity-summary.json || CODE=$?
          echo "exit_code=$CODE" >> "$GITHUB_OUTPUT"
          cat /tmp/parity-report.md >> "$GITHUB_STEP_SUMMARY"
          echo "Auditor exit code: $CODE"

      - name: Upload audit report artifact (transparency on every run)
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: studio-parity-report
          path: |
            /tmp/parity-report.md
            /tmp/parity-summary.json
          if-no-files-found: warn
          retention-days: 30

      - name: Open or update the bi-directional drift alert issue (DRIFT only)
        if: steps.parity.outputs.exit_code == '1'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # Untrusted free-text input passes through env — never interpolated
          # into the shell body (landing.yml injection-fix house style).
          FAIL_ON_DRIFT: ${{ github.event.inputs.fail_on_drift || 'true' }}
        run: |
          DATE_TAG="$(date -u +%Y-%m-%d)"
          MARKER="Studio Parity Alert"
          # Dedup: ONE open alert issue, appended per audit — never issue spam.
          EXISTING="$(gh issue list --repo "${{ github.repository }}" \
            --state open --search "${MARKER} in:title" --json number \
            -q '.[0].number' 2>/dev/null || true)"
          if [ -n "$EXISTING" ] && [ "$EXISTING" != "null" ]; then
            gh issue comment "$EXISTING" --repo "${{ github.repository }}" \
              --body-file /tmp/parity-report.md
            echo "Appended drift report to the existing alert issue #$EXISTING."
          else
            gh issue create --repo "${{ github.repository }}" \
              --title "🔁 ${MARKER} (${DATE_TAG}) — monorepo/frontend <-> supremeai-studio drift" \
              --body-file /tmp/parity-report.md \
              --label "area:ci" \
              || gh issue create --repo "${{ github.repository }}" \
                   --title "🔁 ${MARKER} (${DATE_TAG}) — monorepo/frontend <-> supremeai-studio drift" \
                   --body-file /tmp/parity-report.md \
              || echo "::warning::alert issue creation failed — the report remains in the run summary and the artifact"
          fi
          # fail_on_drift=false turns the run into a report-only audit.
          if [ "$FAIL_ON_DRIFT" = "true" ]; then
            echo "::error::Studio parity DRIFT detected — see the run summary and the alert issue (remediation directions: docs/FEDERATION_PARITY.md §3)."
            exit 1
          fi
          echo "::warning::Drift detected with fail_on_drift=false — report-only run, job stays green."

      - name: Fail honestly on operational error (ERROR only, no tracker spam)
        if: steps.parity.outputs.exit_code == '2'
        run: |
          echo "::error::Parity auditor could not verify (exit 2) — operational failure, NOT a clean run. Inspect the logs; re-run after fixing the environment."
          exit 1
```

## 5. Verification Contract Mapping (issue #399, 3-tier)

| Tier | Issue contract | Where it is satisfied |
|---|---|---|
| 1. Reflection | `git grep -n "upstream-sync" .github/workflows/` | passes in the private monorepo after Appendix A is applied (the file name is referenced in its own header comment and the `concurrency.group: upstream-sync-studio-parity` line carries the token in content) |
| 2. Boot smoke | `bash -n scripts/audit/verify_studio_parity.sh` | executed in the battery (see §6) — syntax gate green; the path is the issue's declared Touching-Files path verbatim (kept despite needing the Appendix B registry expansion — the scope contract wins over path convenience) |
| 3. Test suite | `pnpm run typecheck` | **context-bound by nature**: `pnpm` runs in the studio/frontend trees, which do not exist in `supremeai-open` (no `package.json` workspace here). The equivalent executed-here suite is the auditor's own `--self-test` (20 assertions) + the battery matrix below; `pnpm run typecheck` remains a post-application step in the target repos. |

## 5.5 Appendix B — boundary registry expansion hunk (byte-exact handoff)

> **Application note (maintainer):** the auditor's declared path
> `scripts/audit/verify_studio_parity.sh` is not yet an approved public
> surface — the Layer-3 guard fails closed on it until the registry below is
> expanded. Per `scripts/ci/boundary_sanitization_guard.py`'s own docstring
> ("APPROVED_* below via a PR that references the governing issue"), this is
> that PR. The hunk is content-anchored: the old-line below is byte-unique on
> `main` @ `7f5f08a` (verified by battery), so drift either keeps it matching
> or fails the apply loudly — never silently mis-applies.

**File:** `scripts/ci/boundary_sanitization_guard.py`

**Anchor (old line, byte-unique on `7f5f08a`):**

```python
    "scripts": {"agents", "ops", "ci", "validate_schemas.py"},
```

**Replace with:**

```python
    "scripts": {"agents", "ops", "ci", "audit", "validate_schemas.py"},  # audit/ — issue #399 studio parity auditor surface
```

Battery proof: after applying this hunk to a scratch clone of the delivery
branch, `python3 scripts/ci/boundary_sanitization_guard.py --check` reports
`files_scanned=263 violations=0` — the auditor file passes the Layer-3
surface guard with the issue-mandated path intact. Content-layer
proprietary-logic scanning still applies to the new file (path approval
never bypasses content rules — guard docstring).

## 6. Battery Evidence (executed at submission time)

1. `bash -n scripts/audit/verify_studio_parity.sh` — clean.
2. `--self-test` — **20/20 PASS**: identical-trees exit 0; byte-drift exit 1
   with classified report rows; one-sided files both directions; missing roots
   exit 2; dependency-plane drift rows (`VERSION_MISMATCH` /
   `MISSING_IN_STUDIO`); design-token drift row; `.env` divergence excluded
   pre-read with zero secret content in the report; JSON summary schema
   (`verdict` + per-plane counts); byte-level report determinism across runs.
3. Workflow appendix structural checks (battery-executed): YAML parses;
   `permissions` = read + issues:write only; `concurrency` present with
   `cancel-in-progress: false`; job timeout set; `fail_on_drift` consumed via
   `env` (never inline interpolation); engine invocation flags match §3
   exactly; DRIFT → alert flow, ERROR → `::error::` without issue creation.
4. Boundary apply-simulation — Appendix B hunk applied to a scratch clone of
   the delivery branch, then `boundary_sanitization_guard.py --check`:
   `files_scanned=263 violations=0` (the auditor passes Layer-3 with the
   issue-mandated `scripts/audit/` path); the anchor old-line is byte-unique
   on `main` @ `7f5f08a` (single occurrence across the tree).
5. Secret scan (10 families, structure-aware) — 0 hits across all delivered
   files; UTF-8 round-trip clean.

## 7. U9 Similar-Problem Sweep

| Surface | Status |
|---|---|
| Landing-time patch parity | already covered — bridge streams by merge-commit SHA (by-reference, `landing.yml`) |
| Public↔private doc mirrors | covered separately — byte-mirror doctrine on `docs/CONSUMERS.md` (README §56) with private-source-plane-first application order |
| Schema parity (`api-schemas/`) | covered — `scripts/validate_schemas.py` + OpenAPI SSOT workflow |
| This surface (studio ↔ monorepo frontend trees) | **fixed in-task** — auditor + scheduled workflow (this handoff) |

## 8. Reflection Evidence

- **why:** the drift detector is a three-plane auditor (byte / dependency-map /
  design-token) instead of a raw `diff -r`: byte-parity alone false-positives
  on files whose divergence is legitimate (`package.json` name fields) while
  missing alignment drift that matters (dep versions, token schemas); the
  plane structure keeps every requirement of the issue individually
  attributable and individually exit-code-bearing.
- **alternatives_rejected:** (a) hosting the workflow in `supremeai-studio` —
  requires a private-repo PAT in a public Actions context (credential
  exposure, rejected in §1); (b) auto-syncing drift automatically from the
  workflow — mutation of either tree by a scheduled job violates the
  read-only-auditor principle; alerts with direction-attributed rows keep the
  landing authority with the constitutional gates; (c) a `supremeai-open`
  `.github/workflows/upstream-sync.yml` — violates the public workflow diet
  (2-workflow boundary doctrine) and would place the byte-exact file behind
  the protected-path lane anyway; (d) relocating the auditor to the already
  approved `scripts/ci/` subtree — deviates from the issue's declared
  Touching-Files path (`bash -n scripts/audit/verify_studio_parity.sh`), and
  the guard's own documented registry-expansion process (Appendix B) keeps
  the scope contract intact without path games.
