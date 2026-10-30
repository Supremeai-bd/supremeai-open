/**
 * #1668 — License + provenance gate for the mcp_plugins registry.
 *
 * Mechanical enforcement point for the repo's standing verdict rules
 * (MIT/Apache=accept, GPL=reject, license re-checked at each pin bump) and
 * the S10 doctrine: "Never accept a plugin whose upstream license cannot be
 * verified; ADOPT_IMMEDIATELY verdicts are illegal with an unknown upstream
 * license."
 *
 * The gate runs at CATALOG INGRESS — the plane where third-party code
 * actually enters the trust boundary (marketplace.register_plugin). It is
 * deliberately fail-closed: every rule mismatch yields REJECT with a
 * machine-readable code; only an explicit permissive license verified
 * against a real repository URL passes.
 *
 * Vendor-marker rejection (open-washing anti-pattern, radar R6) takes the
 * mechanical form of the provenance rule: the upstream must be a code-hosting
 * repository URL (github.com/gitlab.com/bitbucket.org, owner/repo shape) —
 * marketing pages, docs sites, and non-https "upstreams" are markers of
 * vendored distribution and are rejected without human judgment.
 */

export type LicenseGateCode =
  | "REJECT_GPL"
  | "REJECT_UNKNOWN_LICENSE"
  | "REJECT_UNRECOGNIZED_LICENSE"
  | "REJECT_NO_UPSTREAM"
  | "REJECT_PROVENANCE"
  | "ACCEPT";

export interface LicenseGateInput {
  /** SPDX license expression of the upstream project, or null when unknown. */
  license: string | null;
  /** Upstream repository URL, or null when not pinned. */
  upstreamUrl: string | null;
}

export interface LicenseGateVerdict {
  verdict: "ACCEPT" | "REJECT";
  code: LicenseGateCode;
  reason: string;
}

/**
 * Permissive allow-list (repo verdict rules). Everything outside this list
 * that is not GPL-family is still REJECTed (fail-closed): adding a new
 * accepted license is a deliberate, auditable code change, not a default.
 */
export const LICENSE_GATE_ACCEPTED: readonly string[] = Object.freeze([
  "MIT",
  "MIT-0",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "ISC",
]);

/** Code-hosting hosts accepted as provenance anchors (repo URLs only). */
export const LICENSE_GATE_REPO_HOSTS: readonly string[] = Object.freeze([
  "github.com",
  "gitlab.com",
  "bitbucket.org",
]);

function isGplFamily(license: string): boolean {
  // Substring test on the uppercased SPDX expression: covers GPL-2.0/3.0
  // (-only/-or-later), LGPL-*, and AGPL-* — the whole copyleft family is
  // rejected by the repo rule. No non-family SPDX ID contains "GPL".
  return license.toUpperCase().includes("GPL");
}

function isPermissiveAccepted(license: string): boolean {
  return LICENSE_GATE_ACCEPTED.some((l) => l === license);
}

/** Repo URL shape: https + code-hosting host + owner/repo (>=2 path segments). */
export function isRepoUrl(upstreamUrl: string): boolean {
  let url: URL;
  try {
    url = new URL(upstreamUrl);
  } catch {
    return false;
  }
  if (url.protocol !== "https:") return false;
  if (!LICENSE_GATE_REPO_HOSTS.includes(url.hostname.toLowerCase())) return false;
  const segments = url.pathname.split("/").filter((s) => s.length > 0);
  return segments.length >= 2;
}

/**
 * Mechanical license + provenance verdict for a plugin's pinned metadata.
 * Order matters: license rules first (S10 emphasis), then provenance.
 */
export function evaluateLicenseProvenance(input: LicenseGateInput): LicenseGateVerdict {
  const license = (input.license ?? "").trim();
  const upstreamUrl = (input.upstreamUrl ?? "").trim();

  if (license.length === 0) {
    return {
      verdict: "REJECT",
      code: "REJECT_UNKNOWN_LICENSE",
      reason: "Upstream license is unknown/unverifiable (S10: never accept a plugin whose upstream license cannot be verified).",
    };
  }
  if (isGplFamily(license)) {
    return {
      verdict: "REJECT",
      code: "REJECT_GPL",
      reason: `License '${license}' is GPL-family (copyleft) — rejected by repo verdict rule (GPL=reject).`,
    };
  }
  if (!isPermissiveAccepted(license)) {
    return {
      verdict: "REJECT",
      code: "REJECT_UNRECOGNIZED_LICENSE",
      reason: `License '${license}' is not on the permissive accept-list (${LICENSE_GATE_ACCEPTED.join(", ")}) — fail-closed.`,
    };
  }
  if (upstreamUrl.length === 0) {
    return {
      verdict: "REJECT",
      code: "REJECT_NO_UPSTREAM",
      reason: "No upstream repository pinned — provenance unverifiable (reject at ingress).",
    };
  }
  if (!isRepoUrl(upstreamUrl)) {
    return {
      verdict: "REJECT",
      code: "REJECT_PROVENANCE",
      reason: `Upstream '${upstreamUrl}' is not a code-hosting repository URL (https + github/gitlab/bitbucket + owner/repo) — vendored/vendor-marketing distribution is rejected.`,
    };
  }

  return {
    verdict: "ACCEPT",
    code: "ACCEPT",
    reason: `License '${license}' is permissive-accepted; upstream repo verified (${upstreamUrl}).`,
  };
}
