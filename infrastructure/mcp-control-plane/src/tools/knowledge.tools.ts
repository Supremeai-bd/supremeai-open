import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import {
  qdrantEnsureCollection,
  qdrantListCollections,
  qdrantSearch,
  qdrantUpsert,
} from "../adapters/qdrant/actions.js";
import { insertRow, updateRows } from "../adapters/supabase/actions.js";

/**
 * Knowledge Store Tools.
 * Хранение собранных практик: метаданные → Supabase, векторы → Qdrant.
 */
export async function registerKnowledgeTools(server: McpServer): Promise<void> {
  server.tool(
    "qdrant.upsert",
    "Insert/update vectors in Qdrant (semantic search index). Store Supabase record id in payload for join.",
    {
      collection: z.string().describe("Collection name, e.g. 'knowledge_base'"),
      points: z.array(z.object({
        id: z.string().describe("Point id (use supabase record id)"),
        vector: z.array(z.number()).describe("Embedding vector"),
        payload: z.record(z.string(), z.unknown()).optional().describe("Metadata payload"),
      })).describe("Points to upsert"),
    },
    async ({ collection, points }) => {
      try {
        const result = await qdrantUpsert(collection, points);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "qdrant.search",
    "Semantic search in Qdrant vector DB. Provide an embedding vector to find most similar collected patterns.",
    {
      collection: z.string().describe("Collection name, e.g. 'knowledge_base'"),
      vector: z.array(z.number()).describe("Query embedding"),
      limit: z.number().int().min(1).max(50).optional().describe("Max results (default: 5)"),
    },
    async ({ collection, vector, limit }) => {
      try {
        const result = await qdrantSearch(collection, vector, limit ?? 5);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "qdrant.ensure_collection",
    "Create a Qdrant collection with a given vector size if it doesn't exist.",
    {
      collection: z.string().describe("Collection name"),
      vectorSize: z.number().int().min(64).max(4096).describe("Embedding dimension"),
      distance: z.enum(["Cosine", "Euclid", "Dot"]).optional().describe("Distance metric (default: Cosine)"),
    },
    async ({ collection, vectorSize, distance }) => {
      try {
        const result = await qdrantEnsureCollection(collection, vectorSize, distance ?? "Cosine");
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "qdrant.collections",
    "List all Qdrant collections.",
    {},
    async () => {
      try {
        const result = await qdrantListCollections();
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "supabase.insert",
    "Insert a row into a Supabase table (used to store collected patterns/practices metadata). Writes go through PostgREST with RLS.",
    {
      accountId: z.string().describe("Account id (supabase-primary)"),
      table: z.string().describe("Table name, e.g. 'best_practices'"),
      data: z.record(z.string(), z.unknown()).describe("Row data"),
    },
    async ({ accountId, table, data }) => {
      try {
        const result = await insertRow(accountId, table, data);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );

  server.tool(
    "supabase.update",
    "Update rows in a Supabase table with a PostgREST filter (e.g. 'id=eq.123').",
    {
      accountId: z.string().describe("Account id (supabase-primary)"),
      table: z.string().describe("Table name"),
      data: z.record(z.string(), z.unknown()).describe("Update payload"),
      filter: z.string().describe("PostgREST filter, e.g. 'id=eq.123'"),
    },
    async ({ accountId, table, data, filter }) => {
      try {
        const result = await updateRows(accountId, table, data, filter);
        return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }] };
      } catch (err) {
        return { isError: true, content: [{ type: "text", text: `Error: ${(err as Error).message}` }] };
      }
    }
  );
}