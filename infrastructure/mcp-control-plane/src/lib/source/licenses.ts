/**
 * License Compliance Checker — открытые исходники нельзя слепо копировать.
 * 3-tier policy: AUTO_ACCEPT / REVIEW / AUTO_REJECT (copyleft).
 */

export type LicenseTier = "accept" | "review" | "reject";

export interface LicenseVerdict {
  allowed: boolean;
  tier: LicenseTier;
  license: string;
  reason: string;
}

const AUTO_ACCEPT = [
  "mit", "apache-2.0", "apache", "bsd-2-clause", "bsd-3-clause", "bsd",
  "isc", "unlicense", "cc0", "cc0-1.0", "wtfpl", "zlib", "python-2.0",
  "0bsd", "bsl-1.0", "mpl", "mpl-2.0",
];

const AUTO_REJECT = [
  "gpl", "gpl-2.0", "gpl-3.0", "lgpl", "agpl", "agpl-3.0",
  "sspl", "sspl-1.0", "proprietary", "closed", "commercial", "other",
  "unknown", "no-license", "unlicensed",
];

const REVIEW_TIER = ["epl", "epl-2.0", "cddl", "cddl-1.0", "opl"];

function normalize(license: string): string {
  return (license ?? "").trim().toLowerCase().replace(/\s+/g, "-");
}

export function checkLicense(license: string | undefined, repoUrl = ""): LicenseVerdict {
  const raw = license?.trim() || "";
  const normalized = normalize(raw);

  if (!raw || raw.toLowerCase() === "none") {
    return {
      allowed: false,
      tier: "reject",
      license: "unknown/no-license",
      reason: `Repo ${repoUrl} declares no recognized license — do NOT copy code without checking the repository LICENSE file.`,
    };
  }

  if (AUTO_REJECT.some((l) => normalized.includes(l))) {
    return {
      allowed: false,
      tier: "reject",
      license: raw,
      reason: `Copyleft/restricted license '${raw}' — cannot inject this code into our codebase. Use it as a reference/adaptation only, with attribution.`,
    };
  }

  if (REVIEW_TIER.some((l) => normalized.includes(l))) {
    return {
      allowed: false,
      tier: "review",
      license: raw,
      reason: `Weak copyleft license '${raw}' — requires manual review before use.`,
    };
  }

  return {
    allowed: true,
    tier: "accept",
    license: raw || "unknown",
    reason: `Permissive license '${raw}' — safe to study, adapt, and reference.`,
  };
}

/** Короткое имя лицензии из GitHub API → наш checker. */
export function normalizeGithubLicense(spdxId: string | undefined): LicenseVerdict {
  return checkLicense(spdxId);
}