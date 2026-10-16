#!/usr/bin/env node
/**
 * mark-outputs.mjs — dual-package hazard guards (issue #338 AC2).
 *
 * After the two tsc passes, stamp each emitted tree with the correct module
 * type so Node's resolution is unambiguous no matter how consumers configure
 * their own "type" field:
 *   dist/esm/package.json  -> { "type": "module" }
 *   dist/cjs/package.json  -> { "type": "commonjs" }
 * Fail-closed: refuses to run if either build output is missing.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const esmDir = join(process.cwd(), "dist", "esm");
const cjsDir = join(process.cwd(), "dist", "cjs");

for (const [dir, kind, entry] of [
  [esmDir, "module", "./index.js"],
  [cjsDir, "commonjs", "./index.js"],
]) {
  if (!existsSync(join(dir, "index.js")) || !existsSync(join(dir, "index.d.ts"))) {
    console.error(`mark-outputs: ${dir} missing index.js/index.d.ts — build first (fail-closed)`);
    process.exit(1);
  }
  mkdirSync(dir, { recursive: true });
  writeFileSync(
    join(dir, "package.json"),
    JSON.stringify({ type: kind, main: entry, types: "./index.d.ts" }, null, 2) + "\n",
  );
  console.log(`mark-outputs: stamped ${dir} as ${kind}`);
}

// Sanity: declaration maps must ship next to declarations (AC2 "complete
// .d.ts declaration maps" — d.ts without .d.ts.map would break go-to-source).
for (const dir of [esmDir, cjsDir]) {
  if (!existsSync(join(dir, "index.d.ts.map"))) {
    console.error(`mark-outputs: ${dir}/index.d.ts.map missing — declarationMap not emitted`);
    process.exit(1);
  }
}
console.log("mark-outputs: declaration maps verified");
