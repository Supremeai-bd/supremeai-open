import assert from "node:assert/strict";
import { clearRemoteServerRegistry, registerRemoteServer } from "../src/registry/remote-mcp-servers.js";
import { clearDiscoveryCache, getDiscoverySnapshot } from "../src/federation/server-discovery.js";
import { listAggregatedTools } from "../src/federation/aggregator.js";

clearRemoteServerRegistry();
clearDiscoveryCache();
const server = registerRemoteServer({ name: "fixture", protocol: "streamable-http", endpoint: "https://fixture.invalid/mcp", tenantId: "tenant-a", scopes: [], trustLevel: "tenant" });
assert.equal(server.status, "pending");
assert.equal(listAggregatedTools("tenant-a").length, 0);
assert.equal(listAggregatedTools("tenant-b").length, 0);
assert.equal(getDiscoverySnapshot(server.id), undefined);
console.log("federation registry tests passed");
