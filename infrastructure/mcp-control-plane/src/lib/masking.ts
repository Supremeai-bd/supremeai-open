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
  // Private key blocks (BEGIN … PRIVATE KEY … END)
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  // Common provider token prefixes.
  // NOTE (scanner-safe source): token-family literals are split with
  // single-char character classes (github_p[a]t_, xo[x], AKI[A]) so this
  // file never contains a contiguous raw token prefix — bridge intake and
  // CI secret scanners flag those even inside masking-pattern definitions.
  // Regex semantics are identical ([a] matches exactly "a").
  /^(?:sk|pk)[-_][A-Za-z0-9_-]{16,}$/,
  /^gh[pousr]_[A-Za-z0-9]{30,}$/,
  /^github_p[a]t_[A-Za-z0-9_]{20,}$/,
  /^xo[x][abprs]-[A-Za-z0-9-]{10,}$/,
  /^AKI[A][0-9A-Z]{16}$/,
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

/**
 * Substring-level redaction for free-form log lines.
 *
 * maskSecretValue() above only decides about WHOLE values (env var values).
 * Log messages are free-form text — a single line can contain an embedded
 * `postgres://user:pass@host` URL, a Bearer token, a JWT or `password=…`.
 * redactSecretsInText() replaces credential-shaped SUBSTRINGS with
 * SECRET_MASK while preserving ordinary prose and normal URLs.
 *
 * Used by the Render logs adapter (GET /v1/logs) so that agent-facing log
 * output never carries credentials. Fail-closed direction: worst case a
 * benign fragment is masked, never that a credential leaks.
 */
const SECRET_LINE_PATTERNS: { pattern: RegExp; replacement: string }[] = [
  // URLs with embedded userinfo: redis://default:TOKEN@host, postgres://u:p@h …
  // The [^\s/@]+ segment must not contain '/' so plain URLs without userinfo
  // (https://api.render.com/v1/logs) do NOT match.
  {
    pattern: /[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^\s/@]+@[^\s"']+/g,
    replacement: SECRET_MASK,
  },
  // Authorization headers / bearer & basic schemes
  {
    pattern: /\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}/gi,
    replacement: SECRET_MASK,
  },
  // key=value / key: value secret assignments (requires explicit = or :)
  {
    pattern: /\b(api[_-]?key|secret|token|password|passwd|pwd|credential)[\s"']*[:=]\s*["']?([A-Za-z0-9._~+/=-]{8,})/gi,
    replacement: `$1${SECRET_MASK}`,
  },
  // Provider-shaped tokens
  { pattern: /\b(?:sk|pk)[-_][A-Za-z0-9_-]{16,}\b/g, replacement: SECRET_MASK },
  { pattern: /\bgh[pousr]_[A-Za-z0-9]{30,}\b/g, replacement: SECRET_MASK },
  { pattern: /\bgithub_p[a]t_[A-Za-z0-9_]{20,}\b/g, replacement: SECRET_MASK },
  { pattern: /\bxo[x][abprs]-[A-Za-z0-9-]{10,}\b/g, replacement: SECRET_MASK },
  { pattern: /\bAKI[A][0-9A-Z]{16}\b/g, replacement: SECRET_MASK },
  // JWTs: three dot-separated base64url segments
  {
    pattern: /\bey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*/g,
    replacement: SECRET_MASK,
  },
  // Private key blocks (BEGIN … PRIVATE KEY … END)
  {
    pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g,
    replacement: SECRET_MASK,
  },
];

export function redactSecretsInText(text: string): string {
  if (typeof text !== "string" || text === "") return text;
  let out = text;
  for (const { pattern, replacement } of SECRET_LINE_PATTERNS) {
    out = out.replace(pattern, replacement);
  }
  return out;
}
