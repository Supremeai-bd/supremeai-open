/**
 * #116 — Test wiring runner + guard (poka-yoke against silent test rot).
 *
 * Problem: nine Tower test files were referenced by NO npm script and NO CI
 * job — they compiled but never executed anywhere, so the #2596 task-engine
 * contract suite (lease locks, duplicate-claim rejection, heartbeat expiry)
 * never ran in CI.
 *
 * Two modes:
 *
 * 1. Runner (default):
 *      tsx scripts/test-runner.ts <test-file> [REQUIRED_ENV_VAR ...]
 *    Runs the given test file via tsx. When any REQUIRED_ENV_VAR is absent
 *    from the environment the suite is SKIPPED with exit 0 and a documented
 *    reason (per #116: "wire with a documented env-skip" — never silently
 *    dead). Any test file wired without required vars runs unconditionally.
 *
 * 2. Wiring guard:
 *      tsx scripts/test-runner.ts --guard
 *    Asserts every `test_*.ts` file at the package root and every `.ts` file
 *    under `test/` is referenced by at least one npm script in package.json.
 *    Exit 1 with a report when a test file is unwired, so new/renamed test
 *    files cannot disappear from CI without a failure (#116 root cause).
 *
 * No external dependencies; Node/Bun compatible.
 */

import { spawnSync } from "node:child_process";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import * as path from "node:path";

const PKG_ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");

function runTest(file: string, requiredEnv: string[]): number {
  const missing = requiredEnv.filter((name) => {
    const value = process.env[name];
    return value === undefined || value === "";
  });
  if (missing.length > 0) {
    console.log(
      `⏭️  SKIP ${file}: missing required env [${missing.join(", ")}] ` +
        `(documented env-skip per #116 — wire target for #98 offline-mode work)`
    );
    return 0;
  }
  console.log(`▶️  RUN ${file}${requiredEnv.length ? ` (env: ${requiredEnv.join(",")})` : ""}`);
  const result = spawnSync("tsx", [file], { stdio: "inherit", cwd: PKG_ROOT });
  if (result.error) {
    console.error(`❌ failed to spawn tsx for ${file}: ${String(result.error)}`);
    return 1;
  }
  return result.status ?? 1;
}

function collectTestFiles(): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(PKG_ROOT)) {
    if (/^test_.*\.ts$/.test(entry)) files.push(entry);
  }
  const testDir = path.join(PKG_ROOT, "test");
  if (existsSync(testDir)) {
    for (const entry of readdirSync(testDir)) {
      if (entry.endsWith(".ts")) files.push(path.join("test", entry));
    }
  }
  return files.sort();
}

function guard(): number {
  const pkg = JSON.parse(readFileSync(path.join(PKG_ROOT, "package.json"), "utf-8")) as {
    scripts?: Record<string, string>;
  };
  const scriptBlob = Object.values(pkg.scripts ?? {}).join(" \n ");
  const unwired = collectTestFiles().filter((file) => !scriptBlob.includes(path.basename(file)));
  if (unwired.length > 0) {
    console.error(`❌ wiring guard: ${unwired.length} test file(s) referenced by NO npm script:`);
    for (const file of unwired) console.error(`   - ${file}`);
    console.error(`Wire each via scripts/test-runner.ts (direct or env-gated) per #116.`);
    return 1;
  }
  const total = collectTestFiles().length;
  console.log(`✅ wiring guard: all ${total} test file(s) referenced by npm scripts (#116 poka-yoke)`);
  return 0;
}

function main(): number {
  const args = process.argv.slice(2);
  if (args[0] === "--guard") return guard();
  const file = args[0];
  if (!file || !file.endsWith(".ts")) {
    console.error("usage: tsx scripts/test-runner.ts <test-file.ts> [REQUIRED_ENV_VAR ...] | --guard");
    return 2;
  }
  return runTest(file, args.slice(1));
}

process.exit(main());
