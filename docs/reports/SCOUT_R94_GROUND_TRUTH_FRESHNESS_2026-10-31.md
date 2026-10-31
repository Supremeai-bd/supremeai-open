# Scout Radar R94 — the credential-free ground-truth hierarchy: web-rendered GitHub views can be ~hours stale (live: a 61-open ghost board), shared-IP REST is 403-dark, and the tower single-fetch plane is the only live-proven fresh board authority — codify the spot-check protocol before the ghost data mints a false finding

- **Lane:** R94 (freeness verified per the #2392 predicate at fresh main `4e553bd`, 2026-10-31 ~08:2x+08: tracked-tree scan — `R94` appears only as base64/hash coincidences (`studio/pnpm-lock.yaml:1721` `…R94M+w6yGWn4…`, `studio/pnpm-lock.yaml:2933` `…R94C/XXamv…`, `vscode/package-lock.json:2136` `…94xHue0oA==`, `studio/src/components/jarvis/avatarAssets.ts:2485` `"8sAzdlD5R944lkSOXmD44n45"`) — the pass-11 honesty-note class, zero lane citations; last-200 origin/main subjects zero; board sweep: tower queue `totalOpen=0` + a 4-row single-fetch spot check (E2). The successor pointer's freeness verification rides the index drift log per the R93 filing precedent — this report cites only its own lane number)
- **Filed by:** GLM Agent 16 (Job 486792, slot agent-16), ecosystem-scout role, 08:16+08 dispatch (cron-agent-loop-202610310816), continuous-loop assigned
- **Defining artifact:** this report + WO (the bridge auto-files the defining issue on submit)
- **Verdict:** `adapt` — one protocol paragraph routed to the docs/owner lane; zero code edits by the filer (registry co-obligation files only)
- **Surface:** the credential-free agent's board-verification practice (the U5 second-tier board scan and every no-pick hold's census) + the loop's board-fallback print (owner lane, optional)

## Finding (one sentence)

The credential-free lane has no codified freshness hierarchy for board ground truth, and the gap is live-proven dangerous: at ~00:17Z 2026-10-31 a web-rendered GitHub issues view served this filer a **61-open "ghost board"** listing at least four issues (`#3946`, `#3825`, `#3812`, `#3841`) that the tower's single-fetch plane proved **closed (`state_reason: completed`, `updatedAt` 23:24–23:34Z — 43–63 minutes *before* the ghost view was fetched)**, anonymous REST was 403-dark on the shared IP, and the only plane that was verifiably fresh was the tower's `bridge_work_order` single fetch — so without a one-paragraph protocol ("tower single-fetch spot-checks are the board's freshness authority; web-rendered views may traverse stale caches; shared-IP REST is rate-limit dark"), every agent re-derives ground truth per cycle and the ghost data mints false findings — this filer drafted one (a "tower board serves false-empty" accusation) and retracted it only because the spot-check protocol was applied mid-draft.

## Evidence (all live-verified 2026-10-31 ~00:16–00:2xZ at fresh main `4e553bd`, zero-credential, zero tower writes)

| # | Claim | Proof |
|---|---|---|
| E1 | A web-rendered GitHub issues view served ghost state: 61 open rows including four that were already closed | WebFetch HTML of `github.com/Supremeai-bd/supremeai-open/issues?q=is%3Aissue+is%3Aopen` at ~00:17Z: header "Open 61", and the list shows `#3946`, `#3825`, `#3812` (bridge:queued) and `#3841` (status:claimed) as open, with "Unread" markers |
| E2 | The tower single-fetch plane was fresh and contradicts all four rows | `bridge_work_order {"number": N}` same cycle: `#3946 → state=closed, stateReason=completed, updatedAt=2026-10-30T23:24:26Z`; `#3841 → closed/completed, 23:31:56Z`; `#3825 → closed/completed, 23:34:33Z`; `#3812 → closed/completed, 23:33:30Z` — every closure 43–63 min before the ghost view was rendered; the `#3946` body came back verbatim (full Task-ID/Branch/Summary fields), proving the plane reads live GitHub data, not a cache |
| E3 | Anonymous REST is not a viable ground-truth fallback on this lane's IP | Single unauthenticated `GET /repos/Supremeai-bd/supremeai-open/issues?state=open` → `HTTP 403 rate limit exceeded` (the shared-IP 60 req/h budget, the #3967 class) — the quota makes REST-unauthenticated structurally unreliable for fleet verification |
| E4 | The tower queue planes' `totalOpen=0` was TRUE-empty, not false-empty — proven only because the spot-checks exist | `bridge_work_queue {}` → `count:0, totalOpen:0, workOrders:[]`; label-filtered `{"label":"bridge:queued"}` and `{"label":"repo:open"}` → also 0; `bridge_work {"view":"queue"}` → 0 — all consistent with E2's closure wave (board drained ~110 rows over the day to true zero). Without E2-style spot-checks, "queue says 0" and "queue is broken serving 0" are indistinguishable — this cycle they were only distinguishable because the four spot-checks ran |
| E5 | The loop's board-fallback print carries no dark/empty discriminator for the board plane | Live dispatch output (08:16+08): `! tower board reachable: 0 open work orders — P0-drainage gate (Invariant 5) is dark on this gh-less runtime` — printed as fact; the loop's own PR-audit plane applies the honest rule ("open PRs UNSEEN, not zero — treating this as clean would be false assurance (U2)") but the board plane trusts `totalOpen=0` verbatim. Correct this cycle (E4), structurally unguarded |
| E6 | The near-miss is the harm case, live | This filer drafted a false finding ("the tower queue serves false-empty; GitHub shows 61 open") from E1's ghost data and retracted it after running E2 — the retraction cost one draft cycle; an agent without the protocol would have filed it, and the ledger would carry a false accusation against a healthy plane |

## Why it matters

1. **Every fleet verification leans on board ground truth.** U5 anti-stampede's second tier is a board scan; every no-pick hold cites a census (48 → 47 → 38 → 5 → 3 → 0 across the day's receipts); the P0-drainage gate reads the same plane. A ghost board inflates demand-side signal (phantom work, phantom P0s); a false-empty board deflates it (holds filed while work waits). Both steer the fleet wrong with receipts as the audit trail.
2. **The false-finding class is already one step from landing.** E6's near-miss survived two drafted paragraphs before the spot-checks killed it. The next agent may draft the same finding from the same stale plane and file it — a false accusation against the tower's board plane would then need its own retraction receipt (the #3966 retraction class, avoidable upstream).
3. **The fix costs one paragraph, zero code, zero credentials.** The fresh plane already exists and is proven (E2's verbatim bodies). Nothing needs building — the protocol only needs codifying where agents already read: the guide's lifecycle step 1/6 and AGENTS.md's verification section.

## Fix direction (owner/docs lane; the filer made zero code edits beyond the radar registry co-obligation)

- **Plan-1 (the protocol paragraph):** in `scripts/bridge/README.md` (the operator contract the guide links) and/or AGENTS.md verification section: *"Board ground truth = tower `bridge_work_order` single-fetch spot-checks of specific issue numbers (proven fresh: verbatim bodies, live state). Web-rendered GitHub views may traverse stale caches (live: a 61-open ghost list served 43–63 min after every row closed). Anonymous REST is rate-limit dark on shared IPs (#3967). Never ground a board-state finding on a web-rendered list alone; when the queue plane and a web view disagree, the single-fetch spot-check wins."*
- **Plan-2 (optional, loop, owner lane):** when the board fallback prints `0 open work orders`, append the one-line hint `ground truth: spot-check N known rows via bridge_work_order before citing emptiness` — the same honesty the PR plane already prints (E5).
- **Plan-3 (ledger):** this radar row records the near-miss (E6) so future agents can cite it as the precedent for why the protocol exists.

## Adjacency / disjointness (per the #2392 predicate)

- **#3967** (federation_anchors quota preflight): cited as the shared-IP 403 class (E3); that lane is quota-mitigation for one script, this lane is the board ground-truth hierarchy. Disjoint.
- **R92** (heartbeat liveness planes): measures the *agent-alive* signal; this lane measures *board-state* freshness. Disjoint planes, same honesty family.
- **R93** (#3993/#3994 anchor-routing None hole): CI-mirror routing surface. Disjoint.
- **#3959 / #3980** (PR-plane RBAC blindspot / "U2 plane RESURRECTED"): this cycle adds one lane-bounded datum, recorded here to prevent a false refutation: a fresh anonymous blind probe `github_list_prs` → `Forbidden: tool 'github_list_prs' requires agent role or higher (default-deny RBAC). Present a valid MCP Bearer token with a sufficient role.` — i.e. the underscore variant exists in the registry but is auth-gated; #3980's resurrection claim stands for whichever lane held credentials, and the anonymous fleet remains on #3959's option C until the owner moves. This lane's subject (board ground truth) is disjoint from the PR plane; the datum rides here because this cycle generated it and it corrects the anonymous-lane expectation.
- **#4001** (adhoc envelope honesty): envelope emission shape — disjoint.

## Method note

Zero-credential, near-zero-network: tower tools (queue/hub/order/feedback reads), one web-rendered page fetch, one 403 REST probe, one blind RBAC probe. No tower writes beyond this lane's own submission; no claim taken on any row (board had none open); the staleness proof is cross-plane timestamp arithmetic (E2 vs E1) reproducible by any agent in one minute. Raw outputs in Appendix A.

## Receipt-closure convention

This report does not resolve its own subject: the lane stays open until Plan-1's protocol paragraph lands in the docs the agents actually read (owner lane). No `closes` claim, no claim taken, no code edits by the filer.

## Appendix A — raw probe outputs (2026-10-31, at `4e553bd`)

```
E1 (web-rendered view, ~00:17Z): "Open 61 (61)" … "### [🌉 Bridge Work Order — fix(loop): wire
    pre_work_rebase_guard() …] #3946" / "#3944" / "#3941" / "#3841 status:claimed" / "#3825" /
    "#3812" listed as open rows with Unread markers
E2 (tower bridge_work_order, same cycle):
    #3946 → {"state":"closed","stateReason":"completed","updatedAt":"2026-10-30T23:24:26Z"}
    #3841 → {"state":"closed","stateReason":"completed","updatedAt":"2026-10-30T23:31:56Z"}
    #3825 → {"state":"closed","stateReason":"completed","updatedAt":"2026-10-30T23:34:33Z"}
    #3812 → {"state":"closed","stateReason":"completed","updatedAt":"2026-10-30T23:33:30Z"}
E3 (REST, one call): "HTTP Error 403: rate limit exceeded"
E4 (tower queue): bridge_work_queue {} → "count":0,"totalOpen":0,"workOrders":[]
    {"label":"bridge:queued"} → 0; {"label":"repo:open"} → 0; bridge_work {"view":"queue"} → 0
E5 (loop dispatch, 08:16+08): "! tower board reachable: 0 open work orders — P0-drainage gate
    (Invariant 5) is dark on this gh-less runtime"
E6: near-miss draft retracted pre-submit (this report is the corrected lane)
Extra datum (PR-plane RBAC bound): tools/list (anonymous) = 20 tools, github.* = 0;
    blind call github_list_prs → "Forbidden: tool 'github_list_prs' requires agent role or
    higher (default-deny RBAC). Present a valid MCP Bearer token with a sufficient role."
Tower health same cycle: status → 12/12 services available (render-primary recovered from the
    prior cycles' degraded update_failed state).
```

---

## বাংলা সারসংক্ষেপ

**সমস্যা:** কোনো ক্রেডেনশিয়াল ছাড়া কাজ করা এজেন্টের জন্য বোর্ডের "সত্য অবস্থা" জানার কোনো লিখিত স্তরক্রম (freshness hierarchy) নেই। এই চক্রে আমি নিজেই ফাঁদে পা দিয়েছিলাম: ওয়েব-রেন্ডার করা GitHub issues পেজ আমাকে দেখাল **৬১টা open issue-এর "ঘোস্ট বোর্ড"** — অথচ tower-এর single-fetch প্লেন প্রমাণ করল তার মধ্যে অন্তত ৪টা রো (`#3946`, `#3825`, `#3812`, `#3841`) আসলে **৪৩–৬৩ মিনিট আগেই closed (completed)** হয়ে গেছে। অর্থাৎ ওয়েব ভিউ কয়েক ঘণ্টা পুরনো হতে পারে। আর anonymous REST শেয়ারড IP-তে 403 (রেট-লিমিট) — তৃতীয় কোনো ফ্রেশ প্লেন নেই।

**ক্ষতির প্রমাণ (লাইভ):** আমি এই ঘোস্ট ডেটা থেকে একটা **ভুল ফাইন্ডিং ড্রাফ্ট করে ফেলেছিলাম** ("tower বোর্ড false-empty সার্ভ করছে!") — স্পট-চেক প্রোটোকল চালানোর পর প্রত্যাহার করেছি। পরের এজেন্ট হয়তো ধরবে না, আর একটা মিথ্যা অভিযোগ লেজারে ঢুকে যাবে (প্রমাণ: এই চক্রের E6)। উল্টোদিকে, লুপ বোর্ড-ফলব্যাকে `0 open work orders` সত্য-হিসেবে ছাপে — এই চক্রে সেটা সঠিক ছিল (বোর্ড সত্যিই খালি, closure-wave-এ), কিন্তু "সত্যিকারের শূন্য" আর "ভাঙা প্লেনের শূন্য" আলাদা করার কোনো guard নেই।

**সমাধানের দিক (owner/docs লেন, আমি কোনো কোড এডিট করিনি):** (১) এক প্যারাগ্রাফের প্রোটোকল — *বোর্ডের ground truth = tower `bridge_work_order` single-fetch স্পট-চেক (নির্দিষ্ট ইস্যু নম্বর ধরে); ওয়েব-রেন্ডার ভিউ stale cache হতে পারে; shared-IP REST 403-dark; দুই প্লেন দ্বিমত করলে single-fetch-ই জিতবে* — সেটা bridge README/AGENTS.md-এ লেগে যাবে; (২) ঐচ্ছিক: লুপের বোর্ড-ফলব্যাক শূন্য দেখালে এক লাইনের স্পট-চেক হিন্ট ছাপবে (PR-প্লেনের U2 সততার মতোই); (৩) এই রাডার রোটাই near-miss-এর নজিৎ, যাতে ভবিষ্যৎ এজেন্ট উদ্ধৃত করতে পারে।

**পাশাপাশি রেকর্ড:** এই চক্রের লাইভ প্রোবে দেখা গেল tower ১২/১২ সার্ভিস healthy (render-primary সেরেছে), টুল-সারফেস ২০-এ স্থিতিশীল, আর `github_list_prs` underscore ভ্যারিয়েন্ট registry-তে আছে কিন্তু `agent role`+Bearer ছাড়া Forbidden — #3980-এর "resurrection" দাবি তাদের লেনের জন্য সত্য থাকল, anonymous লেনের জন্য #3959-এর option C-ই এখনো বাস্তবতা। বোর্ড দিনভর ~১১০ রো থেকে **সত্যিকারের শূন্যে** নেমেছে — সব no-pick hold সঠিক ছিল।

---

*Filed by GLM Agent 16, Job ID 486792, slot agent-16, cycle cron-agent-loop-202610310816, 2026-10-31 ~00:2xZ (08:2x+08). Zero side effects: tower reads + one stale web fetch + one 403 REST probe + one blind RBAC probe; no claim taken; no closure requested — the protocol paragraph is owner-lane.*
