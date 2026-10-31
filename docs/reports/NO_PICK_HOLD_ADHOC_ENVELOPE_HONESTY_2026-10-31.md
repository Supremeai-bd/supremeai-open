# NO-PICK HOLD + adhoc-envelope honesty fix — 08:06+08 cycle (GLM Agent 06)

**Agent:** GLM Agent 06 (Job 486721) · **Cycle:** cron 2026-10-31 08:06+08 · **Mode:** loop `--task-envelope --loop` → dry board → sanctioned `--allow-adhoc` (idle-cycle path, #3933/#3935 precedent)

## 1. Cycle facts (no-pick hold)

- Preflight: **zero open P0** architectural blockers on the live board.
- Board census (tower board fallback; gh CLI absent on PATH): **3 open rows, all `status:claimed`** — #3698 (P1 scout, secrets/SSL/schema/Upstash), #3629 (bridge-intake CI red), #2633 (MCP capability census). **0 rows in gates** (`bridge:in-gates`). U5: every open candidate is covered by an in-flight claim → **no clean pick**; loop deterministically refused dispatch.
- Prior-cycle verification: PR **#3668** (composition integrity gate for the #3649 satellite drift) **merged** at `61263c03`, and extended upstream by #3679 (supremeai-api joined `PACKAGE_SHADOW_REFRESH_TARGETS` + stale ARCHIVE assertion retired — the side-finding this agent recorded in the #3649 receipt).
- Tower-plane observation for the watchers: tool surface rotates per session (this cycle a fresh session exposed only 20 tools twice; `github.*` readers absent — the loop's failed-PR audit honestly recorded "PR-plane dark … not certified clean (U2)"). Consistent with the c66 sentry note (surface re-grew 18→20, dot→underscore renames).

## 2. Live-observed defect fixed in this WO (root-cause, in-lane)

Running the sanctioned ad-hoc path this cycle emitted an **impossible contract**:

- `issue: null` / `task_id: task-adhoc` **and simultaneously**
- `submission.issue_reference_required: true`
- `specialist_prompt`: "PR BLUEPRINT: PR must carry 'Closes #<issue_number>' …"

An agent following the blueprint must **fabricate an issue reference** — precisely the #1609 false-close verb class the bridge guards. Fix in `continuous_agent_loop.py` (the loop is the SSOT every agent reads):

- `issue_reference_required` → `issue_number is not None` (True only on real dispatches).
- PR BLUEPRINT line becomes path-honest: issue dispatch keeps the exact existing line; ad-hoc says reference `task-adhoc` and **do NOT fabricate an issue reference or a 'Closes #N' footer**.
- 3 offline contract tests pin the shape (`tests/test_envelope_problem_statement.py`), incl. the unchanged-issue-path guarantee.

## 3. Verification evidence

- Dual-Rebase honored mid-flight: **#3995 landed while this patch was being built** (consolidated roles); tree re-reset to `39867031`, anchors re-verified present, patch re-applied cleanly — no conflict, no equivalent fix in #3995 (U5 re-checked at branch-cut).
- `pytest` (envelope/contract/picker/evidence family): **105 passed + 9 subtests, 0 failed**.
- Live emission check: `--task-envelope --allow-adhoc` now emits `issue_reference_required: False` + the ad-hoc blueprint line.
- `ruff` on both touched files: 68 findings with patch == 68 on stashed baseline (**zero new lint debt**); `py_compile` OK.
- Scope: loop file + its contract test + this receipt only; no satellite code, no forbidden paths.

## বাংলা সারসংক্ষেপ

এই সাইকেলে বোর্ড শুকনো — ৩টি খোলা রোই ক্লেইমড, P0 শূন্য, তাই লুপ ন্যায্যভাবে ডিসপ্যাচ করেনি (no-pick hold, #3933 প্রেসিডেন্ট)। স্যাংশনড adhoc পথে এনভেলপ নিতে গিয়ে লাইভ দোষ ধরা পড়ল: issue নেই অথচ এনভেলপ বলছে "Closes #<issue_number> দিতেই হবে" — অনুসরণকারী এজেন্ট ইস্যু-রেফারেন্স **বানিয়ে ফেলবে** (#1609 false-close শ্রেণি)। সংশোধন: adhoc পথে `issue_reference_required: false` + সৎ ব্লুপ্রিন্ট (task-adhoc রেফারেন্স, ফেলসিফাই নিষেধ); প্রকৃত dispatch পথের চুক্তি অক্ষত। ৩টি নতুন কনট্র্যাক্ট টেস্ট; ১০৫ টেস্ট পাস; #3995 রেস ডুয়াল-রিবেজে সামলানো। গত সাইকেলের PR #3668 merge-নিশ্চিত ও #3679 দ্বারা বিস্তৃত।
