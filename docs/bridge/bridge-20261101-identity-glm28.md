# GLM Agent 28 — Worklog (Job ID 486832)

> Post-purge restart (2026-11-01). The founder's doc purge wave
> (#4965–#4969, Batches 1–5: 308 bridge/report files / 16,356 lines
> in Batch 1 alone, refs #762 "lean 50–100 files") removed every lane
> worklog, including this lane's 14-revision chain (r1–r14, PRs
> #4658–#4959). Nothing is restored verbatim; full history stays in
> git and the WO archive. This file restarts the small live slot per
> the standing hourly mandate ("keep worklog small, remove old
> worklog and keep only important part"), following the glm19 #4971 /
> glm22 #4973 restart precedent — only the durable facts a fresh
> reader needs.

## Durable facts carried forward

- Identity: GLM Agent 28, Job ID 486832, hourly cron cadence; door =
  raw urllib MCP client (chunk-boundary-safe) → AGENTS.md/bridge
  contract → full census before every receipt; HB slot z.ai-28
  (primary redis).
- #4471 chain (CLOSED pre-purge): fail-open `_INDEX.md` regen
  root-caused; evidence-only PR #4590 (no Closes line); class-killed
  by glm10's committed-blob freshness gate #4612 (25604a3);
  independent third-party mechanical proof by glm25 #4671.
- Payload-corruption class (repaired #4658): a bridge payload landed
  as a raw unified-diff hunk (`--- a/` on L1) → SyntaxError → pytest
  collection error on main → every census ran 0 tests. Repaired
  same-hour (364d4bd/#4658, battery 12/12). Class note: submit
  pipelines must apply-check hunk integrity before diff-mode landing
  or fall back to full_file.
- Census arc (pre-purge): 13 consecutive FLAT red-plane cycles (2F =
  CVE owner duo only) across four board regimes (drain → mass
  land-verification sweep → rebuild → pure accumulation); final
  pre-purge datum 2F/2535P/14S at b46b2ba.
- False-red habit (durable): stale untracked `__pycache__` under
  pruned paths survives on long-lived sandboxes and fires prune
  sentinels — sweep artifacts before reading a census (root-caused
  cycle 43; independently corroborated by glm32 r30).

## Landed cycles (post-restart)

| Cycle | Contribution | Proof |
| - | - | - |
| 44 (23:28+08) | r15 POST-PURGE RESTART (this submission). Founder purge wave #4965–#4969 (Batches 1–5) landed 22:56–23:22+08; my r14 (2da4560/#4959, landed 22:44+08) was purged 12 min later with the whole lane. Standing verify 3421cf9: census COLLECTION-BROKEN — 12 orphan test files (9 gateway/tests/* + 3 tests/* incl. test_stream_sanitizer, test_status_publication, test_provider_registry_lanes), all ModuleNotFoundError on founder-purged modules (gateway.service.* ×7, gateway.services.dynamic_ai.provider_registry, status_publication, stream_sanitizer) → pytest aborts → 0 tests runnable — first census-instrument break since the #4658 repair; repair reach probed live from the tower schema: bridge_submit_patch file mode enum = [full_file, unified_diff], no delete ingress → orphan-test removal is owner lane (founder sweep follow-up); board 20 rows (post-purge restart births #4970/#4972), PR plane 2 open (#4973 glm22 restart, #4872 orphaned pre-purge); loop claimable 0/5; HB first-attempt OK slot z.ai-28 | PR #4979 |
| 45 (00:28+08) | r15 LANDED (370c0e0/#4979, first post-restart receipt accepted); standing verify 1d154e2→93a238f (+24: lean wave continued — mega purge #4984 (717 monolithic files), test prune #4988 (361 legacy test files), repo now 58 lean SSOT files #4995; glm08 de-ghosted loop hooks-path advisory #5000, glm07 restored freshness suite fail-closed #4990): census NEW BASELINE — transient 1F/49P at 1d154e2 (parity-gate manifest listed #4988-pruned paths) healed within the hour by landed #5005 sentinel-sync → final at 93a238f: 50 passed / 12 subtests / 0F in 8.76s — FIRST fully-green census in lane history (pre-lean era: 13× FLAT 2F/2535P with CVE duo, all pruned with the legacy suite); loop claimable 0/5, board 5 rows (20→5, lean drain), PR plane #4872 orphaned; HB first-attempt OK slot z.ai-28 | this worklog |
