import assert from "node:assert/strict";
import {
  MARKETPLACE_PLUGINS,
  clearMarketplaceConnections,
  connectPlugin,
  getMarketplacePlugin,
  listMarketplaceConnections,
  looksLikePlaintextSecret,
} from "./src/registry/marketplace-plugins.js";
import { clearRemoteServerRegistry, getRemoteServer } from "./src/registry/remote-mcp-servers.js";

// ── #1523 Marketplace MVP — plugin catalog + zero-risk BYO connect ─────────

clearRemoteServerRegistry();
clearMarketplaceConnections();

// 1. Catalog integrity: Phase-1 seed (5 providers), templates only.
assert.equal(MARKETPLACE_PLUGINS.length, 5);
const ids = MARKETPLACE_PLUGINS.map((p) => p.pluginId);
assert.deepEqual(ids, ["github", "telegram", "web-search", "google-drive", "notion"]);
for (const plugin of MARKETPLACE_PLUGINS) {
  assert.equal(plugin.trustLevel, "untrusted", "every catalog entry lands untrusted");
  assert.ok(plugin.description.length > 20, `${plugin.pluginId} needs a real description`);
  for (const field of plugin.credentialFields) {
    assert.equal(field.secret, true, "marketplace credential fields are always secret-class");
    assert.equal(field.required, true, "phase-1 credential fields are required");
    assert.ok(!looksLikePlaintextSecret(field.label), "labels must never look like live tokens");
  }
}
// Hosted templates only where the vendor publishes an official endpoint.
assert.equal(getMarketplacePlugin("github")?.endpointTemplate, "https://api.githubcopilot.com/mcp/");
assert.equal(getMarketplacePlugin("notion")?.endpointTemplate, "https://mcp.notion.com/mcp");
assert.equal(getMarketplacePlugin("telegram")?.endpointTemplate, null);
assert.equal(getMarketplacePlugin("web-search")?.endpointTemplate, null);
assert.equal(getMarketplacePlugin("google-drive")?.endpointTemplate, null);

// 2. Plaintext-secret detector (defense in depth at the connect guard).
assert.equal(looksLikePlaintextSecret("vault:github-token"), false);
assert.equal(looksLikePlaintextSecret("ghp_abc123def"), true); // gitleaks:allow — detector fixture, not a real token
assert.equal(looksLikePlaintextSecret("ghs_abc123def"), true); // gitleaks:allow — detector fixture
assert.equal(looksLikePlaintextSecret("sk-proj-abcdef"), true);
assert.equal(looksLikePlaintextSecret("xoxb-123-456"), true);

// 3. Happy path: connect delegates to the SAME federation registry.
const gh = connectPlugin({
  pluginId: "github",
  tenantId: "tenant-a",
  credentialVaultRef: "vault:github-token",
});
assert.ok(gh.ok, "github connect should succeed");
if (gh.ok) {
  assert.equal(gh.connection.pluginId, "github");
  assert.equal(gh.connection.tenantId, "tenant-a");
  assert.equal(gh.connection.credentialVaultRef, "vault:github-token");
  assert.equal(gh.connection.endpointUsed, "https://api.githubcopilot.com/mcp/");
  assert.equal(gh.connection.status, "pending", "connections start pending, never active");
  assert.ok(gh.nextStep.includes("client.discover_mcp_server"), "next step routes to descriptor pinning");
  // The backing remote server IS the federation registry's record.
  const remote = getRemoteServer(gh.connection.remoteServerId, "tenant-a");
  assert.ok(remote, "connection must resolve through the governed registry");
  assert.equal(remote?.name, "marketplace:github");
  assert.equal(remote?.status, "pending");
  assert.equal(remote?.trustLevel, "untrusted");
  assert.equal(getRemoteServer(gh.connection.remoteServerId, "tenant-other"), undefined, "tenant-scoped reads");
}

// 4. Zero-plaintext guard: live-token-shaped refs are rejected outright.
const plaintext = connectPlugin({ pluginId: "github", tenantId: "tenant-b", credentialVaultRef: "ghp_AbCdEf123456" }); // gitleaks:allow — detector fixture
assert.deepEqual(plaintext, { ok: false, error: "credentialVaultRef looks like a live token value — store it in a vault and pass the reference instead." });
const notVault = connectPlugin({ pluginId: "github", tenantId: "tenant-b", credentialVaultRef: "my-raw-token" });
assert.ok(!notVault.ok && notVault.error.includes("vault reference"), "non-vault refs are rejected");
const missing = connectPlugin({ pluginId: "github", tenantId: "tenant-b", credentialVaultRef: "" });
assert.ok(!missing.ok && missing.error.includes("Missing credential field"), "missing ref is rejected");

// 5. Self-hosted plugins require an explicit endpoint (zero default trust).
const tgNoEndpoint = connectPlugin({ pluginId: "telegram", tenantId: "tenant-a", credentialVaultRef: "vault:bot-token" });
assert.ok(!tgNoEndpoint.ok && tgNoEndpoint.error.includes("endpoint is required"), "template-less plugins demand an endpoint");
const tg = connectPlugin({ pluginId: "telegram", tenantId: "tenant-a", credentialVaultRef: "vault:bot-token", endpoint: "https://tg-hub.example.com/mcp" });
assert.ok(tg.ok, "telegram BYO endpoint connect succeeds");
assert.ok(!tg.ok || tg.connection.endpointUsed === "https://tg-hub.example.com/mcp");
const badUrl = connectPlugin({ pluginId: "telegram", tenantId: "tenant-a", credentialVaultRef: "vault:bot-token", endpoint: "not-a-url" });
assert.ok(!badUrl.ok && badUrl.error.includes("not a valid URL"), "endpoint URL is validated");

// 6. Unique per (tenant, plugin) — mirrors the SQL UNIQUE constraint.
const dup = connectPlugin({ pluginId: "github", tenantId: "tenant-a", credentialVaultRef: "vault:github-token-2" });
assert.ok(!dup.ok && dup.error.includes("already connected"), "duplicate connect is rejected");
// Same plugin, different tenant: fine.
const ghOther = connectPlugin({ pluginId: "github", tenantId: "tenant-b", credentialVaultRef: "vault:github-token" });
assert.ok(ghOther.ok, "same plugin in another tenant is allowed");

// 7. Unknown plugin fails closed.
const unknown = connectPlugin({ pluginId: "nope", tenantId: "tenant-a", credentialVaultRef: "vault:x" });
assert.ok(!unknown.ok && unknown.error.includes("Unknown marketplace plugin"));

// 8. Ledger is tenant-scoped; "*" sees all.
assert.equal(listMarketplaceConnections("tenant-a").length, 2);
assert.equal(listMarketplaceConnections("tenant-b").length, 1);
assert.equal(listMarketplaceConnections("*").length, 3);
assert.ok(listMarketplaceConnections("tenant-a").every((c) => c.tenantId === "tenant-a"));

// 9. Test hygiene: clear resets everything.
clearMarketplaceConnections();
clearRemoteServerRegistry();
assert.equal(listMarketplaceConnections("*").length, 0);

console.log("marketplace plugins tests passed");
