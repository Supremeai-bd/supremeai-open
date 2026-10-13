import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { env } from "../lib/env.js";
import { httpRequest, bearerAuth } from "../lib/http.js";
import { RequestContextStore } from "../policy/auth.context.js";

const MAX_PROMPT_LENGTH = 50_000;
const MAX_CONTEXT_LENGTH = 200_000;
const IDEMPOTENCY_TTL_MS = 15 * 60 * 1000;
const activeRequests = new Map<string, { expiresAt: number; result?: unknown }>();

const contextSchema = z.record(z.string(), z.unknown()).optional();

function accessError(required: "agent" | "viewer"): string | undefined {
  const role = RequestContextStore.getRole();
  if (required === "viewer") return role ? undefined : "Authentication required";
  if (role !== "agent" && role !== "admin") return `Forbidden: agent scope required (current role: ${role})`;
  return undefined;
}

async function backendRequest<T>(path: string, body?: unknown): Promise<T> {
  if (!env.backendUrl) throw new Error("SUPREMEAI_BACKEND_URL is not configured");
  const context = RequestContextStore.get();
  const headers = {
    ...(env.backendServiceToken ? bearerAuth(env.backendServiceToken) : {}),
    ...(context?.tenantId ? { "x-tenant-id": context.tenantId } : {}),
    ...(context?.requestId ? { "x-request-id": context.requestId } : {}),
  };
  const response = await httpRequest<T>(`${env.backendUrl.replace(/\/$/, "")}${path}`, {
    method: body ? "POST" : "GET",
    headers,
    body,
    timeoutMs: 90_000,
    retries: 0,
  });
  if (!response.ok) throw new Error(`Backend returned HTTP ${response.status}`);
  return response.data;
}

export async function registerAgentReviewWorkflowTools(server: McpServer): Promise<void> {
  server.tool(
    "agent_review_workflow.execute",
    "Execute the reusable Agent Review Workflow. Provider and model selection are resolved by runtime configuration.",
    {
      prompt: z.string().min(1).max(MAX_PROMPT_LENGTH),
      language: z.string().min(1).max(64).default("python"),
      context: contextSchema,
      idempotencyKey: z.string().min(8).max(128).optional(),
    },
    async ({ prompt, language, context, idempotencyKey }) => {
      try {
        const denied = accessError("agent");
        if (denied) return { isError: true, content: [{ type: "text", text: denied }] };
        const serializedContext = JSON.stringify(context ?? {});
        if (serializedContext.length > MAX_CONTEXT_LENGTH) {
          throw new Error("Workflow context exceeds the configured size limit");
        }
        const caller = RequestContextStore.get();
        const key = `${caller?.tenantId ?? "default"}:${idempotencyKey ?? `${caller?.requestId ?? "request"}:${prompt.slice(0, 64)}`}`;
        const now = Date.now();
        for (const [storedKey, entry] of activeRequests) if (entry.expiresAt <= now) activeRequests.delete(storedKey);
        const previous = activeRequests.get(key);
        if (previous?.result) return { content: [{ type: "text", text: JSON.stringify(previous.result, null, 2) }] };
        if (previous) throw new Error("An identical workflow request is already running");
        const pending: { expiresAt: number; result?: unknown } = { expiresAt: now + IDEMPOTENCY_TTL_MS };
        activeRequests.set(key, pending);
        const result = await backendRequest("/api/v1/agent_review_workflow/execute", {
          prompt,
          language,
          ...((context ?? {}) as Record<string, unknown>),
        });
        pending.result = result;
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    },
  );

  server.tool(
    "agent_review_workflow.status",
    "Report runtime availability of the Agent Review Workflow and its configured capabilities.",
    {},
    async () => {
      try {
        const denied = accessError("viewer");
        if (denied) return { isError: true, content: [{ type: "text", text: denied }] };
        const result = await backendRequest("/api/v1/agent_review_workflow/status");
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    },
  );
}
