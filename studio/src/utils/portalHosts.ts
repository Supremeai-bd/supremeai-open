// Issue #1468 (CRITICAL): the admin Firebase Hosting target
// (supremeai-admin.web.app) serves the SAME SPA build as the user portal —
// visiting the admin URL used to render the user-facing chat app (Chat /
// Models / Features / Pricing nav) instead of the admin console.
//
// Portal identity is derived from the hostname so the single build stays
// deploy-agnostic: no separate admin bundle to drift, no hosting-config-only
// rewrite that bypasses SPA client routing. VITE_ADMIN_HOSTS (comma-separated)
// lets operators add custom admin domains without a code change.

const BUILT_IN_ADMIN_HOSTS: readonly string[] = ["supremeai-admin.web.app"];

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
