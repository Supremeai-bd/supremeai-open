---
id: head-of-planning-ws-compact-command-v1-2026-09-17
title: "Head of Planning — Plan #005: Claude Code-Style User-Controlled /compact Trigger (বিদ্যমান PLAN-002 Compaction মেশিনারির উপর, শূন্য নতুন Dependency, শূন্য নতুন Infra)"
status: proposed
document_role: implementation
owner_circle: Memory Circle + C5 (Execution — LLM Gateway) — PLAN_002-এর হুবহু মালিকানা, একই WS চ্যাট সাবসিস্টেম
target_scope: supremeai_internal
scope: "ONE complete plan, grounded in actual repo code on fresh main 17a8ef41 (2026-09-17) — PLAN-002-এর implemented _compact_history() মেশিনারির উপর একটি ছোট, সুগঠিত user-facing সংযোজন; PLAN_LIFECYCLE_POLICY.md (2026-09-17, target_scope taxonomy সহ) কঠোরভাবে অনুসরণ; Gates 0–6; quantitative claims labeled; explicit out-of-scope"
depends_on:
  - backend/api/routes/websocket_agent.py (implemented PLAN-002 machinery — _compact_history L457–517, WS chat loop L565–631, deque(maxlen=50) L556)
  - backend/core/prompt_handler.py (implemented pure helpers — COMPACTION_SYSTEM_PROMPT L80, COMPACTION_SUMMARY_CHAR_CAP=1400 L91, COMPACTION_BLOCK_LABEL L93, build_compaction_messages L96, estimate_messages_tokens L115)
  - backend/tests/api/test_websocket_compaction.py (existing 11-test suite + StubGateway pattern L29 — এই প্ল্যানের টেস্ট একই ফাইলে একই প্যাটার্নে যুক্ত হবে)
  - backend/core/llm/llm_gateway (existing singleton — task_type="summarization" ইতিমধ্যে implemented compaction path-এ ব্যবহৃত)
  - frontend/src/hooks/useChat.ts L92 + frontend/src/services/chatService.ts L72 (existing [DONE] stream-termination contract — নতুন কোনো frontend change নয়)
  - README.md Constitution #4 (Dynamic Discovery), #8 (Graceful Degradation), #13 (No Silent Failure), #14 (Sustainable Cost)
  - AGENTS.md Mandatory Rule #9 (Enterprise-Grade Completeness & Safety by Design)
implements:
  - Claude Code-এর ব্যবহারকারী-নিয়ন্ত্রিত compaction UX — ইউজার যখন চায় তখনই হিস্ট্রি collapse, automatic trigger-এর অপেক্ষা নয় (Constitution #4)
  - PLAN-002-এর সাইলেন্ট auto-compaction-এর উপর একটি দৃশ্যমান, স্বীকৃত, honest acknowledgment স্তর (Constitution #13 No Silent Failure)
  - শূন্য নতুন subsystem, শূন্য নতুন dependency, শূন্য নতুন infra — বিদ্যমান implemented ফাংশনের পুনঃব্যবহার (Constitution #3, #14)
supersedes: []
superseded_by: []
source_of_truth: false  # proposed candidate — tested code + contracts remain reality; execution only after explicit founder approval per Gate 2; single-plan execution discipline অনুসারে অনুমোদনের পর এটিই হবে একমাত্র active plan
last_verified: "2026-09-17 (fresh main 17a8ef41 code-read: PLAN-002 implementation commits 2fbe7fcd + 65a1f1f6 এবং completion commit fb2ce032 পরবর্তী state; _compact_history L449–497 sed-verified, WS loop receive L559 / content_to_send L570+575 / auto-guard L580 / user append L582 / assistant guard L611 / [DONE] L615; prompt_handler COMPACTION_* L80–115 sed-verified; frontend [DONE] contract useChat.ts L92, chatService.ts L72 grep-verified; grep-verified: websocket_agent.py-তে কোনো slash-command handling নেই — এই প্ল্যানের subject সম্পূর্ণ unclaimed); re-verified 2026-09-17 on main 68cf886c — websocket_agent.py ও prompt_handler.py 2fbe7fcd-এর পর থেকে 0-diff (সব core citation অপরিবর্তিত: _compact_history L449–497, receive L559, payload parse L562–575, auto-guard L580, user append L582, assistant guard L611, [DONE] L615, COMPACTION_* L80–115); founder commit 1dea1fe2 (CI unblock) test_websocket_compaction.py-এ শুধু formatting change করেছে (StubGateway __init__ reformat + ১টি assert line-join — semantically identical, ১১টি টেস্ট অক্ষত, grep-verified); frontend [DONE] contract (useChat.ts L92, chatService.ts L72) 0-diff; সংশোধন (honesty fix): depends_on-এ deque(maxlen=50)-এর citation L554 ভুল ছিল — সঠিক লাইন L548, এবং WS chat loop রেঞ্জ L555–616 → L557–616 (while True L557) — উভয়ই এই commit-এই সংশোধিত); final-state re-verification 2026-09-17 on main 5bdda2e2 (rebase target — evidence 0-diff, transitivity note তখন শুধু commit message-এ ছিল) এবং main 71b55f8a (docs-only commit — evidence files 0-diff): deque(maxlen=50) L548, _compact_history L449, COMPACTION_SUMMARY_CHAR_CAP=1400 L91, ১১টি টেস্ট পুনঃgrep-verified — এই প্লান ফাইল নিজেই এখন তার পূর্ণ verification state বহন করছে (plan_registry নয়, commit message নয়); line-shift re-verification 2026-09-19 on fresh main f53464ed — founder commit d0f314c4 (M03 P0-পূর্ণাংশ: ১৩ serving route-এ বাধ্যতামূলক InferenceContext) websocket_agent.py-তে ১টি import + ২টি context-block যোগ করেছে (+১৫ লাইন, 647→662; _compact_history-র semantics অপরিবর্তিত); সমস্ত anchor পুনঃsed-verified: def _compact_history L457 (ফাংশন region L457–517, পরবর্তী def websocket_chat_endpoint L518), deque(maxlen=50) L556, WS loop while True L565 (loop L565–631), receive_text L567, payload parse/content_to_send L570–583 (content_to_send L578+583), auto-guard if L588/call L589, user append L590, assistant guard if L626/call L627, assistant append L628, [DONE] L630; honesty correction: মূল ভেরিফিকেশনের '_compact_history L449–497' region citation প্রকৃতে happy-path block-ই ছিল — আসল ফাংশন region 17a8ef41-এও ছিল L449–509 (graceful-degradation except ব্লকসহ, পরবর্তী def L510) — ফাইল 17a8ef41 থেকে 0fcd0f4f পর্যন্ত 0-diff (git log-এ শূন্য কমিট) তাই এটি drift নয়, মূল ট্রান্সক্রিপশন-ত্রুটি — এই commit-এই সংশোধিত; prompt_handler.py / test_websocket_compaction.py / useChat.ts / chatService.ts এই range-এ 0-diff (তাদের citation অপরিবর্তিত)"
code_evidence:
  - backend/api/routes/websocket_agent.py L457–517 — implemented _compact_history(chat_history, llm_gateway_ref, session_ref): deque-এর পুরনো অর্ধেক summarize করে compacted_context ব্লক appendleft করে; graceful fallback সহ; কিন্তু এটি শুধুমাত্র L588 ও L626-এ len==maxlen হলে auto-call হয় — ইউজারের কোনো manual নিয়ন্ত্রণ নেই
  - backend/api/routes/websocket_agent.py L567–590 — WS loop-এর ইনটেক পয়েন্ট: receive_text (L567) → JSON payload parse (L570–583, content_to_send) → auto-compaction guard (L588) → user append (L590); /compact interception-এর জন্য স্বাভাবিক পয়েন্ট content_to_send-এর ঠিক পরে, auto-guard-এর আগে
  - backend/core/prompt_handler.py L96–113 — build_compaction_messages(evicted, prior): pure function, বর্তমানে ২-আর্গুমেন্ট; user-instructions সাপোর্টের জন্য backward-compatible optional তৃতীয় প্যারামিটার যোগ করা সম্ভব (বিদ্যমান ১১টি টেস্ট ২-আর্গ কলেই থাকবে)
  - backend/core/prompt_handler.py L80–93 — COMPACTION_SYSTEM_PROMPT / COMPACTION_SUMMARY_CHAR_CAP=1400 / COMPACTION_BLOCK_LABEL — implemented constants, পুনঃব্যবহৃত হবে
  - backend/tests/api/test_websocket_compaction.py L29–182 — StubGateway pattern + ১১টি টেস্ট (success/fallback/cap/bounded); নতুন টেস্ট এই ফাইলেই একই প্যাটার্নে যাবে
  - frontend/src/hooks/useChat.ts L92 + frontend/src/services/chatService.ts L72 — `if (!payload || payload === '[DONE]') return;` — stream-termination contract; /compact ack-ও একই প্যাটার্নে টেক্সট + [DONE] পাঠালে কোনো frontend change ছাড়াই সব ক্লায়েন্টে কাজ করবে
  - implementation_plan.md §13 register — PLAN_002-এর row এখনও "proposed" দেখাচ্ছে (stale); এই প্ল্যানের docs commit-এ founder-verified reality অনুযায়ী "complete (implemented 2fbe7fcd, closed fb2ce032)" হিসেবে annotate করা হবে — reconciliation rule 11
test_evidence: "none yet — implementation PR must deliver (একই ফাইলে) backend/tests/api/test_websocket_compaction.py-এ নতুন টেস্ট-ক্লাস: (১) /compact interception ইউজার টার্নে LLM call স্কিপ করে ack পাঠায়, (২) <4-message threshold-এ সৎ 'not enough history' ack (summarizer call নয়), (৩) /compact <instructions> → build_compaction_messages-এ optional param যায়, (৪) summarizer fail → honest failure ack + history অপরিবর্তিত, (৫) বিদ্যমান ১১ টেস্ট zero regression"
acceptance_criteria:
  - "pytest backend/tests/api/test_websocket_compaction.py → বিদ্যমান ১১ + নতুন ≥৫ assertion সব PASS"
  - "backend/tests/api/test_websocket_agent.py → zero regression (42/42)"
  - "live WS সেশন: ১০+ টার্ন পরে /compact পাঠালে ack আসে, পরবর্তী টার্নে টার্ন-১ তথ্য compacted summary থেকে recall হয়, এবং একই টার্নে দ্বিতীয় LLM response না-ও আসতে পারে (command turn = ack-only)"
  - "forced summarizer failure: /compact সৎ failure ack দেয়, history অপরিবর্তিত, WS লুপ বাঁচে"
  - "pyproject.toml diff = শূন্য; frontend diff = শূন্য; নতুন কোনো route/infra/deps নেই"
test_evidence_note: "mocked-gateway টেস্ট contract behavior প্রমাণ করে (Gate 4); Gate 5-এ live WS সেশন ইভিডেন্স (recall + ack + loop survival) বাধ্যতামূলক — completion claim-এর আগে"
risk_and_rollback:
  - "সিঙ্গেল-কমিট, additive change: _compact_history-এর সিগনেচার অপরিবর্তিত (শুধু caller নতুন); auto-compaction path হুবহু আজকের মতো"
  - "build_compaction_messages-এ optional param default None — বিদ্যমান ২-আর্গ কল সাইট ও ১১ টেস্ট অপরিবর্তিত"
  - "Rollback = একক implementation commit-এর git revert; কোনো DB/config/ডেটা/frontend পরিবর্তন নেই"
  - "Runtime kill-switch অপ্রয়োজনীয়: কমান্ডটি ইউজার-initiated, সার্ভার-সাইড কোনো background behavior পরিবর্তন করে না"
baseline: "(hypothesis — implementation PR-এ মাপা হবে) আজ: ইউজারের কোনো compaction নিয়ন্ত্রণ নেই — ৫০-মেসেজ deque পূর্ণ হলেই auto-compaction; ইউজার long session-এ 'পুরনো কথা ভুলে যাওয়া' বা 'context ভারী হয়ে যাওয়া' বুঝলেও সেটা নিয়ন্ত্রণ করার কোনো উপায় নেই; auto-compaction ঘটলেও ইউজার কিছু জানে না (শুধু server log)"
measurement_method:
  - "(a) টেস্ট-স্যুট কাউন্ট — নতুন টেস্ট পাস + বিদ্যমান regression শূন্য (Gate 4)"
  - "(b) live WS স্মোক — /compact ack লেটেন্সি (summarizer round-trip), ack-এর পর হিস্ট্রি সাইজ ≤ maxlen//2+1, পরবর্তী recall সঠিক (Gate 5)"
  - "(c) গেটওয়ে টেলিমেট্রি — task_type='summarization' কল শুধু /compact বা auto-guard-এই হয় কি না (কোনো অন্য path leak নেই)"
success_threshold: "নতুন সব টেস্ট পাস + live সেশনে /compact-এর পর turn-1 fact recall সফল + summarizer-fail দৃশ্যে সৎ ack — উভয়ই acceptance threshold, hypothesis যতক্ষণ না Gate 5-এ measured হয়"
plan_lifecycle: "living — proposed candidate under strengthened PLAN_LIFECYCLE_POLICY (2026-09-17, target_scope taxonomy সহ). ফাউন্ডার অনুমোদন করলে এটিই একমাত্র active execution plan হবে; PLAN_003/PLAN_004 এই প্ল্যানের সম্পূরক প্রার্থী — কোনোটিই অনুমোদন-পূর্বে executable নয়"

---

# Head of Planning — Plan #005: Claude Code-Style User-Controlled `/compact` Trigger

> **Language:** বাংলা + প্রয়োজনীয় English Identifiers
> **Created:** 2026-09-17 | **Fresh main:** 17a8ef41
> **Owner Circle:** Memory Circle + C5 (Execution — LLM Gateway)
> **ভিত্তি:** PLAN-002 সম্পূর্ণ implemented (2fbe7fcd) ও founder-verified complete (fb2ce032) — এই প্ল্যান সেই মেশিনারির উপর দাঁড়ায়, নতুন কিছু আবিষ্কার করে না

---

## Part 0 — প্রতিযোগী ইন্টেলিজেন্স (Sources & Dates)

| উৎস | তারিখ | শেখা প্যাটার্ন |
|---|---|---|
| [platform.claude.com — Compaction docs](https://platform.claude.com) | verified 2026-09-17 | Compaction effective context length বাড়ায় — পুরনো context স্বয়ংক্রিয়ভাবে summarize হয় |
| [academy.claude.com](https://academy.claude.com) | verified 2026-09-17 | **"You can run compaction manually with the /compact command. This compacts everything up to that point. It's handy when you want to free up context space"** — ম্যানুয়াল ট্রিগার একটি প্রথম-শ্রেণির UX ক্ষমতা, auto-trigger-এর পরিপূরক |
| [hidekazu-konishi.com](https://hidekazu-konishi.com) | 2026-06-14 | §3.3 Manual compaction: "/compact — আপনাকে automatic trigger-এর জন্য অপেক্ষা করতে হয় না" |
| [github.com (claude-code issue)](https://github.com) | 2026-02-04 | `/compact <instructions>` সাথে সাথে কার্যকর হয় — instructions-সহ compaction সম্ভব |
| [claudefa.st](https://claudefa.st) | verified 2026-09-17 | `/context` transparency — টোকেন কোথায় যাচ্ছে তা ইউজার দেখতে পায় (আমাদের এই প্ল্যানের out-of-scope, ভবিষ্যৎ seed) |

**মূল শিক্ষা:** Claude Code-এ auto-compaction এবং user-controlled `/compact` **পাশাপাশি** থাকে — দুটোই দরকার। SupremeAI-তে প্রথমটা (PLAN-002) এখন implemented; দ্বিতীয়টাই এই প্ল্যান।

---

## Part 1 — Gate 0: কি আছে / কি নাই (code-verified, fresh main 17a8ef41)

### ১.১ কি আছে (সব ব্যবহারযোগ্য, implemented)

1. **পূর্ণাঙ্গ semantic compaction মেশিনারি** — `_compact_history()` (websocket_agent.py L457–517): পুরনো অর্ধেক summarize → `compacted_context` ব্লক → history-র শুরুতে; prior-summary merge; 1400-char defensive cap; graceful fallback। Founder-approved PLAN-002-এর সরাসরি ফল।
2. **Pure helpers** — `build_compaction_messages()` (prompt_handler.py L96), `estimate_messages_tokens()` (L115), `COMPACTION_*` constants (L80–93) — সব testable, সব পুনঃব্যবহারযোগ্য।
3. **টেস্ট অবকাঠামো** — backend/tests/api/test_websocket_compaction.py: StubGateway pattern (L29) + ১১টি টেস্ট; implementation PR থেকেই প্রতিষ্ঠিত।
4. **নিরাপদ ইনটেক পয়েন্ট** — WS loop L567–590: payload parse-এর পরে, auto-guard-এর (L588) আগে একটি পরিষ্কার interception পয়েন্ট আছে।
5. **প্রতিষ্ঠিত ক্লায়েন্ট প্রোটোকল** — টেক্সট চাংক + `[DONE]` (useChat.ts L92, chatService.ts L72) — নতুন কোনো ইভেন্ট-টাইপ ছাড়াই ack পাঠানো সম্ভব।
6. **Zero-cost summarizer route** — `task_type="summarization"` ইতিমধ্যে gateway-তে routed (PLAN-002 থেকেই)।

### ১.২ কি নাই (grep-verified, fresh main)

1. **ইউজার-নিয়ন্ত্রিত trigger** — websocket_agent.py-তে কোনো slash-command/`/compact`/manual trigger নেই; compaction শুধু len==maxlen হলে auto (L588, L626)।
2. **Compaction-এর ইউজার-দৃশ্যমানতা** — auto-compaction শুধু `logger.warning` (L489) — ইউজার জানেই না তার হিস্ট্রি collapse হয়েছে।
3. **Instructions-সহ compaction** — `build_compaction_messages`-এ user-instructions প্যারামিটার নেই।
4. **Threshold guard** — হাতে-গড়া সেশনে (১–৩ মেসেজ) compaction চালানোর কোনো সুরক্ষা/প্রত্যাখ্যান পথ নেই (দরকার হবে manual trigger-এ)।

---

## Part 2 — কি করতে হবে (design)

**এক বাক্যে:** WS chat loop-এ `/compact` (ঐ optional `/compact <instructions>`) কমান্ড intercept করে বিদ্যমান `_compact_history()` on-demand চালানো এবং সৎ, দৃশ্যমান acknowledgment পাঠানো — কোনো frontend change, নতুন dependency, বা infra ছাড়াই।

### ২.১ কমান্ড চুক্তি (protocol)

```text
ইনপুট (user turn):  "/compact"                    → পুরো হিস্ট্রি collapse
                    "/compact শুধু কোড-সিদ্ধান্তগুলো রাখো"  → instructions-সহ collapse
আউটপুট (WS টেক্সট): "✅ Compacted N messages into summary (instructions applied)." → "[DONE]"
                    "ℹ️ Not enough history to compact (N messages)."                → "[DONE]"
                    "⚠️ Compaction failed (reason); history unchanged."             → "[DONE]"
```

- ack পাঠানোর পর সেই turn-এ **LLM chat call হয় না** (কমান্ড টার্ন = ack-only) — Claude Code একই কাজ করে।
- `[DONE]` ব্যবহার বাধ্যতামূলক — বিদ্যমান ক্লায়েন্ট প্রোটোকল (Part 1 §১.১ আইটেম ৫) অক্ষুণ্ণ থাকে।

### ২.২ থ্রেশহোল্ড গার্ড (hypothesis, acceptance threshold নিচে)

`len(chat_history) < 4` হলে summarizer call **না করে** সৎ "not enough history" ack — বৃথা LLM খরচ ও অর্থহীন summary দুটোই এড়ানো যায় (Constitution #14)। থ্রেশহোল্ড একটি named constant — `MIN_MESSAGES_FOR_COMPACT = 4` (prompt_handler.py, অন্যান্য COMPACTION_* এর পাশে)।

### ২.৩ Instructions চ্যানেল

`build_compaction_messages(evicted, prior, user_instructions=None)` — optional তৃতীয় প্যারামিটার; থাকলে summarizer প্রম্পটে "ব্যবহারকারীর নির্দেশ: ..." ব্লক হিসেবে যোগ হয় (COMPACTION_SYSTEM_PROMPT-এর অধীনে, cap অপরিবর্তিত)। Backward-compatible: বিদ্যমান সব কল-সাইট ২-আর্গেই।

### ২.৪ সীমাবদ্ধতা (স্বচ্ছতা)

- Manual trigger **একই** `_compact_history()` ব্যবহার করে — auto path-এর মতোই prior-summary merge ও cap; দুই পথে আচরণ-বৈষম্য নেই।
- Auto-compaction-এর UI-দৃশ্যমানতা (Claude-র `/context`-জাতীয়) এই প্ল্যানের **out-of-scope** — frontend event contract প্রয়োজন, ভবিষ্যৎ seed।

---

## Part 3 — কিভাবে করব (implementation steps, ক্রমানুসারে)

### Step 1 — prompt_handler.py: optional instructions param (pure, সবচেয়ে ছোট)

```python
# backend/core/prompt_handler.py
MIN_MESSAGES_FOR_COMPACT = 4  # COMPACTION_* constants-এর পাশে (L93-এর পর)

def build_compaction_messages(
    evicted_messages, prior_summary, user_instructions: str | None = None
):
    # বিদ্যমান বডি অপরিবর্তিত; শেষে একটি ঐচ্ছিক ব্লক:
    # user_instructions থাকলে "ব্যবহারকারীর নির্দেশ: {user_instructions}"
    # লাইনটি সামারাইজার প্রম্পটে যোগ হবে (ক্যাপ অপরিবর্তিত)।
```

### Step 2 — websocket_agent.py: ইনটেক পয়েন্টে interception (L583-এর পরে, L588-এর আগে)

```python
# /compact কমান্ড (Claude Code প্যাটার্ন) — user-initiated compaction
if content_to_send.startswith("/compact"):
    user_instructions = content_to_send[len("/compact"):].strip() or None
    if len(chat_history) < MIN_MESSAGES_FOR_COMPACT:
        await websocket.send_text(
            f"ℹ️ Not enough history to compact ({len(chat_history)} messages).")
    else:
        try:
            await _compact_history(chat_history, llm_gateway,
                                   execution.execution_id, user_instructions)
            await websocket.send_text(
                "✅ Context compacted — older messages summarized; you can continue.")
        except Exception as exc:
            # _compact_history নিজেই fallback করে; এটি extra স্বচ্ছতা স্তর
            await websocket.send_text(
                f"⚠️ Compaction failed ({type(exc).__name__}); history unchanged.")
    await websocket.send_text("[DONE]")
    continue  # কমান্ড টার্ন = ack-only; LLM chat call নয়
```

- `_compact_history`-এর সিগনেচারে একটি optional ৪র্থ প্যারাম `user_instructions=None` যোগ হবে এবং `build_compaction_messages(evicted, prior, user_instructions)`-এ যাবে — auto-call সাইট (L588, L626) অপরিবর্তিত।
- নোট: বর্তমান `_compact_history` fail-এ exception ছোড়ে না (ভেতরে fallback) — তাই উপরের except শাখা একটি defensive স্তর; success-ack নিশ্চিত করতে implementation-এ `_compact_history`-এর summary-fallback পথ থেকে বুলিয়ান রিটার্ন (`bool`) যোগ করা হবে (True = summary block গঠিত; False = dumb eviction হয়েছে) — তখন ack সৎভাবে দুই রকম হবে: "✅ compacted" বা "⚠️ compaction failed, older messages evicted (honest fallback)"। **এটি এই প্ল্যানের একমাত্র বিদ্যমান-কোড টাচ** — রিটার্ন-টাইপ সংযোজন, আচরণ অপরিবর্তিত, বিদ্যমান ১১ টেস্টে নতুন assert যোগ হবে।

### Step 3 — টেস্ট (একই ফাইল, একই প্যাটার্ন)

backend/tests/api/test_websocket_compaction.py-এ নতুন টেস্ট-ক্লাস (StubGateway পুনঃব্যবহার):

1. `test_compact_command_skips_llm_chat_and_acks` — /compact টার্নে gateway-তে chat call নেই, summarization call আছে, ack + [DONE] আছে
2. `test_compact_command_below_threshold_is_honest_no_llm` — ৩ মেসেজে summarizer call নেই
3. `test_compact_command_with_instructions_reaches_prompt` — instructions প্রম্পটে যায়
4. `test_compact_command_failure_ack_is_honest_history_intact` — summarizer fail → honest evicted-ack, history bounded
5. `test_build_compaction_messages_instructions_optional_backcompat` — ২-আর্গ কল আগের মতোই (বিদ্যমান টেস্টও এটাই প্রমাণ করে)

---

## Part 4 — বেনিফিট

1. **ইউজার-নিয়ন্ত্রণ (Claude Code parity)** — long session-এ ইউজার নিজের মুহূর্তে context মুক্ত করতে পারে; auto-trigger-এর ২৫-টার্ন অপেক্ষা বাধ্যতামূলক নয়। (Constitution #4)
2. **সাইলেন্স ভাঙা (Constitution #13)** — compaction এখন ইউজারের চোখে দেখা যায়; "কী হলো, কেন হলো, কি হয়নি" তিনটাই সৎ ack-তে।
3. **খরচ-নিয়ন্ত্রণ (Constitution #14)** — থ্রেশহোল্ড গার্ড বৃথা summarizer call আটকায়; instructions-সহ compaction ইউজারকে summary-র ঘনত্ব নিয়ন্ত্রণ দেয় (একই টোকেনে বেশি কাজের তথ্য)।
4. **শূন্য নতুন পৃষ্ঠ** — কোনো নতুন route/deps/infra/frontend নেই; একটি implemented ফাংশনের দ্বিতীয় caller মাত্র। Gate 0-তে প্রতিটি দাবি line-verified।
5. **সম্পূরক প্রার্থীদের সাথে দ্বন্দ্বহীন** — PLAN_003 (repo map, ভিন্ন subsystem) ও PLAN_004 (persistent memory distillation, ভিন্ন write path) — কোনো overlap নেই; §13 register-এ প্রত্যেকের সম্পূরকতা ঘোষিত।

---

## Part 5 — ক্ষতি-রিস্ক ও প্রশমন

| রিস্ক | সম্ভাবনা | প্রশমন |
|---|---|---|
| `_compact_history`-এ রিটার্ন-টাইপ যোগ → বিদ্যমান টেস্ট ভাঙা | কম (additive) | ১১ টেস্ট রান করে assert যোগ; behavior অপরিবর্তিত — Gate 4-এ প্রমাণ |
| `/compact` স্ট্রিং সাধারণ প্রশ্নে ভুল ম্যাচ (যেমন "how to /compact?") | মাঝারি | হুবহু prefix match (`startswith("/compact")`) — প্রশ্নবোধক বাক্য সাধারণত এই prefix দিয়ে শুরু হয় না; মিথ্যা ট্রিগার হলেও ক্ষতি ন্যূনতম (একটি compaction হয়, কোনো ডেটা-ক্ষতি নেই) |
| ack টেক্সট ইউজার-ভাষা না মেলা | কম | v1 English সিস্টেম-মেসেজ কনভেনশন (বিদ্যমান [DONE]-জাতীয়); ভবিষ্যতে preference-aware |
| Instructions-এ prompt-injection | কম | instructions শুধু summarizer-এর user-block-এ যায়; system prompt অপরিবর্তিত; 1400-cap summary-তেও প্রযোজ্য |
| কমান্ড টার্নে [DONE] না পাঠালে ক্লায়েন্ট hang | সম্ভাব্য যদি ভুল হয় | টেস্ট ১-এ [DONE] assert করা বাধ্যতামূলক; প্রোটোকল Part 1 §১.১ আইটেম ৫-এ verified |

---

## Part 6 — Explicit Out-of-Scope

1. **`/map` বা যেকোনো repo-map কমান্ড** — PLAN_003 এখনও proposed; তার CodeIndexer না হলে /map-এর ভিত্তি নেই। ভবিষ্যৎ seed (নিচে)।
2. **Auto-compaction-এর UI ইভেন্ট/ইন্ডিকেটর** — frontend event contract প্রয়োজন; আলাদা প্ল্যান প্রাপ্য।
3. **`/context`-জাতীয় টোকেন-ব্রেকডাউন কমান্ড** — Claude-র /context transparency; ContextEngine (M2) টেলিমেট্রির সাথে সংযোগ প্রয়োজন — ভবিষ্যৎ।
4. **Frontend slash-command মেনু/autocomplete** — এই প্ল্যান backend-only; frontend পরে।
5. **`estimate_messages_tokens`-ভিত্তিক auto-threshold** — আজ maxlen কাউন্ট-ভিত্তিক; টোকেন-ভিত্তিক হওয়া পৃথক সিদ্ধান্ত।

---

## Roadmap Seeds (scouting-only — candidate list is not an execution queue)

- **#006 (candidate):** Repo-map MCP টুল — PLAN_003 সম্পূর্ণ হলে `render_repo_map()`-কে MCP tool হিসেবে expose (Aider/Cursor parity) — **depends_on PLAN_003**।
- **#007 (candidate):** `/context` transparency — M2 ContextEngine-এর BudgetReport ব্যবহার করে ইউজারকে token breakdown (claudefa.st প্যাটার্ন)।
- **#008 (candidate):** Auto-compaction UI ইভেন্ট — WS JSON notice `{"type":"system_notice","event":"compaction"}` + ফ্রন্টএন্ড ব্যাজ।

> **প্রকাশনা শৃঙ্খলা:** ফাউন্ডারের 2026-09-16 সরাসরি নির্দেশনায় প্ল্যানিং ডিপার্টমেন্ট `docs/plans/`-এ ধারাবাহিক প্ল্যান প্রকাশ করছে (direct-push, PR-মোড বন্ধ)। প্রতিটি প্ল্যান `status: proposed` — কোনো ইঞ্জিনিয়ারিং বাস্তবায়ন ফাউন্ডার অনুমোদন ছাড়া শুরু হবে না (Constitution #6 Policy Before Power)।
