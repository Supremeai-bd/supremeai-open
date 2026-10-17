# Issue Contract Guard — Pipeline Integration Appendix (#473)

Status: r1 · 2026-10-17 · Author: Z.ai Code (session web-26454b1b)
Lane: doc-appendix (`.github/` is a protected path for the zero-credential
bridge lane — the hunk below is applied by a maintainer, exactly like the
CI_GUARDS appendices r1 A–E precedent).

## What ships in this WO

1. `scripts/ci/issue_template_guard.py` — the guard itself (new file,
   stdlib-only, fail-closed, `--self-test` covers valid / invalid /
   bot-bypass / placeholder / malformed-payload cases).
2. This appendix — the exact `pipeline.yml` integration hunk for the
   maintainer to apply.

## Guard contract (verbatim from #473)

- Conventional title `type(scope): subject` (feat|fix|plan|chore|docs|ops|
  refactor|test|ci|perf) OR priority bracket `[P0]`..`[P3]`; placeholder
  titles (`test`, `asdf`, `bug`, `untitled`, ...) rejected.
- Body >= 50 chars and carries markdown headers or one of the markers
  `Context` / `Summary` / `Task Contract` / `Acceptance Criteria` / `Steps`.
- Invalid -> comment with remediation + label `invalid` + close
  `not_planned` (fail-closed). Success -> auto-label `status:unclaimed`
  and `bridge:queued` (no manual labeling).
- Bots (`dependabot[bot]`, `github-actions[bot]`, `renovate[bot]`, ...)
  bypass with zero side effects.

## Pipeline integration hunk (apply verbatim)

```yaml
# --- BEGIN issue-contract-guard (#473) ---
on:
  issues:
    types: [opened, edited]

jobs:
  issue-contract-guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Validate issue contract (fail-closed)
        env:
          ISSUE_NUMBER: ${{ github.event.issue.number }}
          ISSUE_TITLE: ${{ github.event.issue.title }}
          ISSUE_BODY: ${{ github.event.issue.body }}
          ISSUE_AUTHOR: ${{ github.event.issue.user.login }}
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          python3 scripts/ci/issue_template_guard.py --validate-event
      # --- END issue-contract-guard (#473) ---
```

Notes for the maintainer applying the hunk:

- The snippet above is the canonical trigger + job; merge it into the
  existing top-level `on:` block (YAML allows one `on:` mapping — append
  the `issues` entry there) and place `issue-contract-guard` alongside
  the existing guard jobs. Runtime is ~3s (stdlib Python only).
- `--validate-event` is an environment-driven convenience entrypoint:
  it reads `ISSUE_NUMBER/TITLE/BODY/AUTHOR`, runs `validate_issue`, and
  executes the plan (comment + labels + close) with the GitHub CLI
  already authenticated via `GH_TOKEN`. If the maintainer prefers the
  data-only path, `--validate <payload.json>` prints the plan JSON and
  exits 0 (pass) / 2 (reject) for a shell step to act on.

## Verification (3-tier, from #473)

1. Tier 1 (Reflection & Unit Test): `python scripts/ci/issue_template_guard.py --self-test` — all cases green (valid, invalid, bot bypass, placeholders, malformed payloads).
2. Tier 2 (Integration Smoke): `--validate` against mock valid/invalid payloads returns the correct fail-closed exit codes (0 / 2) and plan JSON.
3. Tier 3 (Regression Gate): `python scripts/ci/boundary_sanitization_guard.py` — the guard is a new file under `scripts/ci/` (allowlisted subtree), zero protected-path references.
