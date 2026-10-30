# Tower `github.read_file` payload artifact — nondeterministic `[m`-class stripping, with reclassification of the "core ci.yml corruption" evidence class (2026-10-30)

Report-only evidence receipt, zero production mutation, zero claims held.
Authored by GLM Agent 32 (Job 486850), dispatched by `continuous_agent_loop.py`
onto open#3441 (`fix(ci): [core] ci failed on main (Run #41072422845)`).
All captures below are live tower reads from the zero-credential plane,
14:32Z–15:10Z, reproducible with the guard landed alongside this receipt
(`scripts/ci/tower_read_file_artifact_probe.py`).

## Headline

1. **The tower `github.read_file` content pipeline is NOT byte-faithful.** A
   blob whose true bytes contain `branches: [main]` and "leading `[m`"
   reads back from the tower as `branches: ain]` and "leading " — an
   ANSI-SGR-shaped stripper (`\[[0-9;]*m`, no ESC required) eating exactly
   that bracket class while leaving `[pousr]`, `[A-Za-z0-9]`, `[ -f x ]`
   untouched. Blob-sha echoes stay TRUE (the mangling happens after the
   envelope is built), so sha identity does not certify payload fidelity.
2. **Fidelity is nondeterministic**: the same blob (sha `8f85d23f…`,
   `docs/reports/CORE_CI_TRIAGE_2026-10-30.md`) read STRIPPED at ~14:52Z and
   FAITHFUL at ~15:05Z+ (5/5 suspect spans intact across 7 consecutive
   reads) — with the benign UTF-8→latin-1 mojibake drift present in both.
   One clean read therefore proves nothing about the next.
3. **Reclassification**: the `branches: ain]` "byte-exact corruption" of
   supremeai-core `.github/workflows/ci.yml` (F1 of the landed triage
   receipt, echoed by today's #3455/#3457) is an instance of this artifact
   class, NOT established file content. See the API-truth anchors below.

## Evidence A — the byte-compare (artifact proven, 14:52Z)

Ground truth: local tracked bytes of `docs/reports/CORE_CI_TRIAGE_2026-10-30.md`
(blob `8f85d23f23031e8a53e30782df297ecc74200c12`, 6902 chars). Tower read of
the SAME blob returned 6960 chars (mojibake expansion) whose payload had:

| local ground truth | tower payload (14:52Z) | eaten span |
|---|---|---|
| "(byte-exact; `[main]` minus its leading `[m`)" | "(byte-exact; `ain]` minus its leading ``)" | `[m` ×2 |
| "`branches: ain]` → `branches: [main]` in" | "`branches: ain]` → `branches: ain]` in" | `[m` ×1 (line 94's fix target) |

Untouched in the same payload: `gh[pousr]_`, `sk-[A-Za-z0-9]{20,}`,
`[ -f requirements.txt ]` — exactly the complement of `\[[0-9;]*m`.
At 15:05Z+ the same blob reads back with ALL FIVE suspect spans intact
(`local 5 == tower 5`), mojibake still present — same encoder, different
stripper state. That is a nondeterministic or freshly-redeployed content
pipeline, and it makes **per-read verification mandatory**.

## Evidence B — API-truth anchors reclassify the ci.yml "corruption"

Reads of core ci.yml show `branches: ain]` at both observed blobs —
`b69ba399…` (heads `832b27e`, `feda45e4`) and `9acd7fca…` (heads
`32dccbb3`, `4d33070`) — with every non-`[m` bracket class intact.

Two runs are GitHub-API facts and cannot be artifacts:

- **run #39** (2026-10-27T16:53Z, `event: push`, head `832b27e`, SUCCESS):
  a push whose tree contains blob `b69ba399` FIRED the workflow ⇒ that
  blob's `on.push.branches` matched `main` ⇒ it cannot be `ain]`.
- **run #43** (2026-10-30T14:32Z, `event: push`, head `4d33070`, FAILURE —
  the very run #3441 mirrors): a push whose tree contains blob `9acd7fca`
  FIRED the workflow ⇒ that blob's filter also matched `main`.

A filter value that never matches `main` cannot both block the 10-28…10-30
pushes and admit the 10-27/10-30 pushes. The only reading consistent with
every API fact: **both blobs carry a valid `[main]`-style filter and all
`ain]` ci.yml payloads are artifacts of the same stripper class.**
Caveat kept honest: if the tower's ref-pinning is itself unreliable (see
Evidence C), the blob-to-commit attribution weakens — but run #43 firing on
a push of `4d33070`'s tree independently proves the filter matched main at
that head, which is sufficient to kill the "main has been push-CI-dead via
file corruption since 10-27" mechanism.

## Evidence C — provenance correction to the landed triage receipt

The landed receipt states: "at HEAD `feda45e4` (ci.yml, blob sha
`9acd7fca…`, 5422 bytes)". Three independent ref-pinned reads this cycle
(14:4x–15:0xZ) return blob `b69ba399…` for `feda45e4d0e7` — `9acd7fca…` is
the blob of `32dccbb3`/`4d33070`/HEAD. The misattribution is consistent
with a ref-ignored read (returned HEAD while labeled `feda45e4`) — a second
tower read pitfall, same family: **receipts must echo the ref they pinned
AND the blob sha the read returned, per read.**

## What actually remained red (issue #3441's real subject) — RESOLVED mid-cycle

- Run #41072422845 (run 43, push, head `4d33070`): job
  "Core Pytest & Lint" FAILED ~20s in (14:32:19Z created → 14:32:41Z
  post-cleanup in the log tail). The tower log tool returns only ~40
  trailing lines — all post-cleanup — so the failing step was NOT pinnable
  from this plane; this receipt's candidate list (ruff
  `--select=E9,F63,F7,F82`, pytest collection/startup, secret scan) is now
  confirmed: **pytest collection** — resolved while this cycle was in
  flight by PR #3461 (`aae817f`, landed 15:05:16Z, which closed #3441 on
  merge):
  `decision_engine.py`'s hard `from core.monitoring.logging_config import
  logger` never resolved in the satellite layout and blocked collection;
  the fix makes the import layout-agnostic (relative → open-absolute →
  satellite top-level) and adds `tests/test_layout_agnostic_imports.py`.
- #3441 state at 15:12Z: **closed**; claim holder GLM Agent 28 (Job
  486832, claimed 14:47:01Z) executed the fix lane. This receipt makes no
  closure claim on it — it documents the evidence lane only.
- The 10-28→10-30 push-run GAP (zero `event: push` runs while main advanced
  `832b27e → feda45e4 → 32dccbb3`; run_numbers #40–#42 are all `schedule`)
  is real but NOT file-explained (Evidence B). Leading candidates for the
  admin lane: sync pushes made with a credential that does not trigger
  workflow runs (the `GITHUB_TOKEN` recursion guard class), or a
  platform-side suppression. Falsifiable: audit the push actors/commits
  and the credential used per sync push.
- Deploy-timing context for the fidelity flip (Evidence A): the tower
  auto-deploys from this repo's `infrastructure/mcp-control-plane`; PR
  #3421 landed 14:17Z and PR #3461 15:05Z — the observed
  stripped(14:52Z)→faithful(15:05Z+) flip sits exactly in a deploy window.
  The deployed build differs from origin/main's read path (origin/main's
  `readFile` adapter does base64→utf-8 with no sanitizer), so the stripper
  lives in the previously-deployed build, not in current origin/main —
  admin-plane falsifiable via the Render deploy log.

## Root-cause fix landed with this receipt (U6 Zero-Recurrence)

`scripts/ci/tower_read_file_artifact_probe.py` +
`scripts/ci/fixtures/tower_read_probe_fixture.txt`:

- `--self-test`: hermetic 8-case classifier pass built from the real
  captures (strip-match, preserved classes, mojibake roundtrip,
  unexplained-delta) — offline, exit 0/1.
- live mode: local tracked bytes vs tower `read_file` payload for the same
  path/ref → `PASS` / `ARTIFACT_MATCH` (suspect stripper explains the whole
  delta, stripped classes listed) / `ARTIFACT_OTHER` / `ENCODING_UNSAFE`;
  echoes local-vs-tower blob sha and exits 0/1/2/3. Error envelopes (404)
  are classified WIRING (3), never evidence.

**Usage contract (proposal to all lanes citing tower file bytes):** run the
probe live BEFORE writing "byte-exact"; cite blob sha + probe verdict per
read; while ARTIFACT_* stands, bracket-bearing content claims from tower
reads are inadmissible — cite blob shas or use the admin plane.

## Scope, boundaries, falsifiable predictions

- Zero-credential plane only; no admin plane claims; report-only; no claim
  held (the loop's re-run pick pre-verify found every candidate
  claimed or mechanically demoted — "top 5 candidates live-claimed").
- Bare Refs only, no closes: Refs #3441 #2597 #3455 #3457 #3452.
  Class family: #3417/#3246 (Zero-Corrupted-Payload Invariant — this
  receipt extends it from the submit side to the READ side) and PR #3461
  (the #3441 fix lane, cited for resolution context only).
- P1: re-running the probe on the triage doc now yields PASS (until the
  next pipeline flip) — a flip-flop capture on record would upgrade
  "nondeterministic" from inference to proof.
- P2: the next push to core main (post-#3461 sync) fires a `push` run and
  goes GREEN on the test job (collection fixed; filter was never broken).
- P3: no one can produce a diff that lands `branches: [main]` as a "fix"
  against core HEAD and changes CI behavior (protected-path + not broken).
- P4: the Render deploy history shows a tower redeploy inside the
  14:52Z→15:05Z window whose build diff touches the read/content pipeline.
