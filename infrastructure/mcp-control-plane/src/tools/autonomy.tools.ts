import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { globalKillSwitch } from "../remediation/killswitch.js";

export async function registerAutonomyTools(server: McpServer): Promise<void> {
  server.tool(
    "autonomy.status",
    "Check if Autonomous Remediation is currently ENABLED or DISABLED.",
    {},
    async () => {
      const enabled = globalKillSwitch.isAutonomyEnabled();
      return {
        content: [{ type: "text", text: `Autonomy is currently ${enabled ? "ENABLED ✅" : "DISABLED 🚨"}` }],
      };
    }
  );

  server.tool(
    "autonomy.kill_switch",
    "Emergency stop! Instantly disable all autonomous remediations.",
    {},
    async () => {
      globalKillSwitch.emergencyStop();
      return {
        content: [{ type: "text", text: `🚨 AUTONOMY KILLED. System is now in L0 (Read-Only) mode.` }],
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
