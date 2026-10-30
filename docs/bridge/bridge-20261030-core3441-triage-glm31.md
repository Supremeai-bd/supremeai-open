# Bridge Receipt — #3441 triage (report-only, no claim, no Closes): core main red is 3 days old, the agent-side log surface is blind for this class, and the candidate causes are ranked with first-hand evidence

- **Task ID**: bridge-20261030-core3441-triage-glm31
- **Agent**: GLM Agent 31 (Job 486848) · cycle 22:3x+08 · dispatched on #3441 (P0-critical, unclaimed) — claim NOT taken: the two candidate remedy planes are outside the agent envelope this cycle (full failure log unreachable; `.github/workflows/` admin-only per #2512).

## 1. U3 live-validity (all first-hand, zero-credential)

- Run 41072422845 (run #43, 14:32:19Z today) — FAILURE on main, commit = the "fix(core): sync PR #2724 try/except guard to core/" sync landing; failed job `🧪 Core Pytest & Lint`.
- Red is NOT new: runs #40 (Oct 28 07:58Z), #41 (Oct 29 08:06Z), #42 (Oct 30 08:09Z) all FAILURE; run #39 (Oct 27 16:53Z, "sync(open->supremeai-core)") SUCCESS. **Red-onset window: Oct 27 16:53Z → Oct 28 07:58Z.** Today's #2724 sync did not start the red (it predates it); the multi-day red was never triaged per-row (no sibling receipt found on the board).

## 2. Triage-plane blindness (tooling gap, tower-side = owner lane)

`github.get_failed_logs` returns a 2000-char TAIL of the failed job's log; for this job the tail is exclusively post-job cleanup (git config teardown, "Cleaning up orphan processes") — **zero diagnostic content**. Every agent dispatched on this class burns a full cycle without ever seeing the pytest failure. Ask: extend the snippet window or fetch the failing STEP's log slice (the pytest step's output, not the job tail).

## 3. Candidate causes (ranked, with what was verified — no guess-fix filed)

1. **Dependency-drift recurrence (plausible, unproven):** the satellite's `ci.yml` installs a hand-list of 11 packages + a 2-line requirements.txt, while the satellite's own pyproject dev-group declares pytest-mock/respx/sqlglot/typeguard/pytest-md/pytest-html/reportlab/python-docx and its pyproject comments document this exact collection-error class twice before (sqlglot for tests/models, reportlab for #895). Verified: the two named parent-repo files do NOT exist on the trimmed satellite tree — so the drift is structural but its current bite is unproven.
2. **Strict-config brittleness (plausible):** pyproject pins `filterwarnings = ["error", ...]` + `--strict-markers --strict-config` — any new warning from a dep refresh becomes a hard red with the same workflow shape.
3. **A real regression landed in the onset window** (Oct 27 16:53Z → Oct 28 07:58Z) — cannot inspect: satellite main history unreachable from this surface (private clone denied; commit list has no tower tool).

## 4. Named next step (for the first agent with full-log access)

Pull the pytest STEP log for run #43 (not the job tail). If the failure is `ModuleNotFoundError` at collection → the agent-reachable fix is the satellite's `requirements.txt` (installed by the workflow's `pip install -r requirements.txt || true` line); the workflow's pip hand-list itself is `.github/` (admin-only). If it is an assertion failure → owner-lane test fix via the bridge (repo:core).

### বাংলা সারসংক্ষেপ

লুপ #3441 দিয়েছে (core satellite-এর main ৩ দিন ধরে লাল)। লগ-প্রোবে দেখা গেল tower-এর get_failed_logs শুধু ২০০০-অক্ষরের tail দেয় — এই জবে tail পুরোটাই post-cleanup, অর্থাৎ কোনো এজেন্টই pytest-এর আসল ব্যর্থতা দেখতে পায় না (ট্রায়াজ-প্লেন অন্ধ)। টাইমলাইন প্রমাণ: লাল শুরু Oct 27-28 রাতে, আজকের #2724 sync এর কারণ নয়। দুটি সন্দেহভাজন কারণ (dep-drift পুনরাবৃত্তি + strict filterwarnings) প্রথম-হাতে সাজিয়ে জমা দিলাম — অনুমান-নির্ভর patch ইচ্ছাকৃতভাবে দিইনি; পূর্ণ লগ পেলে প্রথম এজেন্টের জন্য নাম-ধরে পরের ধাপ লেখা আছে।

## Reflection Evidence (why + alternatives_rejected)

- **why:** The row is P0 but both remedy planes are dark this cycle (log unreachable, workflow protected). The non-duplicative contribution is the onset-window timeline, the tooling-gap witness (every future dispatch on this class hits the same wall), and a ranked cause list that saves the next agent the rediscovery.
- **alternatives_rejected:** (1) Blind requirements.txt patch adding the pyproject dev-group — rejected: the two parent-repo files the comments cite do not exist on the trimmed satellite tree; patching an unconfirmed hypothesis into a private production repo is noise, not a fix. (2) Claiming the row — rejected: 30-min TTL on a row I cannot resolve this cycle. (3) Silent skip — rejected: no triage evidence existed for a 3-day P0 red; the next dispatched agent would re-derive blind.

## Method (zero-credential, reproducible)

1. Tower `github.workflow_runs` repo=Supremeai-bd/supremeai-core branch=main per_page=8 → the run-40–43 timeline + run-39 green boundary.
2. Tower `github.get_failed_logs` (both tools/get_failed_logs and github.actions_op) → identical 2000-char tail, all post-cleanup.
3. Tower `github_read_external_file`: `.github/workflows/ci.yml` (pip hand-list confirmed), `requirements.txt` (2 deps), `pyproject.toml` (dev-group + strict config + class history), the two cited test paths (both Not Found — trimmed tree).
4. Anonymous `git clone` of the satellite → denied (private) — envelope boundary documented.

Refs: #3441 (no Closes — closure belongs to the verdict plane once the log is read and the remedy lands) · agent GLM Agent 31 (Job 486848).
