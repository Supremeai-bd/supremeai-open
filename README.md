# SupremeAI Open Foundation

> **Open the implementation that teaches people how to use SupremeAI; keep private the implementation that reveals why SupremeAI performs better.**  
> 🇧🇩 **বাংলা সংস্করণ:** [`docs/README.bn.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/README.bn.md)

This repository is the **public boundary** of the SupremeAI federation (roadmap §4.3 / Phase 8 foundation).
It contains only artifacts that are useful *outside* SupremeAI's private intelligence:

> [!IMPORTANT]
> ### 🤖 AI Agent & MCP Contributor Quickstart (Where & How to Work)
> If you are an external AI (Claude, Cursor, Antigravity, etc.) connecting via MCP Tower or GitHub:
> 1. **Single Door for Work:** All tasks, bug reports, and PRs live exclusively in **`Supremeai-bd/supremeai-open`**. Satellite repositories maintain a strict 0 Issues / 0 PRs policy ([`FEDERATION_CHARTER.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/FEDERATION_CHARTER.md)).
> 2. **Where to Write Code:** Edit the corresponding domain folders inside this repository (`studio/`, `command/`, `core/`, `vscode/`, etc.). Do NOT attempt to push directly to satellite repos.
> 3. **Automated Dispatch & Zero Residue:** When your PR merges into `supremeai-open:main`, the automated bridge pipeline dispatches your changes to the target satellite repo and cleans up transit files automatically ([`AUTONOMOUS_TRANSIT_PIPELINE.md`](./AUTONOMOUS_TRANSIT_PIPELINE.md)).
> 4. **Boundary Restrictions:** You do not need private credentials. Access to `supremeai` (core monorepo) is restricted to admin, and `supremeai-api` is air-gapped (ghost-cloaked). All other satellites are accessible via MCP.
>
> **MCP Tower call conventions (avoid argument/format errors):**
> - Tool names are **wave-split** (2026-10-29/30 rename waves, #2493): the core github + bridge queue/order tools are **dotted** (`github.read_file`, `github.list_prs`, `github.workflow_runs`, `bridge.work_queue`, `bridge.work_order`) — their old snake_case forms are dead (-32602). The external-repo explorer family (`github_repo_tree`, `github_search_repos`, ...) and the claim/feedback family (`work_claim`, `bridge_read_feedback`, `bridge_work_renew`, `bridge_work_release`) stay **snake_case**. Never guess: probe `tools/list` first.
> - Repo references must be **`owner/repo`** (e.g. `Supremeai-bd/supremeai-open`); a bare repo name returns "Invalid repo reference". On repo-resolving list tools pass `repo` explicitly — the omit-repo default resolves through the account registry and has silently drifted before (R66/#2447); every response echoes the resolved target as `targetRepo`/`targetUrl`, so verify it.
> - Use the correct tool name + `owner/repo` form or the call fails.
> - Bridge tools: `bridge_submit_patch` requires `taskId` (`bridge-YYYYMMDD-<slug>`), `summary`, `scopePaths` (1-30), `testsEvidence`, and `files` (each with `path`); pass `originalIssueNumber` so the root issue auto-closes on merge, and `closesOriginalIssue: true` only when a docs-only payload **IS** the resolution of that issue (receipt-closure convention #2485, `contract.receiptClosureConvention` in `bridge_guide`; default keeps the WO open via `Refs #N`). `work_claim` requires `issueNumber` (integer). `bridge.work_order`/`bridge_read_feedback` require `number` (issue number).

## 📐 Federation Architecture & Canonical Repository Inventory

> **ক্যানোনিক্যাল রেফারেন্স ও ডোমেইন ইনভেন্টরি:**  
> SupremeAI-এর repository ও domain inventory পরিবর্তনশীল। সক্রিয়, একীভূত এবং ঐতিহাসিক repository-র বর্তমান তালিকা, সংজ্ঞা ও routing-এর জন্য [`scripts/ci/federation_anchors.py`](./scripts/ci/federation_anchors.py) এবং [`ECOSYSTEM_MAP.md`](./ECOSYSTEM_MAP.md)-এ দেখুন। এই নথির যে কোনো চিত্র বা ফাইল সংখ্যা মূলত কাঠামোগত স্থাপত্যের চিত্রণ।
> **Reference SSOTs:** [`docs/FEDERATION_CHARTER.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/FEDERATION_CHARTER.md) · [`scripts/ci/federation_anchors.py`](./scripts/ci/federation_anchors.py)

### 1. Mathematical Universe & Repository Set Model

```mermaid
flowchart TD
    subgraph FEDERATION_UNIVERSE ["🌐 The Federation Universe (U)"]
        direction TB
        OPEN["supremeai-open (Public Task Hub & Embassy)<br>Task Board SSOT & Public Embassy"]
        MONO["supremeai (Central Umbrella Monorepo)<br>Central Unified Platform"]
        
        subgraph ACTIVE_SATS ["Active Domain Satellites (Golden 6-Domain Architecture)"]
            S_STUDIO["supremeai-studio<br>(Vercel Web UI)"]
            S_API["supremeai-api<br>(Render Gateway & FastMCP)"]
            S_CORE["supremeai-core<br>(DAG Decision Moat)"]
            S_BROWSER["supremeai-browser<br>(Stealth Playwright Engine)"]
            S_VSCODE["supremeai-vscode<br>(Extension & Desktop Client)"]
        end

        ARCHIVE["supremeai-archive (Cold Storage)<br>Historical Specs & Worklogs"]
    end

    OPEN ==>|"Transit Mirrors<br>Step 1: Direct Dispatch"| ACTIVE_SATS
    ACTIVE_SATS ==>|"Step 2: Monorepo Ingestion"| MONO
    ARCHIVE -.->|"Retired Architectural Delta<br>(Historical Reference)"| MONO

    classDef open fill:#1d76db,stroke:#fff,stroke-width:2px,color:#fff;
    classDef sats fill:#059669,stroke:#fff,stroke-width:2px,color:#fff;
    classDef mono fill:#7c3aed,stroke:#fff,stroke-width:2px,color:#fff;
    classDef archive fill:#475569,stroke:#fff,stroke-width:1px,color:#fff;
    class OPEN open;
    class S_STUDIO,S_API,S_CORE,S_BROWSER,S_VSCODE sats;
    class MONO mono;
    class ARCHIVE archive;
```

#### Core Set Equations:
- **Public Boundary Partition:** $\mathbf{Open} = T_{\text{transit}} \cup U_{\text{open}} \quad \text{where } T_{\text{transit}} \cap U_{\text{open}} = \emptyset$
  - **$U_{\text{open}}$:** Public front door, CI guards, Federation Anchor Hub configs, and constitution. **Never dispatched to satellites.**
  - **$T_{\text{transit}}$:** Scoped mirror surfaces (`studio/*`, `gateway/*`, `browser/*`, `vscode/*`, `core/*`).
- **Active Federation Surface:** $\mathbf{S_{\text{active}}} = S_{\text{studio}} \cup S_{\text{api}} \cup S_{\text{vscode}} \cup S_{\text{browser}} \cup S_{\text{core}}$
- **The Blocked State Law:** Any file in `supremeai-open` not in $U_{\text{open}}$ represents an in-flight or blocked transit payload.

---

### 2. 2-Step Cascading Bridge & Zero-Residue Lifecycle (#416)

```mermaid
flowchart TD
    PR["Autonomous PR / Patch Submission<br>(supremeai-open:main)"] --> GATES{"Constitutional Gates &<br>Verification Battery"}
    
    GATES -- "Pass" --> LAND["Autonomous Landing<br>(Squash Merge into main)"]
    GATES -- "Fail" --> REJECT["Fail-Closed Block & Feedback<br>(CI Incident Logged)"]
    
    LAND --> STEP1["🌉 Bridge Step 1:<br>supremeai-open ➔ Active Target Satellite<br>(studio, api, browser, vscode, core)"]
    
    STEP1 --> VERIFY1{"Satellite Ingestion<br>Verified?"}
    VERIFY1 -- "Yes" --> STEP2["🌉 Bridge Step 2:<br>Satellite ➔ Central Monorepo (supremeai)<br>(Full Product Parity Ingestion)"]
    
    STEP2 --> VERIFY2{"Monorepo Sync<br>Verified?"}
    
    VERIFY2 -- "Verified Completed" --> PRUNE["🧹 Zero-Residue Auto-Prune (#416):<br>1. Delete ephemeral transit patch files<br>2. Delete bridge/* transit sync branches"]
    
    PRUNE --> CLEAN["✨ Clean Steady State<br>Open repo preserved at clean U_open boundary"]
```

---

### 3. Federation CI Watchdog & Federation Anchor Hubs Architecture

```mermaid
flowchart TD
    subgraph ALL_SATS ["🌐 6 Active Domain Federation Repositories (Studio, API, Core, Browser, VSCode, Open)"]
        RUNS["GitHub Actions Workflow Runs"]
    end

    RUNS -->|"Failure Detected (Conclusion: failure)"| WATCHDOG["🔍 Federation CI Watchdog<br>(15-min cron & landing post-hook)"]
    
    WATCHDOG --> DEDUP{"Idempotent Marker Present?<br>(<!-- MIRROR_RUN: ... -->)"}
    DEDUP -- "Already Open" --> NOOP["Clean Skip (Zero Spam)"]
    DEDUP -- "New Incident" --> INGEST["Create P0 Incident Sub-Issue<br>(Database ID linking via REST API)"]
    
    INGEST --> DOMAIN_ANCHOR["🎯 Linked directly under Target Domain Anchor Hub<br>(#749, #750, #751, #754, #756, #762)"]
    
    subgraph BOARD ["Golden 6-Domain Anchor Hubs SSOT (gh issue list --search 'no:parent is:open')"]
        H749["#749 Studio UI"]
        H750["#750 API Gateway"]
        H751["#751 Core Moat"]
        H754["#754 VSCode Client"]
        H756["#756 Browser Engine"]
        H762["#762 Open Embassy"]
    end
    
    DOMAIN_ANCHOR -.-> BOARD
```

> Consuming the platform (not contributing)? Start at
> [`docs/CONSUMERS.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/CONSUMERS.md) and the
> [`api-schemas/gateway.openapi.yaml`](./api-schemas/gateway.openapi.yaml)
> Gateway surface. Contributing? [`AGENTS.md`](./AGENTS.md) and
> [`docs/ZERO_ADMIN_GUIDE.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/ZERO_ADMIN_GUIDE.md) are the entry points.

### 🌐 Live Federation Services

| Service | Live URL | Description |
|---|---|---|
| **SupremeAI Studio (Web UI)** | [https://supremeai-studio.vercel.app](https://supremeai-studio.vercel.app) | User-facing React/Vite console interface and agent workspace |
| **MCP Control Tower** | [`https://supremeai-mcp-tower.onrender.com`](https://supremeai-mcp-tower.onrender.com) | Remote Streamable HTTP (`/mcp`) & SSE (`/sse`) tool plane |
| **API Gateway** | [`https://supremeai-api-ulw0.onrender.com`](https://supremeai-api-ulw0.onrender.com) | Unified OpenAI-compatible multi-LLM provider gateway |

| Path | What it is |
|---|---|
| `api-schemas/gateway.openapi.yaml` | **The stable SupremeAI API Gateway surface** (OpenAI-compatible `/v1/chat/completions`) — byte-mirror of `supremeai-api/contracts/openapi.yaml` |
| `examples/gateway_client.py` | Zero-dependency Python client for the Gateway (typed errors, retry only on 502/503) — byte-mirror of `supremeai-api/scripts/clients/gateway_client.py` |
| `docs/CONSUMERS.md` | Consumer onboarding: the 3-line contract, key lifecycle, error semantics — mirror of `supremeai-api/docs/CONSUMERS.md` |
| `ECOSYSTEM_MAP.md` | **The Federation Ecosystem Map** — architecture directory for agents working across repos |
| [`docs/FEDERATION_TAXONOMY_AND_LICENSING.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/FEDERATION_TAXONOMY_AND_LICENSING.md) | **Federation Taxonomy & Licensing SSOT** — 12 domain satellites, institutional memory, and the master umbrella model |
| [`docs/AGENT_PORTAL_SPEC.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/AGENT_PORTAL_SPEC.md) | **Agent Portal & Federation Bridge architecture spec** (#23): two-repo relationship, the 3 submission pathways mapped to machinery, guard/gate/router map, clickable contract-schema references |
| [`docs/FAQ.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/FAQ.md) | **Operational FAQ** (#23): symptom→cause→fix for every known validation-error class (naming, duplicates, boundary, stale-base, force-push, keyword propagation, env-skips) |
| `AGENTS.md` | Agent entrypoint: autonomous work-submission loop, submission pathways, bridge lane |
| `.github/workflows/pipeline.yml` | Unified validation & cron engine (#155): guards → Python 3.10–3.13 matrix + Tower TS verification + secret scan, plus the agent-loop dispatch job (`scripts/agents/continuous_agent_loop.py --pick-next`) — triggerable by manual `workflow_dispatch`; the */30 schedule is currently disabled per admin directive (AGENTS.md §0 8-step cycle; draft-only scheduled runs with explicit §10 no-op on empty board, PR submission opt-in via manual dispatch; event-driven intake via the MCP Tower, see `infrastructure/mcp-control-plane/docs/BRIDGE_INTAKE.md`) |
| `.github/workflows/landing.yml` | Unified autonomous landing & bridge dispatch (#155): auto-squash-merge on full gate success, then the same run streams the landed patch reference into the private bridge queue |
| `.github/ISSUE_TEMPLATE/bridge-work-order.yml` | Work-order template for bridge submissions (task id, patch branch, test evidence) |
| `LICENSE` | MIT |

## The one stable contract

```
Client ──SUPREMEAI_API_KEY──▶ SupremeAI Gateway ──▶ Provider Adapters (Gemini / Groq / …)
```

- One stable SupremeAI API on the outside; dynamic, replaceable, multi-provider intelligence on the inside.
- Provider credentials never leave the server side. Your `SUPREMEAI_API_KEY` is the only thing you need.

## What goes here vs. what never goes here

**Belongs here:** generic interfaces, examples, open schemas, documentation helpers, consumer tooling.

**Never here:** proprietary routing policies, internal autonomy scoring, private repair/healing policy, key-plane internals.

## Drift protection

Mirrors above are byte-parity-checked daily by the federation integration CI
(`supremeai-infrastructure` → `federation-integration.yml`, roadmap §21). If a mirror drifts from its
source-of-truth, that check fails closed.

## 🤖 Continuous Agent Loop & Federation Roles

`supremeai-open` acts as the **Public Face / Embassy** (`scripts/agents/continuous_agent_loop.py`), providing an open zero-dependency CLI entrypoint for any agent or contributor. The internal engines, schedulers, and worker daemons reside in the `supremeai-agents` core satellite.

> **Continuous Loop Core Doctrine:**
> *"কার কী দায়িত্ব তা বুঝিয়ে দেওয়া, দায়িত্ব পালনের সময় কোন রুলস মানতে হবে আর কোনটা মানবে না তা বেঁধে দেওয়া, এবং কাজে লাঠি লাগবে নাকি ছুরি লাগবে (Weapon Provisioning) তা সুনির্দিষ্ট করে দেওয়াই Continuous Agent Loop-এর মূল কাজ।"*

### 1. Two-Paradigm Dispatch Architecture
- **Task-Driven Roles (Event & Runway Driven):**
  - **Coder:** Feature/bug implementation within scope under atomic single-lock.
  - **CI Fixer:** Preempts backlog to heal failing PR checks and unblock the runway.
  - **Task Auditor:** Pre-landing verification for boundaries, secret leaks, and decision ledgers.
- **Time-Driven / Platform-Driven Roles (Scheduled Cron & Periodic Probing):**
  - **Ecosystem Scout:** Global tech radar scouring outside innovations (Meta, Anthropic, OpenAI) with full-spectrum evaluation (pros, cons, "এটা করা যাবে না", risks) producing min. 10 proposals.
  - **Federation Auditor:** Internal inspector auditing commit parity, drift, and cleanliness across the 11 canonical satellites.
  - **Human Eye (Visual QA):** SupremeAI's PR & Styling Team (*"বস, এই ড্রেসে ভালো লাগছে না, ওই ড্রেস পরেন"*), profiling visual polish, typography, and premium user experience (Issue create only).
  - **Rules Breaker:** Dual-vector chaos hacker (breaks existing guards + exploits unprotected gaps to measure worst-case damage, filing failing tests and P0 issues).
  - **3rd-Party Platform Guardian:** High-frequency prober for external model latency and quotas (auto-failovers if possible, else creates issues).

### 2. Weapons & Scoped Permissions Matrix (লাঠি বনাম ছুরি — RBAC)

| Role | Weapon Metaphor | Scoped Tools & Permissions | Forbidden Operations |
|---|---|---|---|
| **Solver** *(Coder + CI Fixer)* | Surgical Knife & Defibrillator 🔪⚡ | Code edit, Local test runner, Git branch, CI fix & PR create | Claiming without atomic lock, breaking scope |
| **Auditor** *(Federation + Task)* | Ledger Microscope & Stamp 🔬📋 | Multi-repo git reader (14 federation repos / 8 active anchors), PR compliance | Direct source code edits |
| **Ecosystem Scout** | Long-Range Telescope 🔭 | Web search, URL readers, High-signal synthesis reports | Local code edits, uncritical hype/speculative tickets |
| **Human Eye** | Stylist Camera & Mirror 📸 | Browser subagent, Screenshot capture, Issue create | Direct code or CSS edits |
| **Rules Breaker** | Sledgehammer & Lockpick 🔨 | Adversarial fuzzers, `tests/adversarial/` commits | Production damage, writing self-patches |
| **Platform Guardian** | Routing Circuit Breaker 🔌 | Provider prober, Dynamic Failover Toggle, Issue create | Corrupting permanent configuration files |

---

## Bridge — external agent work submission (v1)

Agents work **in public**; code lands **private** after the full constitutional gate battery.

> **Lane eligibility:** the `bridge/<task-id>` branch lane requires **collaborator write access**
> to this repo (proxy bots / org agents). Zero-credential agents **cannot push branches here** —
> use §2.1 Pathway 2 of [`AGENTS.md`](./AGENTS.md) (fork + PR) instead; the PR is ingested by the
> same internal automation.

1. Push your patch branch to this repo: `bridge/<task-id>` (diff base = `main`).
2. Open a **Bridge Work Order** issue (issue template above).
3. The bridge (running inside the private codebase) validates fail-closed, applies the patch,
   and opens a gated PR. Status flows back to your issue via labels + comments.

This repo's `main` stays byte-clean: the bridge never writes to it — only the federation
mirror CI maintains the public artifacts above.

---

## Contributing

New here? Start with **[`docs/CONTRIBUTING.md`](https://github.com/Supremeai-bd/supremeai-archive/blob/main/docs/CONTRIBUTING.md)** — the
zero-credential contributor guide covering both human (fork + PR) and autonomous-agent
(8-step loop, MCP Tower lane) workflows, the 3-tier verification contract, scope caps,
and a field-tested troubleshooting table. The governance contracts live in
[`AGENTS.md`](./AGENTS.md) — the Single Door SSOT (the former AGENT_RULES.md was deleted by #1526).
<!-- heartbeat: 2026103106 -->
