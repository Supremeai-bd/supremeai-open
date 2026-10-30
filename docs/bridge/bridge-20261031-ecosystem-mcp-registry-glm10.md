# Bridge receipt — ecosystem-scout: SupremeAI absent from the official MCP Registry + protocol currency gap 2025-06-18 → 2026-07-28 (GLM Agent 10)

- **Agent:** GLM Agent 10 · Job 486755 · **ecosystem-scout** (single-runner role lock, no clean board pick — all candidates U5-covered) · cycle 2026-10-31 07:10+08 · probes 23:11–23:16Z · local main pinned `e0d08b7d` (loop verify-only 8/8 PASS)
- **Report-only:** zero code edits per scout mandate. Two owner/tool-plane findings with live probe receipts; one prior-receipt cross-ref.

**বাংলা:** আজকের স্কাউট ডিসপ্যাচে বোর্ডে ক্লিন পিক ছিল না (সব প্রার্থী U5 anti-stampede কভারেজে), তাই ecosystem-scout ম্যান্ডেটে লাইভ প্রোব করে দুটি বাস্তবায়নযোগ্য ইনোভেশন ফাইন্ডিং এনেছি। ① SupremeAI-র MCP control tower **অফিসিয়াল MCP Registry-তে নেই** (search=supremeai → 0 results), অথচ একই শেপের প্রতিযোগী (suprememind.ai, supremetechy.com) তালিকাভুক্ত — অর্থাৎ ফ্রি গ্লোবাল ডিসকভারেবিলিটি চ্যানেল অব্যবহৃত। ② Tower **protocolVersion 2025-06-18** বলছে, অথচ latest stable spec **2026-07-28** (২ revision পিছিয়ে)। 2025-11-25 গ্রহণ additive/low-risk; 2026-07-28 ভাঙা transport revision — roadmap-এ রাখা উচিত, তাড়াহুড়ো নয়।

## F1 — Official MCP Registry: ABSENT (owner lane · high value · ~30 min · zero code)

**Live evidence (2026-10-31 23:11Z, first-hand):**
- `GET https://registry.modelcontextprotocol.io/v0/servers?search=supremeai` → `{"servers":[],"metadata":{"count":0}}`
- `search=supreme` → 4 hits, including two **remote streamable-http servers of exactly our tower's shape**: `ai.suprememind/expert-witness-simulation` (remotes: mcp.suprememind.ai/mcp, published 2026-10-02, status active) and `com.supremetechy/amorti` (MCPaaS). Registry schema: `2025-12-11/server.schema.json`.

**Why it matters:** the official registry is the cross-client discovery plane (Claude, Cursor, VS Code and other MCP clients browse it). Listing is free distribution + ecosystem legitimacy; same-category competitors are already discoverable, SupremeAI is not.

**Prereqs already verified live on our side (zero-credential probes against the production tower):**
1. Public streamable-http endpoint: `POST https://supremeai-mcp-tower.onrender.com/mcp` — `initialize` succeeds unauthenticated; response `protocolVersion: "2025-06-18"`, `serverInfo: {name:"supremeai-control-tower", version:"1.0.0"}`, capabilities tools/resources/prompts `listChanged:true`.
2. Anonymous plane is correctly gated: fresh zero-credential session `tools/list` returns **exactly 20 tools** — status/system_inspect/system_summary/system_health/slot_status, agent_heartbeat/agent_status, supabase_schema_inspect/db_schema_inspect, and the 10 public bridge-lane tools (bridge_guide, bridge_work_queue, bridge_work_order, bridge_work, bridge_submit_patch, bridge_submit, work_claim, bridge_read_feedback, bridge_lease_manage, bridge_work_renew). **No admin tools** (tenant_*, policy_*, github.*, action_*, client_* absent). A public registry listing therefore does not expose the admin surface. (Consistent with R88 anon-plane census #3816.)

**Implementation recipe (owner lane — needs the Supremeai-bd GitHub identity; agents hold no push/publish credentials):**
1. Add `server.json` at repo root (or `.mcp-registration/`) per schema `https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json`.
2. `name`: `io.github.Supremeai-bd/supremeai-control-tower` (verified via GitHub OAuth login — zero infra) **or** reverse-DNS under an owned domain (DNS/HTTP verification) if the org prefers a domain-scoped identity.
3. `remotes: [{"type":"streamable-http","url":"https://supremeai-mcp-tower.onrender.com/mcp"}]`, display info + repository pointer.
4. Publish with the `mcp-publisher` CLI: `mcp-publisher login github` → `mcp-publisher publish`. Publishing is API-based; no PR to the registry repo is needed.
5. Optional polish: a custom domain for the endpoint (onrender.com subdomains are allowed but a domain-scoped identity reads stronger).

## F2 — Protocol currency: tower at 2025-06-18, latest stable 2026-07-28 (tool plane · additive now, roadmap later)

**Live evidence:** `initialize` probe returns `protocolVersion:"2025-06-18"` (23:11Z). Spec navigation (modelcontextprotocol.io/specification/latest): revisions 2024-11-05, 2025-03-26, **2025-06-18**, 2025-11-25, **2026-07-28 (latest)**, Draft.

**2025-11-25 — additive, low-risk adoption recommended now (changelog-verified):**
- **Icons metadata** on tools/resources/prompts (SEP-973) — client-UI branding, zero behavior risk.
- **OAuth upgrades**: OIDC Discovery (#797), `WWW-Authenticate` incremental scope consent (SEP-835), OAuth Client ID Metadata Documents (SEP-991) — directly relevant when auth is added to `/mcp`.
- Elicitation URL mode (SEP-1036) + titled/untitled/multi-select enum schemas (SEP-1330).
- Sampling gains tool calling (`tools`/`toolChoice`, SEP-1577); experimental tasks (SEP-1686).

**2026-07-28 — breaking transport revision, roadmap only (do NOT rush):** stateless protocol (initialize handshake + `Mcp-Session-Id` removed), mandatory `server/discover`, `subscriptions/listen` replaces resources/subscribe + GET endpoint, Multi-Round-Trip Requests (`InputRequiredResult`/`inputResponses`) replace server-initiated requests, required `resultType` on all results, tasks become official extension, SSE resumability removed. Live note: the tower's current flow is **session-based** (initialize returns `Mcp-Session-Id`; pinned tower clients carry it on every call) — this is a real migration project. No urgency: clients negotiate down to the server's version, so nothing breaks meanwhile.

**Root-cause framing (zero-recurrence):** add a **spec-currency pin** — a CI check (or heartbeat probe) asserting the advertised `protocolVersion` equals the latest stable spec, or carries a documented "pinned-with-reason" marker. Today's gap grew silently; the pin makes any future drift a loud CI failure instead of a quiet two-revision lag.

## Cross-ref — render-primary degraded (already receipted, no new row)

`status` probe (23:11:28Z): render-primary `degraded` — "Container running previous build, but latest deployment update_failed", checkedAt 22:35:29Z; other 20/21 services healthy. **This exact condition is already receipted by this agent as WO/PR #3745** (`docs/bridge/bridge-20261031-renderprimary-updatefailed-glm10.md`: update_failed + boot #3 re-firing all 4 #3699 classes, owner-lane disposition list). No duplicate row filed here (U5).

## Lane routing

| Item | Lane | Why |
| --- | --- | --- |
| F1 registry listing | **owner** (GitHub identity) | publish requires Supremeai-bd GitHub OAuth or domain DNS verification |
| F2a adopt 2025-11-25 (icons, OAuth SEPs, elicitation) | tool plane (code) | additive capability bump in the MCP server layer |
| F2b 2026-07-28 migration | owner/architecture roadmap | breaking transport change; session-based clients exist |
| F2c spec-currency pin | tool plane (CI) | makes protocol drift a CI failure, root-cause fix |
| render-primary update_failed | ops/owner | already WO #3745 |

## Requested disposition

- Promote **F1** to an owner-lane TODO (≈30 min once GitHub-authenticated): server.json + mcp-publisher publish. Highest value-per-effort item found this cycle.
- **F2a/F2c** as normal tool-plane issues (additive); **F2b** as a roadmap watch row — explicitly not urgent.
- No claim taken, no autoclose; watch/census receipt stays open until its subject resolves (default bridge semantics).

## U5 / anti-stampede

`bridge_work_queue` live scan (23:12Z, 20 rows shown of 48 open, windowTruncated): zero rows mention registry listing, MCP registry, or protocol spec currency. #3816 = RBAC anonymous-plane census (different subject); #3777 = gateway vendor-plane drift (different); #3891 = loop work-start freshness (different).

## Reflection Evidence

- **why:** the board is fully receipt-covered (loop demoted every candidate), so the highest marginal value this cycle was outside the board: the registry query is a 2-second live check that revealed a free, competitor-proven distribution channel we are absent from — with every prerequisite (public endpoint, modern-enough protocol, gated anonymous plane) already verifiably satisfied. The protocol-currency gap compounds silently (2 revisions today, more tomorrow); filing it with a changelog-backed adoption split (additive now / breaking later) plus a spec-currency pin converts it into a permanent guard instead of a one-off note.
- **alternatives_rejected:** (1) publishing to the registry myself — publish requires the org's GitHub OAuth/DNS identity; agents hold no such credential and impersonating one would violate the identity contract. (2) Filing the 2026-07-28 stateless migration as an immediate task — it would break session-pinned tower clients (initialize → `Mcp-Session-Id` flow is load-bearing today); wrong sequencing. (3) A new row for render-primary degraded — already first-party receipted as #3745 with deeper evidence; a second row would be a U5 twin. (4) Skipping the anonymous-tools listing in F1 — it is the safety prerequisite that makes a public listing safe to approve; omitting it would leave the owner decision blind.
