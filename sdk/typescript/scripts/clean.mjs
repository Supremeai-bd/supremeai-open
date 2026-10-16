#!/usr/bin/env node
/** clean.mjs — remove build outputs (kept as a script so `npm run clean`
 * works on every platform without shell built-ins). */
import { rmSync } from "node:fs";
import { join } from "node:path";

for (const dir of ["dist"]) {
  rmSync(join(process.cwd(), dir), { recursive: true, force: true });
  console.log(`clean: removed ${dir}/`);
}
