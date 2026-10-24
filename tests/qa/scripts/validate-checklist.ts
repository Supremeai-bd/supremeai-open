/**
 * validate-checklist.ts — schema gate for qa/checklist/{guest,customer,admin,security}.yaml
 *
 * Implements the Part-1 schema from
 * docs/plans/features/qa_engine_auto_checking_implementation_plan.md:
 *   required fields: id, area, role, name, description, route, severity,
 *                    automated, action, assert, manual_note
 *   - id: ^G-\d{2}$ (guest), ^C-\d{2}$ (customer), ^A-\d{2}$ (admin), ^S-\d{2}$ (security);
 *     prefix must match the file's role (G->guest, C->customer, A->admin, S->security)
 *   - ids unique ACROSS all four files
 *   - severity: P0 | P1 | P2 | P3 (each file must contain >= 1 P0/P1)
 *   - automated: boolean
 *   - action: non-empty array of single-key string maps (e.g. `- navigate: /`)
 *   - assert: array of single-key string maps (or plain strings)
 *   - manual_note: non-empty string for manual items; for automated items either
 *     null OR a deferral reason (used by test.fixme blocks pending Part-9 data-testid work)
 *
 * Runs under bun (TS executed natively):  bun qa/scripts/validate-checklist.ts
 * Exit codes: 0 = valid, 1 = schema violations (messages printed).
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import YAML from "yaml";

type ChecklistItem = Record<string, unknown>;

const ROLE_FILES: Array<{ file: string; prefix: string; role: string }> = [
  { file: "guest.yaml", prefix: "G", role: "guest" },
  { file: "customer.yaml", prefix: "C", role: "customer" },
  { file: "admin.yaml", prefix: "A", role: "admin" },
  { file: "security.yaml", prefix: "S", role: "security" },
];

const REQUIRED_FIELDS = [
  "id",
  "area",
  "role",
  "name",
  "description",
  "route",
  "severity",
  "automated",
  "action",
  "assert",
  "manual_note",
] as const;

const SEVERITIES = new Set(["P0", "P1", "P2", "P3"]);

const repoRoot = process.cwd();
const checklistDir = join(repoRoot, "qa", "checklist");

const errors: string[] = [];
const seenIds = new Map<string, string>(); // id -> file (uniqueness across files)
const fileStats = new Map<
  string,
  { total: number; automated: number; manual: number; P0: number; P1: number; P2: number; P3: number }
>();

function isSingleKeyStringMap(value: unknown): value is Record<string, string> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = Object.keys(value as Record<string, unknown>);
  if (keys.length !== 1) return false;
  const v = (value as Record<string, unknown>)[keys[0]];
  return typeof v === "string" && v.trim().length > 0;
}

function assertShapeOk(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((entry) => typeof entry === "string" || isSingleKeyStringMap(entry))
  );
}

if (!existsSync(checklistDir)) {
  console.error(`Missing checklist directory: ${checklistDir}`);
  process.exit(1);
}

let itemCount = 0;
let automatedCount = 0;
let manualCount = 0;

for (const { file, prefix, role } of ROLE_FILES) {
  const path = join(checklistDir, file);
  if (!existsSync(path)) {
    errors.push(`${file}: file is missing (required by the QA engine scaffold)`);
    fileStats.set(file, { total: 0, automated: 0, manual: 0, P0: 0, P1: 0, P2: 0, P3: 0 });
    continue;
  }

  let parsed: unknown;
  try {
    parsed = YAML.parse(readFileSync(path, "utf8"));
  } catch (err) {
    errors.push(`${file}: invalid YAML (${(err as Error).message})`);
    fileStats.set(file, { total: 0, automated: 0, manual: 0, P0: 0, P1: 0, P2: 0, P3: 0 });
    continue;
  }

  const stats = { total: 0, automated: 0, manual: 0, P0: 0, P1: 0, P2: 0, P3: 0 };
  fileStats.set(file, stats);

  if (!Array.isArray(parsed)) {
    errors.push(`${file}: top-level value must be an array of items`);
    continue;
  }

  parsed.forEach((raw, index) => {
    const at = `${file}[${index}]`;
    itemCount += 1;

    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      errors.push(`${at}: item must be a mapping`);
      return;
    }
    const it = raw as ChecklistItem;
    stats.total += 1;

    for (const field of REQUIRED_FIELDS) {
      if (!(field in it)) errors.push(`${at}: missing required field '${field}'`);
    }

    // id: prefix + two digits, prefix matches file/role, unique across ALL files
    const id = it.id;
    const idPattern = new RegExp(`^${prefix}-\\d{2}$`);
    if (typeof id !== "string" || !idPattern.test(id)) {
      errors.push(`${at}: id must match ${prefix}-NN (got ${JSON.stringify(id)})`);
    } else if (seenIds.has(id)) {
      errors.push(`${at}: duplicate id ${id} (already used in ${seenIds.get(id)})`);
    } else {
      seenIds.set(id, file);
    }

    if (it.role !== role) {
      errors.push(`${at}: role must be '${role}' for ${file} (got ${JSON.stringify(it.role)})`);
    }

    if (typeof it.area !== "string" || it.area.trim() === "") {
      errors.push(`${at}: area must be a non-empty string`);
    }
    if (typeof it.name !== "string" || it.name.trim() === "") {
      errors.push(`${at}: name must be a non-empty string`);
    }
    if (typeof it.description !== "string" || it.description.trim() === "") {
      errors.push(`${at}: description must be a non-empty string`);
    }
    if (typeof it.route !== "string" || !(it.route === "*" || it.route.startsWith("/"))) {
      errors.push(`${at}: route must start with '/' or be '*' (got ${JSON.stringify(it.route)})`);
    }

    if (typeof it.severity !== "string" || !SEVERITIES.has(it.severity)) {
      errors.push(`${at}: severity must be one of P0|P1|P2|P3 (got ${JSON.stringify(it.severity)})`);
    } else {
      stats[it.severity as "P0" | "P1" | "P2" | "P3"] += 1;
    }

    if (typeof it.automated !== "boolean") {
      errors.push(`${at}: automated must be a boolean`);
    } else if (it.automated) {
      stats.automated += 1;
    } else {
      stats.manual += 1;
    }

    if (!assertShapeOk(it.action)) {
      errors.push(
        `${at}: action must be a non-empty list of single-key string maps (e.g. '- navigate: /')`,
      );
    }
    if (!assertShapeOk(it.assert)) {
      errors.push(`${at}: assert must be a non-empty list of single-key string maps or strings`);
    }

    const manualNote = it.manual_note;
    const manualNoteOk =
      manualNote === null || (typeof manualNote === "string" && manualNote.trim().length > 0);
    if (!manualNoteOk) {
      errors.push(`${at}: manual_note must be null or a non-empty string`);
    }

    if (it.automated === true) {
      automatedCount += 1;
    } else if (it.automated === false) {
      manualCount += 1;
      if (typeof manualNote !== "string" || manualNote.trim() === "") {
        errors.push(`${at}: manual items require a manual_note explaining why it stays manual`);
      }
    }
  });

  if (stats.P0 + stats.P1 === 0) {
    errors.push(`${file}: must contain at least one P0 or P1 item (severity mix rule)`);
  }
}

if (itemCount !== 40) {
  errors.push(`expected 40 checklist items across the 4 role files (found ${itemCount})`);
}

if (errors.length > 0) {
  console.error(`QA checklist validation FAILED with ${errors.length} violation(s):\n`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log("QA checklist schema valid (Part-1).");
console.log("");
console.log("File            Items  Automated  Manual   P0  P1  P2  P3");
console.log("------------------------------------------------------------");
for (const { file } of ROLE_FILES) {
  const s = fileStats.get(file)!;
  console.log(
    `${file.padEnd(15)} ${String(s.total).padStart(5)}  ${String(s.automated).padStart(9)}  ${String(s.manual).padStart(6)}   ` +
      `${String(s.P0).padStart(2)}  ${String(s.P1).padStart(2)}  ${String(s.P2).padStart(2)}  ${String(s.P3).padStart(2)}`,
  );
}
console.log("------------------------------------------------------------");
console.log(
  `TOTAL           ${String(itemCount).padStart(5)}  ${String(automatedCount).padStart(9)}  ${String(manualCount).padStart(6)}`,
);
console.log("\nAll 40 items passed schema validation; ids unique across files.");
