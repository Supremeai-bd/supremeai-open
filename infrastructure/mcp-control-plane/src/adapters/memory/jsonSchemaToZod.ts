/**
 * Minimal JSON Schema → Zod converter for MCP tool bridging.
 *
 * Python Memory Server exposes its tools with standard JSON Schema
 * `inputSchema`. The Control Tower's `McpServer.tool()` API expects a
 * Zod raw shape. This converter covers the subset actually used by the
 * memory server (string/number/integer/boolean/array/object/enum) and
 * falls back to permissive schemas for anything exotic — so a new Python
 * tool never breaks the gateway (graceful degradation).
 *
 * 100% dynamic — no hardcoded per-tool schema. New Python tools are
 * picked up automatically via `client.listTools()`.
 */

import { z } from "zod";

type JsonSchema = {
  type?: string;
  description?: string;
  default?: unknown;
  enum?: unknown[];
  properties?: Record<string, JsonSchema>;
  required?: string[];
  items?: JsonSchema;
};

/* eslint-disable @typescript-eslint/no-explicit-any */

function convertLeaf(schema: JsonSchema): z.ZodTypeAny {
  const desc = schema.description;
  const withDesc = <T extends z.ZodTypeAny>(inner: T): T => {
    return (desc ? inner.describe(desc) : inner) as T;
  };

  if (Array.isArray(schema.enum) && schema.enum.length > 0) {
    const values = schema.enum.filter(
      (v): v is string => typeof v === "string",
    );
    if (values.length > 0 && values.length === schema.enum.length) {
      return withDesc(z.enum(values as [string, ...string[]]));
    }
    // Mixed-type enum → accept anything from the set.
    return withDesc(z.any());
  }

  switch (schema.type) {
    case "string":
      return withDesc(z.string());
    case "number":
      return withDesc(z.number());
    case "integer":
      return withDesc(z.number().int());
    case "boolean":
      return withDesc(z.boolean());
    case "array": {
      const items = schema.items ? convertLeaf(schema.items) : z.any();
      return withDesc(z.array(items));
    }
    case "object":
      // Nested free-form objects (metadata dicts etc.)
      return withDesc(z.record(z.string(), z.any()));
    default:
      return withDesc(z.any());
  }
}

/**
 * Convert a top-level `{ type: "object", properties, required }` tool
 * schema into a Zod raw shape suitable for `server.tool(name, desc, shape, cb)`.
 * Unknown/missing schemas → empty shape (tool accepts `{}` and forwards raw args).
 */
export function jsonSchemaToZodShape(
  inputSchema: unknown,
): Record<string, z.ZodTypeAny> {
  const schema = (inputSchema ?? {}) as JsonSchema;
  const properties = schema.properties ?? {};
  const required = new Set(schema.required ?? []);
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const [key, prop] of Object.entries(properties)) {
    let field = convertLeaf(prop ?? {});
    if (!required.has(key)) {
      field = field.optional();
    }
    // Honour explicit defaults from Python schema.
    const def = (prop as JsonSchema)?.default;
    if (def !== undefined) {
      try {
        field = (field as any).default(def);
      } catch {
        /* ignore — default() not supported on this type */
      }
    }
    shape[key] = field;
  }

  return shape;
}
