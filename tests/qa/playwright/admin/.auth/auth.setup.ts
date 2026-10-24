/**
 * Auth setup — ADMIN role (produces qa/results/.auth/admin.json).
 *
 * COMPLETED (M0.7 / task M0-G): admin auth is a TWO-stage flow and both stages
 * are now automated:
 *   1. Firebase login on /login (the Part-9 email-input / password-input /
 *      login-submit data-testid attributes now exist on LoginPage).
 *   2. Step-up inside the AdminGate at /admin — admin email/password
 *      (admin-email-input / admin-password-input / admin-login-submit)
 *      followed by the OTP/TOTP challenge (otp-input / otp-submit testids on
 *      components/admin/auth/AdminLogin.tsx). When the backend answers
 *      trusted_browser instead of otp_required the gate clears without an OTP.
 *
 * The plan's caution applies: QA_ADMIN_* must be a DEDICATED QA admin
 * account, never the real production admin.
 *
 * Required environment (kept fail-closed below):
 *   - QA_ADMIN_EMAIL / QA_ADMIN_PASSWORD
 *   - QA_ADMIN_OTP (static dev code) OR QA_ADMIN_TOTP_SECRET (a current code
 *     is derived locally via RFC 6238 — no shared secret ever leaves the box).
 *
 * Final step persists storage state:
 *   await page.context().storageState({ path: STORAGE_STATE });
 */
import { test as setup, expect } from "@playwright/test";
import { createHmac } from "node:crypto";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

const STORAGE_STATE = "qa/results/.auth/admin.json";

/** RFC 6238 TOTP (SHA-1, 6 digits, 30s step) — Google Authenticator/Authy format. */
function deriveTotp(secretBase32: string, atMs: number = Date.now()): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const ch of secretBase32.replace(/=+$/g, "").replace(/\s+/g, "").toUpperCase()) {
    const idx = alphabet.indexOf(ch);
    if (idx >= 0) bits += idx.toString(2).padStart(5, "0");
  }
  const key = Buffer.alloc(Math.floor(bits.length / 8));
  for (let i = 0; i < key.length; i++) key[i] = parseInt(bits.slice(i * 8, i * 8 + 8), 2);

  const counter = Math.floor(atMs / 1000 / 30);
  const counterBuf = Buffer.alloc(8);
  counterBuf.writeUInt32BE(Math.floor(counter / 2 ** 32), 0);
  counterBuf.writeUInt32BE(counter >>> 0, 4);

  const digest = createHmac("sha1", key).update(counterBuf).digest();
  const offset = digest[digest.length - 1]! & 0x0f;
  const binary =
    ((digest[offset]! & 0x7f) << 24) |
    ((digest[offset + 1]! & 0xff) << 16) |
    ((digest[offset + 2]! & 0xff) << 8) |
    (digest[offset + 3]! & 0xff);
  return String(binary % 1_000_000).padStart(6, "0");
}

setup("authenticate as QA admin (login + step-up)", async ({ page }) => {
  const email = process.env.QA_ADMIN_EMAIL;
  const password = process.env.QA_ADMIN_PASSWORD;
  const staticOtp = process.env.QA_ADMIN_OTP;
  const totpSecret = process.env.QA_ADMIN_TOTP_SECRET;
  if (!email || !password || (!staticOtp && !totpSecret)) {
    throw new Error(
      "TODO(auth): QA_ADMIN_EMAIL / QA_ADMIN_PASSWORD / QA_ADMIN_TOTP_SECRET (or QA_ADMIN_OTP) " +
        "are not set. Use a DEDICATED QA admin account — never production credentials.",
    );
  }
  const otp = staticOtp ?? deriveTotp(totpSecret!);

  // ── Stage 1: Firebase identity on the main login form ────────────────────
  await page.goto("/login");
  await page.fill('[data-testid="email-input"]', email);
  await page.fill('[data-testid="password-input"]', password);
  await page.click('[data-testid="login-submit"]');
  await page.waitForURL("**/workspace");
  await expect(page).toHaveURL(/\/workspace$/);

  // ── Stage 2: AdminGate step-up inside /admin ─────────────────────────────
  await page.goto("/admin");
  await page.fill('[data-testid="admin-email-input"]', email);
  await page.fill('[data-testid="admin-password-input"]', password);
  await page.click('[data-testid="admin-login-submit"]');

  // Backend answers otp_required (challenge stays up) or trusted_browser
  // (gate clears immediately) — race both instead of assuming one.
  const otpInput = page.locator('[data-testid="otp-input"]');
  const shell = page.locator('[data-testid="admin-shell"]');
  await Promise.race([otpInput.waitFor({ state: "visible" }), shell.waitFor({ state: "visible" })]);

  if (await otpInput.isVisible()) {
    await otpInput.fill(otp);
    await page.click('[data-testid="otp-submit"]');
    // Wrong code keeps the challenge up; success mounts the console.
    await shell.waitFor({ state: "visible" });
  }

  await expect(shell).toBeVisible();
  mkdirSync(dirname(STORAGE_STATE), { recursive: true });
  await page.context().storageState({ path: STORAGE_STATE });
});
