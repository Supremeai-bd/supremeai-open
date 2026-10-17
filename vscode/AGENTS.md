# SupremeAI VS Code Extension — AGENTS.md

> **Governing Constitution for Supremeai-bd/supremeai-vscode**
>
> **Freedom:** Agent controls **HOW** to implement features inside the declared contract.
> **Control:** Admin/System controls **WHERE, WHAT, ACCESS, LIMITS, STOPPING and major architectural decisions**.

## 1. Authority & Governance

1. **Admin Decision Mandate:** Admin explicit instructions hold the highest authority. Destructive operations or architecture deviations require prior approval.
2. **Constitutional SSOT:** This document and the central [`AGENT_RULES.md`](https://github.com/Supremeai-bd/supremeai-open/blob/main/AGENT_RULES.md) govern all extension code.
3. **Public-First Ingress (Two-Tier Invariant #430):**
   - **No Claim -> No Branch:** Claim marker (`status:claimed` + `<!-- atomic-claim -->`) must exist before branch checkout.
   - **No Branch -> No Push:** Pushes to unclaiimed issues are rejected. All PRs flow through `Supremeai-bd/supremeai-open` via bridge dispatches.

## 2. Extension Scope & Boundaries

1. **Pure Client Surface:** The VS Code extension is a lightweight bridge to the MCP Control Tower.
2. **Zero Inlined Secrets:** Master API keys, Infisical tokens, and cloud infrastructure keys must never be committed to or bundled into the extension package.
3. **Fail-Closed Networking:** Network failures to the Control Tower degrade gracefully to offline indicators; no unhandled promise rejections or UI freezes.
4. **Clean Disposal:** All commands, status bar items, and polling intervals must register with `ExtensionContext.subscriptions` to eliminate memory leaks upon deactivation.
