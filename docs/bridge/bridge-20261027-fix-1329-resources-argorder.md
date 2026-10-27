# fix(tower): [P0] all 12 MCP resources unreadable — resources/list emits uri/name swapped (SDK arg order) (#1329)

## Problem (live-reproduced 2026-10-27)
Every `resources/read` on the deployed tower fails. Two distinct error signatures:
- reading the URI that `resources/list` advertises (e.g. `system-health`) returns
  `-32603 Invalid URL` — the SDK validates the requested uri as a URL first, and a
  bare name is not a URL;
- reading the true URI (e.g. `control-tower://system/health`) returns `-32602
  not found` — valid URL, but no template registered under it.
Net effect: 0/12 resources readable (regressed from 2/12 at first audit), and the
conformance selftest reports 12/12 violations.

## Root cause (wire evidence + SDK signature)
`McpServer.resource(name, uriTemplate, config, readCallback)` — the SDK takes NAME
first, URI TEMPLATE second. `infrastructure/mcp-control-plane/src/index.ts` registers
all four built-in resources with the arguments swapped, e.g.:

  server.resource("control-tower://system/health", "system-health", {...}, cb)

so the registry stores name=`control-tower://system/health`,
uriTemplate=`system-health`. The SDK's list handler then emits
`{uri: "system-health", name: "control-tower://system/health"}` — exactly the
swapped wire output observed. The same reversed pattern produces the eight
`docs-*` resources (uri `docs-<provider>`, name `docs://<provider>`) from their
registration site (docs module on the deployed image; apply the identical swap
wherever they are registered).

## Fix
1. Swap the first two arguments at all four `server.resource` call sites in
   `infrastructure/mcp-control-plane/src/index.ts` (manifest, system health,
   system dependencies, client registry). Corrected full file shipped here as
   `infrastructure/mcp-control-plane/src/index.fixed.ts`; minimal patch as
   `docs/bridge/patches/mcp-index-resources-argorder.diff` (4 hunks, +8/-4).
2. Apply the same argument swap to the `docs-*` registration site (loop over the
   docs providers) so `docs://<provider>` becomes the URI and `docs-<provider>`
   the name.
3. No behavior change elsewhere: all four read callbacks ignore their arguments
   and hardcode the correct `contents[].uri` — verified by reading the source.

## Acceptance criteria
- [ ] `resources/list` emits `uri=control-tower://...` / `docs://...` and short names
- [ ] `resources/read` succeeds for ALL 12 advertised URIs (selftest prints 12/12 readable)
- [ ] `docs_fetch` / docs tools unaffected (they were failing with the same
      URL-construction class of error and share the provider table)
- [ ] No change in tool surface: 130 tools still discovered; discovery filter untouched

## Reflection Evidence
**Why:** Resources are a contractual MCP pillar; 0/12 readable breaks every
conforming client (mission-control, VS Code extension, external agents) and makes
the advertised docs/health/manifest surfaces dead weight. The swap is a two-line
per-site mechanical fix with zero runtime risk because the callbacks never used
the mis-ordered arguments.
**Alternatives rejected:**
- Change the read path to accept bare names: fights the SDK's URL validation,
  diverges from MCP spec, and leaves the list output still misleading.
- Re-register resources under bare-name URIs with a custom scheme handler:
  still fails SDK URL validation for scheme-less names; custom schemes add no value.
- Wait for SDK upgrade: pinned SDK 1.30.0 is fine — the call sites, not the SDK,
  are wrong; upgrades would keep the bug.
