# SupremeAI — AGENTS.md

> **Agent Entry Point / Universal Constitution**
>
> **Freedom:** Agent controls **HOW** to solve an assigned task inside its contract.
> **Control:** Admin/System controls **WHERE, WHAT, ACCESS, LIMITS, STOPPING and major architectural decisions**.
>
> **Canonical rule source:** [`AGENT_RULES.md`](./AGENT_RULES.md)
> **Governance issue:** [#3095](https://github.com/Supremeai-bd/supremeai/issues/3095)

## 0. The Agent Loop — One Simple Entry Point

Every agent runs the same 8-step cycle (Roadmap v2.0 Phase 1, #4143). The dispatcher IS the existing `scripts/agents/continuous_agent_loop.py` — never build a new loop.

> **Operational Note for External / Community Agents on this Repository:**  
> If you are an external or web AI working on Supremeai-bd/supremeai-open without CLI/vault access:
> - **Primary & Recommended (Zero-Credential):** Follow **§2.1 Pathway 1 (MCP Control Tower Bridge)**. The MCP Control Tower directly provides relevant code, task specifications, and context to you via MCP tools. You implement in-context and return the solution; the Control Tower proxy bot handles branch creation, commits, and PR submission.
> - **Alternative (With GitHub Token / Local CLI):** Follow **§2.1 Pathway 2 / §8 Bridge Lane** (fork + branch `contributor/issue-<task-id>` or `bridge/<task-id>` + PR). Use the standalone open runner: `python scripts/agents/continuous_agent_loop.py`.

*(Note: In the table below, internal monorepo scripts such as `atomic_claim.sh` and `role_registry.py` run on the private backend CI Guardian. Open contributors use `scripts/agents/continuous_agent_loop.py` to drive all 8 steps locally.)*

| Step | Do | Existing tool (Public / Monorepo) |
|---|---|---|
| 1. Understand | Read the task issue + linked context | `gh issue view <n>` / `continuous_agent_loop.py --issue <n>` |
| 2. Rules | Load governing rules + your role contract | [`AGENT_RULES.md`](./AGENT_RULES.md) §1–§3 · `scripts/agents/role_registry.py` |
| 3. Inspect state | Queue, open PRs, active claims, token freshness | `continuous_agent_loop.py` · `issue_queue_manager.py audit` |
| 4. Claim | Atomic claim (session marker; no claim, no work) | Session branch / `scripts/ci/atomic_claim.sh` |
| 5. Work | Smallest safe change inside declared scope | Standard Task Contract (`continuous_agent_loop.build_task_contract()`) |
| 6. Verify | 3-tier contract (process phases): reflection → boot smoke → tests · evidence tiers SSOT: AGENT_LOOP_SPEC §4 | `continuous_agent_loop.py --verify-only` |
| 7. Record | PR with full template + Test Evidence (+ meaningful decision note; `Closes #N` must also ride in the **commit message** — squash auto-close doctrine, AGENT_RULES U8) | `continuous_agent_loop.py --auto-pr` / REST PR create |
| 8. Return | Report outcome **with fresh-board re-check** (#4177), release claim, loop back | `continuous_agent_loop.py` + `gh pr list` re-poll |

Hard boundaries during the loop: gates outrank agent preference (§1.4) · no competing/duplicate PRs for issues with an active open PR (AGENT_RULES.md U4) · scoped credentials only (`credential_manager` — master vault keys never reach children) · single-vs-multi execution follows Rule B (`role_registry.plan_task_execution()` — advisory).

## 1. First Rule: Authority

1. Admin's explicit instruction has highest authority, subject to safety: if an instruction may cause data loss, production outage or security breach, stop and request confirmation.
2. When no direct Admin decision exists, this file + [`AGENT_RULES.md`](./AGENT_RULES.md) are the agent baseline. Other documents explain context; they do not silently override the constitution.
3. Major architectural, governance, policy or planning changes require an `ADMIN_DECISION` issue and must wait for the decision before implementation.
4. System-enforced gates outrank agent preference. An agent must never bypass a safety, scope, freshness, template, permission, duplicate, evidence or merge gate.

## 2. Second Rule: Stateless Task Lifecycle

Every agent is a task execution role, not a permanent identity:

```text
READ ENTRYPOINT
  → LOAD AGENT_RULES
  → LOAD TASK/ROLE CONTRACT
  → CHECK GROUP + PRIORITY + SEQUENCE
  → PREFLIGHT MAIN + OPEN PRs + EXISTING WORK
  → CLAIM (atomic_claim.sh — BEFORE any code change or PR)
  → WORK INSIDE SCOPE
  → VERIFY (tests + gates + evidence)
  → RECORD EVIDENCE + DECISION LEDGER
  → PR / HANDOFF (only AFTER claim is posted)
  → BOARD-FRESHNESS RE-CHECK (#4177 — re-poll open PRs + queue before declaring done)
  → CLEAN EXIT (release locks, stop heartbeat, trim worklog)
  → RERUN continue_loop.py (next task immediately — no sleep, per Rule 5)
```

Never invent a parallel workflow. The task contract is the common envelope for every model and role.

**Board-freshness rule (#4177):** the snapshot taken at task-start is not the whole mission. Work often takes long enough for new PRs/issues to arrive mid-flight — a completion declaration made against the start-time snapshot silently drops them. Before declaring any task, batch or founder-directed mission "done", re-poll the board and report the fresh snapshot; handle new arrivals or explicitly list them as outstanding (per [`AGENT_RULES.md`](./AGENT_RULES.md) U5/U7/U8).

**Critical ordering:** `atomic_claim.sh` must run **BEFORE** `gh pr create`. A PR opened without a prior claim will be auto-closed by the Claim Gate (#2644, #2892). The claim comment on the issue is the evidence the gate checks — it must exist before CI runs.

## 2.1 Autonomous Work Submission (Zero-Admin Policy)

Admin work budget is **≤ 0.01%**. Agents (local, cloud, web AI, or external bots) must submit work autonomously using whichever of the following 3 pathways matches their operational capabilities:

### Pathway 1: MCP Control Tower Bridge (Zero-Credential Submission)
* **Target:** Agents connected via Model Context Protocol (MCP) to `supremeai-control-tower` (Claude, Cursor, Antigravity, or MCP clients).
* **Remote MCP Server:**
  - Standard Streamable MCP: `https://supremeai-mcp-tower.onrender.com/mcp`
  - SSE Endpoint: `https://supremeai-mcp-tower.onrender.com/sse`
* **Zero-Credential Connection Config (`mcp.json`):**
  ```json
  {
    "mcpServers": {
      "supremeai-control-tower": {
        "url": "https://supremeai-mcp-tower.onrender.com/mcp"
      }
    }
  }
  ```
  *(Tokenless connections are automatically registered as guest viewers with read-only scopes via zero-manual-registration).*
* **Execution & Code Delivery:**
  1. **Code & Task Provisioning:** The MCP Control Tower directly provides relevant source files, task context, and schemas to the agent via MCP tools (`bridge_work_order`, `bridge_guide`, `github_read_file`). The agent does not need to guess, clone private repos, or have local filesystem access.
  2. **In-Context Implementation:** The agent analyzes the provided code, develops the fix/feature inside its context, and submits the completed files via `bridge_submit_patch`.
  3. **Autonomous Submission & Landing:** Control Tower's server-side GitHub App automatically creates the `bridge/<task-id>` branch on `Supremeai-bd/supremeai-open`, commits the files, and creates the Bridge Work Order issue autonomously.
  4. **Zero Credentials Needed:** Agent needs **zero** direct GitHub tokens, private keys, or collaborator write access.

### Pathway 2: Public Window Fork & Pull Request (`supremeai-open`)
* **Target:** External web agents without MCP or credentials (e.g., Mistral, Z.ai, ChatGPT, external contributors).
* **Public Repository:** [`https://github.com/Supremeai-bd/supremeai-open`](https://github.com/Supremeai-bd/supremeai-open)
* **Execution:**
  1. Agent forks the public `Supremeai-bd/supremeai-open` repository (zero access needed).
  2. Pushes proposed changes to its fork branch.
  3. Opens a Pull Request against `Supremeai-bd/supremeai-open:main`.
  4. Internal automation ingests the PR, ports changes to the private pipeline, verifies, and merges without admin manual effort.

### Pathway 3: Ephemeral JIT Lease (Automated CLI / Script Agents)
* **Target:** Scripted workers, runners, or bots executing with terminal/API access.
* **Execution:**
  1. Mint a 1-hour time-limited lease token via `scripts/agents/credential_manager.py`:
     ```bash
     python scripts/agents/credential_manager.py --lease <agent-name> --ttl 3600
     ```
  2. Push the branch using the ephemeral token:
     ```bash
     git push https://x-access-token:<TOKEN>@github.com/Supremeai-bd/supremeai.git <branch>
     ```
  3. Create the PR via GitHub REST API. Internal CI Guardian evaluates and merges autonomously.

### 2.2 Loop-Granted Authority — No Permission-Asking (U10)

The loop **is** the permission. Agents never emit "should I start / বললেই পরের batch শুরু করছি / shall I proceed?" style output. When self-checkable preconditions pass (claimable issue, no admin gate, fresh board per #4177, valid credentials, green CI), work proceeds immediately; status reports state facts, never permission questions. Escalation is reserved for hard blockers only (missing credentials, destructive ops, ADMIN_DECISION gates, contradictory instructions). Canonical rule: [`AGENT_RULES.md`](./AGENT_RULES.md) **U10**.

## 3. New Agent: Required Reading Path

A newly added agent should not need tribal knowledge. Start here, then follow the links in order:

1. **This file** — authority, lifecycle and navigation.
2. **[ECOSYSTEM_MAP.md](./ECOSYSTEM_MAP.md)** — federation repository directory and cross-repo target routing.
3. **[AGENT_RULES.md](./AGENT_RULES.md)** — global policies + role policies + verification + tooling.
4. **Task Contract / Issue Template** — exact task type, scope, group, priority, sequence, dependencies and acceptance criteria.
5. **Relevant group/domain document** — only the context required by the assigned task.
6. **Issue + related PRs + evidence** — current state before making changes.
7. **After work:** verification + decision ledger + linked evidence.

If a referenced document is missing or contradictory, do not guess. Report the gap and follow the Admin Decision path when required.

## 4. Agent Freedom vs Boundary

### Agent may decide
- implementation details inside assigned scope;
- how to debug and test;
- which existing compatible pattern to reuse;
- the smallest safe implementation approach;
- evidence-backed local optimizations that do not alter protected architecture/policy.

### Agent may not decide alone
- major architecture/workflow topology changes;
- security/permission boundary changes;
- governance/rule changes;
- destructive or irreversible operations;
- broad scope expansion;
- replacing an established architecture with a substantially different one without evidence and required approval.

If an existing design appears unnecessarily complex, do **not** silently preserve it forever and do **not** silently rewrite it:

```text
Finding → Evidence → Simpler Alternative → Impact
       → ADMIN_DECISION (when architectural) → Wait
```

## 5. Document Circle

SupremeAI documentation is a connected ecosystem, not isolated files.

- [`AGENT_RULES.md`](./AGENT_RULES.md) — agent policy constitution.
- [`README.md`](./README.md) — boundary + artifact table · [`docs/CONSUMERS.md`](./docs/CONSUMERS.md) — consumer onboarding · [`api-schemas/gateway.openapi.yaml`](./api-schemas/gateway.openapi.yaml) — the stable API surface.
- Domain/planning documents — detailed context.
- Every canonical document should expose `related_docs`, source issue/PR and status where applicable.
- Prefer repository-relative links for stability; include canonical GitHub URLs where navigation outside the repo is useful.
- Do not create orphan canonical documents.
- When a document is renamed, superseded or split, update inbound/outbound links.

The goal is a navigable circle:

```text
Entry → Rules → Task → Group → Domain Plan
  ↑                                  ↓
  └──── Evidence ← Issue ← PR ← Verify
```

## 6. Core Philosophy

- **Simple + effective > clever + complex.**
- **Incremental improvement > premature scale.**
- **Preserve working architecture by default.**
- **Complexity must earn its existence.**
- **Evidence before action.**
- **Issue validity before implementation.**
- **Existing work before new work.**
- **System guards enforce critical boundaries; agents do not police themselves.**

## 7. Machine Enforcement

The canonical validator is:

```bash
python scripts/ci/generate_agents_md.py --check
```

It should remain the enforcement entrypoint for this two-file constitution and be extended as the document-circle contract evolves.

## 8. Bridge — External / Public Agent Lane

No private-repo access? All work flows through the public bridge on this repo:

> **Lane eligibility:** Zero-credential agents submit directly via **§2.1 Pathway 1** using the `bridge_submit_patch` MCP tool without needing GitHub write access. Alternatively, external agents without MCP access can use **§2.1 Pathway 2** (fork + PR).

1. **Patch branch** `bridge/<task-id>` on this repo (diff base = `main`). Created autonomously via `bridge_submit_patch` or pushed by authorized agents. This repo's `main` is never written by agents.
2. **Bridge Work Order** issue (issue template: `.github/ISSUE_TEMPLATE/bridge-work-order.yml`).
3. **Bridge intake** (inside the private codebase) validates the work order fail-closed:
   task-id format → dedup → diff size/file limits → secret-pattern scan → forbidden-path check.
   Clean orders become a private PR through the full constitutional gate chain; results are
   reported back on your issue (`bridge:in-gates` / `bridge:landed` / `bridge:rejected` / `bridge:admin-review`).

Universal rules U1–U9 and the authority rules §1 apply unchanged to bridge work.
Machine contract: `scripts/bridge/README.md` in the private codebase.

---

**Next:** Read [`AGENT_RULES.md`](./AGENT_RULES.md) and load only the role/task policy required for the current assignment.
