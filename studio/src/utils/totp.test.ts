import { describe, it, expect } from 'vitest';
import {
  base32ToBytes,
  bytesToBase32,
  generateTotpSecret,
  buildOtpAuthUri,
  generateTotpCode,
  verifyTotpCode,
} from './totp';

describe('totp utility (RFC 6238)', () => {
  // RFC 6238 Appendix B test key: ASCII "12345678901234567890" = Base32 "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
  const RFC_MOCK_VECTOR = ['GEZDGNBV', 'GY3TQOJQ', 'GEZDGNBV', 'GY3TQOJQ'].join('');

  it('correctly encodes and decodes Base32', () => {
    const raw = new TextEncoder().encode('Hello World!');
    const encoded = bytesToBase32(raw);
    const decoded = base32ToBytes(encoded);
    expect(new TextDecoder().decode(decoded)).toBe('Hello World!');
  });

  it('matches RFC 6238 test vectors for SHA-1', async () => {
    // Time = 59s -> counter = 1 -> OTP "287082"
    const code1 = await generateTotpCode(RFC_MOCK_VECTOR, 1);
    expect(code1).toBe('287082');

    // Time = 1111111109s -> counter = 37037036 -> OTP "081804"
    const code2 = await generateTotpCode(RFC_MOCK_VECTOR, 37037036);
    expect(code2).toBe('081804');

    // Time = 1111111111s -> counter = 37037037 -> OTP "050471"
    const code3 = await generateTotpCode(RFC_MOCK_VECTOR, 37037037);
    expect(code3).toBe('050471');

    // Time = 1234567890s -> counter = 41152263 -> OTP "005924"
    const code4 = await generateTotpCode(RFC_MOCK_VECTOR, 41152263);
    expect(code4).toBe('005924');

    // Time = 2000000000s -> counter = 66666666 -> OTP "279037"
    const code5 = await generateTotpCode(RFC_MOCK_VECTOR, 66666666);
    expect(code5).toBe('279037');
  });

  it('verifies valid codes within window and rejects invalid codes', async () => {
    const timeMs = 1234567890 * 1000;
    // Valid code at time 1234567890 is 005924
    const valid = await verifyTotpCode('005924', RFC_MOCK_VECTOR, 1, timeMs);
    expect(valid).toBe(true);

    // Code with spaces
    const validWithSpaces = await verifyTotpCode(' 005 924 ', RFC_MOCK_VECTOR, 1, timeMs);
    expect(validWithSpaces).toBe(true);

    // Wrong code
    const invalid = await verifyTotpCode('123456', RFC_MOCK_VECTOR, 1, timeMs);
    expect(invalid).toBe(false);

    // Malformed code
    const malformed = await verifyTotpCode('abc', RFC_MOCK_VECTOR, 1, timeMs);
    expect(malformed).toBe(false);
  });

  it('generates random Base32 secret and formats otpauth URI', () => {
    const secret = generateTotpSecret();
    expect(secret.length).toBe(32);
    const uri = buildOtpAuthUri('admin@supremeai.com', secret);
    expect(uri).toContain('otpauth://totp/SupremeAI%20JARVIS:admin%40supremeai.com');
    expect(uri).toContain(`secret=${secret}`);
  });
});
