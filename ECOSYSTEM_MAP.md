# 🗺️ SupremeAI Federation Ecosystem Map

> **The Definitive Repository Guide for Autonomous, External & Free AI Agents**  
> **Host Repository:** [`Supremeai-bd/supremeai-open`](https://github.com/Supremeai-bd/supremeai-open)  
> **Architecture:** Public Gateway / Embassy to Private Federated Systems  

---

## 1. Overview: The Public Front Door

If you are an AI agent (ChatGPT, Claude, Mistral, Cursor, or an open-source contributor), **this repository is your starting point and operational workspace**.

You do not need credentials or access to private repositories. You can inspect public interfaces, understand system requirements, develop code changes right here, and submit them. Our automated **Bridge Pipeline** will validate and land your code safely in the appropriate private destination.

---

## 2. Federation Repository Directory

The SupremeAI platform consists of specialized repositories under the **`Supremeai-bd`** organization:

| Repository | Scope & Responsibility | What Can Be Changed From Here |
|---|---|---|
| **`supremeai-open`** *(Current)* | **Public Boundary & Ambassador.** Holds public contracts, client SDKs, examples, and agent instructions. | Direct PRs / Issues on this repository. |
| **`supremeai`** | **Core Monolith & CI Safety Anchor.** Orchestration, MCP control plane, and constitutional merge gates. | Core logic, MCP tools, and integration tests via Bridge. |
| **`supremeai-api`** | **Unified Provider Gateway.** Multi-LLM provider routing, API-key authentication, and fallback chains. | Gateway contracts, OpenAPI specs, and client scripts. |
| **`supremeai-studio`** | **Web UI & Experience.** React/Vite dashboard, design tokens, and frontend shell components. | UI components, design tokens, and user experience fixes. |
| **`supremeai-infrastructure`** | **Cloud Operations & CI/CD.** Terraform, Cloudflare Workers, and Render configs. | Read-only from public; managed internally. |
| **`supremeai-core`** | **Proprietary Intelligence Core.** *(Private)* Orchestration, planning, decision, and execution intelligence — the federation's decision moat. | Not directly changeable from public; deep changes via Bridge Work Orders. |
| **`supremeai-sdk`** | **Stable External Contracts.** *(Public)* API/event/task schemas and protos — the contract-first boundary layer for external integrators. | Contract PRs and schema proposals on the SDK repository. |
| **`supremeai-mcp-control-plane`** | **Governed Tool Registry.** *(Private)* Policy enforcement, credential brokering, and the autonomy kill-switch powering the live Tower. | Not directly changeable from public; internal management only. |
| **`supremeai-archive`** | **Institutional Memory.** Append-only worklogs, ADRs, roadmap snapshots, and lessons — no critical decision is ever lost. | Read-only from public; append via internal automation. |

---

## 3. How to Propose Changes for Any Target Repository

You can modify files for other repositories by following the **Bridge Work Order Protocol**:

```
Agent Forks/Clones supremeai-open
  │
  ├─ 1. Create a branch: `bridge/<task-id>` (e.g. `bridge-20261013-add-streaming-client`)
  ├─ 2. Make your proposed changes within the declared scope.
  └─ 3. Open a Bridge Work Order issue (or PR) specifying:
        • Task ID: `bridge-YYYYMMDD-<slug>`
        • Target Repo: (e.g. `Supremeai-bd/supremeai-api`)
        • Summary & Scope Paths
        • Test Evidence & Rollback Plan
```

### Routing Rules (Where Your Patch Lands):
- **Gateway & APIs:** Changes to `api-schemas/` or `examples/` are mirrored directly into `supremeai-api`.
- **Frontend / Studio:** Changes targeting frontend components are routed into `supremeai-studio`.
- **Core / Tools:** Changes targeting MCP tools and agent definitions land in `supremeai`.

---

## 4. Discovery: Finding Open Tasks

To discover what needs to be done:
1. **Check Issues:** Look for issues labeled `bridge:queued` in this repository's Issues tab.
2. **Parity & Audit Checks:** Run local tests or validation scripts (`examples/gateway_client.py`). Any bug, lint failure, or outdated example is a claimable task.
3. **Contracts & Specs:** Compare `api-schemas/gateway.openapi.yaml` with client implementations to ensure full feature parity (streaming, error handling, retries).

---

## 5. Security & Safety Invariants

Every bridge patch is inspected by fail-closed automated scanners:
- **Diff Size:** ≤ 200 KB diff and ≤ 30 files per task.
- **Zero Secrets:** Never include API keys, tokens, or credentials in diffs or commit messages.
- **Protected Paths:** Changes targeting `.github/`, `.env*`, or credentials require explicit admin review.
