/**
 * RFC 6238 Time-based One-Time Password (TOTP) utility
 * Implemented using the standard Web Crypto API (SubtleCrypto HMAC-SHA1).
 * Compatible with Google Authenticator, Microsoft Authenticator, and Apple Passwords.
 */

const BASE32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';

/**
 * Decodes a Base32 string (case-insensitive, ignores spaces/hyphens/padding) into Uint8Array.
 */
export function base32ToBytes(base32: string): Uint8Array {
  const clean = base32.toUpperCase().replace(/[\s\-=]/g, '');
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];

  for (let i = 0; i < clean.length; i++) {
    const idx = BASE32_ALPHABET.indexOf(clean[i]);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 255);
      bits -= 8;
    }
  }
  return new Uint8Array(bytes);
}

/**
 * Encodes a Uint8Array into a standard Base32 string.
 */
export function bytesToBase32(bytes: Uint8Array): string {
  let bits = 0;
  let value = 0;
  let output = '';

  for (let i = 0; i < bytes.length; i++) {
    value = (value << 8) | bytes[i];
    bits += 8;
    while (bits >= 5) {
      output += BASE32_ALPHABET[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) {
    output += BASE32_ALPHABET[(value << (5 - bits)) & 31];
  }
  return output;
}

/**
 * Generates a random Base32 secret for TOTP setup (default 20 bytes = 160-bit security).
 */
export function generateTotpSecret(numBytes = 20): string {
  const bytes = new Uint8Array(numBytes);
  const cryptoObj =
    typeof window !== 'undefined' && window.crypto
      ? window.crypto
      : (globalThis.crypto as Crypto);

  cryptoObj.getRandomValues(bytes);
  return bytesToBase32(bytes).slice(0, 32);
}

/**
 * Formats standard otpauth:// URL for QR code generation.
 */
export function buildOtpAuthUri(
  account: string,
  secret: string,
  issuer = 'SupremeAI JARVIS'
): string {
  const cleanSecret = secret.toUpperCase().replace(/[\s\-=]/g, '');
  const encodedIssuer = encodeURIComponent(issuer);
  const encodedAccount = encodeURIComponent(account);
  return `otpauth://totp/${encodedIssuer}:${encodedAccount}?secret=${cleanSecret}&issuer=${encodedIssuer}&algorithm=SHA1&digits=6&period=30`;
}

/**
 * Computes a 6-digit TOTP code for a specific counter step.
 */
export async function generateTotpCode(secretBase32: string, counter: number): Promise<string> {
  const keyBytes = base32ToBytes(secretBase32);
  const cryptoObj =
    typeof window !== 'undefined' && window.crypto?.subtle
      ? window.crypto
      : (globalThis.crypto as Crypto);

  const cryptoKey = await cryptoObj.subtle.importKey(
    'raw',
    keyBytes,
    { name: 'HMAC', hash: 'SHA-1' },
    false,
    ['sign']
  );

  const buffer = new ArrayBuffer(8);
  const view = new DataView(buffer);
  view.setBigUint64(0, BigInt(counter));

  const signature = await cryptoObj.subtle.sign('HMAC', cryptoKey, buffer);
  const hmac = new Uint8Array(signature);
  const offset = hmac[hmac.length - 1] & 0x0f;
  const codeInt =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff);

  return (codeInt % 1000000).toString().padStart(6, '0');
}

/**
 * Verifies a 6-digit TOTP code against a Base32 secret.
 * Allows +/- windowSteps (default 1 = +/- 30 seconds drift).
 */
export async function verifyTotpCode(
  code: string,
  secretBase32: string,
  windowSteps = 1,
  timeMs = Date.now()
): Promise<boolean> {
  const cleanCode = code.trim().replace(/\s+/g, '');
  if (!/^\d{6}$/.test(cleanCode)) return false;

  const currentCounter = Math.floor(timeMs / 1000 / 30);
  for (let i = -windowSteps; i <= windowSteps; i++) {
    const expected = await generateTotpCode(secretBase32, currentCounter + i);
    if (expected === cleanCode) {
      return true;
    }
  }
  return false;
}
