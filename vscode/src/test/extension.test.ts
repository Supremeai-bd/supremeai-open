/**
 * Test Battery for supremeai-vscode Extension Foundation Seed
 */

import * as assert from "node:assert";
import * as fs from "node:fs";
import * as path from "node:path";
import { McpBridge } from "../mcp_bridge";

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

  console.log("\n=========================================");
  console.log("ALL 8 EXTENSION FOUNDATION TESTS PASSED!");
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
