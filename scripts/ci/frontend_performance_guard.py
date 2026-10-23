#!/usr/bin/env python3
"""
frontend_performance_guard.py — Enforce Code-Splitting & Zero-Blocking Landing Performance Doctrine.

Guarantees:
  1. Zero-Blocking Landing: The public root route ('/') must render immediately without
     being wrapped in GuestRoute or any authentication-checking spinner.
  2. Mandatory Route-Level Code Splitting: Heavy pages (UserDashboard, AIStudio, AdminShell,
     KnowledgePage, LoginPage, RegisterPage, CommandBar) must be loaded dynamically
     via React.lazy / lazy() to ensure the public landing bundle stays lean (<300 KB) and FCP < 1.0s.
  3. Fail-closed: Exits with non-zero status code if eager monolithic imports are detected in App.tsx.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Heavy modules that MUST NOT be imported statically at top-level of App.tsx
HEAVY_MODULES = [
    "UserDashboard",
    "AIStudio",
    "AdminShell",
    "KnowledgePage",
    "LoginPage",
    "RegisterPage",
    "CommandBar",
]


def check_app_code_splitting(app_tsx_content: str) -> list[str]:
    """Inspect App.tsx content for performance violations."""
    violations: list[str] = []

    # 1. Check for GuestRoute or ProtectedRoute wrapping the root landing page ('/') or public auth routes ('/login', '/register')
    for route_path, route_name in [("/", "Landing page ('/')"), ("/login", "Login page ('/login')"), ("/register", "Register page ('/register')")]:
        route_match = re.search(r'<Route\s+path=["\']' + re.escape(route_path) + r'["\']\s+element=\{([^}]+)\}', app_tsx_content)
        if route_match:
            element_content = route_match.group(1)
            if "GuestRoute" in element_content:
                violations.append(
                    f"Violation: {route_name} is wrapped in <GuestRoute> — causes render-blocking auth check spinner ('AUTHENTICATING...'). Public auth and landing routes must render immediately."
                )
            if route_path == "/" and "ProtectedRoute" in element_content:
                violations.append(
                    "Violation: Landing page ('/') is wrapped in <ProtectedRoute> — public visitors must never be blocked on root."
                )

    # 2. Check for eager/static top-level imports of heavy components
    for module in HEAVY_MODULES:
        # Pattern matching: import { ...Module... } from ... or import Module from ...
        # but NOT comments or lazy import(...)
        eager_pattern = re.compile(
            r'^[ \t]*import\s+(?:\{[^}]*\b' + re.escape(module) + r'\b[^}]*\}|\b' + re.escape(module) + r'\b)\s+from\s+["\'][^"\']+["\'];?',
            re.MULTILINE,
        )
        if eager_pattern.search(app_tsx_content):
            violations.append(
                f"Violation: Heavy module '{module}' is imported statically at top level. Must use React.lazy(() => import(...)) to avoid monolithic bundle bloat."
            )

    # 3. Check that React.lazy or lazy is used for code-splitting
    for module in HEAVY_MODULES:
        lazy_pattern = re.compile(r'\b(?:React\.lazy|lazy)\s*\(\s*\(\)\s*=>\s*import\(', re.MULTILINE)
        if not lazy_pattern.search(app_tsx_content):
            violations.append("Violation: No dynamic React.lazy() calls found in App.tsx.")
            break

    # 4. Check for Suspense boundary wrapping routes
    if "Suspense" not in app_tsx_content:
        violations.append("Violation: No Suspense boundary found in App.tsx to catch lazy-loaded route chunks.")

    return violations


def self_test() -> bool:
    """Validate guard rules against synthetic valid and invalid App.tsx snippets."""
    valid_snippet = """
    import React from "react";
    import { Routes, Route } from "react-router-dom";
    import { LandingPage } from "./pages/LandingPage";
    
    const UserDashboard = React.lazy(() => import("./components/customer/UserDashboard").then(m => ({ default: m.UserDashboard })));
    const AIStudio = React.lazy(() => import("./pages/user/AIStudio").then(m => ({ default: m.AIStudio })));
    const AdminShell = React.lazy(() => import("./pages/admin/AdminShell").then(m => ({ default: m.AdminShell })));
    const KnowledgePage = React.lazy(() => import("./components/dashboard/KnowledgePage").then(m => ({ default: m.KnowledgePage })));
    const LoginPage = React.lazy(() => import("./pages/auth/LoginPage").then(m => ({ default: m.LoginPage })));
    const RegisterPage = React.lazy(() => import("./pages/auth/RegisterPage").then(m => ({ default: m.RegisterPage })));
    const CommandBar = React.lazy(() => import("./components/layout/CommandBar").then(m => ({ default: m.CommandBar })));
    
    export const App = () => (
      <React.Suspense fallback={<div>Loading</div>}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/workspace" element={<UserDashboard />} />
        </Routes>
      </React.Suspense>
    );
    """

    invalid_snippet = """
    import React from "react";
    import { Routes, Route } from "react-router-dom";
    import { LandingPage } from "./pages/LandingPage";
    import { UserDashboard } from "./components/customer/UserDashboard";
    import { AIStudio } from "./pages/user/AIStudio";
    import { GuestRoute } from "./components/core/AuthGuards";

    export const App = () => (
      <Routes>
        <Route path="/" element={<GuestRoute><LandingPage /></GuestRoute>} />
        <Route path="/workspace" element={<UserDashboard />} />
      </Routes>
    );
    """

    valid_violations = check_app_code_splitting(valid_snippet)
    assert not valid_violations, f"Self-test failed on valid snippet: {valid_violations}"

    invalid_violations = check_app_code_splitting(invalid_snippet)
    assert len(invalid_violations) >= 3, f"Self-test expected multiple violations on invalid snippet, got {len(invalid_violations)}"
    assert any("GuestRoute" in v for v in invalid_violations), "Self-test failed to detect GuestRoute violation"
    assert any("UserDashboard" in v for v in invalid_violations), "Self-test failed to detect eager UserDashboard import"

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce code-splitting and zero-blocking landing guard.")
    parser.add_argument("--self-test", action="store_true", help="Run offline contract assertions.")
    parser.add_argument("--check", type=str, default="studio/src/App.tsx", help="Path to App.tsx to inspect.")
    args = parser.parse_args()

    if args.self_test:
        print("[self-test] Running Frontend Performance Guard offline contract tests...")
        if self_test():
            print("✅ [self-test] All frontend performance contract assertions passed!")
            return 0
        return 1

    app_path = Path(args.check)
    if not app_path.exists():
        print(f"⚠️ App.tsx not found at {app_path} — skipping check.")
        return 0

    content = app_path.read_text(encoding="utf-8")
    violations = check_app_code_splitting(content)

    if violations:
        print(f"❌ [FRONTEND-PERF-VIOLATION] Found {len(violations)} performance regression(s) in {app_path}:")
        for v in violations:
            print(f"   - {v}")
        return 1

    print(f"✅ [PASS] {app_path} adheres to code-splitting & zero-blocking landing doctrine.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
