---
target_scope: combined_ecosystem
id: canonical-plan-24-omnichannel-mcp-agent-ecosystem
subject: "Plan 24 (Canonical Master): SupremeAI Omnichannel MCP Agent Ecosystem & Remote Control Plane"
document_role: architecture
planning_authority: Architecture Governance / Central Control Tower & Circle C5
status: active
replaces:
  - "docs/plans/features/personal_mcp_gateway_multitenant_hub_plan.md"
  - "docs/plans/features/messaging_bots_telegram_and_whatsapp_architecture.md"
  - "docs/plans/features/mcp_gateway_dynamic_hub_plan.md"
last_updated: 2026-09-19
---

# Plan 24 (Canonical Master): SupremeAI Omnichannel MCP Agent Ecosystem & Remote Control Plane

> **Consolidation & Living Asset Notice:**  
> This master document unifies and replaces the previously fragmented documents:
> 1. `Plan_24_AI_Agent_Ecosystem_Integration.md` (Legacy May 2026 proposal)
> 2. `personal_mcp_gateway_multitenant_hub_plan.md` (Multi-tenant MCP Hub & Vanity Slug)
> 3. `messaging_bots_telegram_and_whatsapp_architecture.md` (Unified 3-Faces Gateway)
> 4. `mcp_gateway_dynamic_hub_plan.md` (Stub pointer)
>
> All architectural designs for **FastMCP, Local IDE Control (Cursor, VS Code, Antigravity, Cline), Web Dashboard Hub, and Telegram Bot Mobile Control** are permanently centralized here.

---

## 🏛️ ১. মূল দর্শন ও নির্বাহী সারাংশ (Executive Vision)

SupremeAI-এর মূল দর্শন হলো: **একটাই সেন্ট্রাল ইন্টেলিজেন্স ও স্টেটফুল অর্কেস্ট্রেশন ব্রেন, কিন্তু ব্যবহারকারী ও অ্যাডমিনের সাথে যোগাযোগের ২টি সক্রিয় ইন্টারঅ্যাকশন ফেস (Web & Telegram), এবং যেকোনো লোকাল আইডিই বা বহিরাগত এআই-কে কমান্ড দেওয়ার জন্য একটি উন্মুক্ত প্রোভাইডার-নিউট্রাল Model Context Protocol (MCP) মেশ নেটওয়ার্ক।**

### মূল স্তম্ভসমূহ:
1. **Public Endpoint, Private Identity, Explicit Authorization:**  
   কানেকশন এন্ডপয়েন্ট উন্মুক্ত হতে পারে (যেমন: `https://<user>.mcp.supremeai.ai` বা `https://<MCP_HOST>/mcp`), কিন্তু প্রতিটি ইনভোকেশন SHA-256 বিয়ারার টোকেন, টেন্যান্ট আইসোলেশন এবং কঠোর RBAC স্কোপ (`viewer`, `agent`, `admin`) দ্বারা সুরক্ষিত।
2. **One Brain, Two Command Faces (Web & Telegram):**  
   ব্যবহারকারী ওয়েব ড্যাশবোর্ড থেকে নির্দেশ দিক অথবা মোবাইল থেকে টেলিগ্রাম চ্যাটে `/task` বলুক—ভেতরের **টাস্ক স্টেট মেশিন, পলিসি গার্ড, মেমোরি কনটেক্সট এবং এক্সিকিউশন ইঞ্জিন ১০০% অভিন্ন।**
3. **Zero Dependency Bloat (Cloud-Parity First):**  
   বাইরের কোনো ভারী সার্ভার বা ফ্রেমওয়ার্ক না টেনে নিজস্ব নোড.জেএস FastMCP গেটওয়ে (`infrastructure/mcp-control-plane/`) এবং পাইথন Micro StateGraph (`backend/runs/stategraph.py`) দিয়ে পুরো আর্কিটেকচার পরিচালিত—যা Render-এর 512MB RAM লিমিটের শতভাগ অনুকূল।

---

## 🌐 ২. ইউনিফাইড সিস্টেম টপোলজি (Unified Architecture Topology)

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             HUMAN COMMAND SURFACES                               │
│                                                                                  │
│   ┌────────────────────────────────────────┐  ┌──────────────────────────────┐   │
│   │   FACE 1: WEB DASHBOARD                │  │  FACE 2: TELEGRAM BOT        │   │
│   │   - React 19 Studio UI                 │  │  - Mobile Command Center     │   │
│   │   - Personal MCP Hub & Token Manager   │  │  - /task & /status Commands  │   │
│   │   - 1-Click IDE Config Generator       │  │  - Inline HITL [Approve/No]  │   │
│   │   - 3D Telemetry & Live Runs           │  │  - RFC 6238 TOTP 2FA Guard   │   │
│   └───────────────────┬────────────────────┘  └──────────────┬───────────────┘   │
└───────────────────────┼──────────────────────────────────────┼───────────────────┘
                        │                                      │
                        ▼                                      ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      CENTRAL CONTROL TOWER & RUN ENGINE                          │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  FastMCP Control Plane (infrastructure/mcp-control-plane/)               │   │
│   │  - 70+ Domain Tools (Supabase, Render, Redis, Qdrant, Infisical, GitHub) │   │
│   │  - Client Registry (SHA-256 Hashed Tokens, Scopes: viewer/agent/admin)   │   │
│   │  - Edge Routing Middleware (Cloudflare Worker wildcard subdomain support)│   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
│                                         │                                        │
│   ┌─────────────────────────────────────┴────────────────────────────────────┐   │
│   │  Core Orchestration & Run Fabric (backend/runs/ & backend/brain/)        │   │
│   │  - Micro StateGraph Engine (Cyclic workflows, conditional edges)         │   │
│   │  - CheckpointManager (Durable state persistence across restarts)         │   │
│   │  - ReAct Reasoning Loop (Real tool calling replacing mock stubs)         │   │
│   └─────────────────────────────────────┬────────────────────────────────────┘   │
└─────────────────────────────────────────┼────────────────────────────────────────┘
                                          │
        ┌─────────────────────────────────┴─────────────────────────────────┐
        ▼                                                                   ▼
┌───────────────────────────────────────┐   ┌──────────────────────────────────────┐
│   LOCAL IDE AGENTS (MCP CLIENTS)      │   │   HEADLESS LOCAL WORKERS (TRIO)      │
│   • Cursor (Streamable HTTP / SSE)    │   │   • Gemini Writer (LLMGateway)       │
│   • Antigravity IDE (MCP Client)      │   │   • Kilo Reviewer (KiloCode CLI)     │
│   • VS Code / Cline (Local stdio/SSE) │   │   • Cline Checker (Local Lint/Test)  │
│   • Windsurf / Claude Code Desktop    │   │   • Docker Sandbox Safe Runner       │
└───────────────────────────────────────┘   └──────────────────────────────────────┘
```

---

## 📱 ৩. হিউম্যান কমান্ড ফেসসমূহ (Command Surfaces)

### ৩.১ Face 1: Web Dashboard (The Visual Hub)
* **Personal MCP Hub:** ব্যবহারকারী তার জন্য ডেডিকেটেড স্লাগ বা ক্লায়েন্ট টোকেন দেখতে পারবেন।
* **1-Click Config Exporter:** এক ক্লিকে নিচের মতো JSON কনফিগ জেনারেট করে Cursor বা Claude Desktop-এ পেস্ট করার সুবিধা:
  ```json
  {
    "mcpServers": {
      "supremeai-control-tower": {
        "url": "https://mcp.supremeai.ai/mcp",
        "headers": {
          "Authorization": "Bearer mcp_live_token_here"
        }
      }
    }
  }
  ```
* **Connected IDE Telemetry:** কোন কোন লোকাল আইডিই বা এক্সটার্নাল এআই বর্তমানে কানেক্টেড এবং কোন টুল কতবার কল করেছে তার লাইভ টেলিমেট্রি।

### ৩.২ Face 2: Telegram Bot (The Mobile Command Center)
* **ফেল-ক্লোজড অ্যাডমিন গেট:** `ADMIN_TELEGRAM_CHAT_ID` আনসেট থাকলে বট সম্পূর্ণ বন্ধ থাকে; কোনো হার্ডকোডেড আইডি নেই।
* **টাস্ক ডিসপ্যাচ (`/task <বিবরণ>`):** মোবাইল থেকে যেকোনো টাস্ক দিলে তা সরাসরি আমাদের সেন্ট্রাল `StateGraph`-এ সাবমিট হবে।
* **হিউম্যান-ইন-দ্য-লুপ (HITL) অনুমোদন:** যখন লোকাল আইডিই কোনো সেনসিটিভ অপারেশন (যেমন: কোড পুশ, প্রোডাকশন ডাটাবেস মাইগ্রেশন) করতে যাবে, বট টেলিগ্রামে তাৎক্ষণিক ইনলাইন বাটন পাঠাবে:
  ```text
  ⚠️ Task #104 requires your approval:
  "Push refactored auth module to main"
  [✅ Approve]   [❌ Reject]
  ```
  ব্যবহারকারী বাটনে চাপ দেওয়া মাত্রই স্টেটগ্রাফ চেকপয়েন্ট রেজুম করে এক্সিকিউশন শেষ করবে।

---

## ⚙️ ৪. সেন্ট্রাল FastMCP কন্ট্রোল টাওয়ার ও ক্লায়েন্ট স্পেক (Control Tower Spec)

### ৪.১ প্রোভাইডার-নিউট্রাল কানেকশন
সুপ্রিমএআই নির্দিষ্ট কোনো ভেন্ডরের উপর নির্ভরশীল নয়। `infrastructure/mcp-control-plane/` নিচের ৪টি ট্রান্সপোর্ট মোড সমর্থন করে:
1. **Streamable HTTP:** আধুনিক ক্লাউড ও রিমোট এআই ক্লায়েন্টদের জন্য (`https://<MCP_HOST>/mcp`).
2. **Server-Sent Events (SSE):** রিয়েল-টাইম বাই-ডাইরেকশনাল কানেকশনের জন্য।
3. **Local stdio:** লোকাল মেশিনে কমান্ড-লাইন আইডিই বা সাব-প্রসেসের জন্য:
   ```json
   {
     "command": "node",
     "args": ["infrastructure/mcp-control-plane/dist/index.js"],
     "env": { "MCP_TRANSPORT": "stdio" }
   }
   ```

### ৪.২ সিকিউরিটি ও আরবিক (RBAC Scopes)
| রোল (Role) | অনুমতি (Permissions) | উদাহরণ ক্লায়েন্ট |
|---|---|---|
| `viewer` | শুধুমাত্র টেলিমেট্রি ও রিড-অনলি টুলস (status, health, memory_search) | মনিটরিং বট, পাবলিক ড্যাশবোর্ড |
| `agent` | টাস্ক এক্সিকিউশন ও কোড টুলস (git, memory_write, run_task) | Cursor, Antigravity, Cline |
| `admin` | সিস্টেম কনফিগ, টোকেন রোটেশন, ডিপ্লয় ও ডিলিট অপারেশন | অ্যাডমিন কনসোল, টেলিগ্রাম ওনার |

---

## 🔄 ৫. লোকাল আইডিই নিয়ন্ত্রণ ও রিভার্স পুশ মেকানিজম (Solving Server-to-IDE Push)

MCP স্বাভাবিকভাবে **Client ➔ Server** (লোকাল আইডিই সার্ভারের টুল ব্যবহার করে)। কিন্তু টেলিগ্রাম বা ড্যাশবোর্ড থেকে লোকাল আইডিই-কে কোনো টাস্ক অ্যাসাইন করতে হলে **৩টি বাস্তবসম্মত সমাধান রয়েছে:**

### সমাধান ক: Long-Polling / Queue Listener (Zero-NAT Configuration)
* লোকাল আইডিই-তে একটি হালকা স্ক্রিপ্ট বা ব্যাকগ্রাউন্ড লিসেনার চলবে, যা সুপ্রিমএআই-এর `GET /runs?assigned_to=cursor_local&status=pending` লং-পোল করবে।
* টেলিগ্রামে কমান্ড দিলে তা কিউতে জমা হবে ➔ লোকাল আইডিই টাস্কটি তুলে নিয়ে লোকাল ফাইলে কাজ করবে ➔ ফলাফল সার্ভারে পুশ করবে।

### সমাধান খ: হেডলেস লোকাল ট্রায়ো রানার ([`backend/agents/ide/trio_adapters.py`](./backend/agents/ide/trio_adapters.py))
* লোকাল মেশিনে যখন সুপ্রিমএআই ব্যাকএন্ড সক্রিয় থাকে, তখন টেলিগ্রাম কমান্ড সরাসরি লোকাল CLI ট্রিগার করতে পারে:
  1. `GeminiWriter`: কোড জেনারেট করে।
  2. `KiloReviewer`: লোকাল `kilocode` CLI দিয়ে রিভিউ করে।
  3. `ClineChecker`: লোকাল `cline` CLI বা লিন্টার দিয়ে প্রোডাকশন প্রস্তুতি পরীক্ষা করে।

### সমাধান গ: গিট-সেন্ট্রিক ট্রায়াড লুপ (The Git PR Invariant)
* টেলিগ্রাম থেকে টাস্ক এলে সুপ্রিমএআই স্বয়ংক্রিয়ভাবে একটি GitHub Issue / Task Branch খোলে (`feat/<task_id>`).
* লোকাল আইডিই এজেন্ট (যেমন Antigravity / Cursor) ব্রাঞ্চটি পুল করে কাজ সম্পন্ন করে PR দেয়।

---

## 📈 ৬. বাস্তবায়িত অবস্থা ও পরবর্তী রোডম্যাপ (Implementation Status)

| উপাদান | বর্তমান অবস্থা | সোর্স কোড |
|---|:---:|---|
| **FastMCP Control Tower (70+ Tools)** | ✅ ১০০% সম্পন্ন | `infrastructure/mcp-control-plane/` |
| **Client Registry & SHA-256 Tokens** | ✅ ১০০% সম্পন্ন | `infrastructure/mcp-control-plane/src/policy/` |
| **Micro StateGraph Cyclic Engine** | ✅ ১০০% সম্পন্ন | `backend/runs/stategraph.py` |
| **ReAct Decision Loop & Tool Calling**| ✅ ১০০% সম্পন্ন | `backend/brain/reasoning_orchestrator.py` |
| **IDE Trio Adapters (Gemini/Kilo/Cline)**| ✅ ১০০% সম্পন্ন | `backend/agents/ide/trio_adapters.py` |
| **Telegram Admin Fail-Closed Gate & TOTP**| ✅ ১০০% সম্পন্ন | `backend/tools/social/telegram_bot/` |
| **Telegram `/task` ➔ StateGraph Bridge** | ⏳ পরবর্তী ধাপ | `backend/tools/social/telegram_bot/handler.py` |
| **Web Dashboard Personal MCP Hub UI** | ⏳ পরবর্তী ধাপ | `frontend/src/pages/user/IntegrationsManager.tsx` |

---

## 🎯 ৭. কনক্লুশন ও রুলস কমপ্লায়েন্স

এই ক্যানোনিকাল মাস্টার ডকুমেন্টটি সুপ্রিমএআই-এর `AGENTS.md` এবং `MASTER_KICKOFF_PROMPT.md`-এর নীতিমালা অনুযায়ী সম্পূর্ণ ডুপ্লিকেশন দূর করে একীভূত করা হয়েছে। এখন থেকে এই ইকোসিস্টেমের যেকোনো পরিবর্তন সরাসরি এই ফাইলে আপডেট (In-place living asset) হিসেবে সংরক্ষিত থাকবে।