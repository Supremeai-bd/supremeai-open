/**
 * Value-shape based secret masking (#695).
 *
 * The old masking (render env-var listing) only inspected KEY NAMES
 * (KEY / TOKEN / SECRET substrings), so real secret VALUES leaked unmasked when
 * they lived under an innocent-looking key — e.g. Upstash `redis://user:pass@host`
 * URLs, bcrypt/argon2 hashes, JWTs, or high-entropy hex/base64 tokens.
 *
 * maskSecretValue() masks by key name (kept for defense in depth) AND by
 * VALUE SHAPE, regardless of the key name.
 */

export const SECRET_MASK = "***MASKED***";

/**
 * Value shapes that indicate a secret no matter what the key is called.
 * Anchored patterns so ordinary prose/URLs without embedded credentials pass.
 */
const SECRET_VALUE_SHAPES: RegExp[] = [
  // Any URI with a userinfo part: scheme://user:pass@host or scheme://token@host
  // (covers redis://, rediss://, postgres://, mysql://, mongodb+srv://, https:// …)
  /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\s/@]+@[^\s]+$/,
  // bcrypt ($2a/$2b/$2y), argon2id/i/d, scrypt and phpass-style hashes
  /^\$(2[aby]|argon2(?:id|i|d)|scrypt|[PHS])\$[^\s]+$/,
  // JWTs: three dot-separated base64url segments, header always starts "eyJ"
  /^ey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*$/,
  // High-entropy hex tokens (32+ hex chars): API keys, digests, session ids
  /^[a-f0-9]{32,}$/i,
  // High-entropy base64 / base64url blobs (40+ chars mixing upper, lower, digits)
  /^(?=[A-Za-z0-9+/=_-]{40,}$)(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])[A-Za-z0-9+/=_-]+$/,
  // SQL-style connection strings with an embedded password
  /;\s*(?:password|pwd)\s*=/i,
  // PEM private keys
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  // Common provider token prefixes
  /^(?:sk|pk)[-_][A-Za-z0-9_-]{16,}$/,
  /^gh[pousr]_[A-Za-z0-9]{30,}$/,
  /^github_pat_[A-Za-z0-9_]{20,}$/,
  /^xox[abprs]-[A-Za-z0-9-]{10,}$/,
  /^AKIA[0-9A-Z]{16}$/,
];

/** True when the VALUE itself looks like a credential/secret material. */
export function looksLikeSecretValue(value: string): boolean {
  if (typeof value !== "string") return false;
  const trimmed = value.trim();
  if (trimmed.length < 12) return false;
  return SECRET_VALUE_SHAPES.some((pattern) => pattern.test(trimmed));
}

/**
 * Mask an env-var/secret value for exposure to (potentially non-admin) callers.
 * Key-name based masking is kept (defense in depth); value-shape based masking
 * catches secrets under innocent key names (#695).
 */
export function maskSecretValue(key: string, value: string): string {
  if (typeof value !== "string" || value === "") return value;
  const keyName = (key ?? "").toLowerCase();
  if (
    keyName.includes("key") ||
    keyName.includes("secret") ||
    keyName.includes("token") ||
    keyName.includes("password") ||
    keyName.includes("passwd") ||
    keyName.includes("credential") ||
    keyName.includes("authorization")
  ) {
    return SECRET_MASK;
  }
  if (looksLikeSecretValue(value)) return SECRET_MASK;
  return value;
}
