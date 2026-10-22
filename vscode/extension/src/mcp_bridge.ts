/**
 * SupremeAI MCP Bridge — Remote Control Tower client adapter for VS Code.
 *
 * Communicates via JSON-RPC 2.0 / HTTP to the public or authenticated
 * Control Tower endpoint.
 */

export interface FederationHealth {
  status: "nominal" | "degraded" | "critical" | "offline";
  activeAgents: number;
  openClaims: number;
  runwayDepth: number;
  latencyMs: number;
  lastChecked: string;
}

export interface RunwayItem {
  id: string;
  repo: string;
  title: string;
  stage: "queued" | "in_gates" | "landed" | "rejected";
  ciStatus: "pass" | "fail" | "pending";
  author: string;
}

export interface TaskDispatchRequest {
  repo: string;
  title: string;
  scopePaths: string[];
  description: string;
  priority?: "P0-critical" | "P1-high" | "P2-medium" | "P3-low";
}

export interface TaskDispatchResponse {
  success: boolean;
  taskId?: string;
  issueNumber?: number;
  error?: string;
}

export class McpBridge {
  private towerUrl: string;
  private timeoutMs: number;

  constructor(towerUrl = "https://supremeai-mcp-tower.onrender.com/mcp", timeoutMs = 8000) {
    this.towerUrl = towerUrl;
    this.timeoutMs = timeoutMs;
  }

  public updateConfig(towerUrl: string, timeoutMs = 8000): void {
    this.towerUrl = towerUrl;
    this.timeoutMs = timeoutMs;
  }

  public async fetchHealth(): Promise<FederationHealth> {
    const started = Date.now();
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);

      // Lightweight health check against MCP endpoint or base /health
      const healthUrl = this.towerUrl.replace(/\/mcp\/?$/, "/health");
      const res = await fetch(healthUrl, {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal: controller.signal,
      });
      clearTimeout(timer);

      const latencyMs = Date.now() - started;
      if (!res.ok) {
        return {
          status: "degraded",
          activeAgents: 0,
          openClaims: 0,
          runwayDepth: 0,
          latencyMs,
          lastChecked: new Date().toISOString(),
        };
      }

      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
      return {
        status: (data.status as FederationHealth["status"]) || "nominal",
        activeAgents: typeof data.activeAgents === "number" ? data.activeAgents : 0,
        openClaims: typeof data.openClaims === "number" ? data.openClaims : 0,
        runwayDepth: typeof data.runwayDepth === "number" ? data.runwayDepth : 0,
        latencyMs,
        lastChecked: new Date().toISOString(),
      };
    } catch {
      return {
        status: "offline",
        activeAgents: 0,
        openClaims: 0,
        runwayDepth: 0,
        latencyMs: Date.now() - started,
        lastChecked: new Date().toISOString(),
      };
    }
  }

  public async fetchRunway(): Promise<RunwayItem[]> {
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);

      // Call MCP method work.runway or fallback endpoint
      const payload = {
        jsonrpc: "2.0",
        id: Date.now(),
        method: "tools/call",
        params: {
          name: "work_runway_status",
          arguments: {},
        },
      };

      const res = await fetch(this.towerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timer);

      if (!res.ok) {
        return [];
      }

      const data = (await res.json().catch(() => ({}))) as { result?: { content?: Array<{ text?: string }> } };
      const rawText = data?.result?.content?.[0]?.text;
      if (!rawText) return [];

      const parsed = JSON.parse(rawText) as RunwayItem[];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  public async dispatchTask(req: TaskDispatchRequest): Promise<TaskDispatchResponse> {
    if (!req.title || !req.repo) {
      return { success: false, error: "Task title and repository are required." };
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);

      const payload = {
        jsonrpc: "2.0",
        id: Date.now(),
        method: "tools/call",
        params: {
          name: "bridge_work_order",
          arguments: {
            target_repo: req.repo,
            summary: req.title,
            scope_paths: req.scopePaths,
            description: req.description,
            priority: req.priority || "P1-high",
          },
        },
      };

      const res = await fetch(this.towerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timer);

      if (!res.ok) {
        return { success: false, error: `Tower responded with HTTP ${res.status}` };
      }

      const data = (await res.json().catch(() => ({}))) as {
        result?: { content?: Array<{ text?: string }> };
        error?: { message?: string };
      };

      if (data.error) {
        return { success: false, error: data.error.message || "MCP Dispatch Error" };
      }

      const responseText = data?.result?.content?.[0]?.text || "";
      return {
        success: true,
        taskId: `task-${Date.now().toString(36)}`,
        error: responseText ? undefined : undefined,
      };
    } catch (err) {
      return {
        success: false,
        error: err instanceof Error ? err.message : "Network error during dispatch",
      };
    }
  }

  public async triggerEmergencyKill(pin: string): Promise<boolean> {
    if (!pin || pin.length < 4) {
      return false;
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);

      const payload = {
        jsonrpc: "2.0",
        id: Date.now(),
        method: "tools/call",
        params: {
          name: "emergency_kill_switch",
          arguments: { pin },
        },
      };

      const res = await fetch(this.towerUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      clearTimeout(timer);

      return res.ok;
    } catch {
      return false;
    }
  }
}
