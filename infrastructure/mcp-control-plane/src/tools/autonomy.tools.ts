import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { globalKillSwitch } from "../remediation/killswitch.js";

export async function registerAutonomyTools(server: McpServer): Promise<void> {
  server.tool(
    "autonomy.status",
    "Check if Autonomous Remediation is currently ENABLED or DISABLED (with persistence truth: env gate, Redis-persisted state, last sync error).",
    {},
    async () => {
      const enabled = globalKillSwitch.isAutonomyEnabled();
      const detail = globalKillSwitch.describe();
      const lines = [
        `Autonomy is currently ${enabled ? "ENABLED ✅" : "DISABLED 🚨"}`,
        `persistence: ${detail.persistEnabled ? "redis-backed" : "in-memory only (no Redis config — restart resets manual stops)"}`,
        `persistedState: ${detail.persistedState}`,
        `envGate(AUTONOMY_DISABLED): ${detail.envGate ? "present" : "absent"}`,
      ];
      if (detail.lastPersistError) lines.push(`lastPersistError: ${detail.lastPersistError}`);
      if (detail.lastRestoreError) lines.push(`lastRestoreError: ${detail.lastRestoreError}`);
      return {
        content: [{ type: "text", text: lines.join("\n") }],
      };
    }
  );

  server.tool(
    "autonomy.kill_switch",
    "Emergency stop! Instantly disable all autonomous remediations (persisted to Redis — survives restarts; admin-only).",
    {},
    async () => {
      globalKillSwitch.emergencyStop();
      return {
        content: [{ type: "text", text: `🚨 AUTONOMY KILLED. System is now in L0 (Read-Only) mode. Decision persisted — it survives restarts (fail-closed if persistence errored; see autonomy.status).` }],
      };
    }
  );

  server.tool(
    "autonomy.enable",
    "Re-enable autonomous remediations.",
    {},
    async () => {
      globalKillSwitch.enableAutonomy();
      return {
        content: [{ type: "text", text: `✅ AUTONOMY ENABLED.` }],
      };
    }
  );
}
