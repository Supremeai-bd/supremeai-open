// SupremeAI — Canonical Identity Helpers (single-frontend migration, roadmap Phase 2/4)
// বাংলা মন্তব্য: role কখনোই client-computed privilege নয়। এই helpers শুধু trusted
// state পড়ে: (a) authStore-এ backend থেকে resolve হওয়া role, এবং (b) backend-ই
// issue করা server-signed admin JWT-র role claim (OTP/TOTP step-up-এর পরে)।
// এগুলো শুধু UX/guard decision — প্রতিটি privileged API call আবার backend-এ
// authorize হয়। URL বা localStorage role key কখনোই এখানে ব্যবহৃত হয় না।

import { normalizeRole, type Role } from '../config/permissions';
import { getAdminToken } from '../services/tokenStorage';

/** Get the resolved canonical application role (fallback to 'user'). */
export function getCanonicalRole(): Role {
  return getAdminJwtRole() || 'user';
}

/** Storage key of the server-signed admin JWT issued after OTP/TOTP step-up. */
export const ADMIN_JWT_KEY = 'supreme_admin_jwt';

interface AdminJwtClaims {
  role?: unknown;
  exp?: unknown;
  [key: string]: unknown;
}

/**
 * Decode the payload of the server-signed admin JWT (no verification —
 * verification happens server-side on every privileged API call; here the
 * claim is only used to decide which UX context to offer).
 */
export function readAdminJwtClaims(): AdminJwtClaims | null {
  if (typeof window === 'undefined') return null;
  try {
    const token =
      getAdminToken() ||
      sessionStorage.getItem(ADMIN_JWT_KEY) ||
      localStorage.getItem(ADMIN_JWT_KEY);
    if (!token) return null;
    const part = token.split('.')[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/');
    const json = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const parsed = JSON.parse(json) as AdminJwtClaims;
    return parsed && typeof parsed === 'object' ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * Role claim from the server-signed admin JWT, if present and unexpired.
 * Returns a normalized canonical Role or null.
 */
export function getAdminJwtRole(): Role | null {
  const claims = readAdminJwtClaims();
  if (!claims) return null;
  // বাংলা: exp থাকলে মেয়াদোত্তীর্ণ JWT-র claim কোনো অধিকার দেখায় না।
  if (typeof claims.exp === 'number' && claims.exp * 1000 < Date.now()) return null;
  return normalizeRole(claims.role);
}

/**
 * Is this identity authorized for the Admin context at all?
 */
export function canAccessAdminContext(): boolean {
  return getAdminJwtRole() === 'admin';
}

/**
 * Runtime landing path per roadmap §6.3:
 *   Guest                → /login
 *   Authenticated admin  → /admin (configured admin landing context)
 *   Authenticated user   → /workspace
 */
export function resolveLandingPath(isAuthenticated: boolean): string {
  if (!isAuthenticated) return '/login';
  return canAccessAdminContext() ? '/admin' : '/workspace';
}
