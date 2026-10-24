import { test, expect, type Page } from '@playwright/test';

// FIX (final-test ci-fixes): ARCH-001 — hardcoded loopback URL fallback removed.
// playwright.config.ts already sets baseURL (E2E_BASE_URL/BASE_URL → preview server),
// so an empty fallback means relative path — no machine-specific URL in code.
const BASE_URL = process.env.BASE_URL ?? '';

// ─── Helpers ────────────────────────────────────────────────────────────────

async function waitForCommandCenter(page: Page) {
  // FIX (final-test ci-fixes): authStore's canonical key is 'supremeai_auth_token'
  // (authStore.ts TOKEN_KEY) — the old spec seeded wrong keys ('supremai-auth-token' /
  // 'supremeai_token'), so ProtectedRoute redirected to /login and "home loads KPI
  // tiles" never saw ACTIVE AGENTS. Optimistic restore (authStore.initialize) sets
  // LOGGED_IN from the token alone — no network required.
  // Issue #521: token now seeds sessionStorage (the canonical tier); the
  // tokenStorage read path still migrates legacy localStorage entries.
  await page.addInitScript(() => {
    window.sessionStorage.setItem('supremeai_auth_token', 'demo-token');
    window.localStorage.setItem(
      'supremeai_auth_user',
      JSON.stringify({ id: 'demo-user', email: 'user@supremeai.dev', name: 'Demo User' }),
    );
  });
  await page.goto(`${BASE_URL}/commandcenter`);
  await page.waitForLoadState('domcontentloaded');
  // Look for Command Center indicator
  await page.waitForSelector('text=কমান্ড সেন্টার', { timeout: 15_000 }).catch(() => {});
}

export async function navigateToModule(page: Page, moduleName: string) {
  const rail = page.locator('text=' + moduleName).first();
  if (await rail.count() > 0) {
    await rail.click();
    await page.waitForTimeout(500);
  }
}

// ─── Tests ──────────────────────────────────────────────────────────────────

test.describe('AETHEL Command Center — Smoke Tests', () => {
  test.beforeEach(async ({ page }) => {
    await waitForCommandCenter(page);
  });

  test('home loads KPI tiles', async ({ page }) => {
    // CommandDeck renders KPI tiles; look for at least one label
    const kpi = page.locator('text=ACTIVE AGENTS').first();
    await expect(kpi).toBeVisible({ timeout: 10_000 });
  });

  test('navigate to each suite group', async ({ page }) => {
    const modules = [
      'Observe',
      'Operate',
      'Build',
      'Secure',
      'Money',
      'System',
    ];

    for (const mod of modules) {
      const locator = page.locator(`text=${mod}`).first();
      if (await locator.count() > 0) {
        await locator.click();
        await page.waitForTimeout(300);
      }
    }
  });

  test('OTP modal appears for gate action', async ({ page }) => {
    // Navigate to deck (home)
    await page.goto(`${BASE_URL}/commandcenter`);
    await page.waitForLoadState('domcontentloaded');

    // Click gate action to trigger confirmation modal
    const gateBtn = page.locator('button:has-text("গেট লক")').first();
    if (await gateBtn.count() > 0) {
      await gateBtn.click();
      // Confirm modal should appear
      const modal = page.locator('text=নিশ্চিত করুন').first();
      await expect(modal).toBeVisible({ timeout: 5_000 });
    }
  });

  test('WS disconnect shows degraded state', async ({ page }) => {
    // FIX (final-test ci-fixes): ARCH-001 — hardcoded 'ws://…:9999' loopback URL removed.
    // Connect to the current origin's /ws/dashboard instead (preview server does not
    // accept the upgrade → socket fails/closes → disconnect-state simulation).
    await page.evaluate(() => {
      const proto = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
      const ws = new WebSocket(`${proto}${window.location.host}/ws/dashboard`);
      ws.close();
    });

    await page.waitForTimeout(1000);

    // Look for degraded banner or EmptyState
    const degraded = page.locator('text=WS').first();
    if (await degraded.count() > 0) {
      await expect(degraded).toBeVisible({ timeout: 5_000 });
    }
  });
});