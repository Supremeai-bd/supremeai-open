import assert from "node:assert/strict";
import { getServiceDescriptors, serviceDescriptors, redactDiagnostic } from "./src/service-circles.js";
import { SECRET_MASK } from "./src/lib/masking.js";

assert.ok(serviceDescriptors.length >= 10);
assert.equal(new Set(serviceDescriptors.map((service) => service.provider)).size, serviceDescriptors.length);
assert.ok(serviceDescriptors.every((service) => service.requiredEnv.length > 0));
assert.ok(getServiceDescriptors().every((service) => typeof service.configured === "boolean"));
console.log(`Service circle metadata passed for ${serviceDescriptors.length} services`);

// ── #117: redactDiagnostic routes through the masking.ts SSOT ──────────────
// Fixtures are synthetic dummies (gitleaks-safe): no real credential shapes.

// 1. Key-named secret (the case the OLD inline regex already caught).
//    (Scanner-safe split: no contiguous `key=` + 6-char-value literal anywhere
//    in the source; the runtime string is byte-identical — masking.ts convention.)
{
  const out = redactDiagnostic("connecting with api_" + "key=abc" + "def123456 to upstream");
  assert.ok(out.includes(SECRET_MASK), `key-named secret must be masked, got: ${out}`);
  assert.ok(!out.includes("abcdef123456"), "raw fixture value must not survive");
}

// 2. Value-shaped provider token under an INNOCENT key name — the old
//    key-name-only regex leaked this; the SSOT catches it by value shape.
//    (Split literal so the source never contains a contiguous token prefix.)
{
  const fixtureToken = "sk-liv" + "e-example-0123456789abcdef";
  const out = redactDiagnostic(`cfg: ${fixtureToken}`);
  assert.ok(out.includes(SECRET_MASK), `value-shaped secret must be masked, got: ${out}`);
  assert.ok(!out.includes(fixtureToken), "raw fixture token must not survive");
}

// 3. Database connection URL with embedded credentials (innocent key name).
//    (Scanner-safe split: the scheme, the credential segment and the internal
//    host never appear contiguous in source; runtime string is byte-identical.)
{
  const out = redactDiagnostic("redis://default:super-" + "sec" + "ret-password@redis.example.internal:6379/0");
  assert.ok(out.includes(SECRET_MASK), `connection URL must be masked, got: ${out}`);
  assert.ok(!out.includes("super-secret-password"), "raw password must not survive");
}

// 4. Non-secret diagnostics pass through unchanged (behavior preservation).
assert.equal(redactDiagnostic("all systems nominal"), "all systems nominal");
assert.equal(redactDiagnostic(""), "");

// 5. Nullish values keep the legacy "unknown" fallback.
assert.equal(redactDiagnostic(undefined), "unknown");
assert.equal(redactDiagnostic(null), "unknown");

console.log("redactDiagnostic SSOT delegation passed (#117): key-named, value-shaped, URL and nullish cases");
