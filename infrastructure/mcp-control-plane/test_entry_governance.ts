#!/usr/bin/env tsx
/**
 * test_entry_governance.ts — #2391 root-cause drift guard (U6 Zero-Recurrence).
 *
 * বাংলা: #1843/#2391 ক্লাসের মূল কারণ ছিল "দুই এন্ট্রি ড্রিফট" — মেইন এন্ট্রি
 * `src/index.ts` (package.json main → dist/index.js) পুরনো কপি থেকে যায়, আর
 * প্রতিটি landed production fix (#1452 resource arg-order, #2454 registerTool
 * governance) শুধু মৃত sibling `src/index.fixed.ts`-এ যায়। ফলে deployable
 * build-এ ১১টি registerTool-রেজিস্টার্ড টুল (github_list_secrets সহ) RBAC গেট
 * ছাড়াই রেজিস্টার হত — যা লাইভে anonymous execution হিসেবে প্রমাণিত (#1843,
 * #2391 V-1 matrix)। এই গার্ড তিনটি স্তরে সেই শ্রেণিকে যান্ত্রিকভাবে আটকে রাখে:
 *
 *   1. ENTRY PARITY: src/index.ts ও src/index.fixed.ts বাইট-সমান হতে বাধ্য —
 *      ভবিষ্যতে কেউ এক ফাইলে fix করে অন্যটি ভুলে গেলে CI লাল হবে।
 *   2. GOVERNANCE PRESENCE: এন্ট্রিতে দুই রেজিস্ট্রেশন সারফেসই (server.tool
 *      override + registerTool override) governedHandler/toolAccessErrorAsync
 *      দিয়ে মোড়া থাকতে হবে — "one choke point, no competing wrappers"।
 *   3. DENY MATRIX (execution-plane unit pin, #2391 V-1): classifyToolCapability
 *      + canAccessCapability দিয়ে প্রমাণ — #1843-র পাঁচ over-exposure টুল ও
 *      secret-family (render_get_env_vars সহ) public_viewer-কে DENY করে, আর
 *      self-serve সেট এখনো reachable।
 *
 * Import নিরাপত্তা: src/index.ts module-load-এই main() বুট করে, তাই এই টেস্ট
 * এন্ট্রিকে import করে না — static source assertions + pure policy imports।
 * (একই কারণে test_bridge_onboarding / test_c29_dual_emission শিম-শেপ mirror
 * করে; parity assertion নিশ্চিত করে mirror সবসময় সত্য থাকবে।)
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { canAccessCapability, classifyToolCapability } from "./src/policy/mcp-access.js";

const PKG_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)));
const ENTRY = readFileSync(path.join(PKG_ROOT, "src", "index.ts"), "utf8");
const SIBLING = readFileSync(path.join(PKG_ROOT, "src", "index.fixed.ts"), "utf8");
const PKG_JSON = JSON.parse(readFileSync(path.join(PKG_ROOT, "package.json"), "utf8")) as {
  main?: string;
  scripts?: Record<string, string>;
};

// ── 1) ENTRY PARITY — the #1452/#2454 "fix the sibling, forget the entry" pin ──
assert.equal(
  ENTRY,
  SIBLING,
  "entry drift detected: src/index.ts and src/index.fixed.ts diverged — landed fixes must " +
    "be applied to BOTH entries (or the pair collapsed into one). This exact divergence is " +
    "the #2391/#1843 root cause: the deployed build compiled from src/index.ts while every " +
    "production fix landed only in index.fixed.ts.",
);

// ── 2) GOVERNANCE PRESENCE — both registration surfaces wrapped ──
assert.match(
  ENTRY,
  /\(server as any\)\.tool = /,
  "server.tool override missing — legacy registration surface is ungoverned",
);
assert.match(
  ENTRY,
  /\(server as any\)\.registerTool = /,
  "registerTool override missing — the SDK-blessed surface is ungoverned; every " +
    "outputSchema/structuredContent tool would bypass RBAC, rate limit, payload " +
    "validation, timeout and truncation (#2423/#2391 class)",
);
assert.match(
  ENTRY,
  /toolAccessErrorAsync\(sanitizedName\)/,
  "governedHandler must call toolAccessErrorAsync (central default-deny RBAC gate, #695)",
);
// Both overrides must route through the ONE governedHandler factory.
const governedFactory = ENTRY.match(/const governedHandler = /);
assert.ok(governedFactory, "governedHandler factory missing — wrappers must share one choke point");
const factoryPos = governedFactory!.index!;
assert.ok(
  ENTRY.indexOf("(server as any).tool = ") > factoryPos &&
    ENTRY.indexOf("(server as any).registerTool = ") > factoryPos,
  "both surface overrides must be defined AFTER the governedHandler factory they route through",
);

// Entry truth: package.json must keep running the governed entry.
assert.equal(PKG_JSON.main, "dist/index.js", "package.json main must stay dist/index.js (built from src/index.ts)");
assert.equal(
  PKG_JSON.scripts?.start,
  "node dist/index.js",
  "package.json start must run node dist/index.js — if the entry moves, collapse the pair first",
);

// ── 3) DENY MATRIX — #1843 five + secret family denied to public_viewer ──
const publicContext = {
  mode: "public_viewer" as const,
  role: "viewer" as const,
  authenticated: false,
  tenantBound: false,
  scopes: [],
};

// The five tools witnessed executing anonymously live (#1843, re-verified by
// #2391 V-1) plus the render secret family (#2391's REGRESSED positive control).
const MUST_DENY = [
  "github_list_secrets",
  "supabase_read_table",
  "redis_read_key",
  "memory_read_graph",
  "tenant_list",
  "render_get_env_vars",
  "render_get_env_var_keys",
];
for (const tool of MUST_DENY) {
  const capability = classifyToolCapability(tool);
  assert.equal(
    canAccessCapability(publicContext, capability),
    false,
    `deny matrix violated: '${tool}' must be denied to anonymous public_viewer ` +
      `(classified ${capability.access}/${capability.dataClassification}) — this is the ` +
      "#1843/#2391 zero-credential execution class",
  );
}

// Positive control: the documented self-serve set stays reachable (#1843 ADMIN
// RECIPE step 2 — the deny matrix must not over-close the public front door).
const MUST_ALLOW = [
  "status",
  "system_health",
  "system_summary",
  "bridge_work",
  "bridge_work_queue",
  "bridge_read_feedback",
  "work_claim",
  "bridge_submit_patch",
  "supabase_schema_inspect",
  "agent_status",
];
for (const tool of MUST_ALLOW) {
  const capability = classifyToolCapability(tool);
  assert.equal(
    canAccessCapability(publicContext, capability),
    true,
    `self-serve matrix violated: '${tool}' must stay reachable anonymously ` +
      `(classified ${capability.access}/${capability.dataClassification}) — the ADMIN ` +
      "RECIPE expects this set reachable after every redeploy",
  );
}

console.log("entry governance tests passed (parity + dual-surface choke point + #2391 deny matrix)");
