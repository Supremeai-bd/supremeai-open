import assert from "node:assert/strict";
import { approveClient, defaultClientScopes, getOrCreateGuestClient, listClients, registerClient, resolveClient, revokeClient, rotateClient } from "./src/policy/client-registry.js";

const created = registerClient("Customer AI", "viewer", defaultClientScopes("viewer"), undefined, "customer-ai", "streamable-http");
assert.equal(created.client.provider, "customer-ai");
assert.equal(created.client.protocol, "streamable-http");
assert.equal(created.client.role, "viewer");
assert.equal(created.client.status, "pending");
assert.equal(resolveClient(created.token), undefined);
assert.equal(approveClient(created.client.id)?.status, "active");
assert.equal(resolveClient(created.token)?.id, created.client.id);
assert.ok(created.client.scopes.includes("health:read"));
const rotated = rotateClient(created.client.id);
assert.ok(rotated?.token);
assert.equal(resolveClient(created.token), undefined);
assert.equal(resolveClient(rotated!.token)?.id, created.client.id);
assert.equal(revokeClient(created.client.id), true);
assert.equal(resolveClient(rotated!.token), undefined);

// ── #2588: guest auto-registration contract ─────────────────────────────
// Zero-manual-registration for no-auth AI clients + live protocol refresh.
const guestSse = getOrCreateGuestClient("guest_test_registry_1", "Test Guest (1.2.3.4)", "cursor", "sse");
assert.equal(guestSse.status, "active");
assert.equal(guestSse.role, "admin"); // pre-production default: admin role until production ready
assert.equal(guestSse.protocol, "sse");

// Reconnect over streamable-http → SAME record, protocol follows the latest transport.
const guestHttp = getOrCreateGuestClient("guest_test_registry_1", "Test Guest (1.2.3.4)", "cursor", "streamable-http");
assert.equal(guestHttp.id, guestSse.id);
assert.equal(guestHttp.protocol, "streamable-http");

// Name-based reuse path (#1787): different preferred id, same name → same record.
const guestByName = getOrCreateGuestClient("guest_some_other_id", "Test Guest (1.2.3.4)", "cursor", "sse");
assert.equal(guestByName.id, guestSse.id);
assert.equal(guestByName.protocol, "sse");

// A known provider label upgrades a previously-generic record on reuse.
const relabeled = getOrCreateGuestClient("guest_test_registry_1", "Test Guest (1.2.3.4)", "grok-lab", "sse");
assert.equal(relabeled.provider, "grok-lab");

// Same display name in the same tenant reuses the record (#1787 name-dedupe
// precedence over the #2030 auto-increment path) — guest names embed the IP,
// so an identical name is the SAME logical client reconnecting.
const guestA = getOrCreateGuestClient("guest_t2_a", "Second Guest", "generic", "stdio", "tenant_two");
const guestB = getOrCreateGuestClient("guest_t2_b", "Second Guest", "generic", "stdio", "tenant_two");
assert.equal(guestB.id, guestA.id);
assert.equal(guestB.name, "Second Guest");

// Guests are visible to tenant admins via listClients.
assert.ok(listClients("*").some((c) => c.id === guestSse.id));
assert.ok(listClients("tenant_two").some((c) => c.id === guestA.id));


// ── #110: 6-tier RBAC ladder + named client identity ────────────────────
// বাংলা মন্তব্য: ৬-স্তর রোল ল্যাডার, র‍্যাঙ্ক-ভিত্তিক roleAllows, এবং
// named_ রেকর্ডের স্থায়িত্ব — সব এখানে যাচাই করা হয়।
import { roleRank, ROLE_RANK } from "./src/policy/auth.context.js";
import { changeClientRole, roleAllows } from "./src/policy/client-registry.js";
import { RequestContextStore } from "./src/policy/auth.context.js";
import { assertRepoReadAccess, repoAccessFor } from "./src/tools/github.tools.js";

// 1. Rank ladder is strictly monotonic.
assert.equal(ROLE_RANK.viewer, 0);
assert.ok(ROLE_RANK.restricted_viewer < ROLE_RANK.repo_viewer);
assert.ok(ROLE_RANK.repo_viewer < ROLE_RANK.agent);
assert.ok(ROLE_RANK.agent < ROLE_RANK.admin);
assert.ok(ROLE_RANK.admin < ROLE_RANK.supremeadmin);
assert.equal(roleRank(undefined), 0); // fail-closed

// 2. roleAllows: read-only tiers pass viewer-level, never agent/admin-level.
assert.equal(roleAllows("viewer", "viewer"), true);
assert.equal(roleAllows("viewer", "agent"), false);
assert.equal(roleAllows("restricted_viewer", "viewer"), true);
assert.equal(roleAllows("restricted_viewer", "agent"), false);
assert.equal(roleAllows("repo_viewer", "viewer"), true);
assert.equal(roleAllows("repo_viewer", "agent"), false);
assert.equal(roleAllows("agent", "agent"), true);
assert.equal(roleAllows("agent", "admin"), false);
assert.equal(roleAllows("admin", "admin"), true);
assert.equal(roleAllows("supremeadmin", "admin"), true);
assert.equal(roleAllows("supremeadmin", "agent"), true);

// 3. Scope matrix: new tiers carry repo-read scopes; agent keeps execute.
assert.ok(defaultClientScopes("restricted_viewer").includes("repos:satellite:read"));
assert.ok(!defaultClientScopes("restricted_viewer").includes("repos:all:read"));
assert.ok(defaultClientScopes("repo_viewer").includes("repos:all:read"));
assert.ok(defaultClientScopes("agent").includes("tools:execute"));
assert.deepEqual(defaultClientScopes("admin"), ["*"]);

// 4. Role change re-derives scopes; role survives re-registration lookups.
const up = registerClient("Tier Client", "viewer", defaultClientScopes("viewer"));
assert.equal(up.client.role, "viewer");
const promoted = changeClientRole(up.client.id, "repo_viewer");
assert.equal(promoted?.role, "repo_viewer");
assert.ok(promoted?.scopes.includes("repos:all:read"));

// 5. Named client record: stable id, role upgrades persist (database truth).
changeClientRole("named_pko_main", "admin");
const namedA = getOrCreateGuestClient("named_pko_main", "Named Client: pko_main (xAI Grok Web)", "xai", "streamable-http");
assert.equal(namedA.id, "named_pko_main");
assert.equal(namedA.role, "admin");
changeClientRole("named_pko_main", "agent");
const namedB = getOrCreateGuestClient("named_pko_main", "Named Client: pko_main (xAI Grok Web)", "xai", "sse");
assert.equal(namedB.id, "named_pko_main");
assert.equal(namedB.role, "agent"); // promotion survives reconnect — #110 contract

// 6. Repo-isolation matrix (github.tools middleware).
assert.equal(repoAccessFor("viewer"), "none");
assert.equal(repoAccessFor("restricted_viewer"), "satellite-readonly");
assert.equal(repoAccessFor("repo_viewer"), "all-readonly");
assert.equal(repoAccessFor("agent"), "read-write");
assert.equal(repoAccessFor("admin"), "read-write");
assert.equal(repoAccessFor("supremeadmin"), "read-write");

// 6a. restricted_viewer: satellite repo allowed, core repo BLOCKED, supremeai-api cloaked.
const satUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-browser";
const coreUrl = "https://api.github.com/repos/Supremeai-bd/supremeai";
const cloakedApiUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-api";
const rvScopes = defaultClientScopes("restricted_viewer");
let deny = RequestContextStore.run({ role: "restricted_viewer", scopes: rvScopes }, () =>
  assertRepoReadAccess("github.read_file", "gh-sat", satUrl));
assert.equal(deny, null, `satellite read should pass for restricted_viewer: ${deny}`);
deny = RequestContextStore.run({ role: "restricted_viewer", scopes: rvScopes }, () =>
  assertRepoReadAccess("github.read_file", "gh-core", coreUrl));
assert.ok(deny && deny.includes("satellite"), "core repo must be blocked for restricted_viewer");
const denyCloaked = RequestContextStore.run({ role: "restricted_viewer", scopes: rvScopes }, () =>
  assertRepoReadAccess("github.read_file", "gh-sat", cloakedApiUrl));
assert.ok(denyCloaked && denyCloaked.includes("Repository not found: 'supremeai-api'"), "supremeai-api must be cloaked into ghost mode for restricted_viewer");

// 6b. repo_viewer: satellite repos readable with scope; core repo blocked (admin-only).
deny = RequestContextStore.run({ role: "repo_viewer", scopes: defaultClientScopes("repo_viewer") }, () =>
  assertRepoReadAccess("github.read_file", "gh-sat", satUrl));
assert.equal(deny, null, `repo_viewer must read satellite repo: ${deny}`);
deny = RequestContextStore.run({ role: "repo_viewer", scopes: defaultClientScopes("repo_viewer") }, () =>
  assertRepoReadAccess("github.read_file", "gh-core", coreUrl));
assert.ok(deny && deny.includes("strictly restricted to admin and supremeadmin"), "core repo must be blocked for repo_viewer");

// 6c. viewer: no repo access at all; no context: default-deny.
deny = RequestContextStore.run({ role: "viewer", scopes: defaultClientScopes("viewer") }, () =>
  assertRepoReadAccess("github.read_file", "gh-sat", satUrl));
assert.ok(deny && deny.includes("no repository read access"));
deny = assertRepoReadAccess("github.read_file", "gh-sat", satUrl);
assert.ok(deny && deny.includes("authenticated request context"));

// 6d. agent: satellite read-write; core repo blocked (admin-only).
deny = RequestContextStore.run({ role: "agent", scopes: ["tools:execute"] }, () =>
  assertRepoReadAccess("github.read_file", "gh-sat", satUrl));
assert.equal(deny, null, `agent must read satellite repo: ${deny}`);
deny = RequestContextStore.run({ role: "agent", scopes: ["tools:execute"] }, () =>
  assertRepoReadAccess("github.read_file", "gh-core", coreUrl));
assert.ok(deny && deny.includes("strictly restricted to admin and supremeadmin"), "core repo must be blocked for agent");

// 6e. admin & supremeadmin: full access to core monorepo.
deny = RequestContextStore.run({ role: "admin", scopes: ["tools:execute"] }, () =>
  assertRepoReadAccess("github.read_file", "gh-core", coreUrl));
assert.equal(deny, null, `admin must read core repo: ${deny}`);
deny = RequestContextStore.run({ role: "supremeadmin", scopes: ["tools:execute"] }, () =>
  assertRepoReadAccess("github.read_file", "gh-core", coreUrl));
assert.equal(deny, null, `supremeadmin must read core repo: ${deny}`);

console.log("client registry contract tests passed");
