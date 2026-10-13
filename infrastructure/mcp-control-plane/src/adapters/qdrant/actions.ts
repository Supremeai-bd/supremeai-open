import { env } from "../../lib/env.js";
import { httpRequest } from "../../lib/http.js";

/**
 * Qdrant — векторная база для семантического поиска собранных практик.
 * Metro-данные лежат в Supabase; здесь только vectors + payload + supabase ref.
 */

function config(): { url: string; apiKey?: string } {
  if (!env.qdrant.url) throw new Error("QDRANT_URL is not configured.");
  return { url: env.qdrant.url, apiKey: env.qdrant.apiKey || undefined };
}

function headers(apiKey?: string): Record<string, string> {
  return apiKey ? { "api-key": apiKey, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

export async function qdrantUpsert(
  collection: string,
  points: Array<{ id: string; vector: number[]; payload?: Record<string, unknown> }>
): Promise<unknown> {
  const { url, apiKey } = config();
  const res = await httpRequest(`${url}/collections/${collection}/points?wait=true`, {
    method: "PUT",
    headers: headers(apiKey),
    body: { points },
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`Qdrant upsert failed (${res.status}): ${JSON.stringify(res.data).slice(0, 300)}`);
  return res.data;
}

export async function qdrantSearch(
  collection: string,
  vector: number[],
  limit = 5,
  filter?: Record<string, unknown>
): Promise<unknown> {
  const { url, apiKey } = config();
  const res = await httpRequest(`${url}/collections/${collection}/points/search`, {
    method: "POST",
    headers: headers(apiKey),
    body: { vector, limit, with_payload: true, filter },
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`Qdrant search failed (${res.status}): ${JSON.stringify(res.data).slice(0, 300)}`);
  return res.data;
}

export async function qdrantEnsureCollection(
  collection: string,
  vectorSize: number,
  distance = "Cosine"
): Promise<unknown> {
  const { url, apiKey } = config();
  const res = await httpRequest(`${url}/collections/${collection}`, {
    method: "PUT",
    headers: headers(apiKey),
    body: { vectors: { size: vectorSize, distance } },
    timeoutMs: 15_000,
  });
  if (!res.ok) throw new Error(`Qdrant ensure collection failed (${res.status}): ${JSON.stringify(res.data).slice(0, 300)}`);
  return res.data;
}

export async function qdrantListCollections(): Promise<unknown> {
  const { url, apiKey } = config();
  const res = await httpRequest(`${url}/collections`, { headers: headers(apiKey), timeoutMs: 10_000 });
  if (!res.ok) throw new Error(`Qdrant list failed (${res.status})`);
  return res.data;
}