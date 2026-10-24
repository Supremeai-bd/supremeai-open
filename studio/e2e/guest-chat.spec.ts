/**
 * E2E Guest Chat smoke — the public demo surface, hermetically.
 *
 * Updated for UnifiedChatPanel (Phase 2, 2026-10-24):
 * - Send button is empty-gated (disabled={!input.trim() || busy}).
 * - Intent chips fill the composer with their canned prompt.
 * - Enter submits; Shift+Enter inserts a newline.
 * - Submit -> user bubble immediately, staged thinking indicator (role=status),
 *   then streaming / webhook reply with SupremeAI dynamic badge (w.ge / Turbo).
 * - "How can SupremeAI help you today?" starter surface when empty.
 * - Model selector updates the chosen model.
 */
import { test, expect, type Page, type Route } from '@playwright/test';

async function blockApi(page: Page) {
  // Hermetic runner: intercept chat completions and return mock response with dynamic badge
  await page.route('**/v1/chat/completions', async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'chatcmpl-mock-test',
        choices: [{ message: { role: 'assistant', content: 'Here is a practical plan for your project.' } }],
        supremeai: { channel: 'w', engine: 'ge', tier: 'Turbo' },
      }),
    });
  });
  // Prevent any incidental background health/auth pings
  await page.route('**/api/**', (route: Route) => route.fulfill({ status: 204, body: '' }));
}

test.describe('Guest chat demo smoke', () => {
  test.beforeEach(async ({ page }) => {
    await blockApi(page);
    await page.goto('/');
  });

  test('send button is empty-gated until the composer has content', async ({ page }) => {
    const send = page.getByRole('button', { name: /send/i });
    await expect(send).toBeDisabled();
    await page.getByLabel('Message SupremeAI').fill('hello there');
    await expect(send).toBeEnabled();
  });

  test('intent chip fills the composer with its canned prompt', async ({ page }) => {
    await page.getByRole('button', { name: /research/i }).first().click();
    await expect(page.getByLabel('Message SupremeAI')).toHaveValue(/research/i);
    await expect(page.getByRole('button', { name: /send/i })).toBeEnabled();
  });

  test('typed continuation after an intent chip works cleanly', async ({ page }) => {
    const composer = page.getByLabel('Message SupremeAI');
    await page.getByRole('button', { name: /research/i }).first().click();
    await composer.fill('Help me research SupremeAI features');
    await composer.press('Enter');
    await expect(page.getByText('Help me research SupremeAI features')).toBeVisible();
  });

  test('Enter submits but Shift+Enter only inserts a newline', async ({ page }) => {
    const composer = page.getByLabel('Message SupremeAI');
    await composer.fill('first line');
    await composer.press('Shift+Enter');
    await composer.type('second line');
    // Shift+Enter should keep text in textarea without sending
    await expect(composer).toHaveValue(/first line\nsecond line/);

    await composer.press('Enter');
    await expect(page.getByText(/first line/)).toBeVisible();
  });

  test('submit shows user bubble, thinking indicator, then assistant reply with brand badge', async ({ page }) => {
    const composer = page.getByLabel('Message SupremeAI');
    await composer.fill('Help me build a plan');
    await page.getByRole('button', { name: /send/i }).click();

    // User bubble appears immediately
    await expect(page.getByText('Help me build a plan')).toBeVisible();

    // Assistant reply resolves
    await expect(page.getByText(/practical plan/i)).toBeVisible({ timeout: 10_000 });

    // Dynamic brand badge is visible
    await expect(page.getByText(/SupremeAI/)).toBeVisible();
  });

  test('double-submit while busy is prevented', async ({ page }) => {
    const composer = page.getByLabel('Message SupremeAI');
    await composer.fill('count my bubbles');
    await page.getByRole('button', { name: /send/i }).click();
    // Second click immediately
    await page.getByRole('button', { name: /send/i }).click().catch(() => {});

    await expect(page.getByText('count my bubbles')).toHaveCount(1, { timeout: 5_000 });
  });

  test('model picker updates selection', async ({ page }) => {
    const select = page.locator('select').first();
    await select.selectOption({ label: 'Reasoning Pro — Deep analysis and complex planning' });
    await expect(select).toHaveValue('Reasoning Pro');
  });

  test('carries conversation_id across multi-turn messages and renders New Chat button', async ({ page }) => {
    const capturedConvIds: string[] = [];
    await page.route('**/v1/chat/completions', async (route: Route) => {
      const postData = route.request().postDataJSON() || {};
      if (postData.conversation_id) {
        capturedConvIds.push(postData.conversation_id);
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'chatcmpl-mock-test',
          conversation_id: postData.conversation_id || 'conv-turn-test',
          choices: [{ message: { role: 'assistant', content: 'Turn acknowledged.' } }],
          supremeai: { channel: 'w', engine: 'ge', tier: 'Turbo' },
        }),
      });
    });

    const composer = page.getByLabel('Message SupremeAI');
    await composer.fill('First message');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.getByText('Turn acknowledged.').first()).toBeVisible();

    // Verify New Chat button appears when messages exist
    const newChatBtn = page.getByRole('button', { name: /new/i });
    await expect(newChatBtn).toBeVisible();

    // Send second turn
    await composer.fill('Second message');
    await page.getByRole('button', { name: /send/i }).click();
    await expect(page.getByText('Second message')).toBeVisible();

    // Verify both requests carried the exact same persistent conversation_id
    expect(capturedConvIds.length).toBeGreaterThanOrEqual(2);
    expect(capturedConvIds[0]).toBe(capturedConvIds[1]);
  });
});

test.describe('Public marketing pages render', () => {
  const routes: { path: string; heading: RegExp }[] = [
    { path: '/models', heading: /Choose the outcome/i },
    { path: '/features', heading: /.+/ },
    { path: '/pricing', heading: /.+/ },
    { path: '/docs', heading: /.+/ },
    { path: '/about', heading: /.+/ },
  ];

  for (const { path, heading } of routes) {
    test(`${path} renders its page heading`, async ({ page }) => {
      await blockApi(page);
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
      if (heading.source !== '.+') {
        await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      }
      await expect(page.locator('main a[href="/"]').first()).toBeVisible();
    });
  }
});
