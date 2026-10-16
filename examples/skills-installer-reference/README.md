# Skills Installer Reference — dynamic MCP capability registry (issue #332)

Zero-dependency Node.js (18+) reference for the skills marketplace layer:
discover, lease, and initialize MCP tool packages on demand with
least-privilege scoping verified against
`api-schemas/permissions.schema.json` (canonical fixture drives the tests).

## Layout

| File | Role |
| ---- | ---- |
| `src/manifest.mjs`   | skill-manifest contract — fail-closed validation (unknown keys, unknown scope ids, host-bearing URLs and `..` traversal all rejected) |
| `src/registry.mjs`   | CapabilityRegistry — marketplace load (one poisoned manifest rejects the WHOLE load), discover, install |
| `src/lease.mjs`      | LeaseAuthority — deny-by-default grants chained exactly like the permissions SSOT (sub-role pinning, min_role_tier, MFA barrier, TTL) |
| `src/installer.mjs`  | McpInstaller — MCP integration: streamable-http and SSE transports, JSON-RPC initialize/tools list/tools call; execute() re-checks the lease BEFORE any wire activity |
| `src/mock_tower.mjs` | offline mock tower (sessions, tools list, server-side deny) for the harness |
| `tests/run_tests.mjs` | 17 offline tests (AC1/AC2/AC3) |

## Trust posture (AC3)

- A lease is a frozen, expiring token; `execute()` re-validates it at call
  time — expired leases, tool mismatches, and scope escalations produce
  structured denials with ZERO wire calls (fail closed before the network).
- Manifests carry no hostnames: the entry path is tower-relative, the agent
  supplies the base URL — no SSRF-by-manifest.
- Server-side boundaries stay independent: a client-approved call can still
  be denied by the tower, and that denial surfaces as an honest error
  envelope (never a fabricated success).

## Usage

```js
import { CapabilityRegistry } from "./src/registry.mjs";
import { LeaseAuthority } from "./src/lease.mjs";
import { McpInstaller } from "./src/installer.mjs";

const registry = new CapabilityRegistry(policy, manifests);   // AC1
const manifest = registry.install("repo-tools");
const lease = new LeaseAuthority(policy).grant({
  sub_role: "coder", role_tier: 2, manifest, tool_name: "repo_read", ttl_s: 300,
});
const installer = new McpInstaller({ baseUrl: towerUrl });    // AC2
await installer.initialize({ transport: manifest.entry.transport, path: manifest.entry.path });
const out = await installer.execute(manifest, lease, leaseCheck, "repo_read", { path: "docs/" });
```

## Verification (issue contract)

```bash
npm run build     # syntax gate over every module
npm test          # 17 offline tests incl. both MCP transports
```
