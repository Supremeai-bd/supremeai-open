/**
 * coverage-matrix.ts — Part 5 of the QA engine plan (starter-scope adaptation).
 *
 * Maps checklist ids -> Playwright spec coverage by scanning every
 * qa/playwright .spec.ts file for:
 *   - id markers:  `// qa-id: G-01`  (the contract between checklist and spec)
 *   - test titles: /^(G|C|A|S)-\d{2}:/  (plan naming convention "G-23: ...")
 *   - fixme status: a test.fixme( block following the marker until the next marker
 *
 * Output: per-role matrix (total / automated / manual-by-design / covered / real /
 * fixme / uncovered) + overall % of the checklist with automated test coverage.
 *
 * Advisory only: ALWAYS exits 0. Uncovered ids are printed so the next passes
 * know what to implement.
 *
 * Runs under bun:  bun qa/scripts/coverage-matrix.ts
 */
import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join } from "node:path";
import YAML from "yaml";

const repoRoot = process.cwd();
const checklistDir = join(repoRoot, "qa", "checklist");
const playwrightDir = join(repoRoot, "qa", "playwright");

const ROLE_FILES = [
  { file: "guest.yaml", label: "Guest" },
  { file: "customer.yaml", label: "Customer" },
  { file: "admin.yaml", label: "Admin" },
  { file: "security.yaml", label: "Security" },
];

// ── load checklist ───────────────────────────────────────────────────────────
type Item = { id: string; name: string; automated: boolean; severity: string };
const checklist = new Map<string, Item>();
for (const { file } of ROLE_FILES) {
  const items = YAML.parse(readFileSync(join(checklistDir, file), "utf8")) as Array<
    Record<string, unknown>
  >;
  for (const i of items) {
    checklist.set(String(i.id), {
      id: String(i.id),
      name: String(i.name),
      automated: i.automated === true,
      severity: String(i.severity),
    });
  }
}

// ── collect spec files ───────────────────────────────────────────────────────
function walkSpecs(dir: string): string[] {
  const out: string[] = [];
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walkSpecs(p));
    else if (name.endsWith(".spec.ts")) out.push(p);
  }
  return out;
}
const specFiles = walkSpecs(playwrightDir);

// ── scan spec files for qa-id markers + fixme ────────────────────────────────
type Coverage = { file: string; kind: "real" | "fixme" };
const covered = new Map<string, Coverage>();
const ID_MARKER = /\/\/\s*qa-id:\s*((?:G|C|A|S)-\d{2})/g;
const TITLE_ID = /\b(?:test(?:\.fixme)?(?:\.skip)?(?:\.describe)?)\s*\(\s*['"`]((?:G|C|A|S)-\d{2})/;

for (const file of specFiles) {
  const text = readFileSync(file, "utf8");
  // marker spans: from each qa-id marker to the next qa-id marker / EOF
  const markers = [...text.matchAll(ID_MARKER)].map((m) => ({
    id: m[1],
    start: m.index ?? 0,
  }));
  const rel = file.replace(repoRoot + "/", "");
  for (let i = 0; i < markers.length; i++) {
    const { id, start } = markers[i];
    const end = i + 1 < markers.length ? markers[i + 1].start : text.length;
    const block = text.slice(start, end);
    const kind: "real" | "fixme" = /\btest\.fixme\s*\(/.test(block) ? "fixme" : "real";
    if (!covered.has(id)) covered.set(id, { file: rel, kind });
  }
  // fallback: ids picked up from test titles ("G-01: ...") when no marker exists
  for (const line of text.split("\n")) {
    const m = line.match(TITLE_ID);
    if (m && !covered.has(m[1])) {
      covered.set(m[1], { file: rel, kind: /\btest\.fixme\s*\(/.test(line) ? "fixme" : "real" });
    }
  }
}

// ── print matrix ─────────────────────────────────────────────────────────────
console.log("SupremeAI QA coverage matrix (starter scope)");
console.log("");
console.log(
  "Role      Items  Automated  Manual  Covered  Real  Fixme  Uncovered(auto)  AutoCoverage%",
);
console.log("------------------------------------------------------------------------------------");

let totalItems = 0;
let totalAutomated = 0;
let totalCoveredReal = 0;
const uncoveredById: string[] = [];

for (const { file, label } of ROLE_FILES) {
  const items = YAML.parse(readFileSync(join(checklistDir, file), "utf8")) as Array<
    Record<string, unknown>
  >;
  const ids = items.map((i) => String(i.id));
  const automated = ids.filter((id) => checklist.get(id)?.automated).length;
  const manual = ids.length - automated;
  const coveredIds = ids.filter((id) => covered.has(id));
  const real = coveredIds.filter((id) => covered.get(id)!.kind === "real").length;
  const fixme = coveredIds.length - real;
  const uncovered = ids.filter((id) => !covered.has(id) && checklist.get(id)?.automated);
  const autoCoverage = automated === 0 ? 0 : Math.round(((real + fixme) / automated) * 100);

  totalItems += ids.length;
  totalAutomated += automated;
  totalCoveredReal += real;
  for (const id of uncovered) uncoveredById.push(id);

  console.log(
    `${label.padEnd(9)} ${String(ids.length).padStart(5)}  ${String(automated).padStart(9)}  ${String(
      manual,
    ).padStart(6)}  ${String(coveredIds.length).padStart(7)}  ${String(real).padStart(4)}  ${String(
      fixme,
    ).padStart(5)}  ${String(uncovered.length).padStart(9)}  ${String(autoCoverage).padStart(13)}%`,
  );
}
const totalFixme = [...covered.values()].filter((c) => c.kind === "fixme").length;
console.log(
  "------------------------------------------------------------------------------------",
);
console.log(
  `TOTAL     ${String(totalItems).padStart(5)}  ${String(totalAutomated).padStart(9)}  ${String(
    totalItems - totalAutomated,
  ).padStart(6)}  ${String(covered.size).padStart(7)}  ${String(totalCoveredReal).padStart(4)}  ${String(
    totalFixme,
  ).padStart(5)}  ${String(uncoveredById.length).padStart(9)}`,
);
console.log("");
console.log(
  `Automated checklist items with a Playwright test (real): ${totalCoveredReal}/${totalAutomated} ` +
    `(${Math.round((totalCoveredReal / Math.max(totalAutomated, 1)) * 100)}% of automated items)`,
);
console.log(
  `Deferred via test.fixme (selector/credential blockers documented in checklist): ${totalFixme}`,
);
console.log(
  `Manual by design (no test expected): ${totalItems - totalAutomated}`,
);

if (uncoveredById.length > 0) {
  console.log("");
  console.log("Uncovered automated ids (need specs in qa/playwright/; manual-by-design ids excluded):");
  for (const id of uncoveredById) {
    const it = checklist.get(id)!;
    console.log(`  ${id}  [${it.severity}] ${it.name}`);
  }
}

// fixme detail — honesty over theater
const fixmeEntries = [...covered.entries()].filter(([, c]) => c.kind === "fixme");
if (fixmeEntries.length > 0) {
  console.log("");
  console.log("test.fixme entries (real implementation pending):");
  for (const [id, c] of fixmeEntries) console.log(`  ${id} -> ${c.file}`);
}

console.log("");
console.log("Coverage matrix is advisory — exit 0 by design (Part 5).");
process.exit(0);
