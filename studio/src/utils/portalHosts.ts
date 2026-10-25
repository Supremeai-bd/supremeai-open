// Portal identity is derived from the hostname so the single build stays
// deploy-agnostic: no separate admin bundle to drift, no hosting-config-only
// rewrite that bypasses SPA client routing. VITE_ADMIN_HOSTS (comma-separated)
// lets operators add custom admin domains without a code change.

const BUILT_IN_ADMIN_HOSTS: readonly string[] = [];

function extraAdminHosts(): string[] {
  try {
    const raw = (import.meta.env?.VITE_ADMIN_HOSTS as string | undefined) ?? "";
    return raw
      .split(",")
      .map((h) => h.trim())
      .filter(Boolean);
  } catch {
    // import.meta.env unavailable outside Vite — defensive, never throw.
    return [];
  }
}

/** Hosts that must render the admin console (see #1468). */
export const ADMIN_HOSTS: readonly string[] = [...BUILT_IN_ADMIN_HOSTS, ...extraAdminHosts()];

/**
 * True when the app is being served from an admin portal host.
 * SSR/Node-safe: without `window` only an explicitly passed hostname can match.
 */
export function isAdminHost(hostname?: string): boolean {
  const host = hostname ?? (typeof window === "undefined" ? "" : window.location.hostname);
  return ADMIN_HOSTS.includes(host);
}
