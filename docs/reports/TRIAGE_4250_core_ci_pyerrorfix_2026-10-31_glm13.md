# TRIAGE #4250 — `[core] ci failed on main (Run #41182951163)` — deterministic scheduled-autofix red, admin-only remedy

**Triage by GLM Agent 13 (Job ID 486783), 08:13–08:40Z Oct 31 2026 UTC. Report-only evidence per the issue's own Protected-Path Routing Note (#2512): no claim taken, no auto-closure requested.**

## 1. The failing run is NOT in this repo — it is in the private satellite `Supremeai-bd/supremeai-core`

- Title grammar (`scripts/ci/federation_ci_watchdog.py::build_issue_title`): `fix(ci): [{short_repo}] {workflow_name} failed on {branch} (Run #{run_id})` with `repo_short_name("Supremeai-bd/supremeai-core") == "core"`. The `[core]` tag therefore names the **satellite repo**, not a "core" area of this repository.
- Cross-repo verification: `github_get_failed_logs` on `Supremeai-bd/supremeai-open` / run 41182951163 → "No failed jobs found"; the public REST API returns **404** for the run in supremeai-open; the same call against `Supremeai-bd/supremeai-core` returns the failed job **"🔧 PyErrorFix Engine"** (payload archived agent-side). The run exists only in the private satellite.

## 2. Failure class: deterministic, commit-independent, environment/settings-scoped

| Run | Event | Conclusion | Sha | When (UTC) |
|---|---|---|---|---|
| 40 | schedule | **failure** | feda45e4d | 10-28 07:58 |
| 41 | schedule | **failure** | **feda45e4d (same)** | 10-29 08:06 |
| 42 | schedule | **failure** | 32dccbb3c | 10-30 08:09 |
| 47 | schedule | **failure** | ba69caba9 | 10-31 08:02 |
| 43 | push | failure (separate incident, self-healed) | 4d33070ad | 10-30 14:32 |
| 44/45/46 | push | success | 2403406e9/059542f3/b57eb9572 | 10-30 15:12–16:24 |

- **The scheduled `autofix` job is 4/4 red across four consecutive nights** (runs 40, 41, 42, 47; GitHub cron jitter puts the nightly tick at ~08:00Z).
- **Runs 40 and 41 failed on the identical commit** `feda45e4d` on two different days — the failure is independent of tree content: an environment/permissions/settings class, not a code regression.
- Push-triggered `test` jobs on the same days are green (44/45/46) — the repo's actual test/lint plane is healthy; the red is confined to the nightly `autofix` job.

## 3. Failing step analysis (from core's `.github/workflows/ci.yml`, `autofix` job)

1. checkout / setup-python — infra steps, not failure-class.
2. `Run pyerrorfix (detect + auto-fix + SARIF)` — **fully guarded**: both `pyerrorfix` invocations carry `|| true`, and a fallback writer guarantees a valid SARIF file even when the tool produces nothing. Cannot fail the job by construction.
3. `Upload SARIF to GitHub code scanning` (`github/codeql-action/upload-sarif@v4`, `if: always()`) — **the only content-bearing step without a failure guard**.
4. `Trigger Federation CI Watchdog on Failure` (`if: failure()`, curl `|| true`) — its token-echo logs appear at 08:06:46.15Z in the retrieved log tail. **This step only runs when a prior step failed**, so a failure before it is a first-hand fact — and the only candidate left is the upload step.

**Root cause (high confidence):** the nightly `upload-sarif` step fails on the private `supremeai-core` repo — the classic signature is code-scanning upload rejecting a private repository without GitHub Advanced Security enabled (403/404 at the upload API). **U2 disclosure:** the exact error line is UNSEEN — the tower log tool returns only the post-job-cleanup tail and the repo is private, so the public log fetch 404s; the classification rests on the guard-elimination chain above, which leaves the upload step as the sole possible failure point.

## 4. Why this keeps regenerating P0s (structural stampede)

The direct-event mirror files a **standalone P0-critical issue per failed run** (`MIRROR_RUN` marker is run-scoped; `find_mirror_in_items`/`find_mirror_by_commit` dedup scans **open** issues only). The board's daily bulk-close drains yesterday's row, the dedup door re-opens, and tonight's deterministic red files a fresh P0. Four P0-critical filings in four days (one per night) from a single environment failure that no agent can patch. The anchor-hub mechanism (`federation_anchors`, CI_FAILURE_ANCHOR #762) already exists but the direct-event path files standalone issues rather than anchor-tracking comments.

## 5. Remedy (admin-only; all three options live outside the agent envelope)

- **(a) Minimal deterministic cure:** add `continue-on-error: true` to the `Upload SARIF to GitHub code scanning` step (or drop the step) in `supremeai-core`'s `.github/workflows/ci.yml`. The nightly scan stays fully functional — the analyze steps are self-guarded and the SARIF fallback writer guarantees a valid artifact. The red gate exists only to mirror signal; a nightly environment-failed upload is not signal.
- **(b) Alternative:** enable GitHub Advanced Security / code scanning on the private `supremeai-core` repo (repo settings) so the upload succeeds.
- **(c) Variant:** condition the upload on repository visibility (`if: github.event.repository.private == false`).
- Watchdog-side hardening (separate work order, open-repo scope): for (repo, workflow, schedule-triggered) recurrences, file anchor-hub tracking comments instead of standalone P0 issues when an open mirror for the same repo+workflow class already exists — would convert this daily stampede into one accumulating incident thread.

## 6. Why report-only (contract compliance)

The remedy is a `.github/workflows/` write in a **satellite repo** (protected-path class per #2512; the bridge lane rejects workflow writes) or a **repo-settings change** (admin plane). Per the loop's own closure-honesty rule and the issue's routing note, a claim+TTL would be burned on a structurally blocked patch; this receipt hands the admin the complete evidence chain instead. No `Closes #4250` line is filed.

## বাংলা সারসংক্ষেপ

**#4250 আসলে এই রিপোর নয় — প্রাইভেট স্যাটেলাইট `supremeai-core`-এর রাত্রিক PyErrorFix জবের নিয়মিত ব্যর্থতা।** শিরোনাম-ব্যাকরণ (`[core]` = `repo_short_name("Supremeai-bd/supremeai-core")`) ও টাওয়ারের ক্রস-রিপো পড়া দুটোই সেটা প্রমাণ করে। প্রমাণ-শৃঙ্খল: **টানা ৪ রাত schedule-জব লাল (৪/৪)**, রান ৪০ ও ৪১ **একই কমিটে** দুদিন লাল (অর্থাৎ কোড-নিরপেক্ষ, এনভায়রনমেন্ট/সেটিংস-শ্রেণি), একই দিনে push-ট্রিগারড test জব সবুজ — রিপোর টেস্ট-প্লেন সুস্থ। জবের প্রতিটি ধাপ `|| true`-সুরক্ষিত **ছাড়া** `upload-sarif@v4` (একমাত্র অসুরক্ষিত ধাপ), আর `if: failure()` watchdog-ধাপের লগ উপস্থিত — ব্যর্থ ধাপ নিশ্চিতভাবেই সেটি; সম্ভাব্য কারণ প্রাইভেট রিপোতে GHAS/কোড-স্ক্যানিং নিষ্ক্রিয় থাকায় আপলোড-API প্রত্যাখ্যান (নির্দিষ্ট error-লাইন UNSEEN, U2 — লগ-টেইল ট্রাংকেশন + প্রাইভেট রিপো)। প্রতিকার তিনটিই admin-এনভেলপে: (ক) আপলোড-ধাপে `continue-on-error: true` (ন্যূনতম নির্ণায়ক নিরাময় — স্ক্যান কাজ চালু থাকবে), (খ) core-এ GHAS সক্রিয়করণ, (গ) visibility-কন্ডিশন। স্ট্যাম্পিড গঠনও ব্যাখ্যা করা হলো: রান-স্কোপড dedup + দৈনিক ড্রেন = প্রতি রাতে নতুন P0; প্রস্তাব — schedule-শ্রেণির পুনরাবৃত্তিতে anchor-hub কমেন্ট-ফাইলিং। #2512 রাউটিং নোট অনুযায়ী report-only: claim নেই, auto-closure নেই, `Closes` লাইন নেই।
