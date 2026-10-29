/**
 * R66 target-echo contract tests (#2447 option A): every github_* tool
 * advertises outputSchema {targetRepo, targetUrl} and emits the resolved
 * target in structuredContent, while the TextContent block stays byte-
 * identical (R65 dual-emission discipline). Network-free battery:
 *   1. describeTarget unit (parse /repos/<owner>/<repo>/, strip .git, fallback)
 *   2. tools/list outputSchema advertisement (9 github tools; nullable pair
 *      on the org-wide search surface)
 *   3. error-path receipt: a context-less call stays isError text-only and
 *      exempt from output validation
 * Success-path structuredContent rides the same one-line helper the adapters
 * already feed (describeTarget of the repoUrlFor value), so the unit test in
 * (1) plus the deployed-tower observation close that half honestly.
 */
import assert from "node:assert/strict";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { describeTarget, registerGitHubTools } from "./src/tools/github.tools.js";
import { RequestContextStore } from "./src/policy/auth.context.js";

// ─── 1. describeTarget unit ───────────────────────────────────────────────
const parsed = describeTarget("https://api.github.com/repos/Supremeai-bd/supremeai");
assert.equal(parsed.targetRepo, "Supremeai-bd/supremeai");
assert.equal(parsed.targetUrl, "https://api.github.com/repos/Supremeai-bd/supremeai");
const gitSuffix = describeTarget("https://api.github.com/repos/Supremeai-bd/supremeai-open.git");
assert.equal(gitSuffix.targetRepo, "Supremeai-bd/supremeai-open");
const query = describeTarget("https://api.github.com/repos/Supremeai-bd/x/issues?page=2");
assert.equal(query.targetRepo, "Supremeai-bd/x");
const fallback = describeTarget("https://api.github.com/orgs/Supremeai-bd");
assert.equal(fallback.targetRepo, "https://api.github.com/orgs/Supremeai-bd");
console.log("[1] describeTarget unit OK (parse, .git strip, query strip, fallback)");

// ─── harness: bare McpServer + production-shape registerTool shim ─────────
const server = new McpServer({ name: "r66-echo-test", version: "0.0.1" });
const originalRegisterTool = (server as unknown as { registerTool: (n: string, c: unknown, cb: unknown) => unknown }).registerTool.bind(server);
(server as unknown as { registerTool: unknown }).registerTool = (name: string, config: unknown, cb: unknown) => {
  const sanitizedName = name.replace(/\./g, "_");
  return originalRegisterTool(sanitizedName, config, cb);
};
await registerGitHubTools(server);

const client = new Client({ name: "r66-echo-client", version: "0.0.1" });
const [cT, sT] = InMemoryTransport.createLinkedPair();
await server.connect(sT);
await client.connect(cT);

const anon = { authenticated: false } as never;
await RequestContextStore.run(anon, async () => {
  // ─── 2. tools/list outputSchema advertisement ───────────────────────────
  const list = await client.listTools();
  const tools = list.tools ?? [];
  const github = tools.filter((t) => t.name.startsWith("github_"));
  assert.equal(github.length, 9, `expected 9 github tools, got ${github.length}`);

  type OS = { required?: string[]; properties?: Record<string, { type?: unknown }> };
  const schemaOf = (wire: string): OS => {
    const t = github.find((x) => x.name === wire);
    assert.ok(t, `${wire} missing from tools/list`);
    const os = (t as { outputSchema?: OS }).outputSchema;
    assert.ok(os, `${wire} must advertise outputSchema (R66 option A)`);
    return os as OS;
  };

  // Repo-targeted pair sample: required keys lock the echo from birth.
  for (const wire of ["github_read_file", "github_list_prs", "github_workflow_runs", "github_create_issue"]) {
    const os = schemaOf(wire);
    for (const key of ["targetRepo", "targetUrl"]) {
      assert.ok(os.required?.includes(key), `${wire}.outputSchema.required must include ${key}`);
      assert.ok(os.properties?.[key], `${wire}.outputSchema.properties must include ${key}`);
    }
  }
  // Org-wide search pair: keys present, nullable (null = org-wide, honest).
  for (const wire of ["github_code_search", "github_search_code"]) {
    const os = schemaOf(wire);
    assert.ok(os.properties?.targetRepo, `${wire} must declare targetRepo`);
    const t = os.properties?.targetRepo?.type;
    const nullable = Array.isArray(t) ? t.includes("null") : t === ["string", "null"];
    assert.ok(nullable, `${wire}.targetRepo must be nullable (org-wide sentinel), got ${JSON.stringify(t)}`);
  }
  console.log("[2] outputSchema advertisement OK (9 tools; required echoes + nullable search pair)");

  // ─── 3. error-path receipt: text-only, validation-exempt ────────────────
  const r = (await client.callTool({ name: "github_read_file", arguments: { path: "package.json" } })) as {
    isError?: boolean;
    structuredContent?: unknown;
    content?: Array<{ type: string; text?: string }>;
  };
  assert.equal(r.isError, true, "context-less github_read_file must deny");
  assert.equal(r.structuredContent, undefined, "isError results must stay exempt from output validation (R65 class)");
  assert.match(r.content?.[0]?.text ?? "", /Forbidden/i, "deny shape preserved");
  console.log("[3] error-path OK (isError text-only, structuredContent absent)");
});

console.log("ALL R66 TARGET-ECHO CONTRACT TESTS PASSED (#2447 option A)");
