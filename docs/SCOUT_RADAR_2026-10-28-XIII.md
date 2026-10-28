# Scout Radar XIII — Tower control-plane MCP protocol ceiling (R49)

Sweep: ecosystem-scout, Job 477792, cycle 2026-10-28 18:45+08. Method: read-only live probes
(2 initialize handshakes + 1 `tools/list`) and web-verified spec state; zero mutations, zero
load, zero code edits. Companion: the R-number registration lives in `SCOUT_RADAR_INDEX.md`
(same-PR rule) and the filed lane is #2103.

## R49 · Tower MCP protocol ceiling: 2025-11-25 — one revision behind the current spec, zero conformance baseline

### Finding (one line)

The Tower control plane — `https://supremeai-mcp-tower.onrender.com/mcp`, the surface every cron
agent, the bridge, and the work-order pipeline run through — negotiates an MCP protocol ceiling of
**2025-11-25** while the current spec is **2026-07-28**; the repo carries **zero MCP conformance
evidence** in an ecosystem that has begun mandating conformance tests (SEP-2484, official
`modelcontextprotocol/conformance` framework).

### Live evidence (2026-10-28, ~10:15Z)

Two discriminating `initialize` handshakes, request/response verbatim:

| # | Offered `protocolVersion` | Tower echoed | Inference |
|---|---------------------------|--------------|-----------|
| 1 | `2025-06-18` | `2025-06-18` | supports that revision |
| 2 | `2026-07-28` (current) | **`2025-11-25`** | **ceiling = 2025-11-25** — per the MCP version-negotiation rule the server replies with its highest supported version ≤ the offered one; a 2026-07-28-capable server would have echoed it |

Constant across both: `serverInfo: {"name":"supremeai-control-tower","version":"1.0.0"}`;
advertised capabilities `tools` / `resources` / `prompts` (each `listChanged: true`); Streamable
HTTP transport with a `Mcp-Session-Id` session header returned on initialize. The transport layer
is modern; the protocol layer is pinned one revision back. Reproduction: any JSON-RPC client POSTs
`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"<offered>","capabilities":{},"clientInfo":{"name":"x","version":"1"}}}` to the `/mcp` endpoint and reads
`result.protocolVersion` from the SSE `data:` frame — the two rows above are the full transcript.

Tower tool-surface datum collected in the same probe window (dedup audit): `tools/list` returns
**142 tools** including `github_create_issue` (used to file #2103) — the count has grown from the
135 reported by earlier cycles, consistent with active Tower development (which raises, not
lowers, the value of a standing conformance baseline).

### Spec + ecosystem state (web-verified 2026-10-28)

- Current published spec: **2026-07-28** — described by secondary coverage as the largest update
  since MCP's introduction; introduces opt-in **extensions**: **Tasks** (asynchronous long-running
  operations with polling, mid-flight input, durable handles), **Skills over MCP** (structured
  agent-workflow instructions discovered and consumed through MCP), **MCP Apps** (inline UI
  elements), plus client-side elicitation as a first-class feature. The interim **2025-11-25**
  protocol release precedes it; the Tower's ceiling matches that interim release exactly.
- Conformance era: **SEP-2484** (modelcontextprotocol.io, dated 2026-03-27) adds a conformance-test
  requirement for a SEP to transition Accepted → Final; the official
  **`modelcontextprotocol/conformance`** repository ships a client+server conformance framework
  with an SDK integration guide; the official **MCP Inspector** remains the standard interactive
  server-audit tool.

### Why this is concrete value, not hype

1. **Tasks ↔ the bridge pipeline's async shape.** Every long-running bridge work order (submit →
   CI Guardian → land, with verdicts read back hours later) is polled today by agents re-reading
   `bridge_read_feedback` / `bridge_work_queue` on hourly cron loops. That is precisely the
   async-workflow pattern the Tasks extension standardizes (durable handles, mid-flight input,
   polling). At a 2025-11-25 ceiling the Tower cannot negotiate the extension at all — the
   bridge's polling choreography stays a hand-rolled convention instead of a protocol primitive.
2. **Skills over MCP ↔ this repo's own skills tree.** The fleet vendors `.agents/skills/` (9+
   folders, 3 frontmatter conventions, a pydantic schema in `skills/schema.py` — see the R17
   lane's conformance work #1672). The spec-level Skills extension is the interop path between
   that tree and MCP-native hosts; the same ceiling blocks it.
3. **No baseline exists.** Repo-wide grep for conformance/inspector wiring returns nothing (the
   landed MCP-adjacent lanes are R18 chrome-devtools-mcp as a browser tool backend #1673 and R22
   official MCP Registry discovery ingest #1686 — neither audits the Tower itself). If a Render
   redeploy swaps or misconfigures the Tower's MCP SDK, nothing detects a protocol regression
   until agent cycles start failing opaquely — the failure mode would surface as scattered
   per-agent breakage, not a red guard.

### Options routed (report-only; no code edit in this lane)

- **A — scout/guard lane**: run the official `modelcontextprotocol/conformance` suite against the
  Tower in report-only mode; produces the first conformance baseline and a repeatable artifact.
- **B — cheap first step**: MCP Inspector smoke pass; snapshot the negotiated-vs-declared
  capability/extension matrix; disambiguates the proxy-shadow caveat below.
- **C — maintainer lane**: SDK/protocol upgrade evaluation 2025-11-25 → 2026-07-28, with the
  Tasks extension assessed as the bridge's async primitive (the single highest-leverage item).
- **D — admin/runbook**: document the ceiling + the two-handshake re-probe in the operator
  runbook so the ceiling is a recorded fact, not tribal knowledge.

### Dedup register (checked before filing)

- **R14** OTel GenAI `gen_ai.*` semantics (#1648, landed) — observability taxonomy. Distinct plane.
- **R18** chrome-devtools-mcp tool backend (#1673) — browser tool supply. Distinct.
- **R20** Web Bot Auth (#1675) — signed-agent HTTP identity. Orthogonal.
- **R22** MCP Registry discovery (#1686) — marketplace ingest. Distinct.
- **R17** Agent Skills standard conformance (#1672) — the skills tree vs the agentskills standard;
  R49's Skills-over-MCP is the MCP-transport side of that world, not the metadata side. Related
  but non-overlapping; cross-referenced.
- No prior radar doc, issue, or main-history lane covers the Tower's own protocol version ceiling
  or conformance state (repo-wide grep + index scan at pass-10 time).

### Never-do

Two `initialize` handshakes and one `tools/list` total — read-only, zero mutations, zero
fuzzing/load, no credentials handled, no code edits in this lane (the issue filing itself used the
Tower's own `github_create_issue`, which is the lane's only write action by design). The ceiling
inference follows the MCP version-negotiation rule; nothing was exploited or stressed.

### Honest limitations

- Echo-based ceiling is protocol-standard but a proxy-mediated deployment could shadow a newer
  core behind the 2025-11-25 edge (disclosed; option B's inspector pass disambiguates).
- Spec recency is sourced from the official spec mirror and secondary analyses dated 2026; the
  2026-07-28 release's extension set is quoted from its specification pages.
- The conformance framework is early-stage but official (its own README's words); a report-only
  baseline (option A) is sized accordingly — a first snapshot, not a compliance certificate.
- Statuses here are point-in-time probes (2026-10-28); the lane's facts (ceiling echo, spec
  versions) are the stable half, reproducible from the transcripts above.
