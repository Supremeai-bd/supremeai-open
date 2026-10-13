import { createHmac, timingSafeEqual } from "node:crypto";
import { env } from "../../lib/env.js";

/**
 * Expiring, single-purpose signatures for browser 1-click HITL approval links.
 *
 * SECURITY FIX (replaces the old `?token=<MCP_ADMIN_KEY>` links):
 * - The permanent admin key must NEVER appear in a URL. URLs leak via Telegram
 *   message history, browser history, proxy/CDN access logs and Referer headers.
 * - Links are now bound to a specific approval request id + decision, carry an
 *   expiry timestamp, and are signed with HMAC-SHA256 over the admin key.
 * - A signature for "REJECTED" can never approve, and vice versa.
 * - Expired links are rejected; a fresh link is sent with every new approval
 *   request, so this does not reduce operator convenience.
 */

const DEFAULT_TTL_MS = 24 * 60 * 60 * 1000; // 24h — HITL approvals can sit pending for hours

function linkTtlMs(): number {
  const parsed = Number(process.env["MCP_APPROVAL_LINK_TTL_MS"]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_TTL_MS;
}

function approvalHmac(requestId: string, decision: string, exp: number): string {
  // mcpAdminKey falls back to mcpApiKey in env.ts; an empty signing key would make
  // signatures forgeable, so refuse to sign rather than sign with a weak secret.
  const key = env.mcpAdminKey || env.mcpApiKey;
  if (!key) {
    throw new Error("[approvals] Cannot sign approval link: MCP_ADMIN_KEY/MCP_API_KEY not configured");
  }
  return createHmac("sha256", key).update(`approval:${requestId}:${decision}:${exp}`).digest("hex");
}

/**
 * Returns the query string (`exp=...&sig=...`) to append to an /approve link.
 */
export function signApprovalLink(requestId: string, decision: "APPROVED" | "REJECTED"): string {
  const exp = Date.now() + linkTtlMs();
  const sig = approvalHmac(requestId, decision, exp);
  return `exp=${exp}&sig=${sig}`;
}

/**
 * Verifies a signed approval link. The decision is part of the signed payload,
 * so a reject-link signature cannot be replayed as an approval.
 */
export function verifyApprovalLink(
  requestId: string,
  decision: string,
  exp: string,
  sig: string
): boolean {
  if (!requestId || !exp || !sig) return false;
  const expNum = Number(exp);
  if (!Number.isFinite(expNum) || expNum < Date.now()) return false;
  try {
    const expected = approvalHmac(requestId, decision, expNum);
    const a = Buffer.from(sig);
    const b = Buffer.from(expected);
    return a.length === b.length && timingSafeEqual(a, b);
  } catch {
    return false;
  }
}
