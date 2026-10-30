# Scout R83 — #1745 (R29 uv-lockfile lane): the lockfile's CI promises are unwired

> **Lane:** R83 · **Filer:** GLM Agent 08 (Job ID 486735) · **Filed:** 2026-10-30 ~15:2xZ
> **Subject lane:** #1745 (open, `status:unclaimed`) — R29 uv adoption, filed 2026-10-27.
> **Class:** doc-behavior drift on a live open lane (report-only; no code edit, no claim taken).

## 1. Premise (byte-level, tree `aae817f`)

`requirements-dev.txt` header (landed 2026-10-30T08:26:53+06 by `723ccc0`/PR #3104) makes two
testable promises about `requirements-dev.lock`:

1. *"the uv-compiled requirements-dev.lock is the **reproducible resolution CI installs from**
   (R29 uv-lockfile lane #1745)"*
2. *"Freshness is **CI-enforced** (fast-lint-syntax-preflight job): recompile to a temp path and
   diff the bodies (skip the 2 autogen header lines)"*

Both are false on today's `main`:

| # | Promise | Reality (byte evidence) |
|---|---------|-------------------------|
| P1 | CI installs from the lock | `.github/workflows/pipeline.yml:555` runs `pip install -r requirements-dev.txt` (loose manifest). `git log -S "requirements-dev.lock" -- .github/workflows/pipeline.yml` is **empty** — pipeline.yml has *never* referenced the lock, so this is not a regression but a never-wired promise. |
| P2 | Freshness diff enforced by fast-lint-syntax-preflight | The job's full step dump (setup-python → pip install pyyaml → pip install -r requirements-dev.txt → deploy_preflight_guard --step1-syntax → lint-imports → …) contains **no** recompile+diff step. Repo-wide, `rg "requirements-dev.lock" .github/ scripts/ci/` hits only a comment line inside `boundary_sanitization_guard.py`. Zero mechanical enforcement exists. |

## 2. Why it matters (reproducibility surface)

The loose manifest pins exactly **one** direct dependency (`import-linter==2.15`). The lock pins
**7 transitive resolutions** (`click==8.5.0`, `grimp==3.18`, `markdown-it-py==4.2.0`,
`mdurl==0.1.2`, `pygments==2.21.0`, `rich==15.0.0`, plus the direct pin). A txt-install resolves
those transitive deps at run time against current PyPI — exactly the drift the lock was compiled
to prevent. The file whose header advertises reproducibility is not what CI consumes, and nothing
flags when the two diverge (the promised freshness diff would be the tripwire; it does not exist).

## 3. Lane status cross-check (anti-stampede)

- #1745 is **open** and `status:unclaimed` (verified 2026-10-30 ~15:2xZ via issue plane); no WO in
  the open queue cites uv/lockfile/1745. This report is a progress-gap appendix to that open lane,
  not a competing work stream.
- #1745 checklist score on today's tree: **1/5 partially** (compiled lock exists — root domain
  only) · **4 not started** (per-domain locks; SHA-pinned uv setup replacing 3 pip sites;
  CI freshness validation; before/after install-timing record).

## 4. Side observation (factual, not a verdict)

The lock, the manifest and its false-promise header all arrived as sidecargo of PR #3104 — a
commit titled *"Evidence #3100 (report-only)"* whose declared Scope Paths list one evidence doc,
while the landed diff is 4,259 files / 808,759 insertions (bulk sync class). Recorded here only
because the index should know which vehicle carried the R29 artifacts; adjudication of owner-side
bulk landings is outside the agent envelope.

## 5. Root-cause fix (ranked, for the #1745 picker)

1. **One line:** fast-lint installs the lock — `pip install -r requirements-dev.lock` (pip accepts
   any requirements-format file; the lock is a flat pin list, byte-compatible).
2. **Tripwire:** add the promised recompile+diff step to fast-lint-syntax-preflight
   (`uv pip compile requirements-dev.txt -o /tmp/relock && diff <(tail -n +3 requirements-dev.lock)
   <(tail -n +3 /tmp/relock)`) or promote it to a standalone `scripts/ci/` guard wired into the
   roster (the #1644 pattern), so the promise is machine-checked, not prose.
3. **Honesty fallback:** if txt-install is intentional, amend the header to stop promising what CI
   does not do (the #1776 lesson: a "completed" surface that never landed is worse than an open
   gap).

**Verdict:** `adopt_via_1745` — feed this evidence into the open lane's checklist; no separate
closure claim is made. Zero-Recurrence note: the general shape (header promises CI enforcement
that no guard implements) is the U4 family's doc-plane variant; the mechanical fix is the guard
itself.
