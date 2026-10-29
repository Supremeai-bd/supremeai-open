# Bridge Provenance Digest Lane — Minimal Land (Issue #1674)

- **Date**: 2026-10-30 (+08)
- **Agent**: zai-cron-agent-loop (Job 477792), session web-a7d72f94
- **Issue**: #1674 — feat(federation): sigstore/artifact-attestation provenance
  lane for bridge-submitted agent patches (supply-chain trust for autonomous PRs)
- **Verdict honored**: EXTRACT_PATTERNS_ONLY — the attestation *pattern* is
  adopted; sigstore itself is not vendored, and no `.github/` path is touched
  (admin-owned).

## What landed

1. **Guard sub-check** — `_provenance_digest()` in
   `scripts/ci/deploy_preflight_guard.py`, wired into `run_step1_syntax`
   full-repo mode only (the same CI Step 1 that runs on every PR and
   push-to-main; the #1630 index-freshness precedent rides there too). The
   offline self-test path passes explicit targets and never consults it, so
   deterministic self-tests are untouched.
2. **Receipt convention** — a bridge submission that wants tamper-evidence
   ships `docs/provenance/bridge-<taskId>.json`:

   ```json
   {
     "taskId": "bridge-YYYYMMDD-<slug>",
     "algorithm": "sha256",
     "files": [
       {"path": "relative/path/in/repo", "sha256": "<64 hex of file bytes>"}
     ]
   }
   ```

   Digests are computed over the **full_file contents as submitted** — the
   exact bytes the bridge writes to the patch branch. The verifier recomputes
   each digest on the checked-out branch and **fails closed** on: malformed
   receipt, non-sha256 algorithm, invalid digest encoding, listed file missing
   from the branch, path traversal outside the repo, and above all
   **PROVENANCE MISMATCH** — any post-receipt edit of a listed file.
3. **Tests** — `tests/test_provenance_digest_guard.py` (9 offline, stdlib-only
   tests): wiring pin, absent-dir no-op, valid-receipt pass, mismatch /
   missing / malformed / unsupported-algorithm / traversal fail-closed,
   explicit-target skip, and a live end-to-end pin of the dogfood receipt.
4. **Dogfood** — this patch ships its own receipt covering the guard, the test
   module, and this report (`docs/provenance/
   bridge-20261030-provenance-digest-lane.json`). The receipt self-excludes:
   a file cannot carry its own digest. From this submission on, the lane is
   exercised by real agent traffic — any post-review mutation of the patch
   files breaks CI Step 1 before merge.

## What this does and does not buy (honest limitations, per the issue)

- The receipt travels with the patch over the same automated channel that
  submits the patch. The bar therefore rises from **narrative trust to
  tamper-evidence**: an editor who changes a listed file after receipt
  generation (review→land gap) is caught deterministically; a fully
  compromised submitter who regenerates the receipt is not eliminated.
- Digest verification proves **provenance consistency, not code
  correctness** — a faithful-but-wrong patch still passes.
- The full lane (an `actions/attest-build-provenance` workflow step under
  `.github/`, SLSA v1.0 provenance, `gh attestation verify`) remains
  admin-owned follow-up; this guard is deliberately structured so receipts
  stay meaningful when that lane arrives (same sha256 file digests).

## Adoption notes for other agents

- Compute sha256 over each file's submitted content bytes (not the diff), list
  every file in the payload except the receipt itself, and drop the receipt in
  `docs/provenance/` with the exact `bridge-<taskId>.json` name.
- Regenerate the receipt if you rebased and file contents changed — a stale
  receipt fails CI Step 1 by design; that signal is the feature.
- New files need no `baseSha`; edits of existing files must carry the per-file
  blob `baseSha` from main at branch-cut time (#2333) so a stale full_file
  payload is rejected before it can clobber fresher main content.
