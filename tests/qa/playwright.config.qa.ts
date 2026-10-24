/**
 * Playwright QA config — Part 2 of the QA engine plan, adapted to this repo.
 *
 * Role projects (guest / customer / admin / security) + auth setup projects.
 * The app under test comes from QA_BASE_URL (default http://127.0.0.1:3000 —
 * matches `vite preview --port 3000` used by the CI workflows; point it at a
 * deployed staging URL instead and the same suites run remotely).
 *
 * Auth: the customer/admin projects depend on setup projects that produce
 * storage states (qa/results/.auth/*.json). Setup automation lives at
 * qa/playwright/customer/.auth/auth.setup.ts and
 * qa/playwright/admin/.auth/auth.setup.ts. M0-G fix: the skeletons were named
 * `setup.ts` while testMatch requires the canonical `<name>.setup.ts` — so
 * the setup projects silently collected ZERO tests since 7-e (also, the old
 * skeleton's JSDoc contained a literal double-star-slash glob that terminated
 * the comment early and broke parsing). Both are fail-closed: they throw when
 * the QA_* credential env vars are unset.
 *
 * Run:  npx playwright test -c qa/playwright.config.qa.ts --project=guest
 */
import { defineConfig, devices } from "@playwright/test";
import { join } from "node:path";

const __qa = __dirname; // config lives at qa/playwright.config.qa.ts
const baseURL = process.env.QA_BASE_URL || "http://127.0.0.1:3000";
const isCI = !!process.env.CI;

export default defineConfig({
  testDir: join(__qa, "playwright"),
  fullyParallel: true,
  forbidOnly: isCI,
  retries: 1,
  workers: isCI ? 2 : undefined,
  timeout: 30_000,

  reporter: [
    ["json", { outputFile: join(__qa, "results", "results.json") }],
    ...(isCI ? ([["github"]] as const) : ([["list"]] as const)),
    ["html", { open: "never", outputFolder: join(__qa, "results", "html") }],
  ],

  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    navigationTimeout: 30_000,
    actionTimeout: 15_000,
  },

  projects: [
    // ── Setup projects (produce storage states for authenticated roles) ────
    {
      name: "setup-customer",
      testMatch: /customer\/\.auth\/.*\.setup\.ts/,
      use: { storageState: undefined },
    },
    {
      name: "setup-admin",
      testMatch: /admin\/\.auth\/.*\.setup\.ts/,
      use: { storageState: undefined },
    },

    // ── Guest (no auth) ────────────────────────────────────────────────────
    {
      name: "guest",
      testMatch: /guest\/.*\.spec\.ts/,
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },

    // ── Customer (authenticated via setup-customer) ────────────────────────
    {
      name: "customer",
      testMatch: /customer\/.*\.spec\.ts/,
      testIgnore: /.*\.setup\.ts/,
      dependencies: ["setup-customer"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: join(__qa, "results", ".auth", "customer.json"),
      },
    },

    // ── Admin (step-up authenticated via setup-admin) ──────────────────────
    {
      name: "admin",
      testMatch: /admin\/.*\.spec\.ts/,
      testIgnore: /.*\.setup\.ts/,
      dependencies: ["setup-admin"],
      use: {
        ...devices["Desktop Chrome"],
        storageState: join(__qa, "results", ".auth", "admin.json"),
      },
    },

    // ── Security (multi-context isolation checks; no shared storage) ───────
    {
      name: "security",
      testMatch: /security\/.*\.spec\.ts/,
      testIgnore: /.*\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
