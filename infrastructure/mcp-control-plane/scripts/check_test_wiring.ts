/**
 * Test wiring guard (#116) — poka-yoke against silent test rot.
 *
 * বাংলা মন্তব্য: `test:unit` / `test:tower-ci` হলো হাতে-বানানো allowlist —
 * নতুন বা rename করা test file কোনো npm script-এ না থাকলে সেটা CI-তে কখনোই
 * চলে না এবং নীরবে পচে যায় (#116-এ ৯টি এমন orphan ধরা পড়েছিল)। এই guard:
 *   (১) প্রতিটি root-level `test_*.ts` + `test/` ফোল্ডারের সব `*.test.ts`
 *       ফাইল অন্তত একটি npm script value-তে referenced কিনা — না হলে EXEMPT
 *       map-এ সৎ কারণসহ নথিভুক্ত থাকতে হবে, নইলে fail;
 *   (২) উল্টো দিক: script value-তে `tsx <path>` দিয়ে বলা প্রতিটি test
 *       ফাইল ডিস্কে আসলেই আছে কিনা (rename-এর পরে ভাঙা allowlist ধরে)।
 *
 * Run: npm run test:wiring-guard (also wired into test:unit / test:tower-ci)
 * Failures here mean: wire the file into an npm script, or record an honest
 * EXEMPT entry with reason + issue reference.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import * as path from "node:path";

import { fileURLToPath } from "node:url";

const pkgRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

type ExemptEntry = { reason: string; trackedBy: string };

/**
 * Documented exemptions — every entry MUST carry an honest reason and an
 * issue reference. This map is the "linked to #98 / recorded reason" half of
 * the acceptance criteria; an orphan file with NO entry fails the guard.
 */
const EXEMPT: Record<string, ExemptEntry> = {
  "test_actions.ts": {
    reason: "env-dependent: hardcodes an ad-hoc ../../.env dotenv load (same class as #109); not clean-env safe",
    trackedBy: "#98 (offline-mode routing for env-dependent suites)",
  },
  "test_github.ts": {
    reason: "env-dependent: hardcodes an ad-hoc ../../.env dotenv load (same class as #109); not clean-env safe",
    trackedBy: "#98 (offline-mode routing for env-dependent suites)",
  },
  "test_infisical.ts": {
    reason: "env-dependent: hardcodes an ad-hoc ../../.env dotenv load (same class as #109); not clean-env safe",
    trackedBy: "#98 (offline-mode routing for env-dependent suites)",
  },
  "test_remediation.ts": {
    reason: "env-dependent: hardcodes an ad-hoc ../../.env dotenv load (same class as #109); not clean-env safe",
    trackedBy: "#98 (offline-mode routing for env-dependent suites)",
  },
  "test_memory_sidecar.ts": {
    reason:
      "layout-dependent: hermetic core passes, but the real-fs assertion at line 43 requires backend/memory/mcp_server.py (private monorepo layout — absent in the public checkout), so it fails on supremeai-open main",
    trackedBy: "#2612 sidecar diagnostics; re-home/fix via #98 follow-up",
  },
};

function collectTestFiles(): string[] {
  const files: string[] = [];
  for (const name of readdirSync(pkgRoot)) {
    if (name.startsWith("test_") && name.endsWith(".ts")) files.push(name);
  }
  const testDir = path.join(pkgRoot, "test");
  if (existsSync(testDir) && statSync(testDir).isDirectory()) {
    for (const name of readdirSync(testDir)) {
      if (name.endsWith(".test.ts")) files.push(path.join("test", name));
    }
  }
  return files.sort();
}

function main(): number {
  const pkg = JSON.parse(readFileSync(path.join(pkgRoot, "package.json"), "utf8")) as {
    scripts: Record<string, string>;
  };
  const scriptBlob = Object.values(pkg.scripts ?? {}).join("\n");

  const failures: string[] = [];
  const wired: string[] = [];
  const exempted: string[] = [];

  for (const rel of collectTestFiles()) {
    const base = path.basename(rel);
    if (scriptBlob.includes(rel) || scriptBlob.includes(base)) {
      wired.push(rel);
    } else if (EXEMPT[base]) {
      exempted.push(`${base}  →  ${EXEMPT[base].reason} [tracked: ${EXEMPT[base].trackedBy}]`);
    } else {
      failures.push(
        `${rel}: referenced by NO npm script and NOT in the EXEMPT map — wire it into a script or record an honest exemption (#116)`
      );
    }
  }

  // Reverse check: every `tsx <test path>` reference in scripts must exist.
  for (const [script, value] of Object.entries(pkg.scripts ?? {})) {
    for (const m of value.matchAll(/tsx\s+(\S+\.ts)/g)) {
      const target = m[1];
      if (target.startsWith("test") && !existsSync(path.join(pkgRoot, target))) {
        failures.push(`scripts.${script}: references missing file ${target}`);
      }
    }
  }

  console.log(`#116 wiring guard: ${wired.length} wired, ${exempted.length} documented-exempt, ${failures.length} failures`);
  for (const line of wired) console.log(`  ✓ wired      ${line}`);
  for (const line of exempted) console.log(`  ○ exempt     ${line}`);
  for (const line of failures) console.log(`  ✗ FAILURE    ${line}`);

  if (failures.length > 0) {
    console.error(`\nWiring guard FAILED — new/renamed test suites must not rot silently (#116).`);
    return 1;
  }
  console.log("All test files are wired or honestly exempted.");
  return 0;
}

process.exit(main());
