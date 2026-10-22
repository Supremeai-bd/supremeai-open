import assert from "node:assert/strict";
import {
  buildAccountRegistry,
  CANONICAL_FEDERATION_REPOS,
  getTrackedOrgRepos,
  registerDiscoveredOrgRepo,
  GITHUB_ORGANIZATION,
} from "./src/registry/account.registry.js";
import { getAccountConfig } from "./src/adapters/github/index.js";
import {
  assertRepoReadAccess,
  isSatelliteRepo,
  repoAccessFor,
  repoUrlFor,
  SATELLITE_REPOS,
} from "./src/tools/github.tools.js";
import { RequestContextStore } from "./src/policy/auth.context.js";
import { defaultClientScopes } from "./src/policy/client-registry.js";

console.log("Starting hybrid repo access & organization discovery tests...");

// 1. Verify organization registry configuration
assert.equal(GITHUB_ORGANIZATION, "Supremeai-bd");
assert.equal(CANONICAL_FEDERATION_REPOS.length, 8);
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-open"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-core"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-api"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-browser"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-studio"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-vscode"));
assert.ok(CANONICAL_FEDERATION_REPOS.includes("supremeai-archive"));

const initialTracked = getTrackedOrgRepos();
assert.equal(initialTracked.length, 8);

// Org-level monitor account presence in registry
const accounts = buildAccountRegistry();
const orgMonitor = accounts.find((a) => a.id === "github-org-supremeai-bd");
assert.ok(orgMonitor, "Must have github-org-supremeai-bd account in registry");
assert.equal(orgMonitor.url, "https://api.github.com/orgs/Supremeai-bd");
assert.equal(orgMonitor.role, "organization");

// Dynamic registration test
registerDiscoveredOrgRepo("supremeai-experimental-lab");
const updatedTracked = getTrackedOrgRepos();
assert.ok(updatedTracked.includes("supremeai-experimental-lab"));
const updatedAccounts = buildAccountRegistry();
const dynAccount = updatedAccounts.find((a) => a.id === "github-pay-supremeai-experimental-lab");
assert.ok(dynAccount, "Dynamic repo should register an account");
assert.equal(dynAccount.url, "https://api.github.com/repos/Supremeai-bd/supremeai-experimental-lab");

// 2. Hybrid repo URL resolution
assert.equal(
  repoUrlFor(undefined, "supremeai-studio"),
  "https://api.github.com/repos/Supremeai-bd/supremeai-studio"
);
assert.equal(
  repoUrlFor("github-primary", "Supremeai-bd/supremeai-browser"),
  "https://api.github.com/repos/Supremeai-bd/supremeai-browser"
);
assert.equal(
  repoUrlFor("github-primary"),
  "https://api.github.com/repos/Supremeai-bd/supremeai"
);

// 3. Adapter getAccountConfig resolution
process.env.GITHUB_TOKEN = process.env.GITHUB_TOKEN || "test-gh-token-dummy";
const studioConfig = getAccountConfig("supremeai-studio");
assert.equal(studioConfig.baseUrl, "https://api.github.com/repos/Supremeai-bd/supremeai-studio");
assert.ok(studioConfig.apiKey);

const browserConfig = getAccountConfig("Supremeai-bd/supremeai-browser");
assert.equal(browserConfig.baseUrl, "https://api.github.com/repos/Supremeai-bd/supremeai-browser");

// 4. Satellite classification
assert.equal(isSatelliteRepo("supremeai"), false, "supremeai is core monorepo, not satellite");
assert.equal(isSatelliteRepo("supremeai-open"), true);
assert.equal(isSatelliteRepo("supremeai-studio"), true);
assert.equal(isSatelliteRepo("supremeai-core"), true);
assert.equal(isSatelliteRepo("supremeai-vscode"), true);
assert.equal(isSatelliteRepo("supremeai-browser"), true);
assert.equal(isSatelliteRepo("supremeai-archive"), true);
assert.equal(SATELLITE_REPOS.has("supremeai-studio"), true);
assert.equal(SATELLITE_REPOS.has("supremeai-browser"), true);

// 5. Authority matrix checks across hybrid repositories
const coreUrl = "https://api.github.com/repos/Supremeai-bd/supremeai";
const studioUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-studio";
const browserUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-browser";

// 5a. Agent authority (Rank = 3) — can access satellite repos, blocked from core monorepo
RequestContextStore.run({ role: "agent", scopes: ["tools:execute"] }, () => {
  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.ok(
    denyCore && denyCore.includes("strictly restricted to admin and supremeadmin"),
    "Agent must be blocked from core repo"
  );

  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.equal(denyStudio, null, "Agent must be permitted to read satellite repo supremeai-studio");

  const denyBrowser = assertRepoReadAccess("github.read_file", "supremeai-browser", browserUrl);
  assert.equal(denyBrowser, null, "Agent must be permitted to read satellite repo supremeai-browser");

  // Ghost Cloaking verification: supremeai-api is completely air-gapped from regular agents
  const apiUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-api";
  const denyApi = assertRepoReadAccess("github.read_file", "supremeai-api", apiUrl);
  assert.equal(denyApi, "Repository not found: 'supremeai-api'.", "Agent must receive Repository not found for cloaked supremeai-api");
});

// 5a.1 Admin & Supremeadmin authority (Rank >= 4) — can access core repo and all satellites
RequestContextStore.run({ role: "admin", scopes: ["tools:execute"] }, () => {
  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.equal(denyCore, null, "Admin must be permitted to read core repo");

  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.equal(denyStudio, null, "Admin must be permitted to read satellite repo");

  const apiUrl = "https://api.github.com/repos/Supremeai-bd/supremeai-api";
  const denyApiAdmin = assertRepoReadAccess("github.read_file", "supremeai-api", apiUrl);
  assert.equal(denyApiAdmin, null, "Admin must be permitted to read cloaked repo");
});

RequestContextStore.run({ role: "supremeadmin", scopes: ["tools:execute"] }, () => {
  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.equal(denyCore, null, "Supremeadmin must be permitted to read core repo");

  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.equal(denyStudio, null, "Supremeadmin must be permitted to read satellite repo");
});

// 5b. Restricted viewer authority — satellite allowed, core blocked
const rvScopes = defaultClientScopes("restricted_viewer");
RequestContextStore.run({ role: "restricted_viewer", scopes: rvScopes }, () => {
  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.equal(denyStudio, null, "restricted_viewer must be permitted to read satellite repo");

  const denyBrowser = assertRepoReadAccess("github.read_file", "supremeai-browser", browserUrl);
  assert.equal(denyBrowser, null, "restricted_viewer must be permitted to read satellite repo");

  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.ok(denyCore && (denyCore.includes("restricted to admin") || denyCore.includes("satellite repos")), "restricted_viewer must be blocked from core repo");
});

// 5c. Repo viewer (Auditor) authority — satellite repos readable with scope; core monorepo blocked
const audScopes = defaultClientScopes("repo_viewer");
RequestContextStore.run({ role: "repo_viewer", scopes: audScopes }, () => {
  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.ok(
    denyCore && denyCore.includes("strictly restricted to admin and supremeadmin"),
    "repo_viewer must be blocked from core repo"
  );

  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.equal(denyStudio, null, "repo_viewer must read satellite repo");
});

// 5d. Guest viewer authority — blocked from all repos except public docs
const guestScopes = defaultClientScopes("viewer");
RequestContextStore.run({ role: "viewer", scopes: guestScopes }, () => {
  const denyCore = assertRepoReadAccess("github.read_file", "supremeai", coreUrl);
  assert.ok(denyCore && denyCore.includes("no repository read access"));

  const denyStudio = assertRepoReadAccess("github.read_file", "supremeai-studio", studioUrl);
  assert.ok(denyStudio && denyStudio.includes("no repository read access"));
});

// 5e. Organization-level resource access: admin/supremeadmin allowed, agent blocked
const orgUrl = "https://api.github.com/orgs/Supremeai-bd";
RequestContextStore.run({ role: "agent", scopes: ["tools:execute"] }, () => {
  const denyOrg = assertRepoReadAccess("github.workflow_runs", "github-org-supremeai-bd", orgUrl);
  assert.ok(denyOrg && denyOrg.includes("organization-level resources are strictly restricted to admin"), "agent must be blocked from org-level resources");
});

RequestContextStore.run({ role: "admin", scopes: ["tools:execute"] }, () => {
  const denyOrg = assertRepoReadAccess("github.workflow_runs", "github-org-supremeai-bd", orgUrl);
  assert.equal(denyOrg, null, "admin must be allowed to access org-level resources");
});

// 6. Role-aware account registry filtering verification (getAccountsForRole)
import { getAccountsForRole } from "./src/registry/account.registry.js";

const adminAccs = getAccountsForRole("admin");
assert.ok(adminAccs.some((a) => a.id === "github-primary"), "admin must see github-primary");
assert.ok(adminAccs.some((a) => a.id === "github-org-supremeai-bd"), "admin must see github-org-supremeai-bd");

const agentAccs = getAccountsForRole("agent");
assert.ok(!agentAccs.some((a) => a.id === "github-primary"), "agent must NOT see github-primary");
assert.ok(!agentAccs.some((a) => a.id === "github-org-supremeai-bd"), "agent must NOT see github-org-supremeai-bd");
assert.ok(!agentAccs.some((a) => a.id.includes("supremeai-api")), "agent must NOT see supremeai-api");
assert.ok(!agentAccs.some((a) => a.id.includes("supremeai-core")), "agent must NOT see supremeai-core");
assert.ok(!agentAccs.some((a) => a.id.includes("supremeai-command")), "agent must NOT see supremeai-command");
assert.ok(!agentAccs.some((a) => a.id.includes("supremeai-infrastructure")), "agent must NOT see supremeai-infrastructure");
assert.ok(agentAccs.some((a) => a.id.includes("supremeai-open")), "agent must see supremeai-open");

const viewerAccs = getAccountsForRole("viewer");
const viewerGhAccs = viewerAccs.filter((a) => a.provider === "github");
assert.equal(viewerGhAccs.length, 1, "viewer must only see 1 GitHub account (supremeai-open)");
assert.ok(viewerGhAccs[0].id.includes("supremeai-open"), "viewer GitHub account must be supremeai-open");

console.log("All hybrid repo access & organization discovery tests passed successfully!");
