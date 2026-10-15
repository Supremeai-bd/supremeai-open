import { createHmac, timingSafeEqual } from "node:crypto";

/**
 * Webhook signature verification (#69).
 *
 * Extracted from the /webhooks route handler in src/index.ts so the raw-body
 * HMAC check is unit-testable. Behavior is identical to the original inline
 * helper:
 *   - missing secret          → fail-closed (false)
 *   - missing/malformed header (must start with "sha256=") → false
 *   - constant-time comparison of the hex sha256 HMAC over the RAW body
 *     (the exact bytes received — never a re-serialized JSON copy)
 */
export function hasWebhookSignature(
  headerValue: string | undefined,
  body: string,
  secret: string,
): boolean {
  const signature = headerValue ?? "";
  if (!secret || !signature.startsWith("sha256=")) return false;
  const expected = `sha256=${createHmac("sha256", secret).update(body).digest("hex")}`;
  return timingSafeStringsEqual(signature, expected);
}

function timingSafeStringsEqual(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}
