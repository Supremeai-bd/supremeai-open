/**
 * SupremeAI Studio — Production Application Router & Public Landing Page
 *
 * ROOT-CAUSE FIX (Refs #876 / bridge-20261023-frontend-router-restore):
 * the Cosmic landing PR REPLACED this router with a marketing-only subset,
 * silently removing /login + /register (every auth button dead in production,
 * the `*` fallback bounced users back to `/`), unmounting the authenticated
 * app (UserDashboard, workspaceFeatureRoutes), providers (ThemeSync, i18n),
 * CommandBar, and routing /admin to OperatorCockpit instead of AdminShell.
 *
 * This file restores the FULL application router — the contract encoded in
 * App.routes.test.tsx. Lesson learned: landing implementations must EXTEND
 * this router, never replace it — always run App.routes.test.tsx before
 * landing a public-funnel change.
 */
import React from "react";
import { Routes, Route } from "react-router-dom";
import "./styles/tokens.css";
import { GlobalConfigInitializer } from "./components/core/GlobalConfigInitializer";
import { setupGlobalFetchInterceptor } from "./utils/apiInterceptor";

// বাংলা: hardened auth guards (Refs #876) — ProtectedRoute/GuestRoute
import { ProtectedRoute, GuestRoute } from "./components/core/AuthGuards";
import { RoleGuard } from "./components/core/guards/RoleGuard";

// Providers + global chrome (ThemeSync, i18n, CommandBar)
import { ThemeSyncProvider } from "./providers/ThemeSyncProvider";
import { TranslationProvider } from "./i18n/I18nProvider";
import { WorkspaceLayout } from "./components/layout/WorkspaceLayout";

// Public funnel (Cosmic landing lives at /; guest chat at /chat) — kept eager for instant FCP (<1s)
import { LandingPage } from "./pages/LandingPage";
import { OurStoryPage } from "./pages/OurStoryPage";
import {
  GuestChat,
  PublicLayout,
  PublicHeader,
  ModelsPage,
  PublicInfoPage,
  PricingPage,
  FeaturesPage,
  DocsPage,
} from "./pages/PublicPages";

import ErrorBoundary from "./components/admin/DashboardErrorBoundary";
import { workspaceFeatureRoutes } from "./routes/workspaceFeatureRoutes";

// 🚀 Performance Architecture: Code-splitting heavy routes with React.lazy
// Prevents monolithic bundle bloat and keeps public landing FCP < 1s
const LoginPage = React.lazy(() =>
  import("./pages/auth/LoginPage").then((m) => ({ default: m.LoginPage }))
);
const RegisterPage = React.lazy(() =>
  import("./pages/auth/RegisterPage").then((m) => ({ default: m.RegisterPage }))
);
// OWNER DECISION (2026-10-24, 3-tab progressive disclosure): UserDashboard is
// no longer the landing route — /workspace now renders the Chat tab (AI
// Studio). The component file is kept per the no-delete doctrine.
const AIStudio = React.lazy(() =>
  import("./pages/user/AIStudio").then((m) => ({ default: m.AIStudio }))
);
const AdminShell = React.lazy(() =>
  import("./pages/admin/AdminShell").then((m) => ({ default: m.AdminShell }))
);
const JarvisAdminConsolePage = React.lazy(() =>
  import("./pages/admin/JarvisAdminConsolePage").then((m) => ({ default: m.JarvisAdminConsolePage }))
);
const KnowledgePage = React.lazy(() =>
  import("./components/dashboard/KnowledgePage").then((m) => ({ default: m.KnowledgePage }))
);
const ErrorPage = React.lazy(() => import("./pages/ErrorPage"));
const DevToolsPage = React.lazy(() => import("./pages/DevToolsPage"));
const AcademyHubPage = React.lazy(() => import("./pages/AcademyHubPage"));
const CommandBar = React.lazy(() =>
  import("./components/layout/CommandBar").then((m) => ({ default: m.CommandBar }))
);

// Lazy-loaded operator telemetry widgets (isolated from public landing bundle)
const SatelliteMatrix = React.lazy(() =>
  import("./components/SatelliteMatrix").then((m) => ({ default: m.SatelliteMatrix }))
);
const ConsensusWidget = React.lazy(() =>
  import("./components/ConsensusWidget").then((m) => ({ default: m.ConsensusWidget }))
);
const EmergencyConsole = React.lazy(() =>
  import("./components/EmergencyConsole").then((m) => ({ default: m.EmergencyConsole }))
);
const RunwayVisualizer = React.lazy(() =>
  import("./components/RunwayVisualizer").then((m) => ({ default: m.RunwayVisualizer }))
);
const SwarmDefenseGauge = React.lazy(() =>
  import("./components/SwarmDefenseGauge").then((m) => ({ default: m.SwarmDefenseGauge }))
);
import { useServerStream } from "./hooks/useServerStream";
import type { SatelliteHealth, RunwayEntry, SwarmDefenseState } from "./types/federation";

setupGlobalFetchInterceptor();

const EMPTY_DEFENSE: SwarmDefenseState = {
  activeClaims: 0,
  claimRejections: 0,
  rateLimitCapacity: 10,
  taskVelocityPerHour: 0,
};

export const OperatorCockpit: React.FC = () => {
  const { streamStatus } = useServerStream();
  const [armed, setArmed] = React.useState(false);
  const [satellites] = React.useState<SatelliteHealth[]>([]);
  const [runway] = React.useState<RunwayEntry[]>([]);
  const [defense] = React.useState<SwarmDefenseState>(EMPTY_DEFENSE);

  return (
    <div className="min-h-screen bg-[#0d0f12] text-slate-100 p-6">
      <header className="mb-6 flex items-center justify-between border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-white">SupremeAI Studio — Operator Cockpit</h1>
          <p className="text-xs text-slate-400 mt-1">Sovereign Federation Telemetry & Ingress Controls</p>
        </div>
        <div className="flex items-center gap-4">
          <a href="/" className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors">← Public Landing</a>
          <span className="text-xs text-slate-400 font-mono">stream: {streamStatus}</span>
        </div>
      </header>
      <main className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <React.Suspense fallback={<div className="p-8 text-center text-xs text-slate-500 font-mono col-span-2">Loading telemetry instrumentation...</div>}>
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">Satellites</h2>
            <SatelliteMatrix satellites={satellites} />
          </section>
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">Runway</h2>
            <RunwayVisualizer entries={runway} />
          </section>
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">Consensus</h2>
            <ConsensusWidget responses={[]} consensusCount={0} />
          </section>
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <h2 className="mb-3 text-sm font-medium text-slate-300">Defense</h2>
            <SwarmDefenseGauge defense={defense} />
          </section>
          <section className="rounded-lg border border-slate-800 bg-slate-900/40 p-4 lg:col-span-2">
            <h2 className="mb-3 text-sm font-medium text-slate-300">Emergency</h2>
            <EmergencyConsole
              armed={armed}
              onRequestKill={() => setArmed(true)}
              onRearm={() => setArmed(false)}
            />
          </section>
        </React.Suspense>
      </main>
    </div>
  );
};

const PublicPageShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <PublicLayout>
    <PublicHeader />
    <div className="pt-16 sm:pt-20 px-4 pb-12 max-w-feed mx-auto">{children}</div>
  </PublicLayout>
);

// RC-2 root-cause fix (frontend research report §6.2/Table 8, 2026-10-25):
// the guest chat needs a bounded h-dvh flex-column host so UnifiedChatPanel
// can flex-fill the real viewport instead of guessing height via
// calc(100dvh-13rem). PublicPageShell stays a scrolling shell for the info
// pages; only /chat gets this dedicated workspace-style host.
export const LiveChatPage: React.FC = () => (
  <PublicLayout>
    <PublicHeader />
    <main className="h-dvh w-full overflow-hidden px-3 pb-3 pt-16 sm:px-4 sm:pt-20">
      <div className="mx-auto flex h-full w-full flex-col">
        <GuestChat />
      </div>
    </main>
  </PublicLayout>
);

const RouteFallback: React.FC = () => (
  <div className="flex h-screen w-full items-center justify-center bg-[#0d0f12]">
    <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-700 border-t-cyan-400" />
  </div>
);

export const App: React.FC = () => {
  return (
    <GlobalConfigInitializer>
      <ThemeSyncProvider>
        <TranslationProvider>
          <React.Suspense fallback={null}>
            <CommandBar />
          </React.Suspense>
          <React.Suspense fallback={<RouteFallback />}>
            <Routes>
              {/* Public Visitor Funnel — Cosmic landing at / (Zero-blocking; renders immediately without auth checks) */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/about" element={<OurStoryPage />} />
              <Route path="/chat" element={<LiveChatPage />} />
              <Route path="/features" element={<PublicPageShell><FeaturesPage /></PublicPageShell>} />
              <Route path="/models" element={<PublicPageShell><ModelsPage /></PublicPageShell>} />
              <Route path="/pricing" element={<PublicPageShell><PricingPage /></PublicPageShell>} />
              <Route path="/docs" element={<PublicPageShell><DocsPage /></PublicPageShell>} />
              <Route path="/contact" element={<PublicPageShell><PublicInfoPage kind="contact" /></PublicPageShell>} />
              {/* Way 4: free developer tools (browser-native, zero sign-up) */}
              <Route path="/tools" element={<PublicPageShell><DevToolsPage /></PublicPageShell>} />
              {/* Way 5: interactive academies (localStorage progress) */}
              <Route path="/academies" element={<PublicPageShell><AcademyHubPage /></PublicPageShell>} />
              <Route path="/knowledge" element={<KnowledgePage />} />

              {/* Split auth — /login + /register render immediately with zero blocking */}
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />

              {/* OWNER DECISION (2026-10-24): the Chat tab IS the landing tab —
                  /workspace renders the unified chat surface directly. */}
              <Route
                path="/workspace"
                element={
                  <ProtectedRoute>
                    <WorkspaceLayout>
                      <AIStudio />
                    </WorkspaceLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/workspace/live"
                element={
                  <ProtectedRoute>
                    <WorkspaceLayout>
                      <AIStudio />
                    </WorkspaceLayout>
                  </ProtectedRoute>
                }
              />

              {/* Supreme OS — JARVIS Dedicated Voice HUD Cockpit */}
              <Route path="/jarvis" element={<JarvisAdminConsolePage />} />

              {/* Admin Console & Shell — Full 32-Module Enterprise Cockpit */}
              <Route
                path="/admin"
                element={
                  <RoleGuard requiredRole="admin">
                    <ErrorBoundary>
                      <AdminShell />
                    </ErrorBoundary>
                  </RoleGuard>
                }
              />
              <Route
                path="/admin/*"
                element={
                  <RoleGuard requiredRole="admin">
                    <ErrorBoundary>
                      <AdminShell />
                    </ErrorBoundary>
                  </RoleGuard>
                }
              />

              {/* Tier-S feature routes (share links, prompt library) */}
              {workspaceFeatureRoutes.map((route) => (
                <Route key={route.path} path={route.path} element={route.element} />
              ))}

              {/* Operator / Internal Telemetry Cockpit */}
              <Route path="/cockpit" element={<OperatorCockpit />} />
              <Route path="/telemetry" element={<OperatorCockpit />} />

              {/* Honest 404 catch-all — never silently bounce to / */}
              <Route path="*" element={<ErrorPage code={404} />} />
            </Routes>
          </React.Suspense>
        </TranslationProvider>
      </ThemeSyncProvider>
    </GlobalConfigInitializer>
  );
};

export default App;
