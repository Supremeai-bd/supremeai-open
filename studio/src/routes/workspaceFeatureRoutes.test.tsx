import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { workspaceFeatureRoutes } from './workspaceFeatureRoutes';
import { AuthStatus, useAuthStore } from '../store/authStore';

// #1521 Phase 0 last-mile (2026-10-28): /research and /scheduled-tasks route
// accessibility contract, exercised against the REAL route table.
// App.routes.test.tsx mocks this module to [] (its own public-funnel smoke
// scope), so the two backend-ready engines have no accessibility proof there —
// this file is that proof: guests are redirected to /login by the real
// ProtectedRoute, authenticated users reach the real panels.

vi.mock('../components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => (
    <main>{children}</main>
  ),
}));

// authStore imports updateTokenCache from this module; the panels fetch
// history/task lists on mount. Default: every network read fails — panels must
// degrade to their error state (never crash the route).
vi.mock('../services/apiClient', () => ({
  apiClient: {
    get: vi.fn().mockRejectedValue(new Error('offline test')),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
  updateTokenCache: vi.fn(),
}));

vi.mock('../utils/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
}));

vi.mock('../services/tokenStorage', () => ({
  getAdminToken: vi.fn(() => null),
  getUserToken: vi.fn(() => null),
  setUserToken: vi.fn(),
  clearUserToken: vi.fn(),
}));

// Panels call globalShowToastRef.current(...) unguarded in their error paths —
// the mock stays callable so a failed history fetch cannot nuke the route.
vi.mock('../contexts/ToastContext', () => ({
  globalShowToastRef: { current: vi.fn() },
}));

function renderRoutesAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        {workspaceFeatureRoutes.map((r, i) => (
          <Route key={i} path={r.path!} element={r.element} />
        ))}
      </Routes>
    </MemoryRouter>,
  );
}

describe('Phase 0 engine routes (#1521): guest vs authenticated accessibility', () => {
  it.each([
    ['/research', 'research'],
    ['/scheduled-tasks', 'scheduled tasks'],
  ])(
    'guest visiting %s is redirected to /login (ProtectedRoute honesty)',
    async (path) => {
      useAuthStore.setState({ status: AuthStatus.UNINITIALIZED });
      renderRoutesAt(path);
      // initialize() finds no token (and the mocked /auth/me cookie probe
      // fails) → LOGGED_OUT → <Navigate to="/login" replace />.
      await waitFor(() =>
        expect(screen.getByText('Login page')).toBeInTheDocument(),
      );
    },
  );

  it.each([
    ['/research', 'Deep Research'],
    ['/scheduled-tasks', 'Scheduled Tasks'],
  ])(
    'authenticated user reaches the real %s panel',
    async (path, heading) => {
      useAuthStore.setState({
        status: AuthStatus.LOGGED_IN,
        role: 'user',
        permissions: [],
      });
      renderRoutesAt(path);
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: heading }),
        ).toBeInTheDocument(),
      );
    },
  );
});
