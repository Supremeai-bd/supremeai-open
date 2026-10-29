/**
 * Annotations structural floor — the deploy-independent guard for the MCP
 * ToolAnnotations contract (radar lanes R71 #2586 -> R72 #2608/#2618 -> R73 #2627).
 *
 * What it asserts, over every STATIC tool registration in src/tools/*.ts and
 * src/dynamic/*.ts (string-literal-named `server.tool(...)` / `(server as any).tool(...)`
 * / `server.registerTool(...)` blocks, comments stripped):
 *   1. FULL COVERAGE — every static registration block carries an annotations object
 *      (`readOnlyHint` present). Unannotated names are listed in the failure output.
 *   2. SHRINK GUARD — the static-block count never drops below MIN_STATIC_BLOCKS.
 *      Bump it in the same PR when a tool is added (#2178 same-PR bump convention);
 *      the count only ratchets, it never silently shrinks.
 *
 * Dynamic surfaces are intentionally out of scope and excluded by construction:
 * loop/identifier-name registrations (e.g. memory.tools.ts's helper branches,
 * src/dynamic/tool.registry.ts's data-driven `server.tool(tool.name, ...)`) have no
 * static name literal to census; the live-plane census (tools/list) covers them.
 * The two units (repo-side blocks vs live tools) are reported separately, never mixed
 * (two-census caveat, R73 scout receipt).
 *
 * History note (disclosed in the R73 landing): this file was committed EMPTY by the
 * R72 wave (origin/main blob e69de29b..., 0 bytes) — its npm wiring
 * (`test:annotations-floor`) passed trivially on an empty module. This implementation
 * replaces the hollow file; the 79/121 metric it inherited existed only in the PR
 * description, never in-tree.
 *
 * Run: tsx test_annotations_floor.ts  (wired as `test:annotations-floor` in test:unit)
 */
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SCAN_DIRS = ["src/tools", "src/dynamic"];
/** Shrink guard: 122 static blocks at the R73 landing (c40, 2026-10-29). Bump same-PR. */
const MIN_STATIC_BLOCKS = 122;

function stripComments(src: string): string {
  let out = "";
  let i = 0;
  const n = src.length;
  while (i < n) {
    const c = src[i];
    if (c === '"' || c === "'" || c === "`") {
      const q = c;
      out += c;
      i++;
      while (i < n) {
        if (src[i] === "\\") {
          out += src.slice(i, i + 2);
          i += 2;
          continue;
        }
        out += src[i];
        if (src[i] === q) {
          i++;
          break;
        }
        i++;
      }
      continue;
    }
    if (c === "/" && src[i + 1] === "/") {
      const j = src.indexOf("\n", i);
      i = j === -1 ? n : j;
      continue;
    }
    if (c === "/" && src[i + 1] === "*") {
      const j = src.indexOf("*/", i);
      i = j === -1 ? n : j + 2;
      continue;
    }
    out += c;
    i++;
  }
  return out;
}

const REGEX_START =
  /(?:server|\(server as any\))\.(?:tool|registerTool)\(\s*\n?\s*(?=["'])/g;

interface Block {
  file: string;
  name: string;
  annotated: boolean;
}

const blocks: Block[] = [];

for (const dir of SCAN_DIRS) {
  const abs = join(ROOT, dir);
  if (!existsSync(abs)) continue;
  for (const fn of readdirSync(abs).sort()) {
    if (!fn.endsWith(".ts")) continue;
    const rel = `${dir}/${fn}`;
    const src = stripComments(readFileSync(join(abs, fn), "utf-8"));
    const starts: Array<{ idx: number; m: RegExpExecArray }> = [];
    REGEX_START.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = REGEX_START.exec(src)) !== null) {
      starts.push({ idx: m.index, m });
    }
    for (let k = 0; k < starts.length; k++) {
      const { idx, m: mm } = starts[k];
      const end = k + 1 < starts.length ? starts[k + 1].idx : Math.min(idx + 4000, src.length);
      const window = src.slice(idx, end);
      const nameMatch = /["']([^"']+)["']/.exec(window);
      blocks.push({
        file: rel,
        name: nameMatch ? nameMatch[1] : "<unnamed>",
        annotated: window.includes("readOnlyHint"),
      });
      void mm;
    }
  }
}

const unannotated = blocks.filter((b) => !b.annotated);

console.log(`[annotations-floor] static blocks scanned: ${blocks.length}`);
console.log(`[annotations-floor] annotated: ${blocks.length - unannotated.length}`);
console.log(`[annotations-floor] unannotated: ${unannotated.length}`);

let failed = false;
if (unannotated.length > 0) {
  failed = true;
  console.error("[annotations-floor] FAIL — unannotated static registrations:");
  for (const b of unannotated) {
    console.error(`  - ${b.file} :: ${b.name}`);
  }
}
if (blocks.length < MIN_STATIC_BLOCKS) {
  failed = true;
  console.error(
    `[annotations-floor] FAIL — static block count ${blocks.length} < floor ${MIN_STATIC_BLOCKS} (shrink guard; bump MIN_STATIC_BLOCKS in the same PR that adds tools)`
  );
}
if (failed) {
  process.exit(1);
}
console.log(
  `[annotations-floor] PASS — full coverage ${blocks.length}/${blocks.length}, floor ${MIN_STATIC_BLOCKS} held`
);
