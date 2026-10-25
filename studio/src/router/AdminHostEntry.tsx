import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { isAdminHost } from "../utils/portalHosts";

// On any designated admin portal host (configured via VITE_ADMIN_HOSTS)
// every non-admin route — including "/" — must land in the admin console
// instead of the user-facing app.
//
// /login stays reachable because the /admin guard chain (ProtectedRoute →
// RoleGuard) redirects unauthenticated visitors there, and the admin login
// form itself lives on that page. After a successful admin login any stray
// user-route navigation (e.g. GuestRoute's "/workspace" bounce) is sent back
// to /admin by the same check.
//
// On any other host this component is a transparent pass-through, so the user
// portal behavior is byte-for-byte unchanged.
export function AdminHostEntry({ children }: { children: ReactNode }) {
  if (!isAdminHost()) {
    return <>{children}</>;
  }
  const { pathname } = window.location;
  if (pathname === "/login" || pathname.startsWith("/admin")) {
    return <>{children}</>;
  }
  return <Navigate to="/admin" replace />;
}

export default AdminHostEntry;
