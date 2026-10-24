---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:codebase_gap_solution_unification_plan_bn
subject: সুপ্রিম এআই কোডবেস একত্রীকরণ পরিকল্পনা
document_role: audit
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# সুপ্রিম এআই কোডবেস একত্রীকরণ পরিকল্পনা
### গভীর ফাইল যাচাই (ডিপ ভেরিফিকেশন) সম্পন্ন — আপডেটেড সংস্করণ

---

## ভেরিফিকেশন-পরবর্তী গুরুত্বপূর্ণ আবিষ্কার (New Findings After File Verification)

> [!IMPORTANT]
> আগের প্ল্যানে বেশ কিছু ভুল ধারণা ছিল যা ফাইল যাচাইয়ের পর সংশোধন করা হয়েছে:

| পূর্ববর্তী ধারণা | ফাইল যাচাইয়ের পর বাস্তব চিত্র |
|---|---|
| ২০টি রুটই সরাসরি অরফান | **তিন শ্রেণীতে বিভক্ত** — ১৩টি নিরাপদ, ২টি ঝুঁকিপূর্ণ, ৫টি স্টাব/ব্রিজ |
| `workspace_feature_routes` অনিবন্ধিত | এটি `backend/core/app.py`-এ `register_workspace_feature_routes()` দিয়ে **আলাদা পথে সক্রিয়** আছে — `routers.py`-তে না থাকলেও চালু! |
| `dock_actions` একটি স্টাব | এটি আসলে `dock_integrations.py`-এর **কম্প্যাটিবিলিটি ব্রিজ** |
| `tier_s_routes` ও `workspace_feature_routes_shim` স্টাব | উভয়ই `workspace_feature_routes`-এর **ব্রিজ ফাইল** |
| সব ১৩টি Tier-S রুট অনিবন্ধিত | এগুলো `workspace_feature_routes.py ` এর `register_workspace_feature_routes()` ফাংশনের মাধ্যমে **app.py-তে একসাথে রেজিস্টার** হচ্ছে |
| `admin_auth` অসম্পূর্ণ রুট | এটি রুট নয়, `Depends()` হিসেবে ব্যবহৃত **সিকিউরিটি হেলপার মডিউল** |

---

## ব্যবহারকারীর পর্যালোচনা (User Review Required)

> [!IMPORTANT]
> **লকফাইল স্ট্যান্ডার্ডাইজেশন:** গিটহাব সিআই পাইপলাইন (`ci.yml`, `maintenance.yml`, `setup-backend`) সম্পূর্ণভাবে `poetry.lock` নির্ভর। তাই ব্যাকএন্ডে **Poetry** রাখা হবে, `uv.lock` অপসারণ করা হবে। মনোরিপোর জন্য **PNPM** বজায় থাকবে, `infrastructure/mcp-control-plane/package-lock.json` সরানো হবে।

> [!WARNING]
> **`workspace_feature_routes` দ্বৈত রেজিস্ট্রেশন ঝুঁকি:** এই মডিউলটি `core/app.py`-তে একটি function call-এর মাধ্যমে চালু আছে কিন্তু `routers.py`-এ নেই। এটি একটি **Governance Gap** — কারণ কোনো এন্ডপয়েন্ট `routers.py`-এর বাইরে দিয়ে যুক্ত হলে সেন্ট্রাল অডিট ও পলিসি বাইপাস হওয়ার সম্ভাবনা থাকে।

> [!CAUTION]
> **`healing_stats` ও `workspace_feature_routes`-এ অথেন্টিকেশন নেই:** এই দুটি রুটে কোনো `get_current_user` বা `Depends` গার্ড নেই, যা প্রোডাকশনে উন্মুক্ত এন্ডপয়েন্ট তৈরি করতে পারে।

---

## প্রস্তাবিত পরিবর্তন (Proposed Changes — Updated)

---

### ফেজ ১: লকফাইল একত্রীকরণ ও কনফ্লিক্ট দূরীকরণ

**লক্ষ্য:** চার প্যাকেজ ম্যানেজারকে দুটিতে নামিয়ে আনা (Python=Poetry, Node=PNPM)।

#### [DELETE] [`backend/uv.lock`](./backend/uv.lock)
- কারণ: সিআই workflow `poetry.lock` ব্যবহার করে, `uv.lock` conflict তৈরি করে।

#### [DELETE] [`infrastructure/mcp-control-plane/package-lock.json`](./infrastructure/mcp-control-plane/package-lock.json)
- কারণ: রুট `pnpm-lock.yaml` প্রজেক্টের একক নোড লকফাইল, npm-এর lockfile পাশে থাকলে ড্রিফট হয়।

---

### ফেজ ২: অরফান রুট — তিন ধাপে বিন্যাস

#### ২ক. নিরাপদ রুট — সরাসরি রেজিস্ট্রেশন (১৩টি)

এই ১৩টি রুটে APIRouter ও অথেন্টিকেশন গার্ড উভয়ই বিদ্যমান। **এগুলো সরাসরি [`routers.py`](./backend/api/routers.py)-এ যোগ করা যাবে:**

| রুট মডিউল | বিবরণ | লাইন |
|---|---|---|
| `artifacts` | আর্টিফ্যাক্ট ম্যানেজমেন্ট | ৪৫০ |
| `branch_conversations` | কথোপকথন ব্রাঞ্চিং | ৪১০ |
| `browser_action_registry` | ব্রাউজার অটোমেশন অ্যাকশন | ১৯৯ |
| `chat_export` | চ্যাট এক্সপোর্ট | ৩৫২ |
| `chat_search` | চ্যাট সার্চ | ২৪৪ |
| `chat_upload` | ফাইল আপলোড | ৩২৭ |
| `code_dependency_graph` | কোড ডিপেন্ডেন্সি অ্যানালিসিস | ৪০ |
| `deep_research` | ডিপ রিসার্চ ইঞ্জিন | ৬৯২ |
| `prompt_templates` | প্রম্পট টেমপ্লেট | ৬৫১ |
| `reasoning` | রিজনিং পাইপলাইন | ৩৪০ |
| `scheduled_tasks` | টাস্ক শিডিউলিং | ৬৩৩ |
| `share` | কন্টেন্ট শেয়ারিং | ৩৯৯ |
| `slash_commands` | স্ল্যাশ কমান্ড | ৬৫০ |

#### ২খ. ঝুঁকিপূর্ণ রুট — অথেন্টিকেশন যোগের পর রেজিস্ট্রেশন (২টি)

> [!CAUTION]
> এগুলোতে অথেন্টিকেশন নেই। রেজিস্টার করার আগে অথেন্টিকেশন গার্ড যোগ করতে হবে।

| রুট মডিউল | সমস্যা | সমাধান |
|---|---|---|
| `healing_stats` | কোনো `Depends` নেই, পাবলিক এন্ডপয়েন্ট | `get_current_user` Depends যোগ করা অথবা ইন্টার্নাল-অনলি ট্যাগ |
| `workspace_feature_routes` | `app.py`-তে আলাদা পথে সক্রিয়, `routers.py`-তে নেই | এই মডিউলকে `routers.py`-এর আওতায় এনে `core/app.py` থেকে সরাসরি কল সরিয়ে দেওয়া (Governance Fix) |

#### ২গ. স্টাব/ব্রিজ ফাইল — পুনঃশ্রেণীকরণ (৫টি)

এই ৫টি ফাইল কোনো স্বাধীন রুট নয়, বরং অন্য মডিউলের ব্রিজ বা হেলপার:

| ফাইল | বাস্তব প্রকৃতি | পদক্ষেপ |
|---|---|---|
| `admin_auth.py` | সিকিউরিটি হেলপার/ডিপেন্ডেন্সি মডিউল | রাউটার হিসেবে নিবন্ধন করতে হবে না — বর্তমান অবস্থা ঠিক আছে |
| `dock_actions.py` | `dock_integrations.py`-এর ব্রিজ | `dock_integrations`-কে মূল রুট হিসেবে চিহ্নিত করা |
| `tier_s_routes.py` | `workspace_feature_routes.py`-এর ব্রিজ | `workspace_feature_routes`-এ একীভূত করা |
| `workspace_feature_routes_shim.py` | একই মডিউলের আরেকটি ব্রিজ | অপসারণ বা `workspace_feature_routes`-এ একীভূত |
| `meta_ai.py` | মাত্র ৩০ লাইন, কোনো রাউটার/এন্ডপয়েন্ট নেই | কন্টেন্ট পরীক্ষা করে সম্পূর্ণ করা বা আর্কাইভ করা |

---

### ফেজ ৩: কম্প্যাটিবিলিটি ব্রিজ — গভীর যাচাইয়ের পর আপডেটেড মাইগ্রেশন পরিকল্পনা

ফাইল যাচাইয়ে দেখা গেছে ব্রিজ ফাইলগুলো পুরোপুরি ফাঁকা নয়, এগুলো **সক্রিয় রি-এক্সপোর্ট মডিউল**। টেস্ট রেফারেন্স সংখ্যাও যাচাই করা হয়েছে:

| ব্রিজ ফাইল (পুরনো নাম) | নতুন মডিউল | টেস্টে রেফারেন্স | অগ্রাধিকার |
|---|---|---|---|
| `churn_prophet.py` | `user_retention_risk_agent.py` | ১টি টেস্ট ফাইল | মাঝারি |
| `insight_mage.py` | `data_trend_anomaly_agent.py` | ২টি টেস্ট ফাইল | মাঝারি |
| `vulnerability_prophet.py` | `code_vulnerability_scanner_agent.py` | ২টি টেস্ট ফাইল | মাঝারি |
| `healing.py` (route) | `healing_stats.py` | **৪টি টেস্ট ফাইল** | **সর্বোচ্চ — আগে মাইগ্রেট করতে হবে** |
| `rider_tracker.py` | `delivery_fleet_tracker.py` | ১টি টেস্ট ফাইল | মাঝারি |
| `freebuff_client.py` | `cli_process_delegator.py` | ১টি টেস্ট ফাইল | মাঝারি |
| `cloud_watchman.py` | `multicloud_quota_monitor.py` | **০টি** | কম — দ্রুত সরানো যাবে |
| `cost_sage.py` | `llm_cost_optimizer.py` | **০টি** | কম — দ্রুত সরানো যাবে |
| `seed_database.py` | `scripts.db.seed_knowledge_fts` | **০টি** | কম — দ্রুত সরানো যাবে |
| `langchain_agent_example.py` | `launchdarkly_agent_adapter.py` | **০টি** | কম — দ্রুত সরানো যাবে |
| `codeflow.py` (route) | `code_dependency_graph.py` | **০টি** | কম — দ্রুত সরানো যাবে |
| `site_actions.py` (route) | `browser_action_registry.py` | **০টি** | কম — দ্রুত সরানো যাবে |

**বাস্তবায়নের ক্রম:**
1. **প্রথমে:** `healing.py` মাইগ্রেট করুন (৪টি টেস্ট ফাইল আপডেট করতে হবে)।
2. **দ্বিতীয়তে:** ০ রেফারেন্সের ৬টি ব্রিজ সরাসরি ডিলিট করুন।
3. **তৃতীয়তে:** `insight_mage`, `vulnerability_prophet`, `churn_prophet`, `rider_tracker`, `freebuff_client` — টেস্ট আপডেট করে সরান।

---

### ফেজ ৪: WebSocket বনাম SSE ট্রান্সপোর্ট স্থায়ী নীতি

ফাইল যাচাইয়ে দেখা গেছে তিনটি WebSocket রুট ফাইল **git-tracked কিন্তু `routers.py`-তে কমেন্ট আউট**, এবং তাদের SSE বিকল্প (`stream_chat_sse`, `stream_hitl_sse`) ইতিমধ্যে **সক্রিয়ভাবে রেজিস্টার্ড**:

**সিদ্ধান্ত নিতে হবে (একটি বেছে নিন):**

| বিকল্প | সুবিধা | অসুবিধা |
|---|---|---|
| **WebSocket চালু রাখা** | রিয়েল-টাইম বাইডিরেকশনাল কমিউনিকেশন | Render/Cloudflare ফ্রি টায়ারে WebSocket সীমাবদ্ধতা |
| **SSE-তে স্থায়ী মাইগ্রেশন** | ক্লাউড ফ্রি-টায়ার ফ্রেন্ডলি, কনস্টিটিউশনের সাথে সামঞ্জস্যপূর্ণ | ক্লায়েন্ট থেকে সার্ভারে ডেটা পাঠানো অতিরিক্ত HTTP কলে করতে হবে |

**সুপারিশ:** ক্লাউড-নেটিভ কনস্টিটিউশন মেনে SSE-কে প্রধান ট্রান্সপোর্ট রাখুন এবং WebSocket ফাইলগুলো ডকুমেন্টেড "Legacy/Experimental" হিসেবে আর্কাইভ করুন।

---

### ফেজ ৫: টপোলজি পুনর্নির্মাণ ও কনস্টিটিউশনাল ভেরিফিকেশন

#### [MODIFY] [`route_inventory.json`](./docs/generated/route_inventory.json)
#### [MODIFY] [`route_knowledge_graph.json`](./docs/generated/route_knowledge_graph.json)
- সব পরিবর্তনের পর অটো-স্ক্রিপ্ট চালিয়ে আপডেটেড টপোলজি ম্যাপ পুনরায় জেনারেট করা।

---

## কাজের অগ্রাধিকার ক্রম (Prioritized Execution Order)

```
ফেজ ১ (দ্রুততম): uv.lock ও package-lock.json ডিলিট → git push
      ↓
ফেজ ৩ক (সহজ): ০ রেফারেন্সের ৬টি ব্রিজ সরাসরি ডিলিট
      ↓
ফেজ ২ক: ১৩টি নিরাপদ অরফান রুট routers.py-তে যোগ
      ↓
ফেজ ২খ: healing_stats-এ auth guard যোগ → রেজিস্টার;
         workspace_feature_routes-কে routers.py-এ আনা
      ↓
ফেজ ৩খ: healing.py ও বাকি ব্রিজ মাইগ্রেশন (টেস্ট আপডেটসহ)
      ↓
ফেজ ৪: WebSocket/SSE নীতি চূড়ান্ত করা
      ↓
ফেজ ৫: টপোলজি রিজেনারেট → CI চালানো
```

---

## যাচাইকরণ পরিকল্পনা (Verification Plan)

### স্বয়ংক্রিয় টেস্ট
```powershell
# কনস্টিটিউশনাল গেট
python .github/scripts/constitution/runner.py

# রাউটার ইমপোর্ট ভ্যালিডেশন
python scripts/ci/validate_router_imports.py

# পূর্ণ টেস্ট স্যুট
pytest backend/tests/api/test_api_router.py backend/tests/agents/ -v
```

### ম্যানুয়াল যাচাই
- `git status` — কোনো অনাকাঙ্ক্ষিত লকফাইল নেই তা নিশ্চিত করা।
- FastAPI `/docs` — OpenAPI স্কিমায় নতুন ১৩টি এন্ডপয়েন্ট দেখা যাচ্ছে কি না।
- কোনো `ModuleNotFoundError` ছাড়াই ব্যাকএন্ড বুট হচ্ছে কি না।