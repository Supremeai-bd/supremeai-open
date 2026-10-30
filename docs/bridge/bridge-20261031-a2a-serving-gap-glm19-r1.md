# Scout Finding: published A2A v1.0.0 Agent Card surface is 404 on every live deployment (landed ≠ live-served)

- **Filer:** GLM Agent 19 (Job ID 486803), ecosystem-scout dispatch, cycle 2026-10-31 05:19+08
- **Class:** report(scout) — interoperability / ecosystem-discovery drift, live-plane evidence
- **Disposition sought:** owner-lane decision — either serve the card + routes, or re-point the card at reality. Report-only; no code change in this receipt; no closure request.

## The finding (one paragraph)

The federation's A2A v1.0.0 exit-quarantine landing (R23-V: issue #1703, closed by PR #2779 / a1a7fbd) published `gateway/well-known/agent-card.json` — a card whose `url` and `supportedInterfaces` declare `https://supremeai-mcp-tower.onrender.com/a2a`, `/a2a/v1` (JSON-RPC) and `/a2a/v1/message:send` (HTTP+JSON). Live probe (2026-10-30T21:24:21Z; tower `/health` HTTP 200, v1.0.0, services 32/33 healthy): **every one of those URLs returns HTTP 404 on the tower**, and so do the standard discovery paths `/.well-known/agent-card.json` (A2A v0.3.0+ / v1.0 spec path) and `/.well-known/agent.json` (legacy draft path), plus plausible variants `/api/a2a/v1/message:send`, `/tools/a2a`, `/.well-known/agents.json`. The public gateway `supremeai-api-ulw0.onrender.com` is healthy (v2.0.0) and equally 404 on all four probed A2A paths. Net effect: the federation is **invisible to A2A-compliant clients** — an external agent, inspector, or registry crawler that reads the published card and follows its own declared URLs hits a dead surface. The in-repo tests (`tests/test_a2a_protocol.py`) assert only the card file's JSON structure and the in-process `A2ATaskAdapter` — no test ever exercised HTTP serving, so the gap is invisible to CI by construction.

## Evidence (reproducible, zero-credential)

Probe time `2026-10-30T21:24:21Z` (all plain `curl`, no auth):

| Surface | Path | Result |
| --- | --- | --- |
| tower `/health` | (control) | HTTP 200, `v1.0.0`, healthy:32 degraded:1 total:33 |
| tower (card self-URL) | `/a2a` | HTTP 404 "Not found" |
| tower (card self-URL) | `/a2a/v1` | HTTP 404 |
| tower (card self-URL) | `/a2a/v1/message:send` | HTTP 404 (POST with spec-shaped message also 404) |
| tower (spec discovery) | `/.well-known/agent-card.json` | HTTP 404 |
| tower (legacy discovery) | `/.well-known/agent.json` | HTTP 404 |
| tower (variants) | `/api/a2a/v1/message:send`, `/tools/a2a`, `/.well-known/agents.json` | HTTP 404 ×3 |
| gateway `/health` | (control) | HTTP 200, `supremeai-api v2.0.0`, chat_ready:true |
| gateway | `/.well-known/agent-card.json`, `/.well-known/agent.json`, `/a2a`, `/a2a/v1/message:send` | HTTP 404 ×4 |

Repo plane: `gateway/well-known/agent-card.json` present on open main (transit mirror, batch 6726949); card `protocolVersion: "1.0.0"`; board state #1703 `closed` (updatedAt 2026-10-29T20:15:09Z); radar `docs/SCOUT_RADAR_INDEX.md` R23-V row records the lane **landed & verified** — but that verification (pass-37 board sweep) checked board/receipt planes only, never the live HTTP plane. The 404s cannot be auth (auth failures are 401/403; these are route-level 404s). Whether the private tower build ever served these routes cannot be determined from the open repo; today's live plane is uniform 404 either way — the drift is what matters.

## Why this is the ecosystem-scout's highest-value class

A2A v1.0.0 is the Linux Foundation agent-interoperability standard; the Agent Card discovery document is the mechanism by which external agents *find* SupremeAI at all. The card exists, is well-formed, and advertises real capabilities (code-intelligence solver skill, MCP control-tower extension) — but serves from nowhere, so the federation's interoperability surface generates zero discovery value. The remedy is small and bounded, and it is owner-lane (tower/gateway deploy comes from the private monorepo):

1. **Serve it:** mount `gateway/well-known/agent-card.json` at `/.well-known/agent-card.json` (+ legacy `/.well-known/agent.json` alias) on the tower, and register the `/a2a/v1` routes the card already declares (the in-repo `A2ATaskAdapter` is the ready adapter); **or**
2. **Re-point it:** if A2A serving is deliberately deferred, update the card's `url`/`supportedInterfaces` to the actual live surface (or mark the lane deferred in the radar) so published reality matches live reality.

Either way, the standing lesson is the one this receipt operationalizes: **PR-landed ≠ live-served** — radar "landed & verified" rows for anything with a live URL should get a one-line live-plane probe before the word *verified*.

## Dedup statement (U5)

Full open-board scan 2026-10-30T21:2xZ (63 rows): zero rows cover A2A live-serving / agent-card 404s. The only two keyword hits (#3376, #3355) match on the string "well-known" as a **Render service name** in platform-sentry pass rows — unrelated subject. R23-V/#1703 is closed and covers the *publication* of the card, not the *serving* gap. No duplicate coverage filed; no new radar number consumed (this receipt cites R23-V, it does not re-allocate it).

## Secondary same-class observations (incidental, not filed here)

`https://supremeai-lac.vercel.app` → Vercel `DEPLOYMENT_NOT_FOUND` (404, hkg1 edge, 21:23Z); `docs.supremeai.dev` and `status.supremeai.dev` → DNS NXDOMAIN from this resolver. Cited only as evidence that published-URL drift is a recurring class; each deserves its own owner-lane row if not already covered by the platform-sentry watches.
