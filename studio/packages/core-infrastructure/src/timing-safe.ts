/**
 * Constant-time string comparison — canonical monorepo primitive.
 *
 * WHY single-sourced (DRY Phase 1-B3): five divergent copies existed
 * (4 in infrastructure/mcp-control-plane using node:crypto timingSafeEqual,
 * 1 in apps/mission-control using charCode XOR). A security primitive must
 * have exactly one audited implementation.
 *
 * This variant is runtime-agnostic (Edge / Node / Browser): pure JS, no
 * node:crypto, no WebCrypto — safe in Next.js middleware and route handlers.
 *
 * Semantics: XOR-accumulates every character code so execution time depends
 * only on the input lengths, never on where the first mismatch occurs.
 * Length mismatch is folded into the accumulator instead of returning early.
 */
export function timingSafeEqualStr(a: string, b: string): boolean {
  if (typeof a !== "string" || typeof b !== "string") return false;
  const len = Math.max(a.length, b.length);
  let diff = a.length === b.length ? 0 : 1;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}
