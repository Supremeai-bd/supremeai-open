/**
 * Auth setup — CUSTOMER role (produces qa/results/.auth/customer.json).
 *
 * COMPLETED (M0.7 / task M0-G): the login automation below follows the exact
 * pattern this file originally sketched as a skeleton:
 *
 *   goto /login -> fill email-input / password-input -> click login-submit
 *   -> waitForURL('**' + '/workspace') -> storageState({ path: STORAGE_STATE })
 *   (the glob is split across a concatenation in this comment: a literal
 *    double-star-slash would terminate this JSDoc block early — the original
 *    skeleton had exactly that bug, which is why the setup never collected).
 *
 * The Part-9 data-testid attributes (email-input / password-input /
 * login-submit) now exist on the real login form
 * (frontend/src/pages/auth/LoginPage.tsx).
 *
 * Still required at runtime (environment, not code):
 *   - QA_CUSTOMER_EMAIL / QA_CUSTOMER_PASSWORD: a DEDICATED non-production QA
 *     customer account. The explicit guard below keeps failing fast when they
 *     are unset — the customer project can never silently run unauthenticated.
 *   - QA_BASE_URL pointing at a deployment (vite preview or staging) whose
 *     /api/** backend can actually authenticate the credentials.
 */
import { test as setup, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname } from "node:path";

const STORAGE_STATE = "qa/results/.auth/customer.json";

setup("authenticate as QA customer", async ({ page }) => {
  const email = process.env.QA_CUSTOMER_EMAIL;
  const password = process.env.QA_CUSTOMER_PASSWORD;
  if (!email || !password) {
    throw new Error(
      "TODO(auth): QA_CUSTOMER_EMAIL / QA_CUSTOMER_PASSWORD are not set. " +
        "Create a dedicated non-production QA account and expose the values " +
        "as environment variables before running the customer project.",
    );
  }

  await page.goto("/login");
  await page.fill('[data-testid="email-input"]', email);
  await page.fill('[data-testid="password-input"]', password);
  await page.click('[data-testid="login-submit"]');

  // Login failure modes (bad credentials, cold backend) keep the browser on
  // /login with an error alert — waitForURL turns that into a clear timeout
  // naming the step instead of a silent unauthenticated storage state.
  await page.waitForURL("**/workspace");
  await expect(page).toHaveURL(/\/workspace$/);

  mkdirSync(dirname(STORAGE_STATE), { recursive: true });
  await page.context().storageState({ path: STORAGE_STATE });
});
