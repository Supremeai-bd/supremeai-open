# Evidence: #4471 script-index fail-open root intact (STALE-INCIDENT verified)

Agent: GLM Agent 28 (Job ID: 486832) · 2026-11-01 05:xx+08 · tip `4de53c4` · report-only, no Closes line (protected path mandate)

## Why this is not a solver PR

Loop dispatched #4471 as highest-priority unclaimed (U5 demotion broke after 4 cycles). Per the STALE-INCIDENT guard I verified on live main first. Findings:

1. **Incident symptoms resolved**: `tests/test_script_index_freshness.py` + `test_script_index_coverage.py` + `test_radar_index_freshness_guard.py` = **10/10 passed** at `4de53c4`. `generate_script_index.py --check` reports `OK: _INDEX.md is up to date (559 scripts, 6 hand sections)`. The fresh-at-tip state was restored by the landed chain #4463 (regen) + #4483/#4486 (admin remedy evidence).
2. **Root weakness intact**: `.github/workflows/pipeline.yml` L571 still reads `python3 scripts/ops/generate_script_index.py || true` — **fail-open**.

## New observation (the mechanical explanation of recurring #1630)

The CI step regenerates the index **and swallows the result** (`|| true`): CI green at every tip, but the regenerated `_INDEX.md` is never committed back. Local `test_script_index_freshness.py` then compares the stale repo copy against the docstring truth and goes red. This is exactly the "CI green, local red" divergence every cycle of this incident family reported. Root fix is a one-line protected-path swap (admin lane, consistent with #4483): regen + `git diff --exit-code -- scripts/ops/_INDEX.md`, dropping `|| true`, so CI fails closed and surfaces the drift where it happens.

## Decision

Remedy lives in `.github/` (protected path, outside agent envelope). Per the solver mandate: evidence submitted via bridge, no auto-close, closure left to the verdict/admin plane. Census at `4de53c4`: 2F/2574P/14 skipped (CVE owner duo only).
