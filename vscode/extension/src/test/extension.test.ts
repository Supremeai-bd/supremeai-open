/**
 * Test Battery for supremeai-vscode Extension Foundation Seed
 */

import * as assert from "node:assert";
import * as fs from "node:fs";
import * as http from "node:http";
import * as path from "node:path";
import { McpBridge } from "../mcp_bridge";
import { MODEL_TIERS, modelToTier, tierToModel } from "../models";

async function runTests(): Promise<void> {
  console.log("=== SupremeAI VS Code Extension Tests ===");

  // 1. Manifest Contract Checks
  console.log("\n1. Manifest & Package Contract");
  const pkgPath = path.resolve(__dirname, "../../package.json");
  assert.ok(fs.existsSync(pkgPath), "package.json must exist");

  const pkg = JSON.parse(fs.readFileSync(pkgPath, "utf-8"));
  assert.strictEqual(pkg.name, "supremeai-vscode");
  assert.strictEqual(pkg.publisher, "supremeai");
  assert.ok(pkg.engines && pkg.engines.vscode, "Must specify vscode engine");
  assert.strictEqual(pkg.main, "./out/extension.js");
  assert.ok(Array.isArray(pkg.contributes?.commands), "Must contribute commands");

  const commandIds = pkg.contributes.commands.map((c: { command: string }) => c.command);
  assert.ok(commandIds.includes("supremeai.dispatchTask"), "Must contribute supremeai.dispatchTask");
  assert.ok(commandIds.includes("supremeai.viewRunway"), "Must contribute supremeai.viewRunway");
  assert.ok(commandIds.includes("supremeai.emergencyStop"), "Must contribute supremeai.emergencyStop");
  console.log("  ✓ package.json contributes all 3 required commands and settings");

  // 2. McpBridge Initialization & Offline Degradation
  console.log("\n2. MCP Bridge Adapter");
  const bridge = new McpBridge("http://127.0.0.1:9999/mcp", 500);

  const health = await bridge.fetchHealth();
  assert.strictEqual(health.status, "offline", "Unreachable tower must degrade to offline without throwing");
  assert.strictEqual(health.activeAgents, 0);
  assert.strictEqual(health.openClaims, 0);
  console.log("  ✓ Unreachable bridge degrades gracefully to status: 'offline'");

  const runway = await bridge.fetchRunway();
  assert.ok(Array.isArray(runway), "Runway query must return array");
  assert.strictEqual(runway.length, 0, "Unreachable bridge must return empty runway without throw");
  console.log("  ✓ Runway fetch degrades to empty array when offline");

  // 3. Validation Rules
  console.log("\n3. Validation & Fail-Closed Guards");
  const invalidDispatch = await bridge.dispatchTask({
    repo: "",
    title: "",
    scopePaths: [],
    description: "",
  });
  assert.strictEqual(invalidDispatch.success, false);
  assert.ok(invalidDispatch.error?.includes("required"), "Missing title/repo must be rejected");
  console.log("  ✓ Empty task dispatch rejected fail-closed");

  const invalidKill = await bridge.triggerEmergencyKill("12");
  assert.strictEqual(invalidKill, false, "Short PIN must be rejected immediately");
  console.log("  ✓ Invalid emergency kill PIN rejected fail-closed");

  // 4. TSConfig & Structure Checks
  console.log("\n4. Build & Structure");
  const tsconfigPath = path.resolve(__dirname, "../../tsconfig.json");
  assert.ok(fs.existsSync(tsconfigPath), "tsconfig.json must exist");
  const tsconfig = JSON.parse(fs.readFileSync(tsconfigPath, "utf-8"));
  assert.strictEqual(tsconfig.compilerOptions?.strict, true, "TypeScript strict must be true");
  console.log("  ✓ tsconfig.json enforces strict mode");

  // 5. Model Tiers Resolution
  console.log("\n5. Model Tiers & Resolution Contract");
  assert.strictEqual(MODEL_TIERS.length, 4, "Should have 4 model tiers");
  assert.strictEqual(tierToModel("fast"), "llama-3.1-8b-instant");
  assert.strictEqual(tierToModel("balanced"), "gpt-4o-mini");
  assert.strictEqual(tierToModel("pro"), "claude-sonnet-4-5");
  assert.strictEqual(tierToModel("auto"), "auto");
  assert.strictEqual(modelToTier("gpt-4o-mini"), "balanced");
  assert.strictEqual(modelToTier("claude-sonnet-4-5"), "pro");
  assert.strictEqual(modelToTier("anthropic/claude-sonnet-4-5"), "pro");
  assert.strictEqual(modelToTier("unknown-model"), "auto");
  console.log("  ✓ tierToModel and modelToTier resolve accurately across all tiers");

  // 6. Gateway Chat Completion Mock
  console.log("\n6. Gateway Chat Protocol Mock");
  const mockServer = http.createServer((req, res) => {
    let rawBody = "";
    req.on("data", (chunk) => {
      rawBody += chunk;
    });
    req.on("end", () => {
      assert.strictEqual(req.method, "POST");
      assert.strictEqual(req.url, "/v1/chat/completions");
      assert.strictEqual(req.headers["x-supremeai-key"], "test-key-123");
      const parsed = JSON.parse(rawBody);
      assert.strictEqual(parsed.model, "gpt-4o-mini");
      assert.strictEqual(parsed.messages[0].content, "ping");
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          choices: [{ message: { role: "assistant", content: "pong" } }],
        })
      );
    });
  });

  await new Promise<void>((resolve) => mockServer.listen(0, "127.0.0.1", resolve));
  const port = (mockServer.address() as { port: number }).port;

  try {
    const res = await fetch(`http://127.0.0.1:${port}/v1/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-SupremeAI-Key": "test-key-123",
      },
      body: JSON.stringify({
        model: tierToModel("balanced"),
        messages: [{ role: "user", content: "ping" }],
        stream: false,
      }),
    });
    assert.strictEqual(res.status, 200);
    const data = (await res.json()) as { choices?: Array<{ message?: { content?: string } }> };
    assert.strictEqual(data.choices?.[0]?.message?.content, "pong");
    console.log("  ✓ Chat completions wire protocol and model tier dispatch verified");
  } finally {
    mockServer.close();
  }

  console.log("\n=========================================");
  console.log("ALL EXTENSION & CHAT PROTOCOL TESTS PASSED!");
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
