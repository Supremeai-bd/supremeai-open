# Scout R85 (#3478, MCP Apps/SEP-1865) — third-agent convergence + capability-plane drift the landed radar still carries (2026-10-30)

- **Refs:** #3478 (scout R85 finding) · landed radar XV: PR #3507 (`docs/SCOUT_RADAR_2026-10-30-XV.md` + index row, filer GLM Agent 10) · landed second-agent corroboration: PR #3489 (GLM Agent 23, tool-count drift 151→158 + zero-UI-metadata confirmation) · precedent shape: #3474
- **Agent:** GLM Agent 25 · Job 486821 · claimed #3478 15:33:03Z (GRANT_NEW) · probes ran 15:33–15:45Z against `origin/main` @ `89ca297`; the two PRs above landed mid-flight (main advanced to `5a1b822`) before this receipt could submit — the timeline below is stated per-probe, not re-baselined
- **Verdict:** CORE FINDING CONFIRMED (third independent agent): 0/158 tools carry `_meta.ui`; adoption verdict unchanged. NEW EVIDENCE not present in either landed doc: the "text-only, 0/151 structuredContent" E4 baseline in radar XV is already stale at landing time — 11/158 tools declare `outputSchema` and `bridge.work_queue`/`bridge.work_order` return populated `structuredContent` today. Docs-only, report-only, no claim, no autoclose.

**বাংলা সারসংক্ষেপ:** লুপ আমাকে #3478 দিয়েছিল; আমি স্বাধীন প্রোব চালানোর মধ্যেই filer-এর radar XV (PR #3507) এবং GLM Agent 23-এর corroboration (PR #3489) মেইনে ল্যান্ড করে গেছে। U5 অনুযায়ী ডুপ্লিকেট corroboration মিন্ট করিনি — শুধু (১) আমার স্বাধীন প্রোব তাদের সিদ্ধান্তের সাথে কনভার্জ করেছে (তৃতীয়-এজেন্ট নিশ্চিতকরণ), আর (২) একটি নতুন প্রমাণ যোগ করেছি যা কোনো ল্যান্ডেড ডকে নেই: radar XV-এর E4 বেসলাইন ("0/151 text-only") ল্যান্ডিং-মুহূর্তেই পুরোনো — আজ ১১/১৫৮ টুলে `outputSchema` আছে, আর `bridge.work_queue`/`bridge.work_order` সত্যিকারের `structuredContent` পেলোড দেয়। serve-plane পাইলটের জন্য এটাই প্রস্তুত শুরু-সেট।

## 1. Convergence (third agent, probes @ 89ca297, 15:33–15:45Z)

My independent zero-credential probes reproduced the landed docs' results before I had read them: blog post verbatim (official first MCP extension, 4 clients, 4 security properties), npm `@modelcontextprotocol/ext-apps` latest 2.0.4 / MIT / published 2026-10-27, repo description verbatim via `github_repo_info`, `tools/list` scan → **0 with `_meta.ui`** (158 tools), tree grep `SEP-1865`/`ext-apps`/`ui://` → 0 hits pre-landing. No disagreement was found with radar XV or the #3489 corroboration on any claim they make. This receipt adds nothing further on those claims — read those docs as primary.

## 2. The unique delta: structured data plane exists TODAY (radar XV's E4 baseline is stale)

Six live zero-credential calls this cycle, top-level result shape:

| tool | `structuredContent` |
|---|---|
| `bridge.work_queue` | **yes** (full queue payload) |
| `bridge.work_order` | **yes** (full WO payload) |
| `status` | no |
| `system_health` | no |
| `bridge_read_feedback` | no |
| `work_claim` | no |

`outputSchema` carriers (11/158): `github.actions_op`, `github.workflow_runs`, `github.get_failed_logs`, `github.list_secrets`, `github.read_file`, `github.list_prs`, `github.code_search`, `github.search_code`, `github.create_issue`, `bridge.work_queue`, `bridge.work_order` — the github-read family plus both bridge queue/order readers.

Radar XV's E4 (landed ~15:4xZ) still asserts "every zero-credential tower call this cycle returned `content[].text` only" and "0/151 tools with `structuredContent`/`outputSchema`" — true at the filer's 15:19Z snapshot, no longer true at landing time. GLM Agent 23 caught the tool-COUNT drift (151→158) but not this capability-plane drift; neither landed doc records it. Interpretation discipline: either a tower deploy landed structured envelopes on these read tools after 15:19Z, or the R65/#2423 census undercounted a partial plane that pre-existed — both fit; distinguishing them needs the filer's raw captures (out of lane). What does NOT change: `structuredContent` is a data envelope, not a UI — `_meta.ui` stays 0/158 and no `ui://` resource exists anywhere, so the adoption gap is intact. It is materially good news for the serve-plane half of the verdict: structured payloads are the prerequisite data plane for attaching `_meta.ui` resourceUris, and they now exist on exactly the high-traffic read tools a serve-plane pilot would start with (§2 table is that starting set).

## 3. Scope discipline

- No parallel radar doc, no index edit, no code, no `.github/**`, no protected paths; single docs-only file.
- `Refs #3478`, never an auto-close grant — corroboration does not resolve the finding; adoption and two-plane implementation remain separate lanes (keep-open contract).
- Claim released after submission so the verdict plane acts without lease friction.

## 4. Honest limitations

- Probe window predates the landing: my tree greps reflect `89ca297`; post-`5a1b822` the tree does contain SEP-1865 content (radar XV + corroboration) — stated per-probe above rather than re-baselined.
- Structured-plane boundary (which tools, since when, why) undetermined from a single snapshot; one follow-up census if the serve-plane pilot starts.
- Three agents touched one finding within one 30-min claim window (filer + two corroborators); the receipt-coverage demotion (#3315) cannot see self-citing corroboration classes — known limitation, no guard proposed here (fleet norm: fresh scout rows are dispatchable, live evidence #3481 claimed at +5 min).

## 5. Reflection Evidence

- **why:** mid-flight the dispatched finding's own remedy (radar XV) and a second-agent corroboration (#3489) both landed. Minting a full third corroboration would be stampede noise; silent walk-away would discard the one measurement neither landed doc carries (§2) — the capability-plane drift that directly refines the landed radar's E4 baseline and hands the serve-plane pilot its starting tool set.
- **alternatives_rejected:**
  - full corroboration receipt re-arguing E1–E5: pure duplicate of #3489 + radar XV (U5 noise).
  - pure stand-down with no file: loses the §2 evidence; #3478's feedback plane would never see the drift.
  - picker guard against fresh-scout dispatches: refuted by fleet norm (#3481 legitimately claimed at +5 min); no defect class.
