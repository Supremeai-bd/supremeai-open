# Rules-Breaker Sweep — R93 liveness + #3995/#3992 fresh-surface audit (2026-10-31, cycle 13 08:14+08)

**Agent:** GLM Agent 14 (Job 486785) · **Roles dispatched this cycle:** human-eye → rules-breaker → platform-guardian (3 loop runs; board 0 rows on all three; no solver dispatch — gh-less runtime, cadence-only). Mid-cycle note: d4f4263 landed `feat(loop): gate scheduled observation roles on claimable issue threshold (>= 5)` — this sweep ran under the pre-gate cadence; future empty-board cycles will no longer emit observation dispatches at all.

## Headline 1 — R93 hole live-verified STILL UNFIXED (actionable dispatch surface)

Independently reproduced offline at main 4e553bd, zero-credential (re-checked after the 05a21ad pull: both ternary sites still present, count = 2):

- `get_anchor_issue_number('Supremeai-bd/supremeai-newsat')` → `None`; control `supremeai-studio` → `749`.
- Both ternary sites still unguarded: `scripts/ci/federation_ci_watchdog.py` L355 + L502, `get_anchor_issue_number(repo) if get_anchor_issue_number else CI_FAILURE_ANCHOR` evaluates to `None` for any repo outside the anchor hubs — the guard tests the IMPORT, not the RESOLUTION (R93's exact claim, re-proven).
- The dedup scan URL would be `repos/Supremeai-bd/supremeai-open/issues/None/comments`.
- `mirror_failure` order re-verified at L495-515: the issue is CREATED first (HTTP 201 → `issue_number`), THEN `target_anchor` is resolved and `link_sub_issue(parent_issue_number=None, …)` is attempted — the `if issue_number and link_sub_issue is not None` guard never checks `target_anchor`; the callee is int-typed → loose root issue + FAILED verdict, violating the zero-loose-issues invariant the change cites.
- R93's fix recipe (Plan-1 `or CI_FAILURE_ANCHOR` at both sites → Plan-2 unmapped-repo self-test row → Plan-3 fallback warning) remains applicable and unpicked. The board is empty and AGENTS.md `NO Speculative Dispatch` bars a self-started solver lane — this report is the surface for the next solver dispatch.

## Headline 2 — #3995 role-taxonomy unify audited CLEAN (no stale lane)

- `DEFAULT_MERGED_ROLES` alias map complete: auditor / federation-auditor / task-auditor → platform-guardian; ci-fixer / fixer / coder → solver; `agent_cadence.json` `scheduled_roles` updated (auditor removed from rotation).
- Envelope legacy names are TEST-PINNED intentional shape, not drift: `tests/test_envelope_role_classification.py` pins `role="task-auditor"` / `task_type=AUDIT`, `role_override="ci-fixer"` → FIX, and a valid-registry loop over all legacy names.
- Cadence machinery canonicalizes consistently: `canonical_role()` applied in `role_is_due` / `due_roles` / `mark_role_run` (same-key write+read, #1569 lineage intact).
- Dispatch path is solver-first with an honest `(classified specialist: …)` suffix — no dispatch-behavior change.
- Residuals found: none requiring action. `ROLE_TASK_TYPES` / `EVIDENCE_LANE_TITLE_ROLES` legacy keys are load-bearing (task_type semantics survive the rename), not leftovers.

## Headline 3 — #3992 skills package (34 files) audited CLEAN

- Credential sweep over every added file: zero real secrets; the only pattern hits are the ai-knowledge-acquisition skill's own DETECTION regex (`validate_record.py` L83) and its test — the detection machinery itself, not a leak.
- `skills/sandbox/executor.py` containment verified first-hand: resolve-guard rejects scripts escaping the skill root (L47-49), sanitized env (PATH/HOME/PYTHONHASHSEED/SKILL_SANDBOX/LANG only), hard timeout with an honest `timed_out` verdict, ephemeral workdir with finally-cleanup. Known nuance, not a defect: `extra_env` merges AFTER sanitization by explicit named-parameter design.
- Boundary invariant respected: `skills/` is repo-native; zero satellite code in repo root.

## Honest non-finding (prevents duplicate guard work)

`bridge_work_queue` at ~08:20+08 returned #4002/#4000 as `open` AFTER their receipts (#4003/#4001) had merged; the next loop read showed `totalOpen=0`. Seconds-scale state lag, same family as the #2111 label-lag class already covered by the STALE-CLAIM GUARD. No new guard warranted.

## Known-class coverage map (verified — no re-audit needed)

- PR-plane dark on gh-less/viewer runtimes → R88 radar + #3772 board-assurance layer (landed).
- Adhoc envelope dishonesty → #4001 (landed, 3 pinned contract tests).
- Anchor-routing None hole → R93 (live; fix unpicked — Headline 1).

Refs: #4002 #4003 #4000 #4001 #3995 #3992 (bare; report-only; no Closes — #2211).
