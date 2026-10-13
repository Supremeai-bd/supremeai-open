import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { McpProtocol } from "../registry/mcp.contracts.js";

export interface OutboundServerConfig {
  id: string;
  protocol: McpProtocol;
  endpoint?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  timeoutMs?: number;
}

export interface OutboundClient {
  readonly config: OutboundServerConfig;
  readonly client: Client;
  close(): Promise<void>;
}

export async function connectOutbound(config: OutboundServerConfig): Promise<OutboundClient> {
  const client = new Client({ name: "supremeai-federation", version: "1.0.0" });
  const transport = config.protocol === "stdio"
    ? new StdioClientTransport({ command: config.command ?? "", args: config.args ?? [] })
    : new StreamableHTTPClientTransport(new URL(config.endpoint ?? ""), {
        requestInit: { headers: config.headers },
      });

  await Promise.race([
    client.connect(transport),
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error(`MCP connection timed out for ${config.id}`)), config.timeoutMs ?? 10_000)),
  ]);

  return { config, client, close: () => client.close() };
}
