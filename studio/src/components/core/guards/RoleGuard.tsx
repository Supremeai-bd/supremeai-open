// SupremeAI — Role & Permission Guards (single-frontend migration, roadmap Phase 4)
// বাংলা মন্তব্য: Guard hierarchy (roadmap §9):
//   GuestRoute → ProtectedRoute → RoleGuard → PermissionGuard → (StepUp: AdminShell) → Page
// গুরুত্বপূর্ণ: frontend guard শুধু UX। Backend RBAC-ই প্রকৃত authorization boundary।
// এই guard কখনো privilege দেয় না — শুধু unauthorized UI কে available functionality
// হিসেবে দেখানো বন্ধ করে (roadmap Rule 14)।

import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ShieldAlert } from 'lucide-react';
import { useAuthStatus, AuthLoadingSpinner } from '../AuthGuards';
import { useAuthStore } from '../../../store/authStore';
import { hasPermission, type Permission } from '../../../config/permissions';
import { canAccessAdminContext } from '../../../auth/identity';
import { getRoutePolicy } from '../../../auth/routePolicies';

/** বাংলা: Access Denied — fake available functionality নয়, স্পষ্ট প্রত্যাখ্যান UX। */
export const AccessDenied: React.FC<{ reason: string }> = ({ reason }) => (
  <div className="flex h-screen w-full items-center justify-center bg-slate-950 text-slate-100 font-sans">
    <div className="w-[420px] p-8 rounded-2xl bg-white/5 border border-red-500/30 text-center flex flex-col items-center gap-4">
      <ShieldAlert className="w-14 h-14 text-red-500" />
      <h1 className="text-2xl font-semibold">Access Denied</h1>
      <p className="text-sm text-gray-400">{reason}</p>
      <Link
        to="/workspace"
        className="mt-2 px-6 py-2 bg-white/5 hover:bg-white/10 text-slate-200 font-medium rounded-lg transition-colors border border-white/10"
      >
        Back to Workspace
      </Link>
    </div>
  </div>
);

export interface RoleGuardProps {
  children: React.ReactNode;
  /** Minimum role (UX gate). Omit to allow any authenticated identity. */
  requiredRole?: 'user' | 'admin';
  /** Human-readable denial explanation override. */
  deniedReason?: string;
}

/**
 * বাংলা: RoleGuard — authenticated identity-র trusted role দেখে UX-level gate করে।
 * - role data না থাকলে (backend এখনো role পাঠায়নি) user-route-এ deny করা হয় না —
 *   backend-ই decide করবে (defer-to-backend principle)।
 * - admin route-এর জন্য server-signed admin JWT claim অথবা authStore.role==='admin' লাগবে।
 */
export const RoleGuard = ({ children, requiredRole, deniedReason }: RoleGuardProps) => {
  const { isChecking, isAuthenticated } = useAuthStatus();
  const location = useLocation();

  if (isChecking) return <AuthLoadingSpinner />;
  if (!isAuthenticated) return <>{children}</>; // ProtectedRoute already handles unauthenticated redirect

  if (requiredRole === 'admin') {
    // বাংলা: step-up required route — authorized identity না হলেই deny।
    // যদি identity admin হয় কিন্তু এখনো step-up না করে থাকে, AdminShell নিজেই
    // OTP/TOTP flow দেখাবে (step-up preserved — roadmap §7.3)।
    if (!canAccessAdminContext()) {
      return (
        <AccessDenied
          reason={deniedReason || 'Your identity is not authorized for the Admin context. Admin access requires an administrator account with two-factor verification.'}
        />
      );
    }
    return <>{children}</>;
  }

  if (requiredRole === 'user') {
    // বাংলা: user route — সব authenticated identity ঢুকতে পারে (admin-ও user feature
    // ব্যবহার করতে পারে, roadmap security matrix: "Admin → /workspace → allowed")।
    // role শুধু deny করা হয় যদি backend স্পষ্টভাবে ভিন্ন role দিয়ে থাকে এবং
    // requiredRole==='admin' হয় — user routes-এ কখনো deny নয়।
    return <>{children}</>;
  }

  // requiredRole না থাকলে route policy থেকে fallback নেওয়া হয়
  const policy = getRoutePolicy(location.pathname);
  if (policy?.requiredRole === 'admin' && !canAccessAdminContext()) {
    return <AccessDenied reason={deniedReason || 'Admin authorization required.'} />;
  }

  return <>{children}</>;
};

export interface PermissionGuardProps {
  children: React.ReactNode;
  requiredPermission: Permission | string;
  deniedReason?: string;
}

/**
 * বাংলা: PermissionGuard — backend-provided permissions array দেখে UX-level gate।
 * permissions data না থাকলে defer-to-backend (deny করা হয় না) — কারণ empty array-র
 * মানে "এখনো resolve হয়নি", "অনুমতি নেই" নয়।
 */
export const PermissionGuard = ({ children, requiredPermission, deniedReason }: PermissionGuardProps) => {
  const permissions = useAuthStore((s) => s.permissions);

  if (!hasPermission(permissions, requiredPermission)) {
    return (
      <AccessDenied
        reason={deniedReason || `You are missing the "${requiredPermission}" permission required for this area.`}
      />
    );
  }
  return <>{children}</>;
};
