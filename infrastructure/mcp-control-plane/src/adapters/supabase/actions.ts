import { buildAccountRegistry } from "../../registry/account.registry.js";
import { httpRequest } from "../../lib/http.js";

/**
 * Supabase Write Actions — сохранение собранных практик/паттернов.
 * Только для tenant-админов (REST endpoint проверяет scope; RLS по tenant_id).
 */

function getSupabaseConfig(accountId: string) {
  const accounts = buildAccountRegistry();
  const account = accounts.find((a) => a.id === accountId && a.provider === "supabase");
  if (!account) throw new Error(`Supabase account not found: ${accountId}`);
  if (!account.available) throw new Error(`Supabase account is not configured/available: ${accountId}`);
  const apiKey = process.env[account.apiKeyRef];
  const url = account.url;
  if (!apiKey || !url) throw new Error(`Missing Supabase URL or Key in env for: ${accountId}`);
  return { url, apiKey };
}

function supabaseHeaders(apiKey: string) {
  return {
    apikey: apiKey,
    Authorization: `Bearer ${apiKey}`,
    "Content-Type": "application/json",
    Prefer: "return=representation",
  };
}

export async function insertRow(
  accountId: string,
  table: string,
  data: Record<string, unknown>
): Promise<unknown> {
  if (!table?.trim()) throw new Error("table is required");
  if (!data || typeof data !== "object") throw new Error("data object is required");

  const { url, apiKey } = getSupabaseConfig(accountId);
  const res = await httpRequest(`${url}/rest/v1/${encodeURIComponent(table)}`, {
    method: "POST",
    headers: supabaseHeaders(apiKey),
    body: data,
    timeoutMs: 12_000,
  });
  if (!res.ok) {
    throw new Error(`Supabase insert failed (${res.status}): ${JSON.stringify(res.data).slice(0, 400)}`);
  }
  return { inserted: 1, row: Array.isArray(res.data) ? res.data[0] : res.data };
}

export async function updateRows(
  accountId: string,
  table: string,
  data: Record<string, unknown>,
  filter: string
): Promise<unknown> {
  if (!table?.trim()) throw new Error("table is required");
  if (!filter?.trim()) throw new Error("filter is required (PostgREST, e.g. id=eq.123)");
  const { url, apiKey } = getSupabaseConfig(accountId);
  const res = await httpRequest(`${url}/rest/v1/${encodeURIComponent(table)}?${filter}`, {
    method: "PATCH",
    headers: supabaseHeaders(apiKey),
    body: data,
    timeoutMs: 12_000,
  });
  if (!res.ok) {
    throw new Error(`Supabase update failed (${res.status}): ${JSON.stringify(res.data).slice(0, 400)}`);
  }
  return { updated: Array.isArray(res.data) ? res.data.length : 1, rows: res.data };
}