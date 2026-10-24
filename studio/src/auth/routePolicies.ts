// SupremeAI — Route Policies (single-frontend migration, roadmap Phase 4)
// বাংলা মন্তব্য: declarative route metadata — প্রতিটি route-এর জন্য required role,
// permission এবং step-up requirement। এটি frontend UX guard-এর contract;
// আসল authorization সবসময় backend-এ হয় (roadmap §9 "Critical rule")।

import type { Role } from '../config/permissions';

export interface RoutePolicy {
  /** Minimum role required to SEE this route (UX gate; backend re-checks). */
  requiredRole?: Role;
  /** Permission string required (deferred to backend when not resolvable client-side). */
  requiredPermission?: string;
  /**
   * Route requires the admin step-up flow (Firebase → OTP/TOTP → admin JWT).
   * Enforcement lives in AdminShell — this flag documents the requirement
   * and lets guards route users into the step-up UX instead of a deny screen.
   */
  requiresStepUp?: boolean;
}

/**
 * Path-prefix → policy map. Longest-prefix match wins.
 * বাংলা: শুধুমাত্র implemented route-গুলোই এখানে থাকবে — মৃত route নিষিদ্ধ।
 */
export const ROUTE_POLICIES: Record<string, RoutePolicy> = {
  // ── Admin context (step-up enforced inside AdminShell) ──
  '/admin': { requiredRole: 'admin', requiresStepUp: true },

  // ── User context (authenticated user routes) ──
  '/workspace': { requiredRole: 'user' },
  '/integrations': { requiredRole: 'user' },
  '/skills-catalog': { requiredRole: 'user', requiredPermission: 'skills.read' },
  '/billing': { requiredRole: 'user', requiredPermission: 'billing.read' },
  '/profile': { requiredRole: 'user', requiredPermission: 'profile.read' },
  '/projects': { requiredRole: 'user' },
  '/activity': { requiredRole: 'user' },
  '/marketplace': { requiredRole: 'user' },
  '/runs': { requiredRole: 'user' },
  '/usage': { requiredRole: 'user' },
  '/settings': { requiredRole: 'user', requiredPermission: 'settings.read' },
  // Compatibility routes: intentionally not shown in the core user navigation.
  '/architect-tower': { requiredRole: 'user' },
  '/swarm': { requiredRole: 'user' },
  '/evolution-forge': { requiredRole: 'user' },
  '/prompt-library': { requiredRole: 'user' },

  // ── Public / intentionally shared ──
  '/login': {},
  '/register': {},
  '/share': {}, // public by design (share links)
};

/** Longest-prefix match lookup; unknown paths get no extra policy. */
export function getRoutePolicy(pathname: string): RoutePolicy | undefined {
  const matches = Object.keys(ROUTE_POLICIES)
    .filter((prefix) => pathname === prefix || pathname.startsWith(prefix + '/'))
    .sort((a, b) => b.length - a.length);
  return matches.length > 0 ? ROUTE_POLICIES[matches[0]] : undefined;
}

/**
 * Frontend UX decision only. Backend authorization remains authoritative.
 * Unknown routes are allowed here so legacy/deep links can reach their own
 * compatibility route and report server-side authorization failures.
 */
export function canAccessRoute(
  pathname: string,
  role: Role | null | undefined,
  permissions?: string[],
): boolean {
  const policy = getRoutePolicy(pathname);
  if (!policy) return true;
  if (policy.requiredRole && policy.requiredRole !== role) return false;
  if (policy.requiredPermission && permissions && permissions.length > 0) {
    return permissions.includes(policy.requiredPermission);
  }
  return true;
}
