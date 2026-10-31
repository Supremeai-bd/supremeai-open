# GLM Agent 04 — Worklog (Job ID 486718, slot agent-3)

> In-place-replace / keep-it-small contract (glm22-r2 precedent): durable facts
> only, landed lanes condensed to one table, replaced in place every cycle.
> Full per-lane text lives in the merged receipts, not here.

- **Identity:** GLM Agent 04 · Job 486718 · slot `agent-3` · hourly cron cadence ·
  door = MCP tower handshake (`supremeai-mcp-tower.onrender.com/mcp`) → AGENTS.md
  (5 invariants) → `scripts/agents/continuous_agent_loop.py` dispatch.

## Durable disciplines (earned, mechanical — future cycles must not re-learn)

1. **bridge_submit mechanics:** `summary` ≤ 1000 chars; diff caps 204.8 KB / 30 files;
   tower diff parser accepts **pure unified diffs only** (`diff --git`/`index`/mode/rename
   lines stripped; keep `---`/`+++`/`@@`); `full_file` only for brand-new paths,
   existing paths need `baseSha` CAS pin from `git rev-parse origin/main:<path>`.
2. **Post-RBAC tower surface (live 2026-10-31):** 20 tools, zero `github.*` read family;
   board/PR truth via tower planes + `git log origin/main` only; list rows camelCase,
   merged-truth only via `pull_number` addressability (AGENTS.md Rule 4 — my remedy, #3526).
3. **Liveness planes (R92 subject, still open):** `agent_heartbeat` (redis, 90 s online
   prose / 300 s TTL, rotating account primary→secondary→tertiary) is disjoint from the
   repo-side `agent_identity.py` JSON (600 s/1800 s) and from `slot_status` (registry
   plane — self-assigned slots legitimately "Slot not found", Rule #19 fallback). The
   loop feeds none of them. `agent_status` exposes the live online/stale machine (37 slots).
4. **Radar hygiene:** take the next R-number from `docs/SCOUT_RADAR_INDEX.md` (the SSOT,
   freshness-guarded); re-verify freeness pre-submit (the pass-26 six-recurrence collision
   class is caught by the filer's own re-verification ladder, R95 preamble).

## Landed lanes (all merged on origin/main, first-registration-wins)

| Lane | Subject (one line) | PR |
| - | - | - |
| guard(loop) | sentry TEST-row demotion in dispatch pick (#3371) | #3469 |
| remedy A | AGENTS.md Rule 4 camelCase payload conventions (#3523) | #3526 |
| fix(ci) | #3656 parity-manifest blindspot closed, sentinels v1→v2 | #3658 |
| evidence ×3 | #2974 / #3567 / #3527 live U3 re-verifications | #3359 / #3593 / #3789 |
| census ×4 | R69 codeql-v4, R74 tool census r2, r2360 push-dark, r2567 gate census r4 | #3275 / #3282 / #3290 / #3304 |
| triage ×4 | #3785 + #3851/#3853/#3854 CI trackers, non-repro classifications | #3797 / #3865 / #3867 / #3870 |
| R92 radar | heartbeat liveness contract: 5 windows, 2 disjoint planes, zero mechanical consumers | #3961 / dbf5186a |
| R93 radar | #3993/#3994 anchor-routing result-None hole | #4003 / 4e553bdd |
| R96 radar | branch-death orphaned-tracking-row lifecycle (10/13 open rows) | #4088 / 0bd75aaf |

## Open watch items (owner lanes; no re-file while receipt-covered)

- R92 Plan-1/2 — heartbeat payload self-describing + loop-side ping or lane-alive signal.
- R96 Plan-1..4 — close-on-prune lifecycle + sweep net + label short-circuit + U6 pin.
- R94 board ground-truth protocol paragraph (owner/docs lane).
- PR-plane dark post-RBAC — glm22 receipt #3959, options A/B/C, owner decision pending.
- render-primary `update_failed` + #3699 boot classes (boot-proven ×3, glm10) — admin/HITL.

## বাংলা সারসংক্ষেপ

স্থায়ী শিক্ষা: bridge_submit-এর তিনটি যান্ত্রিক সীমা, post-RBAC ২০-টুল পৃষ্ঠ, তিনটি
disjoint liveness plane, আর radar-নম্বর hygiene — ভবিষ্যৎ চক্র আর নতুন করে শিখবে না।
এই ফাইলই আমার একমাত্র worklog; পুরনো বিস্তারিত merged receipts-এ আছে, এখানে শুধু
সারণি। প্রতিটি watch item owner-lane-এ receipt-covered — যতক্ষণ না সেটা বদলায়,
re-file করা duplicate হবে।

## Cycle log (append one line, prune on your own cycle per keep-it-small)

- **2026-10-31 10:04+08** — fresh-sandbox re-clone at c8e8e2d7; loop clean (claimable
  0/5, P0 gate green, board 2 fresh report rows); all five watch lanes verified
  receipt-covered (no duplicate filed); this worklog minted. No claim, no code edits.
