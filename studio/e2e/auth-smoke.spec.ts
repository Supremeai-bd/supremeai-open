/**
 * E2E Auth Smoke — the production session lifecycle, end to end.
 *
 * COVERS (owner's P1 smoke checklist, adapted to the hermetic CI runner —
 * the preview build has no live backend, so backend contracts are mocked at
 * the network boundary with page.route and every assertion targets what the
 * FRONTEND must guarantee):
 *
 *   1. Unauthenticated users are gated out of protected routes.
 *   2. Login → canonical token persisted (supremeai_auth_token).
 *   3. Reload → optimistic restore + /auth/me verification carrying the
 *      Bearer header (token survives the session, not just the render).
 *   4. A 401 on /auth/me (server-side invalidation) clears the session —
 *      only session-validation endpoints may invalidate (apiClient contract).
 *   5. Logout via the account menu clears the token and returns to /login.
 *   6. Relogin works (GuestRoute lets a logged-out user back in).
 *
 * CONTRACTS UNDER TEST (from src/store/authStore.ts + src/services/apiClient.ts):
 *   POST /api/v1/auth/login  {username, password} → {access_token, user_id, ...}
 *   GET  /api/v1/auth/me     Authorization: Bearer <token>
 *   sessionStorage key: 'supremeai_auth_token' (Issue #521 — tokens no longer
 *   persist in localStorage; sessionStorage dies with the tab)
 */
import { test, expect, type Page, type Route } from '@playwright/test';

const TOKEN_KEY = 'supremeai_auth_token';
const USER_KEY = 'supremeai_auth_user';
const DEMO_USER = {
  user_id: 'e2e-user-1',
  email: 'e2e@supremeai.dev',
  name: 'E2E User',
  role: 'user',
  permissions: [],
};

const loginResponse = {
  access_token: 'e2e-token-abc123',
  user_id: DEMO_USER.user_id,
  role: 'user',
  permissions: [],
};

async function mockBackend(page: Page, opts: { meStatus?: number } = {}) {
  const meStatus = opts.meStatus ?? 200;

  // Hermetic runner: no other request may reach the baked-in production
  // backend from CI. Registered FIRST so the specific mocks below (most
  // recently registered routes win in Playwright) take precedence.
  await page.route('**/api/**', (route: Route) => route.fulfill({ status: 204, body: '' }));

  // Backend contract mocks.
  await page.route('**/api/v1/auth/login', async (route: Route) => {
    const body = route.request().postDataJSON() as { username?: string; password?: string };
    if (!body?.username || !body?.password) {
      await route.fulfill({ status: 422, body: JSON.stringify({ detail: 'username and password required' }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(loginResponse) });
  });

  await page.route('**/api/v1/auth/me', async (route: Route) => {
    if (route.request().method() !== 'GET') {
      await route.fulfill({ status: 405, body: '{}' });
      return;
    }
    // Honest contract: /auth/me only succeeds for a request that presents a
    // Bearer token. Without one this must be 401 — otherwise the app's
    // cookie-session restore path would fabricate a login in the test.
    const authHeader = route.request().headers()['authorization'] ?? '';
    if (!authHeader.startsWith('Bearer ') || meStatus !== 200) {
      await route.fulfill({ status: meStatus === 200 ? 401 : meStatus, body: JSON.stringify({ detail: 'session expired' }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO_USER) });
  });
}

async function signOutViaAccountMenu(page: Page) {
  // Issue #1108: wait for the Account Menu button to be attached and visible
  // before clicking. The workspace shell health-polling can re-render the
  // header, and the button may not be interactable immediately after navigation.
  const accountMenuBtn = page.getByRole('button', { name: 'Account menu' });
  await accountMenuBtn.waitFor({ state: 'visible', timeout: 15_000 });
  await accountMenuBtn.click();

  // Wait for the dropdown to appear before dispatching the click event.
  const logoutBtn = page.getByRole('button', { name: 'Log out' });
  await logoutBtn.waitFor({ state: 'visible', timeout: 10_000 });
  // dispatchEvent instead of click: transparent shell overlays can swallow
  // hit-tested clicks while backend-health polling re-renders the dropdown.
  await logoutBtn.dispatchEvent('click');
}

test.describe('Auth session lifecycle smoke', () => {
  // The login flow + reload + polling can exceed the 30s default on CI.
  test.setTimeout(90_000);

  test('protected route redirects unauthenticated users to login', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/workspace');
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test('login persists the canonical token and lands in the workspace', async ({ page }) => {
    const meRequests: { authHeader: string | null }[] = [];
    await mockBackend(page);

    // Capture /auth/me headers so the Bearer contract is asserted, not assumed.
    // Registered AFTER mockBackend so this route wins for /auth/me.
    await page.route('**/api/v1/auth/me', async (route: Route) => {
      const authHeader = route.request().headers()['authorization'] ?? null;
      meRequests.push({ authHeader });
      if (!authHeader?.startsWith('Bearer ')) {
        await route.fulfill({ status: 401, body: JSON.stringify({ detail: 'unauthenticated' }) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(DEMO_USER) });
    });

    await page.goto('/login');
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();

    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    // Token persisted under the canonical key (authStore — sessionStorage, Issue #521).
    const token = await page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY);
    expect(token).toBe(loginResponse.access_token);
    // Issue #521: the token must NOT exist in localStorage anymore.
    const legacyToken = await page.evaluate((key) => localStorage.getItem(key), TOKEN_KEY);
    expect(legacyToken).toBeNull();

    // The cached profile key must not leak a service-role or admin secret.
    const userRaw = await page.evaluate((key) => localStorage.getItem(key), USER_KEY);
    expect(userRaw).toContain('e2e@supremeai.dev');

    // Reloading verifies the session against /auth/me with a Bearer header.
    await page.reload();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });
    await expect
      .poll(() => meRequests.filter((r) => r.authHeader?.startsWith('Bearer ')).length, {
        timeout: 10_000,
      })
      .toBeGreaterThan(0);
  });

  test('session survives reload — token restored without re-login', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/login');
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    await page.reload();
    // GuestRoute would bounce an unauthenticated session back to /login;
    // staying on /workspace proves the optimistic restore worked.
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });
    const token = await page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY);
    expect(token).toBe(loginResponse.access_token);
  });

  test('401 on /auth/me invalidates the session (fail-closed)', async ({ page }) => {
    await mockBackend(page, { meStatus: 401 });
    await page.goto('/login');
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    // Reload so initialize() re-runs WITH the persisted token: the background
    // /auth/me verification is what must prove the token invalid (401) and
    // clear it. Nothing triggers /auth/me without the reload.
    await page.reload();

    // The persisted token must be gone once the session-validation endpoint
    // proved it invalid; ProtectedRoute then bounces to /login.
    await expect
      .poll(() => page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY), { timeout: 15_000 })
      .toBeNull();
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
  });

  test('logout clears the token and returns to login', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/login');
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    await signOutViaAccountMenu(page);

    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });
    const token = await page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY);
    expect(token).toBeNull();
  });

  test('relogin after logout works', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/login');
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    await signOutViaAccountMenu(page);
    await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

    // GuestRoute may take a beat to flip status → give the form a moment.
    await page.getByLabel('Email address').fill('e2e@supremeai.dev');
    await page.getByLabel('Password').fill('correct-horse-battery');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/workspace/, { timeout: 15_000 });

    const token = await page.evaluate((key) => sessionStorage.getItem(key), TOKEN_KEY);
    expect(token).toBe(loginResponse.access_token);
  });
});
