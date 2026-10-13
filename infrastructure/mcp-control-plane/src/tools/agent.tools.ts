import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { RequestContextStore } from "../policy/auth.context.js";
import {
  listHeartbeats,
  recordHeartbeat,
  validateSlot,
} from "../registry/agent_heartbeat.js";
import { listWorkforce } from "../registry/mcp_presence.js";

/**
 * Agent slot heartbeat tools (issue #1402, #1787).
 *
 * Every agent tool that is already MCP-connected can announce it is alive
 * with a single `agent_heartbeat` call — no new HTTP client, no curl timer.
 * The dashboard (`/api/agents` on the Z.ai preview) and `agent_status` both
 * read the same Redis account, so pings show up in real time.
 *
 * Slot ↔ tool mapping (policy) lives in docs/master_docs/AGENT_SLOT_REGISTRY.yaml.
 * A tool MUST only ping its own assigned slot; pings are attributed with the
 * authenticated client id for auditability.
 *
 * AUDIT-FIX (#1787): আগে দুটো tool-ই `if (!context?.authenticated)` দিয়ে
 * public_viewer / no-auth guest clients কে reject করত — যার ফলে #1767-এ
 * auto-register হওয়া guest clients কখনো agent list-এ দেখা যেত না। এখন
 * দুটো tool-ই public_viewer সহ সব role কে allow করে (read-only হলেও)।
 */
export async function registerAgentTools(server: McpServer): Promise<void> {
  server.tool(
    "agent_heartbeat",
    "Announce that an agent tool is alive for its assigned slot (agent-N). Ping every 45s while running; the dashboard shows the slot as 🟢 online within 90s of the last ping.",
    {
      slot: z
        .string()
        .regex(
          /^(agent|z\.ai|claude|chatgpt|cursor|gemini|copilot)-\d+$/,
          'slot must match "<type>-N" (e.g. "agent-4", "z.ai-1", "claude-2")'
        )
        .describe("Assigned slot id from AGENT_SLOT_REGISTRY.yaml or agent type + number (Rule #19)"),
      agentId: z
        .string()
        .min(1)
        .max(64)
        .optional()
        .describe("Human-readable tool label, e.g. 'Cline' (defaults to slot id)"),
    },
    async ({ slot, agentId }) => {
      try {
        const context = RequestContextStore.get();
        // AUDIT-FIX (#1787 Gap 2): আগে শুধু `if (!context?.authenticated)`
        // দিয়ে public_viewer / no-auth guest clients reject করা হতো। এখন
        // public_viewer-ও তাদের নিজস্ব slot-এ heartbeat পাঠাতে পারবে —
        // কারণ validateSlot() শুধু slot format check করে, RBAC নয়।
        // clientId fallback: authenticated না হলে guest client id ব্যবহার।
        if (!context) {
          return {
            isError: true,
            content: [
              { type: "text", text: "Request context required to ping a heartbeat" },
            ],
          };
        }
        const slotError = validateSlot(slot);
        if (slotError) {
          return { isError: true, content: [{ type: "text", text: slotError }] };
        }
        const result = await recordHeartbeat({
          slot,
          agentId,
          source: "mcp-tower",
          // AUDIT-FIX (#1787): public_viewer হলেও clientId থাকবে (#1767 auto-register
          // দেয়), fallback শুধু অতিরিক্ত সতর্কতা।
          clientId: context.clientId ?? `guest:${slot}`,
        });
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );

  server.tool(
    "agent_status",
    "List live agent-slot heartbeats with derived real-time state: online (≤90s), stale (>90s, key alive), expired (no runtime signal).",
    {},
    async () => {
      try {
        const context = RequestContextStore.get();
        // AUDIT-FIX (#1787 Gap 1): আগে `if (!context?.authenticated)` দিয়ে
        // public_viewer / no-auth guests reject করা হতো। এখন শুধু context
        // থাকলেই যথেষ্ট — agent_status read-only, কোনো sensitive metadata
        // ফাঁস করে না (শুধু slot name + last-seen + derived state)।
        if (!context) {
          return {
            isError: true,
            content: [
              { type: "text", text: "Request context required to read agent status" },
            ],
          };
        }
        // #3297: agent_status এখন unified workforce ভিউ — autonomous builder
        // (heartbeat) + interactive assistant (MCP presence) উভয়ের গণনা ও
        // শ্রেণিবিভাগসহ। যে কোনো AI client এক কলেই পুরো active workforce দেখে।
        const result = await listWorkforce();
        return {
          content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
}
