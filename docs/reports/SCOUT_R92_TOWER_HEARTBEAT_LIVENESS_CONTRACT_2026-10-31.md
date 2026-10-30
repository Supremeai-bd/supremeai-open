# Scout Radar R92 — Tower heartbeat liveness contract: five windows across three planes, zero in-payload cadence guidance, a loop that feeds neither plane, and a dashboard online-plane structurally dark for the hourly fleet

- **Lane:** R92 (freeness verified per the #2392 predicate at fresh main `d646019`, 2026-10-31 ~07:2x+08, and the pointer advertisement re-verified free at the pre-submit tip `d2c62e3`: tracked-tree scan — `R92` appears only in this index's own pointer advertisement and the pass-48 mechanism text, both allowed exceptions; topic markers `onlineThreshold|ttlSeconds|heartbeat cadence|ping every 45` zero in the tracked tree; last-200 origin/main subjects zero; 20-row open-queue capture zero)
- **Filed by:** GLM Agent 04 (Job 486718, slot agent-3), ecosystem-scout role, 07:04+08 dispatch, continuous-loop assigned
- **Defining artifact:** this report + WO (the bridge auto-files the defining issue on submit)
- **Verdict:** `adapt` — fix direction routed to owner lane; zero code edits by the filer (registry co-obligation files only)
- **Surface:** tower `agent_heartbeat`/`agent_status` payload contract (viewer lane) + `scripts/agents/agent_identity.py` Heartbeat Registry (#2950 follow-up) + `scripts/agents/continuous_agent_loop.py` (the non-caller)

## Finding (one sentence)

The fleet's "agent alive" signal is measured by **two disjoint planes with five different windows** — the tower plane (45 s designed ping cadence and 90 s online threshold living only in tool-description prose, `ttlSeconds: 300` the only payload field, 24 h archive grace) and the repo plane (`agent_identity.py` Heartbeat Registry: `HEARTBEAT_INTERVAL = 600`, `HEARTBEAT_TTL = 1800`) — while the continuous loop **calls neither**, so the dashboard's builder online-plane is structurally dark for an hourly-cadence fleet (live: `onlineAutonomous` read **2/22 → 0/22 → 0/22** across one six-minute window, and 90 s/3600 s caps a lane's online duty cycle at **2.5 %**).

## Evidence (all live-verified 2026-10-31, zero-credential, viewer-allowed tools only)

| # | Claim | Proof |
|---|---|---|
| E1 | The heartbeat response advertises exactly one machine-readable window — `ttlSeconds: 300` — while the real online window is 90 s | T0 response (23:11:25.085Z, this lane): `{"ok":true,"slot":"agent-3","agentId":"GLM-Agent-04","heartbeatAt":"2026-10-30T23:11:25.045Z","ttlSeconds":300,"redisAccount":"tertiary","onlineThreshold":"ping again within 90s to stay 'online'"}` — the 90 s truth arrives only as a free-text string; a consumer parsing the numeric field reads a **3.33×** too-generous validity window (300/90, computed) |
| E2 | The designed ping cadence is 45 s — and it exists only in description prose | `tools/list` (fresh session, 23:10Z): `agent_heartbeat` description: *"Ping every 45s while running; the dashboard shows the slot as 🟢 online within 90s of the last ping"*; `agent_status` description: *"online (≤90s), stale (>90s, key alive), expired (no runtime signal, visible for 24h archive grace)"* — four of the five windows are prose-only |
| E3 | **Live state-machine timeline (self-ping, T0 = 23:11:25.045Z)** | T0: `agent-3` age 0 s → `online`; T0+130 s: age 130 s → `stale`; T0+338 s: age 338 s → `expired` (still listed — archive grace). The key-TTL bracket [130 s, 338 s] contains the advertised 300 s. Cross-slot corroboration at T0: `agent-8` age 174 s = stale; `agent-32` age 1781 s = expired-visible; `agent-11` age 4 s = online |
| E4 | **The builder online-plane is structurally dark at fleet scale** | Same three polls: `onlineAutonomous` = **2/22** (one of the two is this lane's own ping) → **0/22** → **0/22**. Interactive assistants: 10/14 → 8/17 → 12/19 online — continuous pingers, the 45 s contract fits *them* |
| E5 | Duty-cycle arithmetic (computed, not estimated) | Hourly lane pings once per cycle: 90 s online / 3600 s cycle = **2.5 %** max online fraction; E[concurrent online builders] = 22 × 0.025 = **0.55**; P(≥1 of 22 online) = 1 − 0.975²² = **42.7 %** — i.e. even in the best case the dashboard's builder plane is dark >half of all wall-clock moments, and dark ~97.5 % of each lane's cycle |
| E6 | **The loop feeds neither plane** | `git grep agent_heartbeat -- scripts/agents/continuous_agent_loop.py` → zero calls (only a Bangla contract comment at L2262); `agent_identity`/`acquire_role_slot` not imported by the loop. The repo's second registry — `scripts/agents/agent_identity.py` L79–84 (#2950 follow-up): `HEARTBEAT_INTERVAL = 600 # 10 minutes`, `HEARTBEAT_TTL = 1800 # 30 minutes`, local JSON `docs/master_docs/AGENT_HEARTBEAT_REGISTRY.json` that "git-এ commit হয় না" — is a **parallel liveness contract for the same concept with different numbers** |
| E7 | Zero mechanical consumers exist today | `git grep` over the full tracked tree: `onlineThreshold` zero hits, `ttlSeconds` zero hits, "heartbeat cadence"/"ping every 45" zero hits — the windows are unparsed anywhere in the repo, so making the payload self-describing (Plan-1) is purely additive, no breaking change |
| E8 | The `debounced` response field is shape-unstable and undocumented | The same lane's earlier ping (23:04:50.624Z) returned `"debounced": true`; the T0 ping (23:11:25.085Z, 6 m35 s later) returned **no** `debounced` key at all. Presence signals a swallowed ping; absence is the default; no schema description, no debounce window disclosed — whether a debounced ping refreshes the stored `lastPing` is unobservable from outside |
| E9 | Context datum — the viewer surface is still moving (census watch #1 answered) | `tools/list` = **18** tools (RBAC_CENSUS, 20:16:40Z) → **20** this cycle (23:10Z): `bridge_work_queue` and `bridge_work_order` are new split-out read tools. This lane rode only stable core tools (`agent_heartbeat`, `agent_status`, `tools/list`, `bridge_work view:queue`) |

## Why it matters

1. **False-negative fleet liveness.** During any incident, the dashboard's builder plane reads 0/22 online while the fleet lands bridge PRs continuously — the loop's own honesty contract ("dark ≠ zero, UNSEEN never certified clean") is exactly what this plane violates *by construction*: dark here does not even mean "checked", it means "the metric cannot express lane-alive for the fleet's actual cadence". An owner reading 🟢/⚪ during a landing stall (the #3923 starvation class) sees a dead fleet and draws the wrong triage conclusion.
2. **A 3.33× misleading freshness field.** `ttlSeconds: 300` is the only numeric window in the payload and reads as "my heartbeat is valid for 5 minutes"; the true online threshold is 90 s. The correct guidance exists only as description prose, which no payload consumer can parse (E7: zero consumers).
3. **Two planes, one concept, contradictory answers.** The tower plane (45/90/300 s, Redis `tertiary`) and the repo plane (600/1800 s, local JSON) can disagree about the same agent simultaneously, and both are unfed by the loop that assigns all fleet work. Consolidation — or at minimum explicit scoping ("viewer dashboard liveness" vs "repo mesh identity") — is an owner decision that today has no SSOT table to make it against.

## Fix direction (owner lane; the filer made zero code edits)

- **Plan-1 (tower, additive, ~payload only):** make `agent_heartbeat`'s response self-describing: echo `{pingCadenceSec: 45, onlineSec: 90, keyTtlSec: 300, archiveGraceSec: 86400}` and always-present `debounced: boolean` (+ `debounceWindowSec`). No behavior change; turns E7's zero-consumer state into a machine-readable contract.
- **Plan-2 (agent-side, zero tower change):** the loop pings every 45 s **while running** (honoring the designed contract), or the tower derives a second "lane-alive" state from the last bridge receipt timestamp — either way the online plane starts meaning what its legend says.
- **Plan-3 (docs):** one five-window SSOT table (tower plane × repo plane, window × meaning × consumer) in `AGENT_SLOT_REGISTRY.yaml` or `docs/AGENT_OPERATING_SYSTEM.md`; the dashboard legend cites it.
- **Plan-4 (optional):** explicitly scope or consolidate the two planes so no consumer can read contradictory aliveness for the same agent.

## Adjacency / disjointness (per the #2392 predicate)

- **#3785-class lanes** (glm07 receipt + this agent's `TRIAGE_3785_PR3784_CI_2026-10-31.md`): the **CI test plane** of `HEARTBEAT_ARCHIVE_GRACE_SECONDS_DEFAULT` (86 400 → 14 400 flip vs 24 h-pinned tests) — same state machine, different subject (code/test pins, not the live contract's observability). Disjoint; disclosed.
- **#3739 + `RBAC_CENSUS_2026-10-31.md`** (this agent's + glm13's): the **permission plane** (viewer matrix, 18→20-tool mobility E9 answers its next-watch #1). Disjoint.
- **R49** (MCP protocol ceiling), **R88/R89/R91** (gateway planes), **#2950** (repo-plane registry origin — cited as the mechanism's own reference, not a liveness-contract lane): disjoint subjects.

## Method note

Zero-credential throughout: three tower calls of the viewer-allowed core set (`agent_heartbeat` self-ping only, `agent_status` ×3, `tools/list` ×1, `bridge_work view:queue` ×1) bracket the state machine over ~6 minutes of wall clock; the only write was this lane's own heartbeat (`agent-3`); no other slot was touched. All arithmetic (2.5 %, 0.55, 42.7 %, 3.33×) computed by code, not estimated. The three-poll design deliberately brackets the advertised 300 s TTL from both sides (stale at 130 s, expired at 338 s).

## Receipt-closure convention

This report does not resolve its own subject: the lane stays open until an owner-lane change lands Plan-1 (payload windows) and Plan-2 (loop-side ping or lane-alive signal), ideally with Plan-3's SSOT table. No `closes` claim, no claim taken, no code edits by the filer.

## Appendix A — raw transcripts (2026-10-31, viewer lane)

**A1. T0 heartbeat response (23:11:25.085Z):**
```json
{"ok": true, "slot": "agent-3", "agentId": "GLM-Agent-04", "heartbeatAt": "2026-10-30T23:11:25.045Z", "ttlSeconds": 300, "redisAccount": "tertiary", "onlineThreshold": "ping again within 90s to stay 'online'"}
```

**A2. Earlier same-lane ping (23:04:50.624Z) — note the extra key:**
```json
{"ok": true, "slot": "agent-3", "agentId": "GLM-Agent-04", "heartbeatAt": "2026-10-30T23:04:50.624Z", "ttlSeconds": 300, "redisAccount": "tertiary", "onlineThreshold": "ping again within 90s to stay 'online'", "debounced": true}
```

**A3. Live timeline (`agent_status`, `agent-3` rows):**

| Poll | Server now | ageSeconds | state | counts.onlineAutonomous |
|---|---|---|---|---|
| T0 (23:11:25.143Z) | 23:11:25Z | 0 | online | 2 (of 22) |
| T0+130 s (23:13:35Z) | — | 130 | stale | 0 (of 22) |
| T0+338 s (23:16:43Z) | — | 338 | expired | 0 (of 22) |

**A4. T0 cross-slot corroboration:** `agent-11` age 4 s online · `agent-8` age 174 s stale · `agent-32` age 1781 s expired (visible, archive grace).

**A5. Viewer `tools/list` census this cycle (20 tools):** status, system_inspect, system_summary, system_health, slot_status, agent_heartbeat, agent_status, supabase_schema_inspect, db_schema_inspect, bridge_guide, bridge_work_queue, bridge_work_order, bridge_work, bridge_submit_patch, bridge_submit, work_claim, bridge_read_feedback, bridge_lease_manage, bridge_work_renew, bridge_work_release — vs the 18-tool census set: **+`bridge_work_queue`, +`bridge_work_order`**.

---

## বাংলা সারসংক্ষেপ

**সমস্যা:** ফ্লিটের "এজেন্ট বেঁচে আছে" সিগন্যালটা দুইটা আলাদা প্লেনে ছড়িয়ে আছে এবং পাঁচটা ভিন্ন সময়-উইন্ডো ব্যবহার করে — টাওয়ার প্লেনে ৪৫ সেকেন্ড (ডিজাইন-করা ping ক্যাডেন্স), ৯০ সেকেন্ড (online থ্রেশহোল্ড), ৩০০ সেকেন্ড (Redis key TTL, response-এর একমাত্র সংখ্যাগত ফিল্ড), ২৪ ঘণ্টা (archive grace); আর repo-র `agent_identity.py` রেজিস্ট্রিতে ৬০০ সেকেন্ড interval ও ১৮০০ সেকেন্ড TTL। এই উইন্ডোগুলোর কোনোটাই response payload-এ মেশিন-পাঠযোগ্যভাবে নেই (শুধু `ttlSeconds: 300`, যা সত্যি online উইন্ডোর চেয়ে ৩.৩৩× বেশি দেখায়), আর continuous loop কোনো প্লেনকেই feed করে না।

**লাইভ প্রমাণ:** নিজের heartbeat দিয়ে তিনবার পোল করলাম — T0-তে `agent-3` online (age 0), T0+১৩০ সেকেন্ডে stale, T0+৩৩৮ সেকেন্ডে expired। একই মুহূর্তে ২২টা autonomous builder-এর মধ্যে online ছিল ২টা (একটা আমি নিজে, ping দেওয়ার পর), তারপর ০, তারপর ০। ঘণ্টা-ক্যাডেন্সের লেনে সর্বোচ্চ ২.৫% সময় online থাকা সম্ভব — তাই ড্যাশবোর্ডের builder প্লেন কাঠামোগতভাবেই অন্ধকার: **dark মানে মৃত নয়**, কিন্তু মেট্রিকটা এটা বলতেই পারে না। এছাড়া `debounced` ফিল্ডটা কখনো আসে কখনো আসে না — semantics অজানা।

**ক্ষতি:** কোনো landing stall বা incident-এর সময় owner ড্যাশবোর্ড দেখবেন ০/২২ online — অথচ ফ্লিট আসলে প্রতিনিয়ত PR land করছে। ভুল ট্রায়াজ সিদ্ধান্তের ঝুঁকি।

**সমাধানের দিক (owner লেন, আমি কোনো কোড এডিট করিনি):** (১) heartbeat response-এ চারটা উইন্ডোই মেশিন-পাঠযোগ্যভাবে echo করা; (২) loop চলার সময় প্রতি ৪৫ সেকেন্ডে ping দেওয়া, অথবা শেষ bridge receipt থেকে "lane-alive" state বানানো; (৩) পাঁচ উইন্ডোর একটা SSOT টেবিল; (৪) দুই প্লেনের সুস্পষ্ট scoping বা consolidation।

---

*Filed by GLM Agent 04, Job ID 486718, slot agent-3, cycle cron-agent-loop-202610310704, 2026-10-30 ~23:2xZ (07:2x+08). Zero side effects beyond the lane's own heartbeat; no closure requested — remediation is owner-lane.*
