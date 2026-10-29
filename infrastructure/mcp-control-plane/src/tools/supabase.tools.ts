import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { getHealth, getAuthUsers, readTable, getDatabaseSchema } from "../adapters/supabase/index.js";


export async function registerSupabaseTools(server: McpServer): Promise<void> {
  // ── Unified Database Tool ──
  server.tool(
    "db.inspect",
    "Unified Database and Supabase operations (health, schema, read_table, auth_users).",
    {
      action: z.enum(["health", "schema", "read_table", "auth_users"]).describe("Database action to perform"),
      accountId: z.string().describe("The account ID (e.g. supabase-primary)"),
      table: z.string().optional().describe("Table name for schema or read_table"),
      select: z.string().optional().describe("Comma-separated columns to select (default: '*')"),
      limit: z.number().optional().describe("Maximum rows to fetch (default: 20, max: 100)"),
      filter: z.string().optional().describe("PostgREST filter string (e.g. 'status=eq.active')"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async ({ action, accountId, table, select, limit, filter }) => {
      try {
        if (action === "health") {
          const health = await getHealth(accountId);
          return { content: [{ type: "text", text: JSON.stringify(health, null, 2) }] };
        }
        if (action === "auth_users") {
          const users = await getAuthUsers(accountId);
          return { content: [{ type: "text", text: JSON.stringify(users, null, 2) }] };
        }
        if (action === "schema") {
          const schema = await getDatabaseSchema(accountId, table);
          return { content: [{ type: "text", text: JSON.stringify(schema, null, 2) }] };
        }
        if (action === "read_table") {
          if (!table) {
            return { isError: true, content: [{ type: "text", text: "Error: 'table' is required for read_table" }] };
          }
          const data = await readTable(accountId, table, select ?? "*", limit ?? 20, filter);
          return { content: [{ type: "text", text: JSON.stringify(data, null, 2) }] };
        }
        return { isError: true, content: [{ type: "text", text: `Unknown action: ${action}` }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "supabase.health",
    "Ping the Supabase REST API to check connectivity and latency.",
    {
      accountId: z.string().describe("The account ID (e.g. supabase-primary)"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async ({ accountId }) => {
      try {
        const health = await getHealth(accountId);
        return {
          content: [{ type: "text", text: JSON.stringify(health, null, 2) }],
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
    "supabase.auth_users",
    "Get the total number of authenticated users in Supabase.",
    {
      accountId: z.string().describe("The account ID (e.g. supabase-primary)"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async ({ accountId }) => {
      try {
        const users = await getAuthUsers(accountId);
        return {
          content: [{ type: "text", text: JSON.stringify(users, null, 2) }],
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
    "supabase.read_table",
    "Safely query/read rows from any Supabase table (Read-Only access).",
    {
      accountId: z.string().describe("The account ID (e.g. supabase-primary)"),
      table: z.string().describe("The table name to query"),
      select: z.string().optional().describe("Comma-separated columns to select (default: '*')"),
      limit: z.number().optional().describe("Maximum rows to fetch (default: 20, max: 100)"),
      filter: z.string().optional().describe("PostgREST filter string (e.g. 'status=eq.active')"),
    },
    { readOnlyHint: true, idempotentHint: true },
    async ({ accountId, table, select, limit, filter }) => {
      try {
        const data = await readTable(accountId, table, select ?? "*", limit ?? 20, filter);
        return {
          content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
        };
      } catch (err) {
        return {
          isError: true,
          content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
        };
      }
    }
  );
  // supabase.schema_inspect (safe/public) - read-only schema discovery
  const registerSchemaInspect = (toolName: string) => {
    server.tool(
      toolName,
      "Inspect Supabase database schema (tables and columns) read-only.",
      {
        accountId: z.string().describe("The account ID (e.g. supabase-primary)"),
        table: z.string().optional().describe("Optional table name; omit to list all tables"),
      },
      { readOnlyHint: true, idempotentHint: true },
      async ({ accountId, table }) => {
        try {
          const data = await getDatabaseSchema(accountId, table);
          return {
            content: [{ type: "text", text: JSON.stringify(data, null, 2) }],
          };
        } catch (err) {
          return {
            isError: true,
            content: [{ type: "text", text: `Error: ${(err as Error).message}` }],
          };
        }
      }
    );
  };

  registerSchemaInspect("supabase.schema_inspect");
  registerSchemaInspect("db.schema_inspect");
}