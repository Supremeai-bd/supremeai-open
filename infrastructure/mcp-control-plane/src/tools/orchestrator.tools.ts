import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { RequestContextStore } from "../policy/auth.context.js";
import {
  listOpenAssignments,
  MAX_RETRIES,
  orchestratorDispatch,
  ROLE_EVENT_MAP,
} from "../registry/orchestrator_dispatch.js";
import { validateSlot } from "../registry/agent_heartbeat.js";

/**
 * Orchestrator dispatch tool (issue #1803, #1439 Phase D).
 *
 * বাংলা: event → কোন role লাগবে → heartbeat দেখে online agent → task assign।
 * Offline agent skip হয়; সব offline থাকলে SupremeAI (super lane) fallback;
 * max retry ৩ ছাড়ালে human escalation। প্রতিটি সিদ্ধান্ত audit log হয়
 * (deterministic — কেন কোন agent পেলো তার প্রমাণ state-এ থাকে)।
 */
export async function registerOrchestratorTools(server: McpServer): Promise<void> {
  server.tool(
    "orchestrator_dispatch",
    `Route an orchestration event to the right agent lane: event → required role → heartbeat online check → task assignment (fallback: SupremeAI super lane; max ${MAX_RETRIES} retries then human escalation). Deterministic + audit-logged.`,
    {
      issueRef: z
        .string()
        .min(1)
        .max(64)
        .describe("Task reference — issue number, PR number, or run id (state key suffix)"),
      event: z
        .enum(["issues", "pull_request", "workflow_run"])
        .describe("GitHub event type (Phase C ingest set)"),
      action: z
        .string()
        .min(1)
        .max(32)
        .describe("Event action, e.g. opened / labeled / completed"),
      handoffLabel: z
        .string()
        .regex(/^handoff:[a-z][a-z0-9-]*$/)
        .optional()
        .describe("handoff:<role> label signal — overrides the default event→role map"),
    },
    async ({ issueRef, event, action, handoffLabel }) => {
      const context = RequestContextStore.get();
      if (!context?.authenticated) {
        return {
          isError: true,
          content: [{ type: "text", text: "Authentication required for orchestrator_dispatch" }],
        };
      }
      try {
        const { decision, state } = await orchestratorDispatch({
          issueRef,
          event,
          action,
          handoffLabel: handoffLabel ?? null,
        });
        const summary = [
          `decision: ${decision.decision}`,
          `role: ${decision.role ?? "n/a"}`,
          `assignedSlot: ${decision.assignedSlot ?? "none"}`,
          `reason: ${decision.reason}`,
          `attempts: ${state.attempts}/${MAX_RETRIES}`,
          `stateKey: supremeai:orchestrate:${issueRef}`,
          `eventRoleMap: ${JSON.stringify(ROLE_EVENT_MAP)}`,
          ...state.log.slice(-3).map((l) => `audit: ${l}`),
        ].join("\n");
        return {
          content: [
            {
              type: "text",
              text:
                decision.decision === "escalate"
                  ? `🚨 HUMAN ESCALATION REQUIRED\n${summary}`
                  : `✅ routed\n${summary}`,
            },
          ],
        };
      } catch (error) {
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `orchestrator_dispatch failed: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
        };
      }
    },
  );

  // F3 (audit 2026-10-16): agent-side poll — closes the dispatch loop. Without
  // this, 'assigned' decisions lived only in Redis state + logs and no agent
  // ever learned it had work. Read-only; any authenticated caller may check its
  // own slot (assignment payload is routing metadata, not secrets).
  server.tool(
    "orchestrator_my_tasks",
    `Poll open routing assignments for a slot: dispatch decisions previously died in logs — an assigned agent can now fetch its pending tasks (open = assigned/fallback within the last ${"24h"} freshness window).`,
    {
      slot: z
        .string()
        .regex(/^(agent|z\.ai|claude|chatgpt|cursor|gemini|copilot|coder|planner|ci|pr-helper|browser|platform|super)-\d+$/, 'slot must match "<type>-N" (e.g. "coder-3")')
        .describe("Your slot id (as registered via agent_heartbeat)"),
    },
    async ({ slot }) => {
      const context = RequestContextStore.get();
      if (!context?.authenticated) {
        return {
          isError: true,
          content: [{ type: "text", text: "Authentication required for orchestrator_my_tasks" }],
        };
      }
      const slotError = validateSlot(slot);
      if (slotError) {
        return { isError: true, content: [{ type: "text", text: slotError }] };
      }
      try {
        const result = await listOpenAssignments();
        const mine = result.assignments.filter((a) => a.assignedSlot === slot);
        const lines = [
          `open assignments for ${slot}: ${mine.length} (scanned ${result.stateKeysScanned} dispatch states)`,
          ...mine.map((a) => `- ${a.issueRef} [${a.decision}] role=${a.role ?? "n/a"} attempts=${a.attempts} age=${a.ageSeconds}s updated=${a.updatedAt}`),
        ];
        return {
          content: [{ type: "text", text: lines.join("\n") }],
        };
      } catch (error) {
        return {
          isError: true,
          content: [
            {
              type: "text",
              text: `orchestrator_my_tasks failed: ${error instanceof Error ? error.message : String(error)}`,
            },
          ],
        };
      }
    },
  );
}
