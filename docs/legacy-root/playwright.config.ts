/**
 * Playwright E2E Test Configuration — Stable & Reliable
 * v4.0: Fixed flaky tests with retries, timeouts, and parallelization
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  // Test directory
  testDir: './tests/e2e',
  
  // Run tests in parallel (faster CI)
  fullyParallel: true,
  
  // Fail CI on first failure (fail-fast)
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,  // Retry flaky tests in CI
  workers: process.env.CI ? 2 : undefined,
  reporter: [
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-results.json' }],
    process.env.CI ? ['github'] : ['list'],
  ],
  use: {
    // Base URL from environment
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    
    // Collect trace on first retry (for debugging failures)
    trace: 'on-first-retry',
    
    // Screenshot only on failure
    screenshot: 'only-on-failure',
    
    // Video on first retry
    video: 'retain-on-failure',
    
    // Navigation timeout (increased for slow networks)
    navigationTimeout: 30000,
    
    // Action timeout
    actionTimeout: 15000,
    
    // Wait for stability before actions
    waitForTimeout: 1000,
  },
  
  // Configure projects for different browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    // Only run additional browsers in full test suite
    ...(process.env.FULL_E2E
      ? [
          {
            name: 'firefox',
            use: { ...devices['Desktop Firefox'] },
          },
          {
            name: 'webkit',
            use: { ...devices['Desktop Safari'] },
          },
          // Mobile viewport
          {
            name: 'mobile-chrome',
            use: { ...devices['Pixel 5'] },
          },
        ]
      : []),
  ],
  
  // Web server (local dev mode)
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
});
