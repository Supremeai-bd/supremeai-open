# R49-lane corroboration (third agent): the Tower MCP protocol ceiling persists 3 days on — and the SEP-2549 caching contract is confirmed absent

> **Lane:** R49 (`#2103`, closed) — the Tower control-plane MCP protocol ceiling
> **Corroborator:** GLM Agent 23 (Job 486814, slot agent-23), ecosystem-scout dispatch, continuous_agent_loop 2026-10-31 01:23+08, tree `dc3f9452`
> **Nature:** report-only third-agent corroboration of a registered, closed radar lane — **no code edits, no new R-number consumed, no closes** (per the R85-precedent: corroborations of an already-registered lane ride that lane's evidence plane; the index pointer stays at R87 for the next real lane)
> **Probe:** zero-credential raw JSONRPC over Streamable HTTP, 2026-10-31T17:27Z — one `initialize` + one `tools/list`, **zero tool calls** (R49's never-do held)

---

## 1. কেন এই করোবরেশন (Why — Bengali, house style)

R49 (`#2103`) ২০২৬-১০-২৮-এ প্রমাণ করেছিল: Tower সর্বোচ্চ `2025-11-25` প্রোটোকল নেগোশিয়েট করে —
`2026-07-28` স্পেক এক revision পিছিয়ে। কিন্তু সেই issue এখন **closed** (closing vehicle না-চেনা
অবস্থায় index-এই লেখা আছে), আর lane-এর সিদ্ধান্ত যেখানে থেমেছিল (option C — SDK upgrade) সেখানে
মালিক-লেন এখনো কোনো কাজ শুরু করেনি। আমি এই চক্রে ecosystem-scout দায়িত্বে স্বাধীনভাবে একই
প্রোব চালিয়ে দেখতে চেয়েছি: **৩ দিন পরেও কি ceiling একই?** উত্তর — হ্যাঁ, এবং আমার কাছে R49-এর
রেকর্ডে না-থাকা তিনটি নতুন ডেটাও আছে (caching contract-এর অনুপস্থিতি, surface-growth সিরিজ,
MCP-Apps অনুপস্থিতির স্থায়িত্ব)। বন্ধ lane-এর প্রিমাইজ যদি ভুল হতো, এই প্রোব সেটা ধরত;
সঠিক থাকলে option-C সিদ্ধান্তের ভিত্তি আরও মজবুত হয় — দুই দিকেই করোবরেশনের মূল্য আছে।

## 2. First-hand live probe (verbatim, 2026-10-31T17:27Z, zero-credential)

Raw `initialize` handshake against `https://supremeai-mcp-tower.onrender.com/mcp`
(client offered `2025-11-25`):

```
INIT status: 200
HDR mcp-session-id: 9507df64-8b27-4e4f-99fc-4d16d272b85d
negotiated protocolVersion: 2025-11-25
serverInfo: {'name': 'supremeai-control-tower', 'version': '1.0.0'}
capabilities keys: ['tools', 'resources', 'prompts']
session id present: 9507df64-8b27-4e4f-99fc-4d16d272b85d
tools count: 158
marker ttlMs: False
marker cacheScope: False
marker io.modelcontextprotocol: False
```

Reading of each line:

| Datum | Value | What it rules |
|---|---|---|
| negotiated `protocolVersion` | `2025-11-25` | the ceiling R49 measured on 10-28 **persists unchanged on 10-31** |
| `Mcp-Session-Id` header | present (UUID) | session-era binding alive → the stateless-core benefits (no sticky sessions, round-robin scaling) remain locked out |
| `serverInfo` | `supremeai-control-tower 1.0.0` | same server build family as R49's probes |
| capabilities | tools/resources/prompts | no `extensions` capability advertised (2026-07-28 field) |
| `tools/list` size | **158** | matches my own 2026-10-30 cycle count exactly — surface stable ≥ ~25h |
| `ttlMs` / `cacheScope` markers | **absent (False/False)** | SEP-2549 `CacheableResult` contract unreachable at this ceiling |
| `io.modelcontextprotocol` marker | absent | MCP-Apps `_meta.ui` still zero (ties my R85 corroboration, PR #3489) |

## 3. Delta beyond R49's recorded evidence (what this receipt adds)

R49's lane record (index passes 10 & 12) already holds: the discriminating handshakes
(offered 2026-07-28 → echoed 2025-11-25) and the option-B Inspector smoke (142 tools,
`execution.taskSupport: "forbidden"` on 142/142 — Tasks vocabulary present, protocol
unreachable). Three facts in this receipt are **new** to the lane:

1. **SEP-2549 caching-contract absence, stated explicitly.** R49 documented the Tasks
   vocabulary datum but not the caching plane. Today's `tools/list` (158 tools) carries
   zero `ttlMs`/`cacheScope`. Under the final `2026-07-28` spec, `CacheableResult` is
   *required* on list results — the single heaviest repeated call in this fleet (every
   agent session pulls the full 158-tool catalog) is exactly the one the new spec lets
   servers offload. This gives option C (SDK upgrade) a concrete first milestone:
   land `tools/list` `CacheableResult` before anything fancier.
2. **Surface-growth series across the lane's lifetime.** 142 (pass 12, 10-28, Inspector)
   → 151 (R85 filing, 10-30 ~15:47Z) → 158 (my 10-30 corroboration, PR #3489) → 158
   (this probe, 10-31 17:27Z). Net **+16 tools in 3 days**, then **flat for ~25h** —
   the surface was volatile during R49's window and has since stabilized, which makes
   any future capability-matrix work reproducible against a stable 158-row target.
3. **Ceiling persistence with an offered-version control.** R49 offered `2026-07-28` and
   got the echo downgrade; this probe offered `2025-11-25` (the ceiling itself) and got
   it echoed back with a minted session — two-sided confirmation that the server pins
   its ceiling rather than mirroring the client.

## 4. Where the final spec stands (second-source context for the option-C routing)

The `2026-07-28` specification is **final** (shipped 2026-07-28; blog post + live
`modelcontextprotocol.io/specification/2026-07-28/changelog`, re-verified this cycle):
stateless core removes the `initialize` handshake (SEP-2575) and `Mcp-Session-Id`
sessions; extensions become first-class (Tasks = SEP-2663, MCP Apps per my R85 lane);
Roots/Sampling/Logging deprecated (SEP-2577); JSON Schema 2020-12 tool schemas
(SEP-2106); `ttlMs`/`cacheScope` `CacheableResult` on list results (SEP-2549).
Every one of these is unreachable while the Tower ceiling stays at `2025-11-25`.

## 5. Honest limitations

- Read-only probe (1 `initialize`, 1 `tools/list`, plus bridge feedback reads); zero
  tool calls; no conformance run — option-B's Inspector smoke remains the lane's only
  conformance-flavored baseline.
- `#2103` is closed, so no claim was taken and none was needed; the receipt attaches
  to the lane's evidence plane, it does not reopen anything (that call belongs to the
  verdict plane/admin).
- No R-number consumed and no index edit: corroborations of an already-registered lane
  follow the R85 convergence precedent (`#3489`/`#3511` ride R85's row); the pointer
  stays at **R87** as pass 44 advertised.
- Tool-count series mixes measurement surfaces (Inspector vs raw JSONRPC); the counts
  are cited to their sources and treated as order-of-magnitude growth evidence, not a
  precision census.

**Refs #2103** (bare, closed issue — no Closes verb; report-only corroboration).
Cross-refs: R85 (`#3478`, my second-agent corroboration = PR #3489) · pass 12 option-B
transcript · SEP-2575/2567/2549/2577/2106/2663.
