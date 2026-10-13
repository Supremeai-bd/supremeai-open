# Tool Exposure Policy — Capability Registry vs Client-Visible Tool Surface

> Status: implemented on `feat/tool-exposure-policy` · Source of truth: `src/policy/tool-visibility.ts` · Contract tests: `test_tool_visibility.ts`
> Principle (founder-approved): **Internal capability count ≠ Client-visible tool count.**

## 1. The problem this solves

The tower registers ~90 internal tools, and the MCP SDK's default `tools/list`
handler advertises **all of them to every caller**. The call-path RBAC gate
(#695) correctly DENIES most of them at execution time, so an anonymous ChatGPT
guest sees a ~90-tool menu where most entries answer:

```text
Forbidden: tool 'resource_list' requires agent role or higher (default-deny RBAC).
```

That is a **discovery / authorization mismatch** — UX noise, not a security
failure — but it poisons LLM tool-selection and misrepresents the tower's
public surface. Removing tools from the registry is NOT the fix (agents and
admins legitimately need them). The fix is separating:

| Layer | Question | Enforced by |
|---|---|---|
| Capability registry | What CAN the tower do? | `registerAllTools` (unchanged) |
| Authorization | Who may CALL a tool? | `toolAccessError()` (#695, unchanged) |
| **Discovery / exposure** | **What does a client SEE?** | **`attachDiscoveryFilter` (new)** |

## 2. Design

```text
visible(tool) = RBAC-allows-call(tool) AND profile-allows-visibility(tool)
```

### Invariants (all enforced by tests)

1. **list ⊆ call** — nothing is advertised that the caller could not execute.
   The filter composes the SAME `toolAccessError()` used by the call wrapper;
   one RBAC source of truth, drift impossible.
2. **Visibility ≠ authorization** — a profiled client that addresses a hidden
   tool directly still goes through the UNCHANGED RBAC call gate. Profiles
   curate prompts; RBAC enforces security. The profile layer can never become
   a shadow ACL.
3. **Fail-closed** — no `RequestContextStore` ⇒ EMPTY discovery. SDK internals
   drift ⇒ LOUD warning + degraded-but-still-filtered fallbacks.
4. **One choke point for every pillar** — `/sse`, `/messages`, `/mcp`
   (stateful sessions) and `/gemini` (stateless in-memory pair) all serve
   `tools/list` through the same wrapped handler, because each pillar runs
   inside a `RequestContextStore` carrying the caller's `toolProfile`.
5. **Rollback = env flip** — `MCP_DISCOVERY_FILTER=off` restores the
   unfiltered SDK behavior without a code change.

## 3. Profiles

| Profile | Surface | Intended for |
|---|---|---|
| *(none)* | Full RBAC surface (unchanged behavior) | agents, admins, default |
| `chatgpt` | ~36 curated, read-mostly tools + exactly two operational writes (`notify_telegram`, `agent_review_workflow_execute`) | ChatGPT guests (auto-derived) and any client the admin assigns |
| `readonly` | `chatgpt` minus the two writes | strict read-only observers |

Guarantees for every profile:

- secret-class tools (`infisical_*`, `github_list_secrets`,
  `render_get_env_vars`) are NEVER listed (they are also RBAC admin-only);
- destructive tools (`autonomy_kill_switch`, `action_*`) are not listed;
- names are the sanitized wire forms (dots→underscores).

### Who gets a profile automatically

- **Auto-registered ChatGPT guests** (#1767/#2588 path): `profileForProvider("chatgpt")`
  → `chatgpt` profile, applied once at guest creation (derive-once — an
  admin-set profile is never clobbered on reconnects).
- **Every other provider / token client**: no profile (full surface), exactly
  as before this change.

### Managing profiles per client

- MCP tool: `client.set_profile` (`chatgpt` | `readonly` | `clear`)
- HTTP: `PATCH /clients/:id` with body `{"toolProfile": "chatgpt"}` (or
  `{"toolProfile": null}` to clear)
- At registration: `POST /clients` body field `toolProfile`, and the
  `client.register` MCP tool argument `toolProfile`
- Seeds: `MCP_CLIENT_SEEDS_JSON` entries may carry `"toolProfile": "chatgpt"`
- The profile persists through every registry backend (memory / JSON file /
  Upstash chain) and is visible in `GET /clients` output.

## 4. The public bridge onboarding surface (#123)

The front door for `paykaribazaronline/supremeai-open`: any external agent —
zero credentials, zero private access — connects over `/mcp`, `/sse` or
`/gemini`, is auto-registered as a `public_viewer` guest (#1767/#2588), and gets
three additional **read-only, public-classified** tools (registered in
`src/tools/bridge.tools.ts`, classified in `src/policy/mcp-access.ts`):

| Tool | Purpose | Network |
|---|---|---|
| `bridge.guide` | Canonical onboarding contract: lifecycle, branch convention `bridge/<task-id>`, diff caps (≤200 KB / ≤30 files), protected paths, submission flow | none (static) |
| `bridge.work_queue` | OPEN Bridge Work Orders (`bridge:queued`) in the public open-source repo | public GitHub API (unauthenticated read works; tower token only raises rate limits) |
| `bridge.work_order` | One work-order by number: title, labels, sanitized body, URL | public GitHub API |

Safety boundary (fail-closed, unchanged):

- all three are `access: "safe"` + `dataClassification: "public"` + R0 in
  `classifyToolCapability` — callable by every access mode including anonymous
  `public_viewer`; `list ⊆ call` still holds (one RBAC source of truth);
- **no write capability exists in this surface** — submission stays the GitHub
  path (fork → branch → work-order issue/PR) and landing stays with the
  constitutional gates; the bridge never merges;
- outputs carry public repo issue fields only — never tokens, private data or
  raw trust (bodies clipped at 8 000 chars);
- `bridge.guide` is listed even in the fail-closed "Degraded B" discovery path,
  so an external agent always keeps the contract.

Contract tests: `test_bridge_onboarding.ts` (`npm run test:bridge-onboarding`,
part of `test:unit`).

## 5. Implementation notes (SDK 1.30.0, verified against pinned source)

`attachDiscoveryFilter` installs on `McpServer.server` (the inner `Server`):

1. **Preferred (zero-drift)**: CAPTURE the SDK's own `tools/list` handler from
   `Protocol._requestHandlers` (a Map keyed by the method literal) and wrap
   it — descriptor building (name/description/inputSchema/annotations/
   outputSchema/_meta) stays 100% SDK-owned forever; we only filter the final
   array by name.
2. **Degraded A** (handler map renamed): rebuild descriptors from
   `_registeredTools` via zod-4 native `z.toJSONSchema(..., { io: "input" })`
   — still filtered, still loud.
3. **Degraded B** (even that is gone): fail-closed — advertise only the
   public-safe tools that pass RBAC. Never the full registry.

The Gemini adapter's `client.listTools()` and every stateful HTTP session ride
the same wrapped handler — one installation covers the whole tower.

## 6. Rejected alternatives (with reasons)

| Alternative | Why rejected |
|---|---|
| Delete tools from the registry | Agents/admins need them; the registry is the capability SSoT |
| Single mega-tool (`supremeai(operation, …)`) | Breaks per-tool zod validation, ambiguates the policy-schema tool→provider→action→R-level SSoT (#2429), breaks console/agent name contracts |
| Parallel YAML tool-metadata layer | A second source of truth re-creates the drift class #2429 removed; visibility must DERIVE from `classifyToolCapability`, not float beside it |
| Separate risk classification | Already exists and is richer: R0–R6 + dataClassification + approval classes (#695 family) |

## 7. Verification

```bash
cd infrastructure/mcp-control-plane
npm run test:tool-visibility      # this policy's contract tests
npm run test:bridge-onboarding    # public bridge onboarding surface (#123)
npm run test:unit                 # full chain (includes both; no live server needed)
npm run test:integration          # requires a live tower on :3771 (test_resource_list.ts)
npx tsc --noEmit                  # typecheck
```

Matrix covered by tests: admin/agent/viewer/anonymous × no-profile/chatgpt/
readonly × list/call, fail-closed no-context, kill-switch, descriptor fidelity,
registry persistence + derive-once guests, bridge onboarding RBAC + queue
normalization + anonymous e2e (`bridge.guide` executes with no context token).

## 8. Operational effect (once deployed)

- ChatGPT (anonymous guest) sees the public-safe tools — the 4 system/agent
  status tools plus the 3 bridge onboarding tools; the LIST matches what is
  callable.
- A ChatGPT guest upgraded by an admin sees its curated ~36-tool surface, not
  ~90.
- Agents keep their full RBAC surface; admins see everything.
- Rollback: `MCP_DISCOVERY_FILTER=off` (env flip on the Render service).

## Related

- `src/tools/bridge.tools.ts` — bridge onboarding tools (#123)
- `src/policy/mcp-access.ts` — call-path RBAC (#695)
- `src/policy/client-registry.ts` — client records + profile persistence
- `src/policy/auto-register.ts` — guest derivation
- `test_tool_visibility.ts` — contract tests
- `test_bridge_onboarding.ts` — bridge surface contract tests
- `../../scripts/bridge/README.md` — bridge operator contract (public→private lane)
- `../../docs/architecture/AGENT_PORTAL_AND_FEDERATION_BRIDGE.md` — architecture spec
