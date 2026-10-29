import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { App } from './App';

vi.mock('./hooks/useServerStream', () => ({
  useServerStream: () => ({ streamStatus: 'connected' }),
}));

vi.mock('./components/core/AuthGuards', () => ({
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  GuestRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  useAuthStatus: () => ({ isChecking: false, isAuthenticated: false }),
  AuthLoadingSpinner: () => <div>Loading</div>,
}));

vi.mock('./services/apiClient', () => ({
  getRawToken: () => null,
  AUTH_CHANGED_EVENT: 'AUTH_CHANGED_EVENT',
  apiClient: {
    get: vi.fn().mockResolvedValue({ items: [], keys: [], total: 0 }),
    post: vi.fn().mockResolvedValue({}),
    put: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue({}),
  },
}));

vi.mock('./services/chatService', () => ({
  getAethelResponse: vi.fn().mockResolvedValue(''),
}));

vi.mock('./contexts/useTheme', () => ({
  useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }),
}));

vi.mock('./utils/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8000',
  getBackendUrl: () => 'http://localhost:8000',
  getWebSocketBaseUrl: () => 'ws://localhost:8000',
  isAdminContextPath: () => false,
}));

vi.mock('./components/layout/CommandBar', () => ({ CommandBar: () => null }));
vi.mock('./components/core/GlobalConfigInitializer', () => ({
  GlobalConfigInitializer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./providers/ThemeSyncProvider', () => ({
  ThemeSyncProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./i18n/I18nProvider', () => ({
  TranslationProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./components/admin/DashboardErrorBoundary', () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('./components/layout/WorkspaceLayout', () => ({
  WorkspaceLayout: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
}));
vi.mock('./pages/PublicPages', () => ({
  default: () => <div>Guest chat</div>,
  GuestChat: () => <div>Guest chat</div>,
  PublicLayout: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PublicHeader: () => null,
  ModelsPage: () => <div>Models page</div>,
  PublicInfoPage: ({ kind }: { kind: string }) => <div>{kind} page</div>,
  PricingPage: () => <div>Pricing page</div>,
  // Issue #1521/#1523/#1524 follow-up: /features /docs route to their own page
  // components — distinct mocks keep the smoke tests honest.
  FeaturesPage: () => <div>/features page</div>,
  DocsPage: () => <div>/docs page</div>,
}));
// Refs #876 (router restoration): the Cosmic public funnel is now a distinct
// page at / — mocked here so the route smoke suite stays hermetic.
vi.mock('./pages/LandingPage', () => ({
  LandingPage: () => <div>Landing page</div>,
}));
vi.mock('./pages/OurStoryPage', () => ({
  OurStoryPage: () => <div>Our story page</div>,
}));
vi.mock('./pages/ErrorPage', () => ({ default: ({ code }: { code: number }) => <div> Error {code}</div> }));
vi.mock('./pages/auth/LoginPage', () => ({ LoginPage: () => <div>Login page</div> }));
vi.mock('./pages/auth/RegisterPage', () => ({ RegisterPage: () => <div>Register page</div> }));
vi.mock('./pages/user/UserDashboard', () => ({ UserDashboard: () => <div>Dashboard</div> }));
vi.mock('./components/customer/UserDashboard', () => ({ UserDashboard: () => <div>Dashboard</div> }));
vi.mock('./pages/user/AIStudio', () => ({ AIStudio: () => <div>AI Studio</div> }));
vi.mock('./routes/workspaceFeatureRoutes', () => ({ workspaceFeatureRoutes: [] }));
vi.mock('./auth/identity', () => ({ resolveLandingPath: () => '/login' }));

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

describe('application route smoke tests', () => {
  it.each([
    // Refs #876: '/' is the Cosmic landing page; guest chat lives at '/chat'.
    ['/', 'Landing page'],
    ['/chat', 'Guest chat'],
    ['/features', '/features page'],
    ['/models', 'Models page'],
    ['/pricing', 'Pricing page'],
    ['/docs', '/docs page'],
    ['/about', 'Our story page'],
    ['/contact', 'contact page'],
    ['/playground', 'ইন্টারেক্টিভ মাল্টি-ডিভাইস লাইভ কোড স্যান্ডবক্স'],
    ['/login', 'Login page'],
    ['/register', 'Register page'],
  ])('renders the public route %s', async (path, expectedText) => {
    renderRoute(path);
    await waitFor(() => expect(screen.getByText(expectedText)).toBeInTheDocument());
  });

  it('renders the not-found page for an unknown route', async () => {
    renderRoute('/does-not-exist');
    await waitFor(() => expect(screen.getByText(/Error 404/)).toBeInTheDocument());
  });

  // বাংলা মন্তব্য: Task-12 ghost activation — KnowledgePage আগে কোনো route-এ
  // mounted ছিল না; এখন /knowledge route প্রকৃত backend search/seed endpoint-এর
  // সাথে wire করা হয়েছে। এই smoke test প্রমাণ করে route-টি সত্যিই reachable।
  it('renders the knowledge route with real backend wiring (Task-12)', async () => {
    renderRoute('/knowledge');
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Knowledge' })).toBeInTheDocument(),
    );
    expect(screen.getByTestId('seed-knowledge-btn')).toBeInTheDocument();
    expect(screen.getByTestId('knowledge-search-input')).toBeInTheDocument();
  });

  // Refs #876 regression guard: the router must NEVER regress to a marketing-only
  // subset again — with mocked guards, /workspace must render WorkspaceLayout.
  it('keeps the authenticated workspace route mounted (P0 #876)', async () => {
    const { container } = renderRoute('/workspace');
    await waitFor(() => expect(container.querySelector('main')).toBeInTheDocument());
  });
});
