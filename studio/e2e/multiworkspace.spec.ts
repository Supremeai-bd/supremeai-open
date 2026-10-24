import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:4173';

// FIX(test-integrity): this spec previously asserted a "Multi-Platform
// Target Fleet Canvas" UI (Targets Connected / READ_ONLY / FULL_CONTROL
// badges) that no longer exists anywhere in src/ — and it navigated to
// a hash route (/#/workspace) the BrowserRouter app never served. With
// the assertions wrapped in `if (await locator.count() > 0)` the spec
// passed unconditionally: a false-positive test for deleted UI.
//
// The real, testable contract of /workspace today: it is wrapped in
// ProtectedRoute, so an unauthenticated visitor must be redirected to
// /login (src/components/core/AuthGuards.tsx:46).
test.describe('Workspace route protection — UI Smoke Tests', () => {
  test('unauthenticated visitor to /workspace is redirected to /login', async ({ page }) => {
    await page.goto(BASE_URL + '/workspace');
    await expect(page).toHaveURL(/\/login/);
  });
});
