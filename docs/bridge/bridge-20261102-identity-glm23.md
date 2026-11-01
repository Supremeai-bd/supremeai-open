# GLM Agent 23 (Job 486814) — POST-PURGE RESTART receipt

> Founder purge wave #4965-#4969 (Batches 1-5, refs #762) removed the
> predecessor chain (`docs/reports/bridge-20261031-identity-glm23.md`,
> ~40 cycles) AND this lane's flagship test `tests/test_dead_import_drift.py`
> (#4976 prune, 361 test files). Accepted as owner-side hygiene — no
> restoration. Slot restarts at minimum size at a fresh dated path
> (glm19/glm22/glm32/glm04 precedent; same-path resubmission = silent
> purge revert, rejected). Identity: heartbeat slot `agent-23` (TTL 300s),
> hourly cron trace class `...-cron-agent-loop-*`, zero-credential surface.

## Durable facts (folded from the purged chain)

1. **#4195 dead-import ratchet — full lifecycle, now retired**: r8 slice
   merged `e2ef0fb9` (chain 446→345), glm28 re-bound the floor to the
   measured 343 (#4338), then #4976 deleted the test whole with the
   monolithic modules it guarded. Law that survives: a shrink-only
   ratchet is mortal — it dies with its target module; only module-free
   guards (freshness, parity, boundary) outlive purges. Verified zero
   dead workflow/script references to the deleted tests remain (rg clean
   at tip `1c8f7366`) — the purge was done fail-closed, no drift left.
2. **Watchpoint closure census (first-hand, this cycle)**: (a) #4471
   CLOSED — the `generate_script_index.py || true` suppression line is
   gone from `.github/workflows/pipeline.yml`; the 3-agent EVIDENCE-ONLY
   verdict (glm23/glm05/glm11, don't touch admin plane) was vindicated:
   the owner lane applied it themselves. (b) CVE-guard 2-known-red
   watchpoint closed by removal — both guard tests deleted in #4976;
   never-do #1913 (agents don't touch CVE lanes) mooted. (c) ratchet
   BASELINE race closed (file gone). (d) #4124 pair closed earlier.
3. **429/503 ladder doctrine (unchanged, still valid)**: first attempt →
   +90s staggered retry → +150-180s long cool → hard cap 3 attempts per
   cycle; classify 429 = Cloudflare cron-window contention vs 503 =
   Render-side churn; never add pressure beyond cap. This cycle:
   heartbeat green on attempt 1; later probes 429→503, stopped at cap.
4. **Fresh finding, EVIDENCE ONLY (no PR — anti-stampede)**: at tip
   `1c8f7366` the surviving suite has 6 broken items: 4 collection
   errors (dead imports `gateway.config`, `gateway_shield_reference`,
   `core.kaggle_orchestrator`; module-level assert missing purged
   `gateway/.github/workflows/ci.yml`) + 2 `test_core_exports.py`
   failures (`core.__all__` removed by purge). ALL five files are
   already deleted by OPEN PR #4995 (92 files, -25,317 lines) — defect
   owned upstream, so this lane files nothing. Census on the rest:
   96 passed + 12 subtests.
