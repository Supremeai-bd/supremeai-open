---
id: multi-agent-mesh-master-plan
subject: "SupremeAI Distributed Multi-Agent Mesh — Master Plan"
document_role: architecture
planning_authority: Architecture Governance / Planning Circle
canonical: true
status: active
evidence_state: partial
disposition: retain
last_verified: 2026-09-21
supersedes: []
superseded_by: []
target_scope: supremeai_internal
related_docs:
  - docs/plans/implementation_plan.md
  - docs/master_docs/OPS-06-MULTI-AGENT-BRANCHING-LIFECYCLE.md
  - docs/master_docs/OPS-07-DEVELOPER-AGENT-LIFECYCLE.md
  - docs/master_docs/OPS-08-SUPREMEAI-RUNTIME-WORK-PROCESS.md
  - docs/security/SECURITY_GUARDIAN.md
  - docs/master_docs/AGENT_SLOT_REGISTRY.yaml
---

> **STATUS (2026-09-27, epic #1850 Phase F truth-sync):** historical planning document.
> The final locked architecture (19 workflow files: 6 pipelines + 2 retained + 11
> libraries) landed via epic #1850 — see `integration-gate.yml`, `pr-gate.yml`,
> `nightly-ops.yml`, `ci.yml`, `ops-console.yml`, `issue-ops.yml` for the live state.
> Workflow names referenced below may differ from the final state.

# 🏛️ SupremeAI Distributed Multi-Agent Mesh — Master Plan

> **একটি সেন্ট্রালাইজড কন্ট্রোল প্লেন (MCP Tower), ডায়নামিক এআই ফ্লিট, ক্লাউড ওয়েব টুলস এবং ২টি লোকাল পিসির সমন্বয়ে গঠিত জিরো-কস্ট ডিস্ট্রিবিউটেড হাইব্রিড সিস্টেমের পূর্ণাঙ্গ আর্কিটেকচার।**

**Status:** active  
**Source of truth:** `docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md`  
**Plan owner:** SupremeAI Architecture / Planning Circle  
**Last verified:** 2026-09-21  
**Target scope:** supremeai_internal (Layer 1 — internal platform)

---

## ১. সম্পূর্ণ সিস্টেম টপোলজি (System Topology)

```text
                       [ 📱 ইনপুট গেটওয়ে ]
              Telegram Bot    │    Web Dashboard Chat
                              ▼
   ┌─────────────────────────────────────────────────────────────┐
   │            SupremeAI MCP Tower (Control Plane)              │
   │ ─────────────────────────────────────────────────────────── │
   │  • Live Presence Engine (কে অনলাইনে আছে: Web, IDE, PC)       │
   │  • Dynamic Role Matrix (Planner / Coder / Tester / Gate)    │
   │  • Task Router & Lease Manager (টাইমআউট ও ফলব্যাক)        │
   │  • HITL & Policy Engine (বিপজ্জনক কাজের মানব অনুমোদন)       │
   └──────┬───────────────────┬───────────────────┬──────────────┘
          │                   │                   │
  [MCP Protocol]       [MCP / Web Engine]   [Node Daemon]
          │                   │                   │
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ Gemini Web  │     │ Cloud/Web   │     │  Local Rig  │
   │ (MCP Client)│     │ Developers  │     │   Cluster   │
   │ ─────────── │     │ ─────────── │     │ ─────────── │
   │ Role:       │     │ • Lovable   │     │ • PC-1 (Dev)│
   │  Planner /  │     │   (MCP)     │     │ • PC-2 (Ops)│
   │  Architect  │     │ • Bolt.new  │     │ • Cline/Kilo│
   │             │     │   (Browser) │     │ • Terminal  │
   └─────────────┘     └──────┬──────┘     └──────┬──────┘
                              │                   │
                              ▼ (Git Push)        │ (Local Git)
                     ┌─────────────────┐          │
                     │  GitHub PR Bus  │◀─────────┘
                     │ (Universal IPC) │
                     └────────┬────────┘
                              │ (Webhook Trigger)
                              ▼
                     [ Verification & Run ]
```

---

## ২. লাইফসাইকল ও এক্সিকিউশন ফ্লো (Task Execution Flow)

```text
[1. User Command] ──▶ Telegram / Dashboard: "Add rate limiting & run tests"
         │
         ▼
[2. Tower Router] ──▶ Checks Active Presence & Assigns Roles:
         │            • Planner ➔ Gemini Web
         │            • Coder   ➔ Bolt.new / PC-1 (Cline)
         │            • Runner  ➔ PC-2 (Local Terminal)
         │
         ▼
[3. Planning]     ──▶ Gemini Web generates Architecture Spec & File Changes
         │
         ▼
[4. Build/Code]   ──▶ Coder implements changes:
         │            • Bolt/Lovable ➔ Pushes branch directly to GitHub PR
         │            • OR PC-1      ➔ Edits local files & commits
         │
         ▼
[5. Run & Verify] ──▶ PC-2 detects commit ➔ Runs `pytest tests/` in background
         │
         ▼
[6. Completion]   ──▶ SupremeAI Core audits result ➔ Sends report to Telegram:
                      "✅ 12 tests passed. PR #42 ready for merge."
```

---

## ৩. এজেন্ট ফ্লিট ও দায়িত্ব ম্যাট্রিক্স (Fleet Role Matrix)

| এজেন্ট / নোড | কানেকশন মেথড | ডিফল্ট রোল | ক্যাপাসিটি ও স্পেশালিটি |
| --- | --- | --- | --- |
| **Gemini Web** | রিমোট MCP URL | `Planner` | ফ্রি বিগ-কনটেক্সট রিজনিং ও আর্কিটেকচার ডিজাইন। |
| **PC-1 (Dev Rig)** | Local Daemon (`supreme-node`) | `Coder` | ফাইল এডিটিং, Cline/Kilo ফ্রি মডেল (Groq, Qwen)। |
| **PC-2 (Headless)** | Local Daemon (`supreme-node`) | `Tester / Runner` | লোকাল টার্মিনাল, `pytest` এক্সিকিউশন, লোকাল Ollama/GPU। |
| **Bolt.new** | Playwright Session Vault | `UI / Prototyper` | ফুলস্ট্যাক ওয়েব প্রোটোটাইপিং ➔ ডিরেক্ট গিটহাব পিআর। |
| **Lovable.dev** | অফিসিয়াল রিমোট MCP | `App Builder` | রিমোট প্রজেক্ট ইটারেশন ➔ ডিরেক্ট গিটহাব পিআর। |
| **SupremeAI Core** | Server Native Engine | `Supervisor` | মেমরি কনটেক্সট, সিকিউরিটি অডিট ও ফাইনাল অনুমোদন। |

---

## ৪. চারটি কোর ইঞ্জিনিয়ারিং নীতি

### ৪.১ GitHub PR as Universal IPC (নো ডোম স্ক্র্যাপিং)

ওয়েব এআই-গুলোর (Bolt, Lovable) ব্রাউজার স্ক্রিন থেকে কোড কপি করা নিষিদ্ধ।
নির্দেশ একটাই: *"Push solution to branch `mesh/task-{id}` and open a PR"*।
টাওয়ার শুধুমাত্র গিটহাব ওয়েবহুক ট্র্যাক করবে।

**Rationale:** DOM scraping ভঙ্গুর (CSS class change হলে ভেঙে যায়), slow, এবং anti-bot detection ট্রিগার করে। GitHub PR হলো stable API — structured JSON, webhooks, status checks, এবং PR Helper auto-merge সব একই চেইনে।

### ৪.২ পারসিস্টেন্ট সেশন ভল্ট (Bot & Cloudflare Bypass)

- `browser_session_manager.py` একবার ম্যানুয়াল লগইনের মাধ্যমে কুকি/লোকালস্টোরেজ এনক্রিপ্ট করে রাখবে।
- Playwright প্রতিবার সেই সংরক্ষিত প্রোফাইল নিয়ে ওপেন হবে, ফলে কোনো লগইন ব্লক বা ক্যাপচা আসবে না।

**Rationale:** Bolt.new ও Lovable.dev উভয়ই Cloudflare-protected — headless browser দ্রুত flagged হয়। Persistent session vault (encrypted cookies + localStorage) একবার ম্যানুয়াল লগইনের পর সপ্তাহব্যাপী সেশন ধরে রাখে।

### ৪.৩ ডায়নামিক লিজ ও ফেইলওভার (Zero Zombie Tasks)

- কোনো নোড (যেমন: লোকাল পিসি) ১০ মিনিট হার্টবিট না দিলে টাস্কটি অটো-রিলিজ হয়ে ক্লাউড ফলব্যাকে চলে যাবে।
- লোকাল ডিভাইস স্লিপে থাকলে টাওয়ার জিজ্ঞাসা করবে: *"Wait for PC, or use Cloud?"*

**Rationale:** লোকাল পিসি sleep/shutdown/crash হলে task চিরকাল `in-progress` থাকে → backlog অচল। Dynamic lease (TTL-based) + automatic fallback cloud-এ নিশ্চিত করে যে কোনো task ১০ মিনিটের বেশি আটকে থাকবে না। এটি ARCH-GAP-01 GAP-03 (Stale Mutex) fix-এর সাথে সামঞ্জস্যপূর্ণ।

### ৪.৪ মাল্টি-প্রোভাইডার কোটা পুলিং (Zero Cost Architecture)

২টি লোকাল পিসি + ক্লাউড ফ্রি অ্যাকাউন্ট ব্যবহার করে Gemini Free (১,৫০০ req/দিন), Groq, OpenRouter এবং লোকাল Ollama-র সমন্বয়ে প্রতি মাসে $১,০০০+ সমমূল্যের কম্পিউটেশন সম্পূর্ণ ফ্রিতে পরিচালিত হবে।

**Rationale:** কোনো single provider-এর free tier একা যথেষ্ট নয়। Multi-provider pooling (rate-limit-aware routing) নিশ্চিত করে যে যখন এক provider-এর quota শেষ, টাওয়ার স্বয়ংক্রিয়ভাবে পরবর্তী available provider-এ route করবে। এটি issue #904 (Rate Limit Monitor) ও `rate-limit-monitor.yml` workflow-এর সাথে integrated।

---

## ৫. ফাইল ও ডিরেক্টরি কাঠামো (Repository Map)

```text
supremeai/
├── backend/
│   ├── core/
│   │   ├── browser_session_manager.py   # Playwright persistent vault
│   │   ├── task_router.py               # Dynamic role & lease dispatcher
│   │   └── presence_registry.py         # Live active agents tracking
│   ├── mcp/
│   │   ├── mcp_tower.py                 # Central 109+ tool gateway
│   │   └── adapters/
│   │       ├── lovable_adapter.py       # Lovable MCP client
│   │       └── playwright_bolt.py       # Bolt deep-link automation
│   └── integrations/
│       ├── telegram_bot.py              # Ingestion & approval buttons
│       └── github_webhook.py            # Event listener for PR & pushes
├── client/
│   └── supreme-node/                    # PC-1 & PC-2 daemon script
│       ├── daemon.py                    # Outbound WebSocket to Tower
│       └── local_executors.py           # Local bash/pytest & Ollama bridge
```

---

## ৬. রোলআউট চেকলিস্ট

নিচের প্রতিটি checklist item একটি separate GitHub Issue হিসেবে ট্র্যাক করা হবে (per directive: "১টি Issue → ১টি Branch → ১টি PR"):

- [ ] **MESH-1: টাওয়ারে প্রেজেন্স এন্ডপয়েন্ট** — `/api/v1/nodes/heartbeat` চালু করা।
- [ ] **MESH-2: ড্যাশবোর্ড রোল ড্রপডাউন** — কানেক্টেড সেশন তালিকায় `Planner`, `Coder`, `Tester` রোলের অ্যাসাইনমেন্ট কন্ট্রোল তৈরি করা।
- [ ] **MESH-3: লোকাল ডেমন স্ক্রিপ্ট** — PC-1 ও PC-2-তে ব্যাকগ্রাউন্ডে চলার জন্য `daemon.py` লেখা।
- [ ] **MESH-4: টেলিগ্রাম কমান্ড হ্যান্ডলার** — `/task` এবং ইনলাইন বাটন অ্যাপ্রুভাল চালু করা।
- [ ] **MESH-5: Bolt প্লে-রাইট স্ক্রিপ্ট** — সেশন ভল্ট ও ডিপ-লিংক হ্যান্ডলিং কনফিগার করা।

---

## ৭. এক্সিস্টিং সিস্টেমের সাথে সম্পর্ক (Integration Map)

এই master plan বর্তমানে নিম্নলিখিত SupremeAI components-এর সাথে সংযুক্ত হবে:

| Component | Role in Mesh | Status |
|---|---|---|
| **MCP Tower** (`supremeai-mcp-tower.onrender.com`) | Control Plane — Task Router, Presence Engine, HITL Gate | ✅ Live (HTTP 200) |
| **GitHub PR Bus** | Universal IPC — PR Helper auto-merge, branch-naming-guard, pr-pipeline.yml | ✅ Live (branch protection active) |
| **PR Helper (5-Step Lifecycle)** | Auto-merge engine for mesh/task-* PRs | ✅ Live (workflow_call + workflow_dispatch triggers) |
| **Deploy Doctor** | Detects Render deploy failures from mesh-driven pushes | ✅ Live (cron */5 * * * *) |
| **Stale Mutex Cleanup** | Releases orphaned `in-progress` issues (GAP-03) | ✅ Live (cron daily 2 AM) |
| **Rate Limit Monitor** | Tracks GitHub API quota for mesh agents | ✅ Live (cron hourly) |
| **atomic_claim.sh** | Race-safe issue claiming for concurrent mesh agents | ✅ Live (GAP-01 fix) |
| **AGENT_SLOT_REGISTRY.yaml** | Slot mapping (agent-1=Antigravity, agent-2=Claude, …, agent-10=SupremeAI) | ✅ Populated |
| **Security Guardian (SG-01..SG-15)** | 15 timeless invariants enforced via pr-pipeline.yml | ✅ Live |
| **Render Fleet (4 services)** | Production deploy targets (primary/worker/scraper/mcp-tower) | ⚠️ 2/4 healthy |

---

## ৮. সিকিউরিটি ও গভর্নেন্স অ্যালাইনমেন্ট

এই plan নিম্নলিখিত governance documents-এর সাথে সম্পূর্ণ সামঞ্জস্যপূর্ণ:

- **`docs/security/SECURITY_GUARDIAN.md`** — 15 timeless invariants (SG-01..SG-15)
  - SG-03 (Explicit Auth): MCP Tower শুধু authenticated agent-দের task receive করতে দেবে
  - SG-05 (Boundary Isolation): PC-1 ও PC-2-এর task scope আলাদা — একটির issue অন্যটি touch করবে না
  - SG-09 (Destructive Automation HITL): Bolt/Lovable-এর direct-to-PR push এখনও pr-pipeline.yml gate পাবে
  - SG-11 (Bootstrap Trust): SupremeAI Core নিজের mesh routing logic modify করলে mandatory human review

- **`docs/master_docs/OPS-06-MULTI-AGENT-BRANCHING-LIFECYCLE.md`** — atomic_claim.sh usage mandate
- **`docs/master_docs/OPS-07-DEVELOPER-AGENT-LIFECYCLE.md`** — agent slot assignment protocol
- **`docs/master_docs/OPS-08-SUPREMEAI-RUNTIME-WORK-PROCESS.md`** — SupremeAI Developer Mode
- **`docs/master_docs/AGENT_SLOT_REGISTRY.yaml`** — polymorphic slot registry (max 5 active)

---

## ৯. ফেজ-বাই-ফেজ রোলআউট টাইমলাইন

| Phase | কাজ | Target | Dependencies |
|---|---|---|---|
| **Phase A** | MESH-1 (heartbeat endpoint) + MESH-3 (local daemon) | Foundation — tower ও node-এর মধ্যে connection স্থাপন | None |
| **Phase B** | MESH-2 (dashboard role dropdown) + MESH-4 (Telegram commands) | User-facing control layer | Phase A |
| **Phase C** | MESH-5 (Bolt session vault) + Lovable adapter integration | Cloud agent integration | Phase A |
| **Phase D** | Multi-provider quota pooling (Gemini/Groq/Ollama routing) | Zero-cost scaling | Phase A + B |
| **Phase E** | Dynamic lease + failover (10-min heartbeat TTL) | Zero-zombie-tasks guarantee | Phase A |

---

## ১০. সাফল্যের মেট্রিকস

| Metric | Target | Measurement |
|---|---|---|
| **Mesh agent uptime** | ≥ ৯৫% (2 local PCs) | heartbeat endpoint metrics |
| **Task end-to-end latency** | P50 < ৫ মিনিট, P95 < ৩০ মিনিট | Tower audit log |
| **Zero-cost compute** | ≥ $১,০০০/মাস equivalent | Multi-provider quota tracker |
| **Auto-merge success rate** | ≥ ৮০% (pure-improvement PRs) | PR Helper Step 5 stats |
| **Stale task rate** | < ৫% (no zombie tasks > ১০ মিনিট) | Stale mutex cleanup weekly report |
| **GitHub API quota utilization** | < ৮০% (5,000 req/hr) | Rate-limit monitor alerts |

---

## ১১. রিস্ক ও মাইটিগেশন

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Bolt/Lovable session expiry (Cloudflare block) | Medium | High — agent offline | Persistent session vault (re-login every 7 days) + cloud fallback |
| Local PC crash during task | High (laptops sleep) | Medium — task delayed | Dynamic lease (10-min TTL) + auto-fallback to cloud agent |
| GitHub API rate limit hit (5 concurrent agents) | Medium | High — all PRs block | Multi-token strategy (issue #434: Infisical blind-index) + quota pooling |
| MCP Tower single-point-of-failure | Low | Critical — entire mesh down | Render auto-deploy + health check + Deploy Doctor alerting |
| DOM scraping temptation (Bolt screen copy) | Medium | Low — code quality degrades | Strict policy (Section 4.1) + PR Helper rejects non-PR submissions |

---

## ১২. ডকুমেন্ট মেটাডেটা

- **Created:** 2026-09-21
- **Author:** SupremeAI Architecture / Planning Circle
- **Review cadence:** Monthly (or on major topology change)
- **Successor documents:** প্রতিটি MESH-1 থেকে MESH-5 issue-এর PR-এ এই plan reference করা হবে
- **Evidence trail:** প্রতিটি checklist item complete হলে এই doc-এ `[x]` দিয়ে mark করা হবে + linked PR number যোগ হবে

---

*এই document টি SupremeAI Distributed Multi-Agent Mesh-এর canonical architecture reference। সমস্ত mesh-related implementation এখান থেকে trace করা যাবে।*
