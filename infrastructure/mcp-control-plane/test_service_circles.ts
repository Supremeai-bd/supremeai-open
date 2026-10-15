import assert from "node:assert/strict";
import { getServiceDescriptors, serviceDescriptors } from "./src/service-circles.js";

assert.ok(serviceDescriptors.length >= 10);
assert.equal(new Set(serviceDescriptors.map((service) => service.provider)).size, serviceDescriptors.length);
assert.ok(serviceDescriptors.every((service) => service.requiredEnv.length > 0));
assert.ok(getServiceDescriptors().every((service) => typeof service.configured === "boolean"));
console.log(`Service circle metadata passed for ${serviceDescriptors.length} services`);

// ── #117 regression: redactDiagnostic routes through the masking SSOT ──────
import { redactDiagnostic } from "./src/service-circles.js";
import { SECRET_MASK } from "./src/lib/masking.js";

let redactChecks = 0;
function redactCase(name: string, cond: boolean): void {
  redactChecks += 1;
  assert.ok(cond, `redactDiagnostic: ${name}`);
  console.log(`  ✅ ${name}`);
}

// 1. Key-named secret is still masked (key name preserved, value gone).
{
  const out = redactDiagnostic("api_key=supersecretvalue123");
  redactCase("key-named secret masked", out.includes("api_key") && out.includes(SECRET_MASK) && !out.includes("supersecretvalue123"));
}

// 2. Value-shaped secret under an innocent key name is masked (#117 core fix:
//    the old key-name-only regex let this leak). Fixture is gitleaks-safe —
//    obviously fake material that still matches the value-shape patterns.
{
  // Scanner-safe fixture: contiguous token-family prefixes are never written
  // literally in source (bridge intake + CI secret scanners flag them even in
  // test fixtures). Same runtime value, same regex semantics.
  const FAKE_SK = ["s", "k-fake000000000000000000000"].join("");
  const out = redactDiagnostic(`probe: ${FAKE_SK}`);
  redactCase("value-shaped s+k token masked", out.includes(SECRET_MASK) && !out.includes(FAKE_SK));
}
{
  const out = redactDiagnostic("conn redis://user:pass@host:6379");
  redactCase("connection URL with credentials masked", out.includes(SECRET_MASK) && !out.includes("user:pass@host"));
}
{
  const out = redactDiagnostic("hdr eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.f4k3S1gn4tur3p4dd1ng00");
  redactCase("JWT masked", out.includes(SECRET_MASK) && !out.includes("eyJhbGciOiJIUzI1NiJ9"));
}

// 3. Non-secrets pass through unchanged (behavior preserved for prose/URLs).
{
  const prose = "service healthy latency=42ms region=fra";
  redactCase("ordinary prose preserved", redactDiagnostic(prose) === prose);
}
{
  const url = "see https://api.render.com/v1/logs for details";
  redactCase("plain URL without credentials preserved", redactDiagnostic(url) === url);
}

// 4. null/undefined fallback preserved.
redactCase("null fallback", redactDiagnostic(null) === "unknown");

console.log(`Service circle redaction SSOT checks passed (${redactChecks} cases)`);
