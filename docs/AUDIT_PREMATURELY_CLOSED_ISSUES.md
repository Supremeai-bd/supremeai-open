# Audit Report: Prematurely Closed Issues (Doc/Spec Only, Unimplemented in Code)

> **Generated on:** 2026-10-27  
> **Repository:** `Supremeai-bd/supremeai-open`  
> **Investigation Root Cause:** Automated bridge submissions generated PRs with `Closes #<ID>` for documentation/specification-only commits (`docs/bridge/*`), prematurely closing critical feature and bug-fix issues in GitHub before any implementation code reached `studio/*`, `gateway/*`, or `core/*`.

---

## 1. Executive Summary

A comprehensive scan of the repository commit history reveals **30 issues** that were marked **Closed (Completed)** on GitHub via automated PR merges, where **only a markdown specification or documentation was committed**. 

In reality, **no corresponding functional frontend or backend code was merged** for these issues.

---

## 2. Categorized Inventory of Prematurely Closed Issues

### Category A: Missing Core Product Features (Monica Gap Map — Bangla Audit)
These are high-priority user-facing features that users expect to see, but only have markdown specifications in `docs/bridge/`:

| Issue # | Priority | Feature Name / Scope | Premature Commit | Files Touched (Specs Only) | Actual Code Status |
|:---:|:---:|:---|:---:|:---|:---:|
| **#1462** | **P1** | **Studio Multi-Model Picker** | `7b8096ac` | `docs/bridge/bridge-20261027-audit-gap-model-picker.md` | ❌ **Unimplemented** (Studio UI has no provider health dots or multi-model selector) |
| **#1464** | **P2** | **AI Multi-Chat (Side-by-Side View)** | `9c7d30c7` | `docs/bridge/bridge-20261027-audit-gap-multichat-compare.md` | ❌ **Unimplemented** (No side-by-side comparison screen) |
| **#1466** | **P2** | **Agent Mode (Task Plan & HITL UI)** | `c52cf06f` | `docs/bridge/bridge-20261027-audit-gap-agent-mode.md` | ❌ **Unimplemented** (Agent toggle & approval cards not in Studio) |
| **#1468** | **P2** | **Tools Suite (Translate, Mindmap, Doc)** | `ae790fa2` | `docs/bridge/bridge-20261027-audit-gap-tools-suite.md` | ❌ **Unimplemented** (Zero tools surfaced in user UI) |
| **#1470** | **P1** | **Memory-Aware Chat UX (Graph View)** | *(Queue)* | `docs/bridge/bridge-20261027-audit-gap-memory-chat-ux.md` | ❌ **Unimplemented** (Memory entities hidden from chat) |
| **#1474** | **P2** | **Image Generation Studio Tab** | `120cd8a7` | `docs/bridge/bridge-20261027-audit-gap-image-gen.md` | ❌ **Unimplemented** (No image generation tab or route) |
| **#1476** | **P3** | **Browser Extension Store Artifact** | *(Queue)* | `docs/bridge/bridge-20261027-audit-gap-extension-store.md` | ❌ **Unimplemented** (No build artifact prepared for store) |
| **#1478** | **P3** | **Distribution Infra (Status/SEO/Share)** | `c4433ec3` | `docs/bridge/bridge-20261027-audit-gap-distribution-infra.md` | ❌ **Unimplemented** (No public status page or SEO metadata) |
| **#1480** | **P1** | **Consolidated Broken-Feature Tracker** | `09dec15b` | `docs/bridge/bridge-20261027-audit-broken-tracker.md` | ❌ **Tracker Closed** (Closed as soon as doc was added!) |

---

### Category B: Critical System & Production Defects (Unresolved Findings)
These issues describe runtime flaws, security gaps, and operational bottlenecks. The issues were closed when the finding was documented:

| Issue # | Priority | Description / Bug Scope | Premature Commit | Files Touched (Specs Only) | Actual Code Status |
|:---:|:---:|:---|:---:|:---|:---:|
| **#1314** | **P0** | **Render primary-node deploy failure** | `1469dc3e` | `docs/bridge/orders/bridge-20261027-render-poetry-lock.md` | ❌ Lockfile fix not verified in code |
| **#1316** | **P0** | **Plaintext OTP Logging in Browser Sandbox** | `07ceec72` | `docs/bridge/orders/bridge-20261027-otp-plaintext-log.md` | ❌ Security vulnerability open |
| **#1318** | **P0** | **Ghost Bridge Server XSS / Injection Risk** | `3a462d8c` | `docs/bridge/orders/bridge-20261027-ghost-bridge-xss.md` | ❌ Unpatched in code |
| **#1320** | **P0** | **Studio `/admin` Route Guard Bypass** | `178251cf` | `docs/bridge/orders/bridge-20261027-studio-admin-guard.md` | ❌ Client-only route protection flaw |
| **#1322** | **P0** | **Upstash Redis Primary Quota Exhaustion** | `c56c0947` | `docs/bridge/orders/bridge-20261027-redis-quota-ledger.md` | ❌ In-memory ledger fallback not deployed |
| **#1324** | **P0** | **Readiness vs Liveness Smoke Gates** | `e45f7b5f` | `docs/bridge/orders/bridge-20261027-readyz-smoke-gates.md` | ❌ Health checks remain superficial |
| **#1326** | **P1** | **CI failure-masking in `supremeai-core`** | `3fc60268` | `docs/bridge/orders/bridge-20261027-ci-failure-masking.md` | ❌ Core CI error masking still present |
| **#1329** | **P0** | **MCP Tower self-capability broken** | `9000c405` | `docs/bridge/bridge-20261027-tower-self-capability.md` | ❌ Tower tools still report empty AST graphs |
| **#1331** | **P1** | **Guardian Verdict Executor Not Enacted** | `fa4b1720` | `docs/bridge/bridge-20261027-guardian-verdict-executor.md` | ❌ Verdicts evaluated but not executed |
| **#1333** | **P1** | **Client Streaming Retry (SupremeAIService)** | `ae6fd633` | `docs/bridge/bridge-20261027-client-streaming-retry.md` | ❌ Retry mechanism missing in desktop/VSCode |
| **#1335** | **P1** | **Frontend Observability & Error Telemetry** | `6c29c9a5` | `docs/bridge/bridge-20261027-frontend-observability.md` | ❌ Sentry/telemetry missing from UI |
| **#1337** | **P1** | **Feedback Loop / Knowledge Loop Dead** | `5e4cb099` | `docs/bridge/bridge-20261027-knowledge-loop.md` | ❌ Feedback table has 0 active learner rows |
| **#1339** | **P2** | **Studio Bundle Splitting (~1.2 MB uncompressed)** | `e337e402` | `docs/bridge/bridge-20261027-studio-bundle-split.md` | ❌ Heavy chunks not code-split |
| **#1341** | **P2** | **Memory Graph Store Structurally Empty** | `260846be` | `docs/bridge/bridge-20261027-memory-graph-empty.md` | ❌ Node relations not automatically hydrated |
| **#1343** | **P2** | **Tenant Isolation Never Exercised** | `c7d1a2b0` | `docs/bridge/bridge-20261027-tenant-dogfood.md` | ❌ Multi-tenant testing missing |
| **#1345** | **P2** | **Redis Rotation Rule Cooldown Flaw** | `17bb0926` | `docs/bridge/bridge-20261027-redis-rotation-rule.md` | ❌ Buggy cooldown calculation intact |
| **#1347** | **P2** | **Core God-Init Hygiene (`core/__init__.py`)** | `7fe08716` | `docs/bridge/bridge-20261027-core-hygiene.md` | ❌ Bloated 16KB `__init__.py` untouched |
| **#1384** | **P1** | **Verdict-Executor Cron Pipeline Installation** | `6740e43d` | `docs/ci-templates/verdict-executor.yml` | ❌ Template committed to `docs/`, not `.github/` |
| **#1386** | **P2** | **Edge WAF Filter Blocking MCP Tool Calls** | `8e992cee` | `docs/bridge/bridge-20261027-waf-body-filter-hazard.md` | ❌ Request payload sanitizer not active |
| **#1442** | **P2** | **Bridge v2 Unified Diff Lane Gap** | `25d806fa` | `docs/bridge/bridge-20261027-bridge-unified-diff-lane-gap.md` | ❌ Patch applier lacks fallback lane |
| **#1446** | **P0** | **Nightly PyErrorFix SARIF Failure Mask** | `29838b39` | `docs/ci-templates/ci-core-pyerrorfix-guard.yml` | ❌ Guard template not active in satellite |
| **#1456** | **P0** | **AST Sync Nightly Cron Activation** | `517c5c0c` | `docs/ci-templates/graphify-ast-sync.yml` | ❌ Template not wired to workflow |
| **#1458** | **P2** | **Stale CI Orders Cleanup (19 orders)** | `7c44efde` | `docs/bridge/bridge-20261027-housekeeping-stale-ci-orders.md` | ❌ Closed with a markdown doc |

---

## 3. Recommended Remediation Plan

1. **Reopen the 9 Bangla Audit Feature Gaps:**
   - Issues **#1462, #1464, #1466, #1468, #1470, #1474, #1476, #1478, #1480** should be marked as **Reopened** or converted into actionable satellite Sub-Issues under `#749 (Studio)` and `#750 (API)`.
2. **Execute Actual Implementation Branches:**
   - Agents should pick these issues, read their respective specifications in `docs/bridge/`, and submit code changes directly targeting `studio/*` and `gateway/*`.
3. **Strict Policy Enforcement:**
   - With our newly applied root fix in `bridge.tools.ts`, `bridge_intake.py`, and `auto_bridge_pr_opener.py`, future spec files will strictly use `Refs #N` without `Closes #N`, preventing any further false completions.
