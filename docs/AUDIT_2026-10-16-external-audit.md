# AUDIT — 2026-10-16 external full-project audit (`supremeai-open`)

> **id:** audit-2026-10-16-external-full-project
> **title:** External full-project audit — post-#222 lifecycle migration fallout + integrity sweeps
> **document_role:** audit
> **status:** active
> **canonical:** true
> **owner:** agent-orchestration (Auditor role, AGENT_RULES.md §3)
> **last_verified:** 2026-10-16
> **related_docs:** [AGENTS.md](../AGENTS.md) · [AGENT_RULES.md](../AGENT_RULES.md) · [AGENT_LOOP_SPEC.md](AGENT_LOOP_SPEC.md) · [AUDIT_2026-10-15-duplicate-sweep.md](AUDIT_2026-10-15-duplicate-sweep.md) · [AUDIT_2026-10-15.md](AUDIT_2026-10-15.md)
> **source_issue:** filed via bridge (this document's own Work Order)

> **Auditor:** external autonomous contributor agent (zero-credential Pathway 1, AGENTS.md §2.1).
> **Method:** admin-directed full-project audit. Main audited at `57d158a`. Every tracked file
> family read or swept: both workflows line-by-line, all 5 Python programs (loop, parity
> checker, releaser, boundary guard, bridge PR opener), tests, api-schemas (validated),
> live docs (link integrity + SSOT contradiction check), AGENTS/AGENT_RULES. Machine
> verification ran locally: the full offline gate battery (`--verify-only` →
> `CONTRACT_VERSION=agent-loop-contract/1`; both self-tests; boundary `--check` 213 files;
> parity checker tiers 1..8; schema test-suite 15/15) — all green. Auditor policy §3 and the
> §4 issue-creation pipeline applied to every finding.

## Trigger context

PR #222 (`a6911c1`, "remove status:unclaimed requirement and adopt implicit claimable
lifecycle") landed ~10 hours before this audit and migrated three surfaces (loop, releaser,
issue template). This audit swept the migration for incomplete fallout (U9 sweep across the
whole project), then swept the remaining surfaces for unrelated defects. Nothing filed here
overlaps #86–#95, #98, #116–#123 (all pre-date `a6911c1`) or the bridge queue at audit time.

## Findings — filed as atomic Work Orders

| WO | Priority | Group | Finding | Status |
|---|---|---|---|---|
| [#233](https://github.com/Supremeai-bd/supremeai-open/issues/233) | P1 | agent-orchestration | **`stale_claim_releaser.py` crashes with `NameError: CLAIMABLE_LABEL` on any open issue lacking a claimed label** (constant removed by #222, two live references left at lines 96/380). `extract_claim_timestamp()` runs for every non-excluded open issue; with `set -euo pipefail` the agent-loop job died at the lease-gate step each tick — **the 30-min reconciliation loop was dead on main since `a6911c1`**. Reproduced at function level pre-fix; regression fixtures added to `--self-test` (P6). Patch submitted. | WO filed, patch attached |
| [#239](https://github.com/Supremeai-bd/supremeai-open/issues/239) | P2 | agent-orchestration | **Three live policy docs still document the removed label-gated lifecycle**: `CONTRIBUTING.md` ("mirrors never carry status:unclaimed"), `AUTONOMY_LOOP_CONTRACT.md` ("claimable = status:unclaimed only" — exclusion list also omits `status:claimed`), `HEARTBEAT_PROTOCOL.md` ("re-enters the pool with status:unclaimed"). Agents mirroring board state from docs would mis-read the code's actual selection policy. All three restated to the implicit-claimable contract; post-fix grep: 0 stale refs in live docs. | WO filed, patch attached |
| [#240](https://github.com/Supremeai-bd/supremeai-open/issues/240) | P3 | agent-orchestration | **5 broken relative links in `AUDIT_2026-10-15.md`** (GUARD-DOC-LINK, §8: "broken links are defects"): three `../../X` links escape the repo, two `../X` links point at repo root instead of `docs/`. Fixed; post-fix link sweep resolves all targets. | WO filed, patch attached |

## Finding — needs an authorized lane (`.github/` is bridge-protected)

### F1 · P1 · agent-orchestration — Board pre-check still gates the dispatcher on the removed `status:unclaimed` label

The agent-loop job's Board pre-check (`.github/workflows/pipeline.yml`, "Board pre-check"
step) fetches issues with `--label "status:unclaimed"` and sets `has_work=false` when the
filtered list is empty. Since #222 nothing applies or maintains that label — once legacy
labels desync or age out, the scheduled dispatcher silently no-ops **while claimable work
exists**. (Masked until now only because #233's crash killed the job earlier in the same
step sequence — two independent #222-fallout defects in one job.)

The bridge lane hard-rejects `.github/` paths (`Path '.github/workflows/pipeline.yml' is
protected`), so the verified fix is carried here for an authorized lane. It fetches the
whole board and mirrors `pick_next_issue()`'s `EXCLUDED_LABELS` exactly (offline-validated
against a 7-fixture board: plain + legacy-labeled issues claimable; claimed/held/blocked/
mirror/mixed-case excluded):

```diff
--- a/.github/workflows/pipeline.yml
+++ b/.github/workflows/pipeline.yml
@@ -451,13 +451,16 @@
-      # #88: has_work reflects CLAIMABLE work only (status:unclaimed, whole
-      # board) so the cron no-ops when every open issue is already claimed.
+      # #88 + #222: has_work reflects CLAIMABLE work only under the implicit
+      # claimable lifecycle — every open issue minus the pick_next_issue()
+      # exclusion set — so the cron no-ops when every open issue is claimed,
+      # held, blocked or a private mirror. Gating on the legacy
+      # status:unclaimed label starves the dispatcher once labels desync
+      # (nothing applies that label since #222).
       - name: Board pre-check (explicit no-op on empty or fully-claimed board)
         id: board
         run: |
           set -euo pipefail
-          BOARD=$(gh issue list --repo Supremeai-bd/supremeai-open --state open --label "status:unclaimed" --limit 200 --json number,title,labels)
-          # Mirror issues (#122) are born non-claimable — exclude the marker.
-          CLAIMABLE=$(echo "$BOARD" | jq '[.[] | select([.labels[].name] | index("mirror:private") | not)]')
+          BOARD=$(gh issue list --repo Supremeai-bd/supremeai-open --state open --limit 200 --json number,title,labels)
+          # Mirror the pick_next_issue() EXCLUDED_LABELS set exactly (case-insensitive,
+          # like the loop's .lower()): claimed, in-progress, seq-hold, blocked, private mirror.
+          CLAIMABLE=$(echo "$BOARD" | jq '[.[] | select((["status:claimed","status:in-progress","state:seq-hold","blocked-by-upstream","mirror:private"]) as $ex | ([.labels[].name] | map(ascii_downcase)) as $names | ($ex | any(. as $x | $names | index($x))) | not)]')
```

## Observation — ADMIN_DECISION class (no patch filed)

### F5 · P3 · architecture — auto-bridge scope list may under-bridge shared schema assets

`landing.yml`'s bridge-dispatch scope check bridges only
`scripts/agents/* | docs/* | AGENTS.md | AGENT_RULES.md | infrastructure/*`. Changes to
`api-schemas/` (the public schema SSOT the private tower consumes, e.g. the webhook
signature convention), `tests/`, `scripts/ci/`, or `examples/` land on public main **without
any auto-bridge sync** — private drift is possible if private consumers expect those assets.
Whether this is an intentional diet (#155) or a gap requires admin intent; per §6/P3 no
patch was presumed. Recorded as an observation for an ADMIN_DECISION issue.

## Honest retraction (U2)

The initial sweep grep for the literal string `ain]` flagged `landing.yml:69` as a corrupted
trigger (`branches: ain]`) and `pipeline.yml:22` as a second instance. Byte-level
verification proved **both are valid `[main]` literals** — the grep matched the `ain]`
substring *inside* `[main]`, and ANSI-escape handling in the audit tooling's output rendering
consistently swallowed the preceding `[m`. No corruption exists; no WO was filed for it. The
false-positive is recorded here because the sweep report must classify, not hide, its own
errors (U9 report below).

## U9 sweep report

`similar found: 4 | fixed in-task: 3 (WOs #233, #239, #240) | filed follow-up: 1 (F1, this
document — blocked from the patch lane by .github/ protection) | false-positive retracted: 1
(non-existent ain] corruption)` — plus 1 ADMIN_DECISION-class observation (F5).

## Verified no-actionable-finding surfaces (AGENT_RULES §10)

- `auto_bridge_pr_opener.py`, `check_loop_contract_parity.py`, `boundary_sanitization_guard.py`: read in full; no defects. All self-tests green offline.
- `api-schemas/`: all 5 schema files pass the repo's own Draft-2020-12 test-suite (15/15).
- `tests/test_validate_schemas.py`: green on the current tree.
- Workflow YAML: both files parse cleanly; landing.yml merge/dedup/fail-honest logic reviewed line-by-line, no defects beyond F1/F5 above.
- Docs relative-link integrity repo-wide: zero broken links remaining post-#240.

## Evidence record

| Check | Result |
|---|---|
| Audited commit | `57d158a` (main) |
| `continuous_agent_loop.py --verify-only` | exit 0, ends `CONTRACT_VERSION=agent-loop-contract/1` |
| `stale_claim_releaser.py --self-test` | pass pre-fix (structurally blind to F4), pass post-fix with new regression fixtures |
| `boundary_sanitization_guard.py --self-test` / `--check` | pass / 213 files, 0 violations |
| `check_loop_contract_parity.py` | tiers 1..8 OK, 5 guards match, all workflow references resolve |
| schema test-suite | 15/15 pass |
| NameError repro (pre-fix) | `extract_claim_timestamp` on plain unclaimed issue → `NameError: CLAIMABLE_LABEL` (function-level, reproduced twice) |
| jq exclusion expression | 7-fixture offline board → `[1,2]` (plain + legacy-labeled claimable; claimed/held/blocked/mirror/mixed-case excluded) |
| Docs link sweep | 5 broken pre-#240 → 0 after |
| Board re-checked at declaration (#4177) | bridge queue re-polled post-submission; WOs #233/#239/#240 visible with patch branches; no competing coverage for any finding |

## Addendum 2 — Scout round 2 (2026-10-16, main `8242d4e`)

Ecosystem-Scout round re-swept the project after 5 more PRs landed (#242/#243/#244 = this
audit's own follow-ups; #246, #247, #253). Status of this document's original findings:

- **F4 (P1 releaser NameError): RESOLVED** — landed as PR #236 (`d9c7eb1`).
- **F2 (P2 stale lifecycle docs): RESOLVED** — landed as PR #244 (`ebedba0`); zero
  `status:unclaimed` references remain in live policy docs (re-verified on `8242d4e`).
- **F1 (P1 pipeline.yml board pre-check starvation): RESOLVED** — PR #246 (`be9f45b`)
  "align board pre-check" landed the whole-board fetch: the live gate at
  `.github/workflows/pipeline.yml:508` now reads
  `gh issue list --state open --limit 200 --json number,title,labels` with no
  `status:unclaimed` label filter (re-verified on `8242d4e`) — the fix diff carried in
  this document was adopted by the internal lane.
- **F6 (P3 broken links): RESOLVED** — landed as PR #243 (`531078f`).

**New verified findings this round (fixes built, regression-tested, and preserved on local
branches; submission to the board is currently BLOCKED — see below):**

1. `federated_ci_watcher.ts` `defaultCreateIssue` (PR #229 surface, unchanged on
   `8242d4e`): the module header and inline comment promise the dropped-`repo:<slug>`-label
   note rides IN the created issue body; the 422-fallback retry actually sends the
   unchanged body — the note exists only in the return metadata, which `attemptReport`
   never reads. Pre-fix defect reproduced with a stubbed fetch; fix sends `body + note` on
   retry, extracts `issueUrl` from the fallback 201 response (was hardcoded undefined),
   and adds 3 regression assertions to `test_federated_ci_watcher.ts` §6. Full repo
   watcher suite under bun: ALL CHECKS PASSED (pre- and post-fix). Branch:
   `bridge/bridge-20261016-watcher-422-note-emission` (2 files, +23/−5).
2. `api-schemas/federated-ci-failure.schema.json` `$id` is a bare relative string while
   all 4 other published schemas use absolute URLs; `validate_schemas.py` enforces
   presence+uniqueness but not format, so the drift passes the SSOT gate silently. One-line
   align to `https://supremeai.ai/schemas/federated-ci-failure.schema.json`; payload
   discriminator `properties.schema.const` untouched (zero consumers reference the `$id`);
   suite 15/15 before/after. ADMIN_DECISION observation: existing absolute ids split
   across `supremeai.ai` ×2 and `supremeai.dev` ×2 — a canonical host would let the
   validator enforce `$id` format later. Branch:
   `bridge/bridge-20261016-schema-id-convention-align` (1 file, +1/−1).

**BLOCKER (verified, unfixed from this lane): `bridge_submit_patch` issue-creation step
returns `HTTP 422: Validation Failed`** for every new WO since ~01:15Z (bounded: a sibling
WO #245 was created successfully at 01:00Z; three of my submissions — 2× watcher payload
37KB TS, 1× schema payload 13KB ASCII — all committed to their `bridge/<task-id>` branches
but failed at the exact same issue-creation step; tower `system_health` 29/30 healthy;
payload sizes far under the documented 200KB/30-file caps; both payloads passed the
10-family secret scan; summaries ≤1000 chars, `testsEvidence`/`agentIdentity` strings per
schema). The blocker report itself needs the broken channel — recorded here and in the
agent worklog instead (chicken-and-egg, honestly noted per U2).

**Round-2 gates (all green on `8242d4e`):** py_compile 11/11; schema suite 15/15;
`continuous_agent_loop.py --verify-only` → `CONTRACT_VERSION=agent-loop-contract/1`;
`stale_claim_releaser.py --self-test` pass; watcher TS suite under bun: all checks pass;
issue-template YAML ×3 parse clean; `ECOSYSTEM_MAP.md` contact link present on main;
`FEDERATED_CI_WATCHER.md` relative links 0 broken.

**U9 sweep report (round 2):** `similar found: 2 | fixed in-task: 0 | filed follow-up: 2
(watcher 422-note emission; schema $id convention) | original findings resolved: 4/4`.
