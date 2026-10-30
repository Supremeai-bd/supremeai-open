# AUDIT #3093 — Live-State Verdict Attachment: outage LIVE 28.5h+, root cause pinned to one missing tower env var (docs-only)

**Task ID:** bridge-20261030-a3093-live-state · **Refs #3093 · Refs #2557** (report-only, no autoclose) · **Probed:** 2026-10-30T12:17:23–12:19:49Z
**Claim:** GRANT_NEW on #3093 at 12:19:49Z (TTL 30m → 12:49:49Z), GLM Agent 13 (Job 486783).

## 1. What #3093 asks

Cycle-57's post-closure verification found #2557 (Agent Review Workflow outage —
`agent_review_workflow_execute` / `agent_review_workflow_status` both fail with
`SUPREMEAI_BACKEND_URL is not configured`) closed prematurely: probe 07:47Z still
failing (~24h outage live). The row asks, per the #2925 live-state gate: **reopen
#2557 or attach the verdict**. This receipt is the verdict attachment, with the
isolation the earlier cycle could not make.

## 2. Fresh live receipts (2026-10-30, tower session bf774508 lineage)

**(a) Tool probe @ 12:17:23Z** — `agent_review_workflow_status` returns, verbatim:
`Error: SUPREMEAI_BACKEND_URL is not configured`. Same failure class as #2557's
original finding and #3093's 07:47Z probe ⇒ outage continuous 10-29 ~07:47Z →
12:17:23Z 10-30 = **28.5h+ and counting**.

**(b) Backend health @ 12:17:39Z** — `system_health`: **18 healthy · 2 degraded ·
1 unreachable · 0 unconfigured (of 21)**. `render-primary` (Core API) answers
HTTP 200 (degraded only by deploy plane: `update_failed`, the known #2225-class
burn); the tower itself (`render-mcp`) healthy/live. **The backend the tool would
call is UP.**

**(c) Tower env-key census @ 12:19Z (read-only, key names only, no values)** —
`render_get_env_var_keys` on `supremeai-mcp-tower` (serviceId
`srv-dabm7inqj5pc738jkrt0`, account `render-mcp`): **42 keys** present, including
`SUPREMEAI_API_URL`, `SUPREMEAI_GATEWAY_URL`, `SUPREMEAI_API_KEY` — and
**`SUPREMEAI_BACKEND_URL` is ABSENT**.

## 3. Root cause (pinned, not speculated)

The agent-review tooling demands an env var the tower has **never had**:
`SUPREMEAI_BACKEND_URL`. Its sibling names (`SUPREMEAI_API_URL`,
`SUPREMEAI_GATEWAY_URL`) are set — so this is a **name mismatch in the tool's
config contract, not a service outage**: the "28.5h outage" is one tool surface
reading a variable name that does not exist in its own process environment, while
the backend it names runs 200-healthy. Admin fix is one env var (value = primary
API base URL, admin's choice among the existing URL vars) on
`srv-dabm7inqj5pc738jkrt0` + redeploy; then a single `agent_review_workflow_status`
probe should flip. No code change is implied anywhere.

## 4. Verdict per the #2925 live-state gate

- **#2557's closure remains PREMATURE** — the outage is live at 28.5h+, longer
  than at #3093's filing.
- This receipt **attaches the verdict** #3093 asked for; the reopen decision itself
  stays with the maintainers (this submission intentionally does NOT auto-close
  anything: closing #3093 while #2557 stays closed would repeat the exact
  closure-integrity failure #2916 documents).
- After the env fix lands: #2557's closure becomes legitimate, and #3093 can close
  against that probe — both rows then rest on live ground truth instead of a
  config artifact.

## 5. বাংলা ব্যাখ্যা (সহজ ভাষায়)

**সমস্যা:** tower-এর "Agent Review Workflow" tool দুটি (execute/status) ~২৮.৫ ঘণ্টা
ধরে ব্যর্থ হচ্ছে — error বলছে "SUPREMEAI_BACKEND_URL is not configured"। #2557 টিকিট
এই কারণেই খোলা ছিল, অথচ তা বন্ধ করে দেওয়া হয়েছিল — #3093 সেটাকে "অসময়োচিত বন্ধতা" বলে
প্রমাণসহ চ্যালেঞ্জ করেছে এবং রায় জুড়তে বলেছে।

**আমি যা পেলাম (তিনটি জীবন্ত প্রমাণ):**
১. এখনই (12:17:23Z) tool ডাকলে **একই error** — ত্রুটি এখনও বেঁচে আছে।
২. কিন্তু backend নিজে **সুস্থ** — health প্লেন বলছে ২১টির মধ্যে ১৮টি healthy,
   "0 unconfigured"; Core API 200 সাড়া দিচ্ছে।
৩. tower-এর env-ভেরিয়েবলের **নাম-তালিকা** (মান নয়, শুধু নাম — read-only) পড়ে দেখলাম:
   ৪২টি key-এর মধ্যে `SUPREMEAI_API_URL`, `SUPREMEAI_GATEWAY_URL`, `SUPREMEAI_API_KEY`
   **আছে**, কিন্তু `SUPREMEAI_BACKEND_URL` **নেই-ই**।

**মূল কারণ এখন ধরা আছে:** tool-টি এমন একটি ভেরিয়েবলের নাম চায় যা tower-এর
environment-এ **কখনো সেটই হয়নি** — অর্থাৎ এটা সার্ভিস-বিপর্যয় নয়, **নাম-বিভ্রান্তির
config-সমস্যা**। প্রতিকার একটাই: admin সেই একটি env var বসিয়ে tower রিডিপ্লয় করবেন।

**সিদ্ধান্ত:** তাই #2557-এর বন্ধতা **এখনও অসময়োচিত** — এই receipt-ই #3093-এর চাওয়া
"verdict" হিসেবে জুড়ে দিলাম। ইচ্ছাকৃতভাবে কোনো টিকিট স্বয়ংক্রিয়ভাবে বন্ধ করিনি —
admin ভেরিয়েবলটি বসানোর পর একটি প্রোব সবকিছু স্পষ্ট করবে।

— GLM Agent 13 (Job 486783), 2026-10-30
