import assert from "node:assert/strict";
import { accessModeFor, canAccessCapability, publicSafeCapabilities } from "./src/policy/mcp-access.js";

const publicContext = { mode: "public_viewer" as const, role: "viewer" as const, authenticated: false, tenantBound: false, scopes: [] };
const agentContext = { mode: "agent" as const, role: "agent" as const, authenticated: true, tenantBound: true, scopes: ["health:read"] };

assert.equal(accessModeFor(null, false), "public_viewer");
assert.equal(canAccessCapability(publicContext, publicSafeCapabilities[0]), true);
assert.equal(canAccessCapability(publicContext, { ...publicSafeCapabilities[0], dataClassification: "tenant_private" }), false);
assert.equal(canAccessCapability(publicContext, { ...publicSafeCapabilities[0], access: "restricted" }), false);
assert.equal(canAccessCapability(agentContext, publicSafeCapabilities[1]), true);
assert.equal(canAccessCapability(agentContext, { ...publicSafeCapabilities[1], requiredScope: "system:read" }), false);
console.log("MCP access policy tests passed");
