---
target_scope: supremeai_internal
# [V5 audit 2026-09-17] Legacy doc migrated to canonical governance schema; defaults are conservative (historical/derived role) — refine on next lifecycle review.
id: auto:qa_engine_auto_checking_implementation_plan
subject: SupremeAI QA Engine — Complete Implementation Plan
document_role: implementation
planning_authority: Architecture Governance / Planning Circle
status: historical

---

# SupremeAI QA Engine — Complete Implementation Plan

> **Document Purpose:** This is the single authoritative plan for building the SupremeAI Automated QA Engine. It explains **what** we want to build, **why** it matters, and **exactly how** to implement it — step by step — so that any contributor can pick it up and execute without ambiguity.

---

## The Problem We Are Solving

SupremeAI has a 300+ item manual QA checklist covering Guest, Customer, Admin, Security, Network, Production, and E2E journeys. The frontend has existing quality tooling (`build`, `typecheck`, `lint`, `vitest`, Playwright) but the **last CI run skipped all frontend jobs**, meaning:

- Code technically exists in CI but was never executed against the latest release.
- A single developer cannot manually run 300 checks before every release.
- No machine-readable contract links the checklist to actual test code.
- There is no automated gate between "code merged" and "production deploy."

**Goal:** Transform the manual checklist from a Markdown document into a **living, machine-executable QA contract** that runs automatically on every PR, merge, and deploy — while keeping the human in the loop only for the 10–20% of checks that genuinely require human judgment.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    QA CHECKLIST / YAML                           │
│              (Single Source of Truth — qa/checklist/)            │
└──────────────────────────┬───────────────────────────────────────┘
                           │ parsed by
                    ┌──────▼───────┐
                    │  QA Runner   │  (qa/runner/index.ts)
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  Static QA           Playwright E2E     Runtime QA
  ─────────────       ─────────────────  ──────────────
  build/typecheck     guest/             /health
  lint                customer/          /readiness
  unit tests (vitest) admin/             DB / Redis
  route audit         security/          MCP
  knip dead-code      mobile/            AI provider
  visual regression   cross-browser      memory
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  QA Aggregator  │  (qa/scripts/generate-report.ts)
                  └────────┬────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
           JSON         HTML         AI Analysis
           report       report       (root-cause hints)
              │            │            │
              └────────────┼────────────┘
                           ▼
                    RELEASE GATE
                    ─────────────
                    P0 fail → BLOCK
                    P1 fail → BLOCK
                    P2 fail → WARN
                    P3 fail → LOG
                           │
                  ┌────────┴────────┐
                  ▼                 ▼
               PASS              BLOCKED
                  │
                  ▼
           PRODUCTION DEPLOY
                  │
                  ▼
          POST-DEPLOY SMOKE
                  │
          ┌───────┴───────┐
          ▼               ▼
        LIVE           UNHEALTHY
                           │
                     ALERT + ROLLBACK
```

---

## Repository Structure (New Files to Create)

```
qa/
├── checklist/
│   ├── guest.yaml            # A. Guest journey (G-01 to G-51)
│   ├── customer.yaml         # C. Customer journey (U-01 to U-105)
│   ├── admin.yaml            # E+F. Admin journey (ADM-01 to ADM-55)
│   ├── security.yaml         # D. Security isolation (SEC-01 to SEC-14)
│   ├── network.yaml          # H. Network/DevTools (NET-01 to NET-18)
│   ├── production.yaml       # I. Production config (PROD-01 to PROD-14)
│   ├── ux.yaml               # J. Responsive/UX (UX-01 to UX-18)
│   ├── e2e.yaml              # M. End-to-end journeys (E2E-01 to E2E-15)
│   └── release.yaml          # N. Release sign-off gates
│
├── playwright/
│   ├── fixtures/
│   │   ├── auth.fixture.ts   # Login helpers for all roles
│   │   ├── page.fixture.ts   # Common page helpers + data-testid guards
│   │   └── api.fixture.ts    # API request interception helpers
│   ├── guest/
│   │   ├── first-load.spec.ts
│   │   ├── navigation.spec.ts
│   │   ├── chat.spec.ts
│   │   ├── model-picker.spec.ts
│   │   └── file-attachment.spec.ts
│   ├── customer/
│   │   ├── workspace.spec.ts
│   │   ├── chat.spec.ts
│   │   ├── projects-files.spec.ts
│   │   ├── agents.spec.ts
│   │   ├── ide.spec.ts
│   │   ├── integrations.spec.ts
│   │   ├── research-memory.spec.ts
│   │   ├── scheduled-tasks.spec.ts
│   │   └── billing-profile.spec.ts
│   ├── admin/
│   │   ├── auth.spec.ts      # ADM-01 to ADM-07 (entry + step-up)
│   │   ├── stepup.spec.ts    # ADM-08 to ADM-15 (OTP/TOTP/RBAC)
│   │   └── panels.spec.ts    # ADM-16 to ADM-55 (all 40 panels)
│   ├── security/
│   │   ├── isolation.spec.ts # SEC-01 to SEC-09 (user A/B isolation)
│   │   └── headers.spec.ts   # SEC-10 to SEC-14 + NET-06 to NET-11
│   ├── e2e/
│   │   └── journeys.spec.ts  # E2E-01 to E2E-15
│   └── visual/
│       └── snapshots/        # Baseline screenshots (committed to Git)
│
├── scripts/
│   ├── generate-report.ts    # Aggregates all results → JSON + HTML
│   ├── validate-checklist.ts # Ensures YAML schema is correct
│   ├── route-audit.ts        # Confirms all App.tsx routes have test coverage
│   └── coverage-matrix.ts   # Prints UI/API/E2E/Security/Prod coverage table
│
├── reports/
│   └── latest.json           # Last run results (gitignored in CI, committed locally)
│
└── playwright.config.qa.ts   # QA-specific Playwright config (auth state projects)
```

GitHub Actions workflows to add:
```
.github/workflows/
├── 05-e2e-guest.yml
├── 06-e2e-customer.yml
├── 07-e2e-admin.yml
├── 08-production-preflight.yml
└── 09-post-deploy-smoke.yml
```

---

## Part 1: The YAML Checklist Schema (Single Source of Truth)

Every checklist item is a machine-readable YAML object. The checklist is not documentation — it **is** the specification.

### Schema

```yaml
# Example item from qa/checklist/guest.yaml
- id: G-23
  area: chat
  role: guest
  name: Empty submit is disabled
  description: >
    When the chat input is empty, clicking Send should be a no-op
    (button disabled or submission ignored). Nothing should be sent.
  route: /
  severity: P1           # P0=blocker, P1=critical, P2=important, P3=cosmetic
  automated: true
  action:
    - navigate: /
    - assert: selector=[data-testid="chat-input"]
    - assert: selector=[data-testid="send-button"][disabled]
  assert:
    - no_network_request: /api/chat
  manual_note: null

- id: G-36
  area: chat
  role: guest
  name: Save chat redirects to auth
  description: >
    A guest clicking "Save chat" should be redirected to /login or /register,
    not silently fail.
  route: /
  severity: P1
  automated: true
  action:
    - navigate: /
    - click: "[data-testid='save-chat-btn']"
  assert:
    - url_matches: /(login|register)/
  manual_note: null
```

### Severity Rules (enforced by release gate)

| Level | Meaning | Release Impact |
|-------|---------|----------------|
| **P0** | Production blocker (auth failure, data loss, security breach) | **STOP RELEASE** |
| **P1** | Critical user flow (login, chat, file upload broken) | **STOP RELEASE** |
| **P2** | Important feature degraded | **WARNING — human decides** |
| **P3** | Cosmetic / non-critical | **LOG ONLY** |

---

## Part 2: Playwright Configuration with Role-Based Projects

The key insight is that Playwright **projects** let us run the same suite with different authentication state. We create one config to rule them all.

### `qa/playwright.config.qa.ts`

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './qa/playwright',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 4 : undefined,

  reporter: [
    ['html', { open: 'never', outputFolder: 'qa/reports/html' }],
    ['json', { outputFile: 'qa/reports/results.json' }],
    ['junit', { outputFile: 'qa/reports/junit.xml' }],
    process.env.CI ? ['github'] : ['list'],
  ],

  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },

  projects: [
    // ── Setup projects (run first, save auth state) ──────────────────
    {
      name: 'setup-customer',
      testMatch: /.*\.setup\.ts/,
      use: { storageState: undefined },
    },
    {
      name: 'setup-admin',
      testMatch: /.*admin\.setup\.ts/,
      use: { storageState: undefined },
    },

    // ── Guest (no auth) ──────────────────────────────────────────────
    {
      name: 'guest-chromium',
      testMatch: /guest\/.*/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'guest-mobile',
      testMatch: /guest\/.*/,
      use: { ...devices['Pixel 5'] },
    },

    // ── Customer (authenticated) ─────────────────────────────────────
    {
      name: 'customer-chromium',
      testMatch: /customer\/.*/,
      dependencies: ['setup-customer'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'qa/.auth/customer.json',
      },
    },
    {
      name: 'customer-firefox',
      testMatch: /customer\/.*/,
      dependencies: ['setup-customer'],
      use: {
        ...devices['Desktop Firefox'],
        storageState: 'qa/.auth/customer.json',
      },
    },

    // ── Admin (step-up authenticated) ────────────────────────────────
    {
      name: 'admin-chromium',
      testMatch: /admin\/.*/,
      dependencies: ['setup-admin'],
      use: {
        ...devices['Desktop Chrome'],
        storageState: 'qa/.auth/admin.json',
      },
    },

    // ── Security (multi-user isolation) ──────────────────────────────
    {
      name: 'security',
      testMatch: /security\/.*/,
      use: { ...devices['Desktop Chrome'] },
    },

    // ── E2E Journeys ─────────────────────────────────────────────────
    {
      name: 'e2e-journeys',
      testMatch: /e2e\/.*/,
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
```

### Auth Setup Files

**`qa/playwright/fixtures/auth.fixture.ts`** — reusable login helpers:
```typescript
import { Page } from '@playwright/test';

export async function loginAsCustomer(page: Page) {
  await page.goto('/login');
  await page.fill('[data-testid="email-input"]', process.env.QA_CUSTOMER_EMAIL!);
  await page.fill('[data-testid="password-input"]', process.env.QA_CUSTOMER_PASSWORD!);
  await page.click('[data-testid="login-submit"]');
  await page.waitForURL('/workspace');
}

export async function loginAsAdmin(page: Page) {
  await loginAsCustomer(page);          // Firebase auth
  await page.goto('/admin');
  // Step-up: enter OTP
  await page.fill('[data-testid="otp-input"]', process.env.QA_ADMIN_OTP!);
  await page.click('[data-testid="otp-submit"]');
  await page.waitForURL(/\/admin/);
}
```

---

## Part 3: Test Implementation by Area

### 3.1 Guest Tests (`qa/playwright/guest/`)

Each spec file maps directly to a checklist section. Every test has:
1. The checklist ID as a comment
2. A `data-testid` selector (no brittle class/text selectors)
3. Both UI assertion AND API assertion where applicable

Example — `qa/playwright/guest/chat.spec.ts`:
```typescript
import { test, expect } from '@playwright/test';

test.describe('Guest Chat (G-23 to G-40)', () => {

  // G-23: Empty submit
  test('G-23: empty input — send is disabled', async ({ page }) => {
    await page.goto('/');
    const send = page.locator('[data-testid="send-button"]');
    await expect(send).toBeDisabled();
  });

  // G-24: Normal question gets a response
  test('G-24: normal question returns response', async ({ page, request }) => {
    await page.goto('/');
    await page.fill('[data-testid="chat-input"]', 'Hello');
    
    // Track API call
    const [apiCall] = await Promise.all([
      page.waitForResponse(r => r.url().includes('/api/chat') && r.status() === 200),
      page.click('[data-testid="send-button"]'),
    ]);
    
    // UI shows response
    const messages = page.locator('[data-testid="assistant-message"]');
    await expect(messages).toHaveCount(1, { timeout: 15_000 });
    expect(apiCall.ok()).toBeTruthy();
  });

  // G-25: Enter to send
  test('G-25: Enter key sends message', async ({ page }) => {
    await page.goto('/');
    await page.fill('[data-testid="chat-input"]', 'Test');
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-testid="user-message"]')).toBeVisible();
  });

  // G-26: Shift+Enter creates newline (does NOT send)
  test('G-26: Shift+Enter creates newline', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="chat-input"]');
    await page.keyboard.press('Shift+Enter');
    // Input value should contain a newline
    const value = await page.locator('[data-testid="chat-input"]').inputValue();
    expect(value).toContain('\n');
  });

  // G-28: Bangla input
  test('G-28: Bangla input works', async ({ page }) => {
    await page.goto('/');
    await page.fill('[data-testid="chat-input"]', 'তুমি কি বাংলায় কথা বলতে পারো?');
    const value = await page.locator('[data-testid="chat-input"]').inputValue();
    expect(value).toContain('বাংলা');
  });

  // G-36: Save chat → auth redirect
  test('G-36: save chat redirects guest to auth', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="save-chat-btn"]');
    await expect(page).toHaveURL(/(login|register)/);
  });
});
```

### 3.2 Customer Tests (`qa/playwright/customer/`)

Uses saved auth state. Tests verify **both UI and backend persistence**:

```typescript
// qa/playwright/customer/projects-files.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Projects & Files (U-27 to U-38)', () => {

  // U-28: Create project — verify backend persists it
  test('U-28: create project persists in backend', async ({ page }) => {
    const projectName = `QA-Project-${Date.now()}`;
    
    await page.goto('/projects');
    await page.click('[data-testid="create-project-btn"]');
    await page.fill('[data-testid="project-name-input"]', projectName);
    await page.click('[data-testid="create-project-submit"]');
    
    // UI confirmation
    await expect(page.locator(`text=${projectName}`)).toBeVisible();
    
    // Verify persistence: reload and re-check
    await page.reload();
    await expect(page.locator(`text=${projectName}`)).toBeVisible({ timeout: 10_000 });
  });

  // U-33: File upload — verify actual storage
  test('U-33: file upload stores in backend', async ({ page }) => {
    await page.goto('/files');
    
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles({
      name: 'qa-test.txt',
      mimeType: 'text/plain',
      buffer: Buffer.from('QA test file content'),
    });
    
    await page.click('[data-testid="upload-submit"]');
    await expect(page.locator('text=qa-test.txt')).toBeVisible({ timeout: 15_000 });
    
    // Reload to confirm persistence
    await page.reload();
    await expect(page.locator('text=qa-test.txt')).toBeVisible();
  });
});
```

### 3.3 Admin Tests (`qa/playwright/admin/`)

The admin tests follow the **Load → Read → Filter → Edit → Save → Cancel → Delete → Refresh → Audit** pattern for all 40 panels:

```typescript
// qa/playwright/admin/panels.spec.ts
import { test, expect } from '@playwright/test';

const ADMIN_PANELS = [
  { id: 'ADM-16', name: 'Dashboard', path: '/admin', kpi: '[data-testid="admin-kpi"]' },
  { id: 'ADM-23', name: 'User Management', path: '/admin/users', kpi: '[data-testid="user-list"]' },
  { id: 'ADM-18', name: 'Model Router', path: '/admin/model-router', kpi: '[data-testid="router-config"]' },
  // ... all 40 panels
];

for (const panel of ADMIN_PANELS) {
  test(`${panel.id}: ${panel.name} loads and shows data`, async ({ page }) => {
    await page.goto(panel.path);
    await expect(page.locator(panel.kpi)).toBeVisible({ timeout: 15_000 });
    // No full-shell crash
    await expect(page.locator('[data-testid="admin-shell"]')).toBeVisible();
  });
}
```

### 3.4 Security Tests (`qa/playwright/security/isolation.spec.ts`)

This is the most critical test — two separate browser contexts simulate User A and User B:

```typescript
import { test, expect, Browser } from '@playwright/test';

test('SEC-01: User A cannot access User B project', async ({ browser }) => {
  // Create two isolated contexts
  const ctxA = await browser.newContext();
  const ctxB = await browser.newContext();
  
  const pageA = await ctxA.newPage();
  const pageB = await ctxB.newPage();
  
  // User A creates a project
  await loginAsUserA(pageA);
  const projectId = await createProject(pageA, 'UserA-Private-Project');
  
  // User B tries to access User A's project directly
  await loginAsUserB(pageB);
  const response = await pageB.goto(`/projects/${projectId}`);
  
  // Must be denied (404 or redirect, never 200 with private data)
  expect([403, 404]).toContain(response?.status() ?? 404);
  await expect(pageB.locator('text=UserA-Private-Project')).not.toBeVisible();
  
  await ctxA.close();
  await ctxB.close();
});
```

---

## Part 4: The Route Audit Script

This catches the case where a new route is added to `App.tsx` but no test covers it.

### `qa/scripts/route-audit.ts`

```typescript
import { parse } from '@babel/parser';
import traverse from '@babel/traverse';
import { readFileSync, readdirSync } from 'fs';
import { glob } from 'glob';

// 1. Extract all routes from App.tsx
const appSource = readFileSync('frontend/src/App.tsx', 'utf-8');
const appRoutes: string[] = [];
// Parse and find all <Route path="..." /> elements
// (simplified — real implementation uses full AST traversal)

// 2. Extract all routes tested in qa/playwright/
const testFiles = glob.sync('qa/playwright/**/*.spec.ts');
const testedRoutes: string[] = [];
// Parse test files for page.goto('/route') calls

// 3. Find untested routes
const untestedRoutes = appRoutes.filter(r => !testedRoutes.includes(r));

if (untestedRoutes.length > 0) {
  console.error('⚠️  UNTESTED ROUTES:');
  untestedRoutes.forEach(r => console.error(`   ${r}`));
  process.exit(1);
}

console.log('✅ All routes have E2E coverage.');
```

---

## Part 5: The Coverage Matrix Script

Prints a human-readable table showing which features have which test types:

```typescript
// qa/scripts/coverage-matrix.ts
const features = [
  { name: 'Guest Chat',     ui: '✓', api: '✓', e2e: '✓', security: '-',  production: '✓' },
  { name: 'Login/Register', ui: '✓', api: '✓', e2e: '✓', security: '✓', production: '✓' },
  { name: 'File Upload',    ui: '✓', api: '✓', e2e: '✓', security: '✓', production: '✓' },
  { name: 'IDE',            ui: '✓', api: '✓', e2e: '✓', security: '-',  production: '✓' },
  { name: 'Admin RBAC',     ui: '✓', api: '✓', e2e: '✓', security: '✓', production: '✓' },
  { name: 'MCP',            ui: '✓', api: '✓', e2e: '✓', security: '✓', production: '✓' },
  // ...
];
```

Sample output:
```
Feature              UI   API   E2E   Security   Production
────────────────────────────────────────────────────────────
Guest Chat           ✓    ✓     ✓       -          ✓
Login/Register       ✓    ✓     ✓       ✓          ✓
File Upload          ✓    ✓     ✓       ✓          ✓
IDE                  ✓    ✓     ✓       -          ✓
Admin RBAC           ✓    ✓     ✓       ✓          ✓
MCP                  ✓    ✓     ✓       ✓          ✓
```

---

## Part 6: The QA Report Aggregator

### `qa/scripts/generate-report.ts`

Reads `qa/reports/results.json` (from Playwright) + static check outputs, produces:

```
╔══════════════════════════════════════════════════╗
║           SUPREMEAI QA REPORT                    ║
╚══════════════════════════════════════════════════╝

Commit:      8f92ab1
Environment: production
Date:        2026-09-13T19:33:04+06:00

Area              Total   Pass   Fail   Blocked   Score
────────────────────────────────────────────────────────
Guest               51      51      0       0     100%
Customer           105     102      3       0      97%
Admin               55      54      1       0      98%
Security            14      14      0       0     100%
Network             18      18      0       0     100%
E2E Journeys        15      14      1       0      93%
────────────────────────────────────────────────────────
TOTAL              258     253      5       0      98%

P0 failures:   0
P1 failures:   3    ← BLOCKS RELEASE
P2 failures:   2
P3 failures:   0

RELEASE DECISION: ⛔ BLOCKED
Reason: 3 P1 failures (customer chat, file upload, IDE load)
```

### Release Gate Logic

```typescript
const p0 = failures.filter(f => f.severity === 'P0');
const p1 = failures.filter(f => f.severity === 'P1');

if (p0.length > 0 || p1.length > 0) {
  console.error('⛔ RELEASE BLOCKED');
  process.exit(1);   // CI fails here, deploy job is skipped
}
```

---

## Part 7: GitHub Actions Workflows

### 7.1 PR Preflight (`05-e2e-guest.yml` — runs on every PR)

```yaml
name: E2E — Guest Smoke

on:
  pull_request:
    branches: [main, develop]
    paths:
      - 'frontend/**'
      - 'qa/**'

jobs:
  guest-smoke:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@...
      - uses: ./.github/actions/setup-node
      - run: pnpm install
      - run: pnpm --filter supremeai-studio-client build
      - run: npx playwright install --with-deps chromium
      - name: Run Guest E2E
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=guest-chromium
        env:
          E2E_BASE_URL: ${{ secrets.STAGING_URL }}
      - uses: actions/upload-artifact@...
        if: failure()
        with:
          name: guest-playwright-report
          path: qa/reports/html/
```

### 7.2 Full Customer Suite (`06-e2e-customer.yml` — runs on merge to main)

```yaml
name: E2E — Customer Full Suite

on:
  push:
    branches: [main]

jobs:
  customer-e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    strategy:
      matrix:
        project: [customer-chromium, customer-firefox]
    steps:
      - uses: actions/checkout@...
      - name: Install Playwright browsers
        run: npx playwright install --with-deps
      - name: Run Customer E2E (${{ matrix.project }})
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=${{ matrix.project }}
        env:
          E2E_BASE_URL: ${{ secrets.STAGING_URL }}
          QA_CUSTOMER_EMAIL: ${{ secrets.QA_CUSTOMER_EMAIL }}
          QA_CUSTOMER_PASSWORD: ${{ secrets.QA_CUSTOMER_PASSWORD }}
      - name: Generate QA Report
        run: npx ts-node qa/scripts/generate-report.ts
      - name: Release Gate
        run: npx ts-node qa/scripts/release-gate.ts  # exits 1 if P0/P1 failures
```

### 7.3 Admin Suite (`07-e2e-admin.yml` — runs on merge to main)

```yaml
name: E2E — Admin Suite

on:
  push:
    branches: [main]

jobs:
  admin-e2e:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Run Admin E2E
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=admin-chromium
        env:
          QA_ADMIN_EMAIL: ${{ secrets.QA_ADMIN_EMAIL }}
          QA_ADMIN_PASSWORD: ${{ secrets.QA_ADMIN_PASSWORD }}
          QA_ADMIN_OTP: ${{ secrets.QA_ADMIN_TOTP_SECRET }}  # TOTP secret for step-up
```

### 7.4 Production Preflight (`08-production-preflight.yml` — runs before every production deploy)

```yaml
name: Production Preflight

on:
  workflow_call:   # Called by the main deploy pipeline
  workflow_dispatch:

jobs:
  build-verify:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm --filter supremeai-studio-client build
      - run: pnpm --filter supremeai-studio-client typecheck
      - run: pnpm --filter supremeai-studio-client lint

  smoke-staging:
    needs: build-verify
    runs-on: ubuntu-latest
    steps:
      - name: Guest smoke on staging
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=guest-chromium --grep="@smoke"
      - name: Customer smoke on staging
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=customer-chromium --grep="@smoke"
      - name: Admin smoke on staging
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=admin-chromium --grep="@smoke"
      - name: Health endpoint
        run: |
          curl -f $PROD_BACKEND/health || exit 1
          curl -f $PROD_BACKEND/readiness || exit 1

  release-gate:
    needs: smoke-staging
    runs-on: ubuntu-latest
    steps:
      - run: npx ts-node qa/scripts/release-gate.ts
```

### 7.5 Post-Deploy Smoke (`09-post-deploy-smoke.yml`)

```yaml
name: Post-Deploy Smoke

on:
  workflow_run:
    workflows: ["Deploy to Production"]
    types: [completed]

jobs:
  canary-check:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    steps:
      - name: Wait for deployment to stabilize
        run: sleep 60
      - name: Run production smoke tests
        run: npx playwright test --config=qa/playwright.config.qa.ts --project=guest-chromium --grep="@smoke"
        env:
          E2E_BASE_URL: ${{ secrets.PRODUCTION_URL }}
      - name: Alert on failure
        if: failure()
        uses: ./.github/actions/alert-rollback
```

---

## Part 8: Local Developer Commands

Add to root `package.json`:

```json
{
  "scripts": {
    "qa": "npx playwright test --config=qa/playwright.config.qa.ts",
    "qa:guest": "npm run qa -- --project=guest-chromium",
    "qa:customer": "npm run qa -- --project=customer-chromium",
    "qa:admin": "npm run qa -- --project=admin-chromium",
    "qa:security": "npm run qa -- --project=security",
    "qa:e2e": "npm run qa -- --project=e2e-journeys",
    "qa:smoke": "npm run qa -- --grep=@smoke",
    "qa:full": "FULL_E2E=true npm run qa",
    "qa:report": "npx ts-node qa/scripts/generate-report.ts",
    "qa:coverage": "npx ts-node qa/scripts/coverage-matrix.ts",
    "qa:routes": "npx ts-node qa/scripts/route-audit.ts"
  }
}
```

---

## Part 9: `data-testid` Strategy (Prerequisite)

Playwright tests are only reliable if the frontend has stable selectors. We use `data-testid` attributes — never class names or text content (which change with i18n/redesigns).

### Required `data-testid` attributes (must be added to frontend)

| Component | Required `data-testid` |
|-----------|----------------------|
| Chat input | `chat-input` |
| Send button | `send-button` |
| User message bubble | `user-message` |
| Assistant message bubble | `assistant-message` |
| Model picker trigger | `model-picker-btn` |
| Save chat button | `save-chat-btn` |
| New chat button | `new-chat-btn` |
| Login email input | `email-input` |
| Login password input | `password-input` |
| Login submit | `login-submit` |
| Register form | `register-form` |
| Workspace nav | `workspace-nav` |
| Sidebar toggle | `sidebar-toggle` |
| Admin shell wrapper | `admin-shell` |
| OTP input | `otp-input` |
| OTP submit | `otp-submit` |
| Upload button | `upload-btn` or `file-input` |
| Create project | `create-project-btn` |
| Project name input | `project-name-input` |
| ... (full list in `qa/DATA_TESTID_MAP.md`) | |

> [!IMPORTANT]
> Adding `data-testid` to the frontend components is the **first prerequisite** before any Playwright test can run reliably. This is a systematic frontend change that touches many components but each individual change is trivial.

---

## Part 10: What Remains Manual (10–20%)

Even with full automation, some checks require human judgment:

| Check Type | Why It Must Stay Manual |
|------------|------------------------|
| UI "feels polished" | Subjective quality — machine can't judge visual appeal |
| Copy / wording naturalness | Language quality requires human reader |
| Workflow confusion | UX judgment requires real user mental model |
| AI response quality | Correctness and helpfulness are semantic, not syntactic |
| Visual hierarchy | Design intent requires human eye |
| Accessibility usability | Screen reader experience, cognitive load |
| Unusual real-world behavior | Edge cases machines don't know to look for |
| Business correctness | Only a human knows if the product makes sense |

These are documented as `automated: false` in the YAML checklist and must be executed before every release sign-off.

---

## Implementation Phases & Priority

### Phase 1 — Foundation (Week 1–2) 🔴 Highest Priority
**Goal:** Make the CI not skip frontend jobs. Get basic automation running.

- [ ] Add `data-testid` to critical components (chat, auth, nav)
- [ ] Create `qa/checklist/guest.yaml` and `qa/checklist/customer.yaml`
- [ ] Create `qa/playwright/guest/chat.spec.ts` (G-23 to G-40) — most important user flow
- [ ] Create `qa/playwright/fixtures/auth.fixture.ts`
- [ ] Create `qa/playwright.config.qa.ts`
- [ ] Add `npm run qa:guest` script
- [ ] Fix CI to not skip frontend jobs (update `ci.yml` to always run `typecheck` + `lint` + `vitest` on frontend changes)
- [ ] Add `05-e2e-guest.yml` workflow

**Definition of Done:** `npm run qa:guest` passes locally and in CI on every PR.

---

### Phase 2 — Customer Coverage (Week 3–4) 🟠 High Priority
**Goal:** Automate the critical customer flows.

- [ ] Add remaining `data-testid` attributes for workspace, files, projects
- [ ] Create `qa/playwright/customer/` specs (U-11 to U-38, U-65 to U-77)
- [ ] Create auth setup file (`qa/playwright/fixtures/customer.setup.ts`)
- [ ] Add `06-e2e-customer.yml` workflow
- [ ] Create `qa/scripts/route-audit.ts`
- [ ] Run route audit and fix any coverage gaps

**Definition of Done:** Customer auth flow, chat, files, and projects are automatically tested on every merge to main.

---

### Phase 3 — Admin & Security (Week 5–6) 🟡 Important
**Goal:** Automate the most critical security and admin checks.

- [ ] Create `qa/playwright/security/isolation.spec.ts` (SEC-01 to SEC-06)
- [ ] Create `qa/playwright/security/headers.spec.ts` (NET-06 to NET-11)
- [ ] Create `qa/playwright/admin/auth.spec.ts` (ADM-01 to ADM-15)
- [ ] Create `qa/playwright/admin/panels.spec.ts` (ADM-16 to ADM-55)
- [ ] Add `07-e2e-admin.yml` workflow
- [ ] Add TOTP step-up test (using TOTP secret from QA secrets)

**Definition of Done:** Admin auth + step-up + RBAC are automatically tested. User isolation is verified on every merge.

---

### Phase 4 — Production Gates (Week 7) 🟢 Production Readiness
**Goal:** No deploy happens without passing smoke tests.

- [ ] Add `@smoke` tags to the 20 most critical tests
- [ ] Create `08-production-preflight.yml` (called by deploy pipeline)
- [ ] Create `09-post-deploy-smoke.yml` (post-deploy canary check)
- [ ] Create `qa/scripts/generate-report.ts` (QA report aggregator)
- [ ] Create `qa/scripts/release-gate.ts` (P0/P1 exit-1 gate)
- [ ] Wire `release-gate.ts` into CI — blocks deploy on P0/P1 failures

**Definition of Done:** A P0 or P1 test failure automatically blocks the production deploy in CI.

---

### Phase 5 — Full Coverage + Visual Regression (Week 8+) 🔵 Long-term
**Goal:** 90% of the 300+ checklist items are automated.

- [ ] Create all E2E journey specs (E2E-01 to E2E-15)
- [ ] Add visual regression baseline screenshots
- [ ] Create `qa/scripts/coverage-matrix.ts`
- [ ] Create `qa/checklist/admin.yaml` (all 55 admin checks)
- [ ] Add axe accessibility tests to critical pages
- [ ] Set up nightly full regression run (cross-browser + mobile)

---

## Required Secrets in GitHub

The following secrets must be added to the repository's GitHub Actions secrets:

| Secret Name | Description |
|-------------|-------------|
| `STAGING_URL` | Staging frontend URL |
| `PRODUCTION_URL` | Production frontend URL |
| `PROD_BACKEND` | Production backend URL |
| `QA_CUSTOMER_EMAIL` | QA test customer account email |
| `QA_CUSTOMER_PASSWORD` | QA test customer account password |
| `QA_USER_A_EMAIL` | User A for isolation tests |
| `QA_USER_A_PASSWORD` | User A password |
| `QA_USER_B_EMAIL` | User B for isolation tests |
| `QA_USER_B_PASSWORD` | User B password |
| `QA_ADMIN_EMAIL` | Admin test account email |
| `QA_ADMIN_PASSWORD` | Admin test account password |
| `QA_ADMIN_TOTP_SECRET` | TOTP secret for admin step-up in CI |

> [!CAUTION]
> The `QA_ADMIN_TOTP_SECRET` must be a **dedicated QA admin account**, never the real production admin. Create a separate admin account for QA purposes only.

---

## Open Questions for User Review

> [!IMPORTANT]
> **Q1: Test Account Setup** — Do dedicated QA accounts (`qa-customer@...`, `qa-admin@...`) already exist in the production/staging Firebase project, or do they need to be created?

> [!IMPORTANT]
> **Q2: Staging Environment** — Does a stable staging environment exist that E2E tests can run against, or should the CI spin up a local frontend + mock backend for now?

> [!IMPORTANT]
> **Q3: Admin TOTP for CI** — The admin step-up uses OTP/TOTP. For CI automation, we need a way to generate valid OTPs programmatically (using the TOTP secret). Is there a dedicated QA TOTP account that can be used, or should step-up be bypassed for test environments?

> [!WARNING]
> **Q4: Visual Regression Baseline** — Visual regression tests require committed baseline screenshots. Should we establish the baseline now (screenshots of current UI = "correct") or wait until the UI is considered stable?

> [!NOTE]
> **Q5: Phase Priority** — The plan above orders phases by impact. Do you want to start with Phase 1 (Foundation) immediately, or is there a specific area (e.g., security isolation tests) you want prioritized?

---

## Verification Plan

### Automated
- `npm run qa:guest` — passes all guest tests locally
- `npm run qa:customer` — passes all customer tests locally (with test credentials)
- `npm run qa:smoke` — passes the @smoke-tagged subset in under 5 minutes
- `npm run qa:routes` — 0 untested routes

### CI Gates
- PR: Guest smoke tests pass → green checkmark
- Merge to main: Full customer + admin suite passes → green
- Before deploy: Production preflight passes → deploy proceeds
- After deploy: Post-deploy canary passes → LIVE status confirmed

### Human Sign-off (Release Checklist)
- Manual checks with `automated: false` in YAML are executed by tester
- Release sign-off document (`N. Release Sign-off`) is completed
- GO/NO-GO decision recorded with tester signature

---

## Summary

| What | Before | After |
|------|--------|-------|
| Checklist type | Markdown document | Machine-readable YAML |
| Test execution | 100% manual | 80–90% automated |
| CI coverage | Frontend jobs skipped | Always runs on frontend changes |
| Deploy gate | None | P0/P1 failures block deploy |
| Security isolation | Never tested | Automated with 2-user browser contexts |
| Admin step-up | Never tested in CI | Automated with TOTP in CI secrets |
| Time per release | Hours of manual QA | ~30 min for automated + human spot-checks |
| Coverage visibility | Unknown | Coverage matrix printed per run |