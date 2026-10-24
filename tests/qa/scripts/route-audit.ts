/**
 * route-audit.ts — Part 4 of the QA engine plan, adapted for this repo.
 *
 * Direction of the check (starter scope): every `route:` declared in the
 * qa/checklist/*.yaml files MUST exist in the REAL frontend route graph.
 * The frontend router is frontend/src/App.tsx (react-router <Route path="...">)
 * plus the Tier-S route table frontend/src/routes/workspaceFeatureRoutes.tsx
 * (path: '...' entries). Routes are extracted by regex over those two files —
 * no AST dependency needed.
 *
 * Matching rules:
 *   - exact string match (e.g. `/workspace/live`)
 *   - frontend param routes (`/share/:shareId`) match checklist routes that use
 *     the same `:param` shape OR any single-segment value
 *   - frontend wildcard routes (`/admin/*`) match any checklist route under
 *     that prefix (including the bare prefix)
 *   - the frontend catch-all (`*`) matches anything unknown (404 page tests)
 *
 * Additionally prints an advisory list of frontend routes that no checklist
 * item references yet (coverage-gap radar — plan's "untested routes" report,
 * advisory while the checklist is still 40/300+ items).
 *
 * Exit codes: 0 = every checklist route verified real, 1 = unknown route(s).
 * Runs under bun:  bun qa/scripts/route-audit.ts
 */
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import YAML from "yaml";

const repoRoot = process.cwd();
const checklistDir = join(repoRoot, "qa", "checklist");
const routerSources = [
  join(repoRoot, "frontend", "src", "App.tsx"),
  join(repoRoot, "frontend", "src", "routes", "workspaceFeatureRoutes.tsx"),
];

// ── 1. Extract the frontend route set ────────────────────────────────────────
const frontendRoutes = new Set<string>();
for (const src of routerSources) {
  if (!existsSync(src)) {
    console.error(`Router source missing: ${src}`);
    process.exit(1);
  }
  const text = readFileSync(src, "utf8");
  // <Route path="/login" ...>  and  <Route key={...} path={r.path!} ...> are
  // handled by the first pattern; RouteObject tables use `path: '/share/:shareId'`.
  for (const m of text.matchAll(/path=["']([^"']+)["']/g)) frontendRoutes.add(m[1]);
  for (const m of text.matchAll(/path:\s*["']([^"']+)["']/g)) frontendRoutes.add(m[1]);
}

// ── 2. Load checklist routes ─────────────────────────────────────────────────
const checklistFiles = ["guest.yaml", "customer.yaml", "admin.yaml", "security.yaml"];
type Entry = { id: string; route: string; file: string };
const entries: Entry[] = [];
for (const file of checklistFiles) {
  const path = join(checklistDir, file);
  if (!existsSync(path)) {
    console.error(`Checklist missing: ${path}`);
    process.exit(1);
  }
  const items = YAML.parse(readFileSync(path, "utf8")) as Array<Record<string, unknown>>;
  for (const item of items) {
    entries.push({ id: String(item.id), route: String(item.route), file });
  }
}

// ── 3. Matching ──────────────────────────────────────────────────────────────
function routeToRegex(frontendRoute: string): RegExp {
  // The "*" catch-all is only matched via exact equality in
  // checklistMatchesFrontend — this regex intentionally never matches.
  if (frontendRoute === "*") return /^^$/;
  // "/admin/*" style prefix wildcards match the bare prefix and anything under
  // it; ":param" segments match any single segment.
  let base = frontendRoute;
  let tail = "";
  if (base.endsWith("/*")) {
    base = base.slice(0, -2);
    tail = "(?:/.*)?";
  }
  const segs = base
    .replace(/^\//, "")
    .split("/")
    .map((seg) =>
      seg.startsWith(":")
        ? "[^/]+"
        : seg.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    );
  return new RegExp("^/" + segs.join("/") + tail + "$");
}

function checklistMatchesFrontend(route: string): string | null {
  for (const fr of frontendRoutes) {
    if (fr === route) return fr; // exact match (covers checklist route "*")
    if (fr === "*") continue; // the 404 catch-all only satisfies the literal "*" route
    const re = routeToRegex(fr);
    if (re.test(route)) return fr;
  }
  return null;
}

// ── 4. Report ────────────────────────────────────────────────────────────────
console.log("SupremeAI QA route audit");
console.log(`Frontend route sources: ${routerSources.map((p) => p.replace(repoRoot + "/", "")).join(", ")}`);
console.log(`Frontend routes found:  ${frontendRoutes.size}`);
console.log("");
console.log("ID     Route                  Verdict");
console.log("---------------------------------------------");
let unknown = 0;
const coveredFrontend = new Set<string>();
for (const e of entries) {
  const matched = checklistMatchesFrontend(e.route);
  if (matched) {
    coveredFrontend.add(matched);
    console.log(`${e.id.padEnd(6)} ${e.route.padEnd(22)} OK (frontend: ${matched})`);
  } else {
    unknown += 1;
    console.log(`${e.id.padEnd(6)} ${e.route.padEnd(22)} UNKNOWN — not in frontend router`);
  }
}
console.log("---------------------------------------------");

// Advisory: frontend routes no checklist item touches yet (starter scope is
// 40 of 300+ items, so this is a radar, not a gate).
const advisory = [...frontendRoutes]
  .filter((r) => !coveredFrontend.has(r) && r !== "*")
  .sort();
if (advisory.length > 0) {
  console.log("");
  console.log(`⚠️  Advisory — ${advisory.length} frontend route(s) not referenced by any checklist item yet:`);
  for (const r of advisory) console.log(`    ${r}`);
  console.log("    (expected while the checklist is at starter scope — extend qa/checklist/ in later passes)");
}

if (unknown > 0) {
  console.error(`\n❌ ${unknown} checklist route(s) do not exist in the frontend router. Fix qa/checklist/*.yaml or the router.`);
  process.exit(1);
}
console.log(`\n✅ All ${entries.length} checklist routes verified against the real frontend route graph.`);
