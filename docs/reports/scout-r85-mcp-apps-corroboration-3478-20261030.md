# Scout R85 Corroboration — MCP Apps (SEP-1865) live-verified (Refs #3478, report-only)

- **Task ID:** `bridge-20261030-glm23-scoutr85-mcpapps-corrob`
- **Agent:** GLM Agent 23 (Job 486814, slot agent-23) — independent second-agent corroboration lane
- **Lane:** scout follow-through — docs-only, zero code, **no closure requested** (`Refs #3478` only)
- **Probed:** 2026-10-30T15:23–15:27Z (web + live tower, zero-credential)

## Verdict: #3478's core claims independently CONFIRMED

1. **SEP-1865 is a live official MCP extension.** Verified across four independent
   surfaces: the official extension docs site (`apps.extensions.modelcontextprotocol.io`:
   "MCP Apps is an extension to the Model Context Protocol"), the official MCP blog
   (2026-01-26, "MCP Apps — Bringing UI Capabilities To MCP Clients"), the spec source
   (`ext-apps/specification/2026-01-26/apps.mdx` in the modelcontextprotocol org), and
   the reference TypeScript SDK `@modelcontextprotocol/ext-apps` (C# SDK convenience
   layer is tracking in modelcontextprotocol/csharp-sdk#1431). An active
   `#mcp-apps-wg` exists on meet.modelcontextprotocol.io (next session 2026-11-04).
   Anthropic/OpenAI joint announcement of the extension: 2025-11-21.
2. **Client hosts match the scout's list (4).** Claude (web + desktop), Goose,
   VS Code (Insiders), ChatGPT — per the official blog's Client Support section.
3. **Tower serve-plane is text-only — live receipt.** `tools/list` on the deployed
   tower returned **158 tools** (count is live-moving; scout measured 151 at
   15:10Z — fleet tool surface grows continuously, the invariant below is what
   matters): **ZERO** tools carry `_meta.ui`, `ui://`, `text/html;profile=mcp-app`,
   or the `io.modelcontextprotocol/ui` extension id. No `_meta` of any kind is
   advertised. No lane R1–R85 covers MCP Apps in code; the only repo mention is a
   2-line bullet inside `docs/SCOUT_RADAR_2026-10-28-XIII.md` (2026-07-28 spec
   overview), which predates the graduation this scout reports.

## Wire facts pinned for the eventual adaptation (corroboration delta beyond the scout)

- Extension/capability id: **`io.modelcontextprotocol/ui`** (client advertises
  supported MIME types there; servers gate UI-tool registration on it).
- Tool attachment: `_meta.ui.resourceUri` (e.g. `ui://<server>/<view>.html`); the
  legacy flat key `_meta["ui/resourceUri"]` is deprecated-but-required for
  backward-compatible hosts — dual-write normalization is the documented pattern.
- Resource MIME: **`text/html;profile=mcp-app`**, pre-declared via `resources`
  (HTML-first, rendered in sandboxed iframes).
- **Progressive enhancement contract:** hosts without UI support see plain text
  results; tools stay fully functional — adopting it changes nothing for the
  current text-only consumers.
- Security model: sandboxed iframes + declarative CSP (connect/resource/frame
  domain allowlists), auditable JSON-RPC over postMessage, host-side user consent
  for UI-initiated tool calls.

## Routing (verdict-plane guidance, owner-lane)

The adaptation surfaces named by the scout are real: control-plane serve-plane
(attaching `_meta.ui` + serving `ui://` resources) and studio host-plane (embedding
the ext-apps client). But the tower's advertised tool surface is owner-lane per the
standing exposure-probe precedent (#2076/#2082, "routed not wired"): any change to
what the tower advertises to hosts — UI metadata included — is an admin decision
with redeploy, not a board-agent patch. This receipt pins the wire facts so that
decision starts from evidence, not from a re-derived scout sweep.

**Resolution predicate:** #3478 is a radar row; it stays open until the verdict
plane either opens an implementation lane (serve-plane `_meta.ui` + host-plane
client) or records an explicit wont-track decision. Nothing here auto-closes.

## Refs

- **#3478** — subject scout row (bare citation, no close verb)
- **#2076 / #2082** — tool-surface-advertisement owner-lane precedent (routing basis)
- Companion: `docs/SCOUT_RADAR_2026-10-28-XIII.md` — the 2026-07-28 spec ceiling note (Tower ceiling = 2025-11-25 interim release; MCP Apps ships in the 2026-01-26+ extension lane, above that ceiling)

## Cycle worklog (GLM Agent 23, 15:23–15:3xZ — one line per event)

1. Heartbeat slot agent-23 OK (15:23:20Z); loop served #3478 (scout/radar, role
   ecosystem-scout); receipt-coverage demotions cleared 5 in-flight rows first.
2. Independent verification: 4-source web confirmation of SEP-1865 official status +
   4-host support; tower probe 158 tools / zero UI metadata; repo grep — only the
   10-28 radar bullet covers MCP Apps.
3. This corroboration receipt filed (docs-only, Refs #3478, no close).
