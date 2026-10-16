import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { RequestContextStore } from "../policy/auth.context.js";
import {
  MAX_RETRIES,
  makeDispatchStore,
  MY_TASKS_DEFAULT_LIMIT,
  orchestratorDispatch,
  orchestratorMyTasks,
  ROLE_EVENT_MAP,
  type DispatchStore,
  type MyTasksResult,
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

  // ── F3 (audit 2026-10-16): agent-side poll — close the assignment loop ────
  //
  // বাংলা: dispatch সিদ্ধান্ত আগে শুধু Redis ledger + console log-এ যেত —
  // কোনো agent তার assigned task দেখতেই পারত না। এই tool সেই loop বন্ধ করে:
  // heartbeat slot → আমার assigned tasks (SCAN orchestrate:* → filter)।
  //
  // Telegram/WhatsApp dispatch-notice variant: channel + credentials =
  // ADMIN_DECISION class (§6) — deferred, not presumed. The poll tool alone
  // already restores visibility (the P1 impact).
  server.tool(
    "orchestrator_my_tasks",
    `Poll the orchestrator for tasks assigned to my slot (agent-side loop closure for orchestrator_dispatch). Scans orchestrate:* state, filters by assignedSlot, newest first (cap ${MY_TASKS_DEFAULT_LIMIT}, honest truncation/partial flags). Zero tasks = genuinely empty queue — scan-capable store guaranteed (fail-closed otherwise).`,
    {
      slot: z
        .string()
        .min(1)
        .max(64)
        .regex(/^[\w.:-]+$/)
        .describe("My heartbeat slot id (as reported by agent_heartbeat / agent_status), e.g. coder-2 or agent-3"),
    },
    async ({ slot }) => {
      const context = RequestContextStore.get();
      if (!context?.authenticated) {
        return {
          isError: true,
          content: [{ type: "text", text: "Authentication required for orchestrator_my_tasks" }],
        };
      }
      try {
        const report = await myTasksReport(slot);
        return { content: [{ type: "text", text: report }] };
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

/**
 * Pure-ish report builder for orchestrator_my_tasks (F3) — exported for
 * regression tests (same doctrine as buildHeartbeatRecord: the MCP handler
 * stays a thin auth+catch wrapper, all logic is unit-testable with an
 * injected store).
 */
export async function myTasksReport(
  slot: string,
  store?: DispatchStore,
  opts?: { limit?: number },
): Promise<string> {
  const result: MyTasksResult = await orchestratorMyTasks({
    slot,
    store: store ?? (await makeDispatchStore()),
    limit: opts?.limit,
  });
  const flags: string[] = [];
  if (result.truncated) flags.push(`truncated to ${MY_TASKS_DEFAULT_LIMIT}`);
  if (result.partialScan) flags.push("partial scan (page bound exceeded)");
  if (result.corruptSkipped > 0) flags.push(`${result.corruptSkipped} corrupt state(s) skipped`);
  const header =
    result.tasks.length === 0
      ? `📭 no orchestrator tasks assigned to slot ${result.slot}`
      : `📋 orchestrator tasks for slot ${result.slot}: ${result.tasks.length}`;
  const lines = [
    header,
    ...result.tasks.map((t, i) => {
      const age = t.ageSeconds === null ? "age unknown" : `age ${t.ageSeconds}s`;
      const audit = t.lastAudit ? `\n   audit: ${t.lastAudit}` : "";
      return `${i + 1}. issue ${t.issueRef} — role ${t.role ?? "n/a"}, attempts ${t.attempts}/${MAX_RETRIES}, ${age}${audit}`;
    }),
    `(scanned ${result.scannedStates} orchestrate state(s)${flags.length ? ` — ${flags.join(", ")}` : ""})`,
  ];
  return lines.join("\n");
}
