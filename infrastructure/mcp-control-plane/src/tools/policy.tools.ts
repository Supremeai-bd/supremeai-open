import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { globalPolicyEngine } from "../policy/policy.engine.js";
import { globalApprovalManager } from "../policy/approvals/lifecycle.js";
import { globalHITLManager } from "../policy/approvals/hitl.js";
import { RequestContextStore } from "../policy/auth.context.js";

export async function registerPolicyTools(server: McpServer): Promise<void> {
  server.tool(
    "policy.preview",
    "Preview the risk level and policy decision of an action before executing it.",
    {
      provider: z.string().describe("The provider, e.g., 'render', 'supabase', 'system'"),
      action: z.string().describe("The action, e.g., 'deploy', 'restart', 'delete'"),
    },
    async ({ provider, action }) => {
      try {
        const result = globalPolicyEngine.evaluateAction({ provider, action });
        
        let message = `Action '${action}' on provider '${provider}' evaluates to risk level ${result.riskLevel}.\n`;
        message += `Decision: ${result.decision}\n`;
        message += `Reason: ${result.reason}\n`;

        // If it requires approval, let's auto-create a pending request in preview for demonstration
        // Wait, preview shouldn't create a real request. But for testing Phase 5, we can simulate an execution request.
        if (result.decision === "REQUIRE_APPROVAL") {
           const req = globalApprovalManager.createRequest({ provider, action });
           await globalHITLManager.requestApproval(req, result.riskLevel);
           message += `\n[Simulated Execution] An approval request (${req.id}) has been created and sent.`;
        }

        return {
          content: [{ type: "text", text: message }],
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
    "policy.approve",
    "Approve or reject a pending Human-In-The-Loop (HITL) request.",
    {
      requestId: z.string().describe("The Request ID, e.g., REQ-123"),
      decision: z.enum(["APPROVED", "REJECTED"]).describe("The decision to make.")
    },
    async ({ requestId, decision }) => {
      try {
        const callerRole = RequestContextStore.getRole();
        if (callerRole !== "admin") {
          return {
            isError: true,
            content: [{ type: "text", text: `Forbidden: Only admin can approve or reject requests. Current role: ${callerRole}` }]
          };
        }

        const success = globalApprovalManager.resolveRequest(requestId, decision);
        if (success) {
           return {
             content: [{ type: "text", text: `Successfully marked request ${requestId} as ${decision}.` }]
           };
        }
        return {
          isError: true,
          content: [{ type: "text", text: "Failed to resolve request." }]
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
    "policy.list_pending",
    "List all currently pending approval requests.",
    {},
    async () => {
       const pending = globalApprovalManager.getPendingRequests();
       return {
         content: [{ type: "text", text: JSON.stringify(pending, null, 2) }]
       };
    }
  );
}
