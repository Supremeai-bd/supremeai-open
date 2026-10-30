import assert from "node:assert/strict";
import {
  LICENSE_GATE_ACCEPTED,
  evaluateLicenseProvenance,
  isRepoUrl,
} from "./src/registry/license-gate.js";
import {
  MARKETPLACE_PLUGINS,
  clearMarketplaceConnections,
  clearMarketplaceRegistry,
  connectPlugin,
  getMarketplacePlugin,
  listMarketplacePlugins,
  marketplaceLicenseGate,
  registerMarketplacePlugin,
} from "./src/registry/marketplace-plugins.js";
import { clearRemoteServerRegistry as clearFederation } from "./src/registry/remote-mcp-servers.js";

// ── #1668 License + provenance gate — mechanical, fail-closed, S10-aware ───

clearFederation();
clearMarketplaceConnections();
clearMarketplaceRegistry();

// 1. GPL family rejection (repo verdict rule: GPL=reject), all SPDX shapes.
for (const gpl of ["GPL-3.0-only", "GPL-2.0-or-later", "AGPL-3.0-only", "LGPL-2.1", "GPL-3.0"]) {
  const v = evaluateLicenseProvenance({ license: gpl, upstreamUrl: "https://github.com/owner/repo" });
  assert.equal(v.verdict, "REJECT", `${gpl} must reject`);
  assert.equal(v.code, "REJECT_GPL", `${gpl} -> REJECT_GPL`);
}

// 2. Unknown license = unverifiable upstream -> S10 rejection.
const unknown = evaluateLicenseProvenance({ license: null, upstreamUrl: "https://github.com/owner/repo" });
assert.equal(unknown.verdict, "REJECT");
assert.equal(unknown.code, "REJECT_UNKNOWN_LICENSE");
assert.equal(evaluateLicenseProvenance({ license: "  ", upstreamUrl: "https://github.com/owner/repo" }).code, "REJECT_UNKNOWN_LICENSE");

// 3. Fail-closed: licenses outside the permissive allow-list are rejected.
for (const odd of ["Artistic-2.0", "EPL-2.0", "MPL-2.0", "Proprietary", "EUPL-1.2"]) {
  const v = evaluateLicenseProvenance({ license: odd, upstreamUrl: "https://github.com/owner/repo" });
  assert.equal(v.verdict, "REJECT", `${odd} must reject (fail-closed)`);
  assert.equal(v.code, "REJECT_UNRECOGNIZED_LICENSE");
}

// 4. Permissive accept-list passes the license half.
for (const ok of LICENSE_GATE_ACCEPTED) {
  const v = evaluateLicenseProvenance({ license: ok, upstreamUrl: "https://github.com/owner/repo" });
  assert.equal(v.verdict, "ACCEPT", `${ok} must accept`);
}

// 5. Provenance: upstream must be pinned AND a repo URL (vendor markers).
const noUpstream = evaluateLicenseProvenance({ license: "MIT", upstreamUrl: null });
assert.equal(noUpstream.verdict, "REJECT");
assert.equal(noUpstream.code, "REJECT_NO_UPSTREAM");

for (const bad of [
  "https://notion.so/docs/mcp",              // vendor docs/marketing page
  "http://github.com/owner/repo",            // not https
  "https://example.com/owner/repo",          // not a code host
  "https://github.com/owner",                // missing repo segment
  "https://github.com/",                     // no path at all
  "not-a-url",                               // garbage
]) {
  const v = evaluateLicenseProvenance({ license: "MIT", upstreamUrl: bad });
  assert.equal(v.verdict, "REJECT", `${bad} must reject`);
  assert.equal(v.code, "REJECT_PROVENANCE");
}
assert.equal(isRepoUrl("https://github.com/github/github-mcp-server"), true);
assert.equal(isRepoUrl("https://gitlab.com/owner/repo/-/tree/main"), true);

// 6. Seed catalog honesty: verdicts are visible per row (machine-checkable).
const ghSeed = getMarketplacePlugin("github");
assert.ok(ghSeed);
assert.equal(ghSeed.license, "MIT");
assert.equal(ghSeed.upstreamUrl, "https://github.com/github/github-mcp-server");
assert.equal(marketplaceLicenseGate(ghSeed).code, "ACCEPT");
// Rows without a pinned upstream honestly show their gate status.
for (const id of ["telegram", "web-search", "google-drive", "notion"]) {
  const p = getMarketplacePlugin(id);
  assert.ok(p);
  assert.equal(p.license, null, `${id} has no pinned license (honest null)`);
  assert.equal(marketplaceLicenseGate(p).code, "REJECT_UNKNOWN_LICENSE");
}
// Frozen seeds stay exactly the Phase-1 five (SQL-sync anchor).
assert.equal(MARKETPLACE_PLUGINS.length, 5);

// 7. Catalog ingress: GPL plugin never reaches catalog state.
const gplAttempt = registerMarketplacePlugin({
  pluginId: "copyleft-tool",
  name: "Copyleft Tool",
  description: "A third-party MCP plugin whose upstream is GPL-licensed.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [],
  docsUrl: null,
  license: "GPL-3.0-only",
  upstreamUrl: "https://github.com/third-party/copyleft-tool",
});
assert.ok(!gplAttempt.ok, "GPL registration must be rejected");
assert.ok(!gplAttempt.ok && gplAttempt.gate?.code === "REJECT_GPL");
assert.equal(getMarketplacePlugin("copyleft-tool"), undefined, "rejected plugin has no catalog state");

// 8. Unknown license and vendor-marketing upstream rejected at ingress.
const unknownAttempt = registerMarketplacePlugin({
  pluginId: "mystery-plugin",
  name: "Mystery Plugin",
  description: "A third-party MCP plugin with no verifiable upstream license.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [],
  docsUrl: null,
  license: null,
  upstreamUrl: "https://github.com/third-party/mystery",
});
assert.ok(!unknownAttempt.ok && unknownAttempt.gate?.code === "REJECT_UNKNOWN_LICENSE");
const vendorAttempt = registerMarketplacePlugin({
  pluginId: "open-washed",
  name: "Open Washed",
  description: "A plugin whose 'upstream' is a marketing page, not a repository.",
  provider: "vendor",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [],
  docsUrl: null,
  license: "MIT",
  upstreamUrl: "https://vendor.example.com/open-washed",
});
assert.ok(!vendorAttempt.ok && vendorAttempt.gate?.code === "REJECT_PROVENANCE");

// 9. Happy path: permissive license + real repo URL is admitted.
const goodAttempt = registerMarketplacePlugin({
  pluginId: "permissive-plugin",
  name: "Permissive Plugin",
  description: "A third-party MCP plugin under a verified MIT license.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [{ name: "api-key", label: "API key (vault ref)", required: true, secret: true }],
  docsUrl: null,
  license: "MIT",
  upstreamUrl: "https://github.com/third-party/permissive-plugin",
});
assert.ok(goodAttempt.ok, "permissive + repo upstream must be admitted");
if (goodAttempt.ok) {
  assert.equal(goodAttempt.plugin.trustLevel, "untrusted", "admissions land untrusted");
  assert.equal(goodAttempt.gate.code, "ACCEPT");
}
assert.ok(listMarketplacePlugins().some((p) => p.pluginId === "permissive-plugin"), "admitted plugin appears in the combined catalog view");
assert.equal(MARKETPLACE_PLUGINS.length, 5, "frozen seed list is never mutated by admissions");

// 10. Admitted plugin is connectable through the SAME governed path.
const connect = connectPlugin({
  pluginId: "permissive-plugin",
  tenantId: "tenant-a",
  credentialVaultRef: "vault:api-key",
  endpoint: "https://self-hosted.example.com/mcp",
});
assert.ok(connect.ok, "admitted plugin connects through the governed registry");

// 11. Duplicates and bad shapes fail closed.
const dup = registerMarketplacePlugin({
  pluginId: "permissive-plugin",
  name: "Permissive Plugin",
  description: "Duplicate registration attempt for the same pluginId.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [],
  docsUrl: null,
  license: "MIT",
  upstreamUrl: "https://github.com/third-party/permissive-plugin",
});
assert.ok(!dup.ok && dup.error.includes("already registered"));
const badId = registerMarketplacePlugin({
  pluginId: "Bad_ID!",
  name: "Bad Id",
  description: "A plugin registration with an invalid pluginId shape.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [],
  docsUrl: null,
  license: "MIT",
  upstreamUrl: "https://github.com/owner/repo",
});
assert.ok(!badId.ok && badId.error.includes("pluginId must match"));
const leaky = registerMarketplacePlugin({
  pluginId: "leaky-spec",
  name: "Leaky Spec",
  description: "A registration whose credential label carries a live token shape.",
  provider: "third-party",
  endpointTemplate: null,
  protocol: "streamable-http",
  credentialFields: [{ name: "token", label: "ghp_AbCdEf123456" }], // gitleaks:allow — detector fixture
  docsUrl: null,
  license: "MIT",
  upstreamUrl: "https://github.com/owner/repo",
});
assert.ok(!leaky.ok && leaky.error.includes("specs only"), "credential specs are never live values");

// 12. Test hygiene.
clearMarketplaceConnections();
clearMarketplaceRegistry();
clearFederation();
assert.equal(listMarketplacePlugins().length, 5);

console.log("license gate tests passed");
