import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { RequestContextStore } from "../policy/auth.context.js";
import {
  MAX_RETRIES,
  orchestratorDispatch,
  ROLE_EVENT_MAP,
} from "../registry/orchestrator_dispatch.js";

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
}
