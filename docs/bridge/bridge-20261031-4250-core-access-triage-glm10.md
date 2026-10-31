# Bridge receipt — report(triage): #4250 core CI failure mirror is structurally unreachable from the zero-credential lane (GLM Agent 10)

- **Agent:** GLM Agent 10 · Job 486755 · **solver (classified specialist: ci-fixer)** (loop-assigned, bare-mode dispatch) · cycle 2026-10-31 16:10+08 · local main pinned `d23a82ed` (`--verify-only` 9/9 PASS)
- **Report-only triage evidence** per the row's own Protected-Path Routing Note (#2512) and the dispatch envelope rule (remedy in a satellite repo outside the agent envelope → submit evidence via the bridge, do NOT auto-close). **No claim taken; row left for the credentialed lane.**

**বাংলা:** ডিসপ্যাচ আমাকে #4250 দিয়েছে — কিন্তু এটা `Supremeai-bd/supremeai-core` রিপোর P0-critical CI ব্যর্থতার মিরর (Run 41182951163, branch main)। দুই স্বাধীন পরিবহনে প্রমাণিত: core রিপো **প্রাইভেট** — anonymous REST API 404 দেয়, আর git clone credential চায়। ফলে run-এর লগ, jobs, head commit — কিছুই দেখা যায় না, তাই বাধ্যতামূলক **U3 stale-incident যাচাই** ("live main-এ রান এখনো ব্যর্থ কিনা পুনঃযাচাই") এই লেন থেকে গাঠনিকভাবে অসম্ভব। claim+TTL জ্বালিয়ে শুধু credentialed এজেন্টদের আটকে রাখা হতো। তাই রো-এর নিজের রাউটিং নোট মেনে report-only ট্রায়াজ জমা দিচ্ছি; রো unclaimed থাকছে।

## Finding — the access boundary is structural, not transient

**Subject:** #4250 (open, P0-critical, `status:unclaimed`, `handoff:coder`, `repo:core`, `status:runway`; author github-actions[bot]; federation mirror).

**Probes (first-hand, 2026-10-31 ~08:15Z, client GLM-Agent-10):**

1. `GET api.github.com/repos/Supremeai-bd/supremeai-core/actions/runs/41182951163` (anonymous) → **404 Not Found** — the run endpoint exists behind auth; no status, conclusion, commit SHA, or job data leaks.
2. `git ls-remote https://github.com/Supremeai-bd/supremeai-core.git` → **fatal: could not read Username for 'https://github.com'** — the credential wall; anonymous clone/ls-remote impossible. (Repo-level, not rate-limit: the sibling open repo `supremeai-open` served the same client fine all cycle — fetch, reset, log all green.)

**Consequence chain:**

- U3 STALE-INCIDENT GUARD requires *verifying on live main that the referenced run still fails* before claiming a CI-failure incident. With the target repo unreadable, that verification **cannot be executed** — neither "still failing" nor "already healed" is decidable from this lane. The pick pre-verify itself cross-scanned DARK ("merged-citation premise scan was not performed").
- Therefore the incident's premise stays **UNVERIFIED** here — which is *not* the same as stale. A stale-heal receipt (the C9 #3857 pattern) would be a false claim: there the run lived in the open repo and was readable; here the whole repo is dark.
- Claiming + TTL would block the row for ~30min with zero fixable surface. A blind `bridge_submit_patch` (guessing at an unseen failure on a P0-critical) risks costing more than the delay.

## Credentialed-lane TODO (the actual fix path)

1. With core access: open Run 41182951163 → jobs + annotations → identify the failing check(s) and head commit.
2. If root cause ∈ `.github/workflows/` (sync clobber / guard removal / action-version breakage) → **admin-only** per #2512; no agent patch can land it.
3. Else fix in `supremeai-core` via zero-credential `bridge_submit_patch` (if the tower-side lane carries core write access) or a credentialed fork PR; keep the fix + its tests in the same change (Full-Scope Completeness).
4. Close #4250 via the verdict plane once the healing run is provable — a `Closes` line from an agent that never saw the logs would be a false closure (#2211/#2225 family).

## Scope & rollback

- Files: this receipt + `docs/bridge/worklog-glm10.md` (one C17 row, in-place). Zero code edits, no claim, no auto-close.
- Rollback: delete this receipt; restore worklog row to baseSha content.
