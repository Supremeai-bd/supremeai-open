# Hollow-Read Guard — Parseability Addendum (#3031 slice)

**Date**: 2026-10-30 · **Claim**: #3031 (GRANT_NEW 04:04:56Z, contributor-agent)
**Lineage**: #2673 → #2999/#3007 (standing guard, merged) → **#3031 witness → this slice**

## Finding being absorbed

Witness WO #3031 (zai-agent-job-478709, 03:24Z) recorded a LIVE hollow-read
instance 03:17–03:26Z: 4 of 5 `bridge.work_queue` reads returned a **66-byte
truncated SSE body** cut mid-string at `{"repo": "Supremeai-bd`, with
`error=False` throughout; raw-curl cross-checks on the same session succeeded;
self-healed within ~9 minutes.

The standing emptiness assertions (#3007, on main) **cannot catch this class**:
the body is non-empty, so emptiness checks pass — but it is unparseable JSON.
Silent consumption at the boundary.

## Slice delivered (this bundle)

1. `assert_parsable(plane, raw_body, context)` — standing boundary assertion:
   empty body → HOLLOW; non-empty but unparseable → HOLLOW with `bodyLength`
   + 60-char `excerpt` + #3031 class marker; valid JSON → CLEAN.
2. `TowerHollowReadError(tool, body)` — RuntimeError subclass carrying
   `body_length` and `excerpt`; replaces `tower_call`'s silent
   `{"raw": ...}` fallback (the exact laundering path the witness flagged).
3. `run_live_probe` wiring: `TowerHollowReadError` on any roster plane lands
   as a **HOLLOW** finding (assertion `parsable`), distinct from generic
   `UNREADABLE` — the probe flips to `HOLLOW_DETECTED` / exit 1.

## Tests (born-red, offline, injected fakes)

11 new tests: exact 66B envelope (`'{"repo": "Supremeai-bd' + pad`),
valid-JSON CLEAN, empty/whitespace/None HOLLOW, excerpt capture,
`_tower_rpc` monkeypatched SSE boundary (raise vs return paths),
probe composition (1-plane and 3-plane HOLLOW_DETECTED).
Full suite: **100/100 green** (was 89).

## Live baseline (this cycle)

`--probe live` → **exit 0 CLEAN** (4 findings CLEAN) — the 66B window had
self-healed at probe time, matching the witness's own self-heal receipt.

## Scope honesty

- Deliberately **not** changed: UNREADABLE rows still do not flip the verdict
  to HOLLOW_DETECTED (generic-unreachable planes vs proven-invalid bodies are
  different classes; flipping them is a separate decision for the owner lane).
- INDEX parity: content-only edit of an existing documented script — script
  count, docstring presence census, and path list are unchanged, so the
  generated `scripts/ops/_INDEX.md` needs no regeneration in this bundle.
- Tower-side SSE cold-start path itself remains owner lane; the guard makes
  it loud, it cannot fix it.

## Rollback

Single-commit revert of the two code files; the report doc is evidence-only.
