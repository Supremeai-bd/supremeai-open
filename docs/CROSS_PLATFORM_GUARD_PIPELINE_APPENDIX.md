# S14 — Cross-Platform Invariant Guard: Pipeline Wiring Appendix (issue #515)

Status: OPERATOR-APPLIED INTEGRATION (protected-path appendix; the agent
lane never edits .github/ — CI_GUARDS r1 A-E precedent).

This appendix ships the exact integration for
`scripts/ci/cross_platform_invariant_guard.py` (landed as a new file) so
the 6 cross-platform invariants become a mandatory pre-merge gate in the
PR fast-metadata stage of `pipeline.yml`, alongside
`boundary_sanitization_guard.py`.

## 1. Why an appendix

`.github/` is on the bridge protected-path list
(`protectedPathsToAdminReview`). Attempts to hunk-edit it from the
agent lane are rejected fail-closed. The guard module itself is a
pure-new file and lands through the normal bridge; only this wiring
needs the operator seat.

## 2. pipeline.yml hunk (PR fast-metadata stage)

Insert one step directly after the existing boundary-sanitization step
(anchor on the `boundary_sanitization_guard.py` invocation):

```yaml
      - name: Cross-platform invariant guard (issue 515)
        id: cross_platform_guard
        shell: bash
        run: |
          CHANGED=$(git diff --name-only --diff-filter=ACM origin/main...HEAD \
            -- '*.py' '*.sh' '*.ts' '*.tsx' '*.js' '*.mjs' '*.cjs' '*.md')
          if [ -z "$CHANGED" ]; then
            echo "CROSS-PLATFORM GUARD: no changed source files, clean"
            exit 0
          fi
          python3 scripts/ci/cross_platform_invariant_guard.py --files $CHANGED
```

Behavior contract (already machine-enforced by the module):

- Exit 0 = clean; Exit 2 = violation (CI must fail the PR — fail-closed);
  Exit 3 = malformed input (fail-closed).
- Unparseable Python is itself a PARSE-FAIL-CLOSED violation inside exit 2.
- Scan completes in well under 2 seconds for a typical PR diff
  (pure stdlib `ast`, no subprocess, no network).

## 3. Optional pre-commit hook (developer seat)

Drop-in for `.githooks/pre-commit` (repo already ships .githooks per
the stale-base guard line):

```bash
# cross-platform invariant pre-flight (issue 515)
CHANGED=$(git diff --cached --name-only --diff-filter=ACM \
  -- '*.py' '*.sh' '*.ts' '*.tsx' '*.js' '*.mjs' '*.cjs' '*.md')
if [ -n "$CHANGED" ]; then
  python3 scripts/ci/cross_platform_invariant_guard.py --files $CHANGED || exit 1
fi
```

## 4. Retrofitting existing scripts (acceptance criterion 3)

The auto-fixer retrofits R1 (encoding='utf-8'), R2 (timeout=30) and R3
(CRLF to LF) with per-file ast round-trip validation; R4/R5/R6 need
semantic decisions and are reported, never auto-fixed:

```bash
python3 scripts/ci/cross_platform_invariant_guard.py --fix --files scripts/**/*.py
```

Run it once per directory batch, review the diff, and commit. The fixer
is idempotent and skips anything that cannot re-parse.

## 5. Rollback

Remove the single pipeline step from section 2 (and the optional hook
block from section 3). The guard module file itself is inert when not
invoked and can be deleted independently.
