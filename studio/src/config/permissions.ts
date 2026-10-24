// SupremeAI — Canonical Role & Permission Contract (single-frontend migration, roadmap Phase 2)
// বাংলা মন্তব্য: এটিই একমাত্র role/permission সোর্স-অব-ট্রুথ কন্ট্রাক্ট।
// নিয়ম: frontend role state কখনোই privilege গ্রহণ করে না — backend RBAC-ই final authority।

/**
 * Canonical application roles.
 * - `user`  : resolved from backend `/api/v1/auth/*` responses (primary_role)
 * - `admin` : resolved ONLY from (a) backend `/api/v1/auth/me` role claim, or
 *             (b) the server-signed admin JWT issued after OTP/TOTP step-up.
 * Never resolved from localStorage role keys, URL, or UI state.
 */
export const ROLES = ['user', 'admin'] as const;
export type Role = (typeof ROLES)[number];

/**
 * Permission strings (backend-enforced; frontend checks are UX only).
 * The backend `/api/v1/auth/me` response may return a `permissions: string[]`
 * array — empty means "no extra permissions resolved yet", NOT "deny everything".
 * Route guards must treat missing permission data as "defer to backend".
 */
export const PERMISSIONS = {
  WORKSPACE_READ: 'workspace.read',
  PROFILE_READ: 'profile.read',
  SETTINGS_READ: 'settings.read',
  BILLING_READ: 'billing.read',
  SKILLS_READ: 'skills.read',
  ADMIN_READ: 'admin.read',
  ADMIN_SECURITY: 'admin.security',
  ADMIN_DEPLOY: 'deployment.trigger',
  ADMIN_USERS: 'admin.users',
  SYSTEM_HEALTH: 'system.health',
} as const;
export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];

/** Type guard for a backend-provided role string. */
export function isRole(value: unknown): value is Role {
  return typeof value === 'string' && (ROLES as readonly string[]).includes(value);
}

/** Normalize an unknown role value (backend drift tolerance) to a canonical Role. */
export function normalizeRole(value: unknown): Role | null {
  if (typeof value !== 'string') return null;
  const v = value.toLowerCase();
  if (v === 'admin' || v === 'god' || v === 'superadmin') return 'admin';
  if (v === 'user' || v === 'viewer' || v === 'operator' || v === 'developer') return 'user';
  return null;
}

/** Pure permission check — defers to backend when no permission data exists. */
export function hasPermission(
  permissions: string[] | null | undefined,
  required: Permission | string
): boolean {
  if (!permissions || permissions.length === 0) return true; // defer to backend
  return permissions.includes(required);
}
