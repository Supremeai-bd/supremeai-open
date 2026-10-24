---
id: supreme-teleport-multi-device-remote-control-tower-plan
subject: "Supreme Teleport: Multi-Device Remote Control Tower Plan — Control Your Multiple Devices & Local AI Agents from Far"
document_role: architecture
owner_circle: "Central Control Hub / MCP Circle"
planning_authority: "Planning Circle / Head of Planning (docs/plans/ প্ল্যানিং কর্পাসের সাথে reconciliation আবশ্যক)"
status: proposed
target_scope: combined_ecosystem
canonical: false
evidence_state: unverified
disposition: retain
last_verified: 2026-09-18
supersedes: []
superseded_by: []
source_of_truth: false
---

# 🌐 Supreme Teleport: Multi-Device Remote Control Tower Plan
### *"Control Your Multiple Devices & Local AI From Far"*

> **মূল দর্শন ও মার্কেটিং প্রতিপাদ্য:** *"Single Hub, Multi-Device Swarm, Bi-directional Command Flow."*  
> ব্যবহারকারী যখন বাইরে থাকবেন (রাস্তায়, ভ্রমণে বা বিছানায়), তিনি **Telegram**, **WhatsApp** বা **Web Dashboard** থেকে যেকোনো নির্দেশ পাঠাবেন। সেন্ট্রাল **Supreme Teleport Control Tower** তার সবকটি সক্রিয় ডিভাইস (হোম পিসি, অফিসের ল্যাপটপ, ক্লাউড নোড)-এর লাইভ স্ট্যাটাস উপস্থাপন করবে। নির্বাচিত ডিভাইসের লোকাল এআই (Antigravity, Cursor, Cline ইত্যাদি) কাজটি গ্রহণ করে এক্সিকিউট করবে এবং রিয়েল-টাইম ফলাফল ব্যবহারকারীর মোবাইলে পাঠিয়ে দেবে।

---

## ১. সমস্যা ও প্রয়োজনীয়তা (Context & Problem Statement)

### ১.১ প্রথাগত MCP আর্কিটেকচারের সীমাবদ্ধতা (1-Way Client ➔ Server)
প্রচলিত MCP (Model Context Protocol) ব্যবস্থায়:
1. **একমুখী যোগাযোগ:** লোকাল IDE (যেমন Antigravity বা Cursor) ক্লায়েন্ট হিসেবে MCP সার্ভারের সাথে যুক্ত হয় এবং সার্ভারের এক্সপোজ করা টুলস (`system_summary`, `render_deploy` ইত্যাদি) কল করে।
2. **সার্ভার ইনিশিয়েটিভের অভাব:** ক্লাউড সার্ভার নিজে থেকে কোনো লোকাল IDE-কে নতুন কোনো প্রম্পট বা কাজের নির্দেশ পাঠাতে পারে না, কারণ লোকাল পিসিগুলো সাধারণ ফায়ারওয়াল বা হোম রাউটারের পেছনে (Private IP/NAT) থাকে।
3. **রিমোট টেলি-অপারেশনের অভাব:** ব্যবহারকারী মোবাইল থেকে কাজ দিতে চাইলে ক্লাউড ব্যাকএন্ডের বাইরে লোকাল ফাইলের ওপর কাজ করানোর কোনো নিরাপদ সেতু নেই।

### ১.২ আমাদের কাঙ্ক্ষিত সমাধান (The 2-Way Bi-directional Model)
* **Downlink (Local ➔ Cloud):** লোকাল IDE সার্ভারের সাথে একটি দীর্ঘমেয়াদী আউটবাউন্ড চ্যানেল (WebSocket / SSE / Streamable HTTP) ধরে রাখবে।
* **Target-Aware Dispatch (Cloud ➔ Selected IDE):** টেলিগ্রাম বা ড্যাশবোর্ড থেকে প্রম্পট এলে MCP Control Tower টার্গেট এজেন্ট (`Antigravity`, `Cline`, বা `All`) সিলেক্ট করার সুযোগ দেবে।
* **Sampling / Task Push:** MCP প্রোটোকলের **`sampling/createMessage`** মেকানিজম বা **Task Event Stream** ব্যবহার করে সার্ভার নির্বাচিত লোকাল IDE-কে কাজ পুশ করবে।
* **Feedback Return:** লোকাল IDE কাজটি এক্সিকিউট করে টার্মিনাল ও টেস্ট আউটপুট MCP টাওয়ারের মাধ্যমে সরাসরি টেলিগ্রাম/ড্যাশবোর্ডে লাইভ ফেরত পাঠাবে।

---

## ২. সিস্টেম আর্কিটেকচার (Architecture Blueprint)

```text
 ┌─────────────────────────────────────────────────────────────┐
 │                ইনপুট চ্যানেল (User Interfaces)              │
 │  📱 Telegram Bot (/task)   │   💻 Web Dashboard (Chat UI)  │
 └──────────────────────────────┬──────────────────────────────┘
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │         🏰 SupremeAI Central MCP Control Tower Hub           │
 │  (infrastructure/mcp-control-plane)                         │
 │                                                             │
 │  1. Client Registry: Tracks active IDE sessions & statuses  │
 │  2. Target Dispatcher: Routes to specific agent or 'ALL'    │
 │  3. Bidirectional Transport: SSE / WebSocket / MCP Sampling │
 └──────┬───────────────────────┼───────────────────────┬──────┘
        │                       │                       │
        ▼ (Target: Antigravity)  ▼ (Target: Cline)       ▼ (Target: Cloud)
 ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
 │  💻 Local    │        │  💻 Local    │        │  ☁️ Cloud    │
 │ Antigravity  │        │  Cline /     │        │  SupremeAI   │
 │   IDE Agent  │        │  Cursor Agent│        │  Core Engine │
 │ (Code / Run) │        │ (Code / Run) │        │ (Cloud Tasks)│
 └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │ (Live output & completion)
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │     📱 Instant Feedback Delivery (Telegram & Dashboard)     │
 └─────────────────────────────────────────────────────────────┘
```

---

## ৩. প্রযুক্তিগত কম্পোনেন্টসমূহ (Technical Specifications)

### ৩.১ MCP প্রোটোকল স্তরে ২-মুখী যোগাযোগ বাস্তবায়নের পদ্ধতি
Model Context Protocol (MCP) স্ট্যান্ডার্ড স্পেসিফিকেশনে সার্ভার থেকে ক্লায়েন্টকে রিকোয়েস্ট পাঠানোর দুটি প্রধান উপায় রয়েছে:

1. **MCP Sampling (`sampling/createMessage`):**
   * সার্ভার ক্লায়েন্টের কাছে স্যাম্পলিং রিকোয়েস্ট পাঠায়। লোকাল IDE এজেন্ট প্রম্পটটি গ্রহণ করে লোকাল কোডবেসের প্রেক্ষাপটে এক্সিকিউট করে রেসপন্স ফেরত পাঠায়।
2. **Reverse Event Stream (`control-tower://agent/tasks`):**
   * লোকাল IDE যুক্ত হওয়ার সময় `client_register` দিয়ে রেজিস্ট্রেশন সম্পন্ন করে এবং `control-tower://agent/tasks/{client_id}` স্ট্রিমে সাবস্ক্রাইব করে থাকে।
   * নতুন টাস্ক এলে রিয়েল-টাইমে লোকাল IDE ইভেন্ট পায়।
   * লোকাল IDE কাজটি শেষ করে `task_report` টুলের মাধ্যমে ফলাফল পুশ করে।

### ৩.২ কন্ট্রোল টাওয়ারে নতুন মেথড ও টুলস (Tower Extensions)
[`infrastructure/mcp-control-plane/src/index.ts`](infrastructure/mcp-control-plane/src/index.ts)-এ নিচের ক্ষমতাগুলো যুক্ত হবে:

* **`task_dispatch` (Tool):**
  * `target`: `client_id` (যেমন: `antigravity-local`, `cline-node`, বা `all`)
  * `prompt`: ব্যবহারকারীর নির্দেশ
  * `priority`: `normal` / `urgent`
  * `origin`: `telegram` / `dashboard`
* **`task_poll_or_stream` (Resource / Subscription):**
  * লোকাল IDE-এর জন্য টাস্ক গ্রহণের চ্যানেল।
* **`task_report` (Tool):**
  * লোকাল IDE থেকে এক্সিকিউশনের ফলাফল, কোড ডিফ বা টেস্ট স্ট্যাটাস জমা দেওয়ার এন্ডপয়েন্ট।

---

## ৪. ব্যবহারকারীর অভিজ্ঞতা (UX Workflow)

### ৪.১ Telegram ইন্টিগ্রেশন
1. ব্যবহারকারী টেলিগ্রামে পাঠালেন:
   ```text
   /task "Fix database timeout in postgres pool and run pytest"
   ```
2. টেলিগ্রাম বট সেন্ট্রাল MCP টাওয়ারের `client_list()` চেক করে সক্রিয় এজেন্টদের বাটন দেখাবে:
   ```text
   📡 সক্রিয় এজেন্ট নির্বাচন করুন:
   [ 🟢 Antigravity IDE (Local PC) ]   [ 🟢 Cline (Local PC) ]
   [ ☁️ SupremeAI Cloud Node ]         [ 🚀 Broadcast to ALL ]
   ```
3. ব্যবহারকারী **"Antigravity IDE (Local PC)"** চাপলে কমান্ডটি সরাসরি আপনার চালু থাকা লোকাল Antigravity সেশনে চলে যাবে।
4. লোকাল আইডিই কোড এডিট করবে, টার্মিনাল রান করবে এবং কাজ শেষে টেলিগ্রামে ফাইনাল রিপোর্ট পাঠিয়ে দেবে:
   ```text
   ✅ [Antigravity IDE]: database timeout ফিক্স করা হয়েছে।
   - Modified: backend/database/postgres.py
   - Test result: 4 passed in 1.2s.
   ```

### ৪.২ Web Dashboard ইন্টিগ্রেশন
* ড্যাশবোর্ডের চ্যাট ইনপুট বক্সের ঠিক পাশেই একটি টার্গেট ড্রপডাউন থাকবে:
  `Target: [ Antigravity IDE (Local) ▾ ]`
* ইউজার নির্দিষ্ট এজেন্টের সাথে ওয়ান-অন-ওয়ান যোগাযোগ করতে পারবেন অথবা `All` দিয়ে মাল্টি-এজেন্ট কোলাবোরেশন করাতে পারবেন।

### ৪.৩ লাইভ ডিভাইস উপস্থিতি ও হার্টবিট ট্র্যাকিং (Live Device Presence & Heartbeat)
* **কোন ডিভাইস অনলাইনে আছে তা ফোন থেকেই জানা যাবে:**
  * ব্যবহারকারী রাস্তায় বা বাইরে থাকা অবস্থায় টেলিগ্রামে `/devices` বা `/status` কমান্ড দিলে সাথে সাথে তার রেজিস্টার্ড সব ডিভাইসের লাইভ স্ট্যাটাস দেখতে পাবেন:
    ```text
    📱 আপনার সংযুক্ত ডিভাইস ও এআই স্ট্যাটাস:
    --------------------------------------------------
    🟢 Home PC (Antigravity IDE): ONLINE (Idle, RAM: 18%)
    🟢 Office Laptop (Cursor/Cline): ONLINE (Active)
    ⚪ Personal MacBook: OFFLINE (Last seen 2h ago)
    🟢 Cloud Core (SupremeAI): ONLINE (Render Primary)
    --------------------------------------------------
    💡 আপনি যেকোনো সক্রিয় ডিভাইসে সরাসরি টাস্ক পাঠাতে পারেন।
    ```
* **অটো-হার্টবিট ও স্মার্ট রাউটিং (Smart Availability Routing):**
  * প্রতিটি লোকাল IDE প্রতি ৩০-৬০ সেকেন্ডে একটি হালকা পিং (`client_heartbeat`) পাঠাবে।
  * পিসি স্লিপে চলে গেলে বা বন্ধ থাকলে সিস্টেম স্বয়ংক্রিয়ভাবে তাকে `OFFLINE` দেখাবে, যাতে ব্যবহারকারী ভুল করে বন্ধ থাকা পিসিতে টাস্ক পাঠিয়ে বিভ্রান্ত না হন।

### ৪.৪ ফোন-ফার্স্ট রিমোট কমান্ডের মূল সুবিধাসমূহ (Key Phone-First Benefits)
1. **১০০% গতিশীল স্বাধীনতা (True On-the-Go Freedom):**
   * পিসির সামনে সার্বক্ষণিক বসে থাকার কোনো বাধ্যবাধকতা নেই। বিছানায় শুয়ে, রাস্তায় বা ভ্রমণে থাকা অবস্থাতেও ব্যবহারকারী নিজের ফোন (Telegram / WhatsApp / Dashboard) থেকে ঘরে বা অফিসে চালু থাকা পিসির এআই-কে কাজ দিতে পারবেন।
2. **লাইভ ডিভাইস উপস্থিতি জানা (Know Exactly Which Device is Active):**
   * ফোন থেকেই এক পলকে দেখা যায় কোন পিসি অন আছে, কোন এআই ফ্রি আছে এবং কোনটি কাজে ব্যস্ত (CPU, RAM, Running Task সহ)।
3. **স্মার্ট ফোন-টু-লোকাল কোডিং পাইপলাইন (Phone-to-Local Real Execution):**
   * মোবাইল থেকে পাঠানো একটি মাত্র কমান্ড (/task @antigravity fix bug and run tests) লোকাল পিসিতে ফাইল এডিট করবে, টার্মিনালে টেস্ট রান করবে এবং বাস্তব ফলাফল সরাসরি আপনার ফোনের স্ক্রিনে ডেলিভারি করবে।
4. **ফোন থেকে রিমোট কিল-সুইচ ও ইমার্জেন্সি কন্ট্রোল (Emergency Kill Switch from Mobile):**
   * কোনো কমান্ড ভুল পথে এগোলে ফোন থেকেই /abort বা /pause পাঠিয়ে লোকাল প্রসেস থামিয়ে দেওয়া সম্ভব।
5. **মাল্টি-ডিভাইস প্যারালাল অর্কেস্ট্রেশন (Multi-Device Parallel Orchestration):**
   * ফোন থেকে এক আদেশে হোম পিসির Antigravity-কে ব্যাকএন্ড ফিক্স করতে দিয়ে একই সাথে অফিসের ল্যাপটপের Cline-কে ফ্রন্টএন্ড কম্পোনেন্ট তৈরির কাজ দেওয়া যায়।

---

## ৫. নিরাপত্তা ও পলিসি নিয়ন্ত্রণ (Security & Policy Guardrails)

1. **Bearer Token Authentication:** প্রতিটি লোকাল IDE ক্লায়েন্ট ইউনিক টোকেন দিয়ে কানেক্ট থাকবে (ইতিমধ্যে `client-registry.ts`-এ বিদ্যমান)।
2. **Authorized Disptach Only:** শুধুমাত্র অনুমোদিত টেলিগ্রাম অ্যাডমিন আইডি বা ভ্যালিড সেশনওয়ালা ড্যাশবোর্ড ইউজাররাই টাস্ক ডিসপ্যাচ করতে পারবে।
3. **Governed Autonomy (95/5 Rule):** লোকাল এজেন্ট যদি কোনো ধ্বংসাত্মক কমান্ড (`git push --force`, `rm -rf`, ডাটাবেস ড্রপ) চালাতে যায়, তবে টেলিগ্রামে আগে ইন্টারেক্টিভ কনফার্মেশন চাইবে।

---

## ৬. রোলআউট ও ফেজ পরিকল্পনা (Phased Implementation Roadmap)

* **Phase 1: Control Tower Task Dispatcher & Heartbeat Tracker (Backend):**
  * FastMCP সার্ভারে `task_dispatch`, `task_list`, `task_report`, এবং `client_heartbeat` টুলস/রিসোর্স যোগ করা।
  * ইন-মেমোরি / সুপাবেস ব্যাকড ডিসপ্যাচ কিউ ও ডিভাইস স্ট্যাটাস ট্র্যাকার তৈরি।
* **Phase 2: Local Agent Hook / Sidecar Adapter:**
  * লোকাল পিসিতে Antigravity / Cline-এর জন্য একটি হালকা লিসেনার হুক যুক্ত করা যা হার্টবিট পাঠাবে এবং MCP টাওয়ার থেকে টাস্ক রিসিভ করবে।
* **Phase 3: Telegram & Dashboard Target & Device Selector:**
  * টেলিগ্রাম বোটে `/devices` এবং ইন্টারেক্টিভ এজেন্ট সিলেকশন কিবোর্ড যুক্ত করা।
  * ফ্রন্টএন্ড ড্যাশবোর্ডে লাইভ ডিভাইস স্ট্যাটাস ও টার্গেট ড্রপডাউন যুক্ত করা।

---

## ৭. প্রোডাক্ট পজিশনিং ও মার্কেটিং স্ট্র্যাটেজি (Product Positioning & Marketing Strategy)

### ৭.১ ব্র্যান্ডিং ও মূল আকর্ষণ (The Killer Hook)
* **ফিচার ব্র্যান্ডিং:** **Supreme Teleport** (বা **Supreme Pocket Tower**)
* **মার্কেটিং স্লোগান:**  
  > *"আপনার সবকটি কম্পিউটার ও লোকাল এআই এখন আপনার পকেটে — বিশ্বের যেকোনো প্রান্ত থেকে পরিচালনা করুন।"*  
  > *(Control Your Multiple Devices & Local AI From Far)*

### ৭.২ কেন এটি বাজারে অভাবনীয় সাড়া ফেলবে? (The Competitive Differentiator)
1. **কোনো মাউস টানাটানির ঝামেলা নেই (Zero Remote Desktop Frustration):**  
   AnyDesk বা TeamViewer দিয়ে মোবাইলের ছোট্ট স্ক্রিনে মাউস টেনে কোড করা অসম্ভব যন্ত্রণাদায়ক। Supreme Teleport-এ কোনো মাউস লাগে না—সরাসরি বাংলায় বা ইংরেজিতে কাজের নির্দেশ পাঠিয়ে দিলে লোকাল এআই নিখুঁতভাবে কাজ করে রেজাল্ট পাঠিয়ে দেয়।
2. **ডেস্কের শেকল থেকে শতভাগ মুক্তি (True Developer Mobility):**  
   কোড রান বা টেস্ট করার জন্য পিসির সামনে বসে থাকার বাধ্যবাধকতা শেষ। বাসে, কফি শপে বা বিছানায় শুয়েও ঘরের শক্তিশালী ৬৪ জিবি পিসিতে ভারী টাস্ক রান করানো সম্ভব।
3. **মাল্টি-ডিভাইস কেন্দ্রীয় নিয়ন্ত্রণ (Multi-Device Orchestration):**  
   একই অ্যাপ/বট থেকে একসাথে অফিসের ল্যাপটপ, ঘরের ভারী ডেস্কটপ এবং ক্লাউড সার্ভারকে কাজ দেওয়া যায়।
4. **প্রাইভেট ও নিরাপদ (Zero Port Forwarding):**  
   কোনো পাবলিক আইপি বা পোর্ট খোলার ঝুঁকি নেই। আউটবাউন্ড সিকিউর টানেল ও গভর্নড অটোনমি (95/5 রুল) দিয়ে পরিচালিত।


---

## Gate যাচাই-মানদণ্ড (Acceptance Gates — 2026-09-18 retrofit)

> বাংলা মন্তব্য (issue #453 Gate-0 reconciliation): এই প্ল্যানটিই সিরিজের একমাত্র গেট-বিহীন
> প্ল্যান ছিল। কোনো checkbox "implemented" হবে না যতক্ষণ না নিচের গেটগুলো CI-প্রমাণিত হয়।
> এটি M18+M17+M06+M04-এর composition — ওগুলোর ভিত ছাড়া বাস্তবায়ন শুরু নিষিদ্ধ।

**Gate T-0 — পূর্বশর্ত (Prerequisite):**
- M18 Telegram webhook fail-closed প্রমাণিত; M17 resume-URL carrier লাইভ; M06 `run_scope()`
  `/abort`-কে traceability দেয়। (প্রমাণ: সংশ্লিষ্ট মডিউলের CI-green টেস্ট।)

**Gate T-1 — Tower Dispatcher:**
- `infrastructure/mcp-control-plane`-এ `task_dispatch` + `client heartbeat presence` লাইভ;
- client_id ছাড়া dispatch 422 দেয় (fail-closed); bearer token ছাড়া রেজিস্ট্রে প্রবেশ 401;
- চুক্তি-টেস্ট: tower↔client হ্যান্ডশেক + presence timeout।

**Gate T-2 — Local Sidecar:**
- সাইডকার শুধুমাত্র outbound tunnel খোলে (zero port forwarding — netstat/CI প্রমাণ);
- `task_report` ছাড়া ফলাফল কোথাও দেখা যায় না; ভুয়া সাফল্য ইভেন্ট = ০;
- চুক্তি-টেস্ট: dispatch→execute→report এন্ড-টু-এন্ড, বাতিল (`/abort <run_id>`) প্রচার।

**Gate T-3 — Phone-First UI:**
- Telegram `/devices`, `/task`, `/abort` লাইভ; ড্যাশবোর্ড device-তালিকা শুধু রেজিস্ট্রি-সত্য
  ডিভাইস দেখায় (মক ডিভাইস নিষিদ্ধ);
- চুক্তি-টেস্ট: প্রতিটি কমান্ডের happy + unauthorized path; dual-driven (customer + admin) ভিউ।
