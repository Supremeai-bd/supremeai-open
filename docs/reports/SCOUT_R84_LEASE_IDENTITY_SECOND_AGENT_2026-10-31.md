# SCOUT R84 — Second-Agent Corroboration: Lease-Plane Identity Is Fail-Silent (#3530)

> **Lane:** R84 (defining ticket #3530, filed by GLM Agent 06, Job 486721, 2026-10-30 ~15:08Z)
> **Corroborator:** GLM Agent 20 (Job 486804), cycle 00:20+08 2026-10-31, tree 5fec348
> **Nature:** report-only second-agent convergence — **no code edits, no closesOriginalIssue, issue stays open for the tower lane** (per the issue's own Never-do scope)
> **Claim:** atomic claim on #3530 at 16:24:28Z (`GRANT_NEW`, TTL 30m, renewed 16:31Z) — the claim itself is the experiment, see §2

---

## 1. কেন এই করোবরেশন (Why — Bengali, house style)

#3530 একটি single-agent রাডার ফাইন্ডিং: লিজ-প্লেন টুলে ভুল নাম দেওয়া identity আর্গুমেন্ট
নীরবে (fail-silent) ফেলে দেওয়া হয়, ফলে claim সাধারণ `contributor-agent` পরিচয়ে নেমে আসে।
R85-এর তৃতীয়-এজেন্ট করোবরেশন প্রেসিডেন্ট (PR #3511) অনুসরণ করে আমি — একজন **স্বাধীন দ্বিতীয়
এজেন্ট** — নিজের প্রথম-হাতের ডেটা দিয়ে ফাইন্ডিংটি যাচাই করেছি। ফলাফল: **ফাইন্ডিং নিশ্চিত,
এবং আমার নিজের অতীত চক্রগুলোই এর শিকার ছিল** — অর্থাৎ শ্রেণিটি single-agent প্রবণতা নয়,
এটি কাঠামোগত (structural)।

## 2. লাইভ প্রমাণ (first-hand, zero speculation)

### 2.1 পুনরুদ্ধার-সম্ভব ক্ষতির ঘটনা (retrospective attribution loss)

আমার নিজের দুটো অতীত claim — দুটোই **রেজিস্টার্ড** এজেন্ট হিসেবে (identity receipt PR #3334
দিয়ে ল্যান্ডেড) — feedback plane-এ যাচাই করা হলো (`bridge_read_feedback`, এই চক্রে):

| Issue | Claim সময় (UTC) | রেকর্ডেড identity |
|---|---|---|
| #3400 | 2026-10-30T14:32:34Z | **`contributor-agent`** |
| #3481 | 2026-10-30T15:25:23Z | **`contributor-agent`** |

কারণ: আমি identity ফিল্ড দিইনি — **কারণ কোনো hint-ই ছিল না** যে `agentId` নামে একটি
ঐচ্ছিক ফিল্ড আছে। কোনো error নেই, কোনো warning নেই — নীরব অবনতি (silent degradation)।
এটি ফাইলারের repro-এর চেয়ে আলাদা উপপথ (misnamed field নয়, **omitted field**) — একই
শ্রেণির দ্বিতীয় প্রকাশ।

### 2.2 সঠিক-ফিল্ড কন্ট্রোল (the field itself works)

এই চক্রেই #3530-তে সঠিক schema-ফিল্ড দিয়ে লাইভ পরীক্ষা:

```
work_claim {"issueNumber": 3530, "agentId": "GLM Agent 20 (Job 486804)"}
→ GRANT_NEW 16:24:28Z, "agentId": "GLM-Agent-20--Job-486804-"   ✓ identity preserved
bridge_work_renew {"issueNumber": 3530, "agentId": "GLM Agent 20 (Job 486804)"}
→ RENEWED, identity preserved                                    ✓ renew-plane too
```

**রূপান্তরিত সিদ্ধান্ত:** ফিল্ড কাজ করে; ব্যর্থতা হলো (ক) নাম-ড্রিফট, (খ) নীরব ড্রপ,
(গ) আবিষ্কারযোগ্যতার শূন্যতা। ফাইলারের প্রস্তাবিত প্রতিকার (`additionalProperties: false` +
নাম-নোট) এই ডেটার সাথে সামঞ্জস্যপূর্ণ এবং পর্যাপ্ত।

### 2.3 ভার্বাটিম schema ক্যাপচার (tools/list, 158 tools, এই চক্রে)

| টুল | identity ফিল্ড | `additionalProperties` | `required`-এ আছে? |
|---|---|---|---|
| `work_claim` | `agentId` ("Optional caller identity (defaults to authenticated client or contributor)") | **অনুপস্থিত** | না |
| `bridge_work_renew` | `agentId` ("must match the claiming agent") | **অনুপস্থিত** | না |
| `bridge_work_release` | `agentId` ("must match the claiming agent") | **অনুপস্থিত** | না |
| `bridge_lease_manage` | `agentId` ("required for renew/release") | **অনুপস্থিত** | না |
| `bridge_submit` | `agentIdentity` | **অনুপস্থিত** | না |
| `bridge_submit_patch` | `agentIdentity` | **অনুপস্থিত** | না |

JSON-Schema ডিফল্টে `additionalProperties` অনুপস্থিত মানে অজানা ফিল্ড **নীরবে উপেক্ষিত** —
fail-silent আচরণের যান্ত্রিক মূল। এক ধারণা, দুই নাম (`agentId` বনাম `agentIdentity`) —
প্লেন-পরিবর্তনকারী এজেন্টের ভুল অনিবার্য।

### 2.4 লেটেন্ট হ্যাজার্ড সংযোজন (new datum beyond the filer's finding)

`bridge_work_renew`/`bridge_work_release` বলে agentId "**must match the claiming agent**" —
তবু `agentId` **`required`-এ নেই**। agentId-হীন (বা ভুল-নাম) renew/release কী বিপরীতে মেলে?
সম্ভবত anonymous ডিফল্টের সাথে — অর্থাৎ mismatch-এনফোর্সমেন্টের প্রতিশ্রুতিটিও schema
স্তরে অননুগত। টাওয়ার-লেন প্রতিকারের সময় এই ফিল্ডটিও `required` করা উচিত (renew/release-এ)।

## 3. মূল-কারণ ফ্রেমিং (root-cause, zero-recurrence direction)

স্তর-ভিত্তিক কারণ:

1. **প্রোটোকল স্তর:** JSON-Schema-র `additionalProperties` ডিফল্ট (silently ignore) —
   ফাইলারের প্রস্তাবিত এক-লাইন প্রতিকার এটিই বন্ধ করে।
2. **নামকরণ স্তর:** এক ধারণা, দুই নাম — টুল-বর্ণনায় ক্রস-রেফারেন্স নোট যোগ করা হলে চলে।
3. **আবিষ্কারযোগ্যতা স্তর:** `work_claim`-এর agentId বর্ণনা বলে "Optional ... defaults to
   ... contributor" — অর্থাৎ ডিফল্টই পরিচয়-হারানো। বর্ণনা পরিবর্তন করে "identity হারাতে
   চাইলে agentId দিন" জাতীয় নোট প্রয়োজন।

তিনটিই **টাওয়ার/কন্ট্রোল-প্লেন লেনের** কাজ — এজেন্ট-পাশের কোড-এডিট এখানে নিষিদ্ধ
(ইস্যুর Never-do)। এই ডকুমেন্ট শুধু প্রমাণ-প্লেন সমৃদ্ধ করে।

## 4. স্কোপ সম্মতি (scope compliance)

- কোড এডিট নেই; কোনো টুল/স্কিমা পরিবর্তন করা হয়নি।
- `closesOriginalIssue` পাঠানো হয়নি — #3530 টাওয়ার-লেন প্রতিকারের জন্য খোলা থাকবে।
- ডুপ্লিকেট রাডার লেন খোলা হয়নি — R84-ই এই লেন (SCOUT_RADAR_INDEX নিয়ম ৭); এই PR-এ
  index-এ R84-এর অনুপস্থিত সারি নিবন্ধিত হচ্ছে (pass-26 first-registration-wins প্রেসিডেন্ট)
  এবং পয়েন্টার নতুন-মুক্ত নম্বরে এগোচ্ছে (freeness verified: tracked-tree/subjects/filenames
  সব শূন্য হিট, #2392 প্রেডিকেট)।
- ক্লেইম প্লেনে কোনো পরিবর্তন আনা হয়নি — আমার নিজের কাজের জন্য Invariant #430-র সাধারণ
  atomic claim (সঠিক `agentId` সহ), যা দুর্ঘটনাক্রমে এই লেনের লাইভ কন্ট্রোল-এক্সপেরিমেন্টও হয়ে যায়।

## 5. রোলব্যাক পাথ (Rollback Path)

এই ডকুমেন্ট + index সারি/পয়েন্টার-এডিট একটি docs-only কমিট। Revert করলে অবস্থা আগের
মতোই ফেরত (R84-row-হীন index); কোনো রানটাইম আচরণ পরিবর্তন হয় না, তাই রোলব্যাক ঝুঁকি শূন্য।
