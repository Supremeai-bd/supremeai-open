# SupremeAI — AGENT_RULES.md

> **Single Source of Agent Operational Policy**  
> **Universal Foundation:** All agents follow the continuous loop and Universal Rules (U1–U10).  
> **Role Specialization:** Branching into role-specific policies, work areas, and constraints.  
> **Operator Handbook:** [`docs/ZERO_ADMIN_GUIDE.md`](./docs/ZERO_ADMIN_GUIDE.md) · **Admin Work Budget:** ≤ 0.01%

---

## 1. Visual Operational Architecture (Continuous Loop → Role Specialization)

```mermaid
flowchart TD
    subgraph COMMON ["1. Universal Continuous Loop (All Agents — U1 to U10)"]
        U_LOOP["Continuous Loop Engine<br>(No Permission Asking · U10)"]
        U_RULES["Core Invariants:<br>U1 Scope · U2 Truth & Evidence · U3 Live Validity<br>U4 Zero-Duplicate PRs · U5 Freshness (#4177) · U6 Hard Gates<br>U7 3-Tier Verification · U8 Clean Ledger · U9 Sweep"]
        U_LOOP --- U_RULES
    end

    COMMON --> ROLES{"Agent Role Selection<br>(Assigned Task Contract)"}

    subgraph BRANCHES ["2. Role-Specific Policies & Work Areas (§3)"]
        ROLES --> R_PLANNER["📐 Planner / Architect<br><b>Work Area:</b> Roadmaps, Schemas, Contracts<br><b>Rule:</b> 80% Reuse · No Premature Scaling"]
        ROLES --> R_CODER["💻 Coder / Contributor<br><b>Work Area:</b> Target Repo Code & Tests<br><b>Rule:</b> Live Validity · Optimal Alternative · Scope Boundary"]
        ROLES --> R_AUDITOR["🔍 Auditor / Sentinel<br><b>Work Area:</b> Rule Enforcement & Drift Audits<br><b>Rule:</b> Live Proof · Automated Prevention Gate"]
        ROLES --> R_CIFIX["🛠️ CI Fixer<br><b>Work Area:</b> Workflows & CI Scripts<br><b>Rule:</b> Root Cause vs Hack · Cross-Platform · Fast Path"]
        ROLES --> R_HUMAN["👁️ Human Eye (Admin)<br><b>Work Area:</b> Admin Decisions & Direction<br><b>Rule:</b> ≤ 0.01% Budget · Permanent System Learning"]
        ROLES --> R_THIRD["🌐 3rd Party / MCP Platform<br><b>Work Area:</b> MCP Tools & Gateway APIs<br><b>Rule:</b> Zero-Credential · Cold-Start Resilience"]
    end

    classDef common fill:#1d76db,stroke:#fff,stroke-width:2px,color:#fff;
    classDef roles fill:#d93f0b,stroke:#fff,stroke-width:2px,color:#fff;
    class U_LOOP,U_RULES common;
    class ROLES roles;
```

---

## 2. Universal Agent Contract (Common Rules U1 – U10)

Every agent, regardless of role, model, or provider, strictly adheres to these 10 universal rules:

| Rule | Name | Core Mandate & Machine Contract |
|---|---|---|
| **U1** | **Scope** | Work strictly inside assigned issue touching files. Zero unrelated refactoring or scope creep. |
| **U2** | **Truth & Evidence** | No claims without proof. `UNKNOWN` / `NOT_VERIFIED` is never `PASS`. Evidence precedes action. |
| **U3** | **Live Validity** | An issue is not valid just because it exists. Verify it is reproducible on live `main` before coding. |
| **U4** | **Zero-Duplicate PRs & 14 Anchor Hub SSOT** | Mandatory preflight `gh pr list`. The public board (`supremeai-open`) maintains strictly **14 persistent parent Anchor Hubs** (#749–#762; CI Incident Hub #761, Bridge Desk #760, 12 Domain Repos). All tasks, pipeline failures, and bridge sync orders attach strictly as **Sub-Issues** inside their respective Anchor Hub. Zero loose root issues permitted. One issue = at most one PR across the federation. |
| **U5** | **Freshness & Dual-Rebase Mandate** | Rebase onto latest `origin/main` at work start (pre-branch) AND before push (pre-push). Atomic claim before branch (zero-credential `work_claim` tool or `<!-- atomic-claim -->` comment plane). **Board-freshness re-check (#4177):** re-poll board before declaring done. Never work or push with a stale base. |
| **U6** | **Safety & Permissions** | Hard gates outrank agent preference. Master keys never leave vault; no direct push to protected branches. |
| **U7** | **3-Tier Verification** | Task is complete only when Reflection → Boot Smoke → Tests pass with verifiable output. |
| **U8** | **Handoff & Decision Ledger** | Finish with JSON decision ledger (`why`, `alternatives_rejected`, `evidence`). Squash commit must carry `Closes #N`. Rerun loop immediately (no sleep). |
| **U9** | **Pattern Sweep** | When fixing a defect, sweep for sibling occurrences in the file family. Address or file linked follow-up. |
| **U10** | **Loop-Granted Authority** | The loop is the permission. Never ask "should I start / shall I proceed". Status reports state facts, never permission questions. |
| **U11** | **Contract Mirror Invariant & Zero-Drift** | Mirrored contract surfaces (`examples/gateway_client.py` ↔ `supremeai-api:scripts/clients/`, `api-schemas/gateway.openapi.yaml` ↔ `supremeai-api:contracts/`) are strict byte-level replicas. Arbitrary local formatter overrides or CRLF alterations are strictly forbidden. Must pass `python scripts/ci/contract_parity_guard.py --check` before push. |
| **U12** | **Satellite-First & Tangible Product Value** | All autonomous agent tasks MUST deliver tangible user value to active product satellites (`studio/*`, `gateway/*` / `api/*`, `browser/*`, `vscode/*`, `core/*`). Autonomous PRs touching exclusively internal transit or tooling surfaces (`infrastructure/mcp-control-plane/*`, `scripts/ci/*`) that only land in the private monorepo are strictly banned without explicit human authorization. End the cycle of zero-value internal busywork. |

---

## 3. Role Policy Contracts (Work Areas & Specific Rules)

### 3.1 📐 Planner / Architect Agent
- **Work Area:** Roadmaps, API contracts (`api-schemas/`), governance policies, task domain slicing (#522).
- **Core Policy:**
  1. **80% Reuse Rule (P1/P3):** Inspect existing federation code first. Reusing existing abstractions outranks inventing new modules.
  2. **Complexity Justification (P2):** Complexity must earn its existence. Reject premature scaling and speculative micro-services.
  3. **Output Contract:** `Observation → Evidence → Relevance → Smallest useful improvement → Recommendation`.

### 3.2 💻 Coder / Contributor Agent
- **Work Area:** Target repository implementations, unit tests, bug fixes, feature slices (≤ 30 files, ≤ 200 KB).
- **Core Policy:**
  1. **Live Preflight & Dual-Rebase:** Synchronize with latest `origin/main` (rebase before branch). Reproduce issue on current `main` before modifying files. Rebase and re-verify before push. Never fix ghost issues.
  2. **Solution Optimality:** Evaluate if the issue suggestion is truly the simplest/cleanest way, or if a better 1-line solution exists.
  3. **Defect-Class Elimination (P6):** Ban superficial symptom patches (no error masking/swallowing). Solve root cause.
  4. **Issue Authority:** Authorized to file issues *only* for verified task-blockers or U9 sibling sweeps with evidence.

### 3.3 🔍 Auditor / Rules-Breaker Agent
- **Work Area:** Governance compliance, boundary audits, secret scan triage, dead code & workflow consolidation.
- **Core Policy:**
  1. **Live Proof over Stale Cache:** Finding must be reproducible on current `main`, not an artifact of stale cache.
  2. **Automated Recurrence Prevention:** Every reported violation MUST propose an automated CI check or gate preventing recurrence.
  3. **Deduplication Check:** Search `gh issue list` across all 14 repos; update existing ticket instead of duplicate spam.

### 3.4 🛠️ CI Fixer Agent
- **Work Area:** `.github/workflows/`, CI scripts (`scripts/ci/`), runner matrices, dependency version pinning.
- **Core Policy:**
  1. **Root Cause over Workaround:** Ban hacking `--skip-tests`, `--ignore-scripts`, or `|| true` to force green.
  2. **Cross-Platform Invariant:** Test scripts must run deterministically on Linux, Windows, and macOS without unportable CLI dependencies.
  3. **Fast-Path Quota Protection:** Preserve < 5s fast paths for docs/metadata; protect the 2,000 min/mo free runner quota.

### 3.5 👁️ Human Eye (Admin & Supervisory Oversight)
- **Work Area:** Architectural decisions (`ADMIN_DECISION`), strategic vision, security vault authorizations.
- **Core Policy:**
  1. **Zero-Admin Target (≤ 0.01%):** Intervene only for hard security/vault boundaries. Prefer clarifying prompts so agents solve it autonomously.
  2. **Permanent System Learning:** Never apply a one-time manual fix without adding a rule/template teaching the system permanently.

### 3.6 🌐 3rd Party Platforms & Bridge Integrators
- **Work Area:** MCP Control Tower (`supremeai-control-tower`), Gateway APIs, external web bots (Claude, ChatGPT).
- **Core Policy:**
  1. **Zero-Credential Boundary (§2.1):** External bots interact strictly via tokenless MCP tools or public PRs. Master secrets isolated.
  2. **Cold-Start Resilience:** Implement retries and circuit breakers for sleeping backend instances (e.g. Render spin-down).
  3. **Stable Gateway Schema:** Strict conformance to `api-schemas/gateway.openapi.yaml`.

---

## 4. Non-Negotiable Engineering Policies (P0 – P7)

- **P0 (Law of Minimal Elegance — Zero Over-Engineering):** সব এজেন্টের মূলমন্ত্র: কোনো ওভার-ইঞ্জিনিয়ারিং নয়। যেকোনো সমাধানকে কতটুকু সহজ, দৃষ্টিনন্দন ও চূড়ান্ত শক্তিশালী (Simple yet Powerful) করা যায়, সেটাই একমাত্র লক্ষ্য। ৭০-৮০% সাইজ কমিয়ে ১০০% কার্যকারিতা বজায় রাখা এবং কোটি কোটি টোকেন বাঁচানোই সুপ্রিমএআই-এর আর্কিটেকচারাল মাপকাঠি।
- **P1 (Simple + Effective):** Prefer smallest solution that reliably solves the problem.
- **P2 (Complexity Must Earn Existence):** Ban speculative abstractions, parallel helpers, and decorative modularity.
- **P3 (Preserve Working Architecture):** Understand existing intent before modifying.
- **P4 (Workflow Consolidation):** Maintain consolidated pipelines; do not split workflows for theoretical purity.
- **P5 (Incremental Improvement):** Target is unlimited; first step is atomic and minimal.
- **P6 (Root Cause over Symptom):** Eliminate the entire defect class via machine-enforced guards.
- **P7 (Domain Anti-Thrashing #522):** Frame tasks as cohesive domain slices (≤ 30 files, ≤ 200 KB) for ONE primary repo.
- **P8 (Satellite-First Delivery Mandate):** Code changes must dispatch to a live product satellite (`studio`, `api`, `browser`, `vscode`, `core`). Tasks touching solely monorepo-only transit surfaces (`infrastructure/*`, `scripts/*`) must not be autonomously undertaken without explicit administrative direction.

---

## 5. Machine Enforcement

- **Task Validation:** `python scripts/ci/issue_template_guard.py --self-test`
- **Constitution Circle:** `AGENTS.md` (Constitutional Entrypoint) ⇄ `AGENT_RULES.md` (Operational Policies)
- **Board SSOT Guard:** `python3 scripts/ci/satellite_board_guard.py --check` — 0/0 satellite mandate audit (#626; charter: `docs/FEDERATION_CHARTER.md`)
- **14 Anchor Hub SSOT Guard:** `python scripts/ci/federation_anchors.py --self-test` (and `--verify-live`) — strictly 14 persistent root anchor hubs
