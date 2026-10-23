/**
 * SupremeAI Studio — Production Application Router & Public Landing Page
 *
 * RESTORATION (Refs #876, 2026-10-23): the Cosmic landing work had replaced this
 * router with a marketing-only subset — /login, /register and the entire
 * authenticated app became unreachable (silent `*` -> `/` bounce broke every
 * auth button on production). The full route contract is restored below per
 * App.routes.test.tsx; the Cosmic public funnel (/, /about, /chat) is KEPT and
 * now EXTENDS the application instead of replacing it.
 */
import React, { lazy, Suspense } from "react";
import { Routes, Route } from "react-router-dom";
import "./styles/tokens.css";
import { GlobalConfigInitializer } from "./components/core/GlobalConfigInitializer";
import { GuestRoute, ProtectedRoute } from "./components/core/AuthGuards";
import { RoleGuard } from "./components/core/guards/RoleGuard";
import { AdminHostEntry } from "./router/AdminHostEntry";
import { ThemeSyncProvider } from "./providers/ThemeSyncProvider";
import { TranslationProvider } from "./i18n/I18nProvider";
import { WorkspaceLayout } from "./components/layout/WorkspaceLayout";
import { CommandBar } from "./components/layout/CommandBar";
import { workspaceFeatureRoutes } from "./routes/workspaceFeatureRoutes";
import { useServerStream } from "./hooks/useServerStream";
import { setupGlobalFetchInterceptor } from "./utils/apiInterceptor";
import { SatelliteMatrix } from "./components/SatelliteMatrix";
import { ConsensusWidget } from "./components/ConsensusWidget";
import { EmergencyConsole } from "./components/EmergencyConsole";
import { RunwayVisualizer } from "./components/RunwayVisualizer";
import { SwarmDefenseGauge } from "./components/SwarmDefenseGauge";
import type { SatelliteHealth, RunwayEntry, SwarmDefenseState } from "./types/federation";

import { LandingPage } from "./pages/LandingPage";
import { OurStoryPage } from "./pages/OurStoryPage";
import { GuestChat, PublicLayout, PublicHeader, ModelsPage, FeaturesPage, PricingPage, DocsPage, PublicInfoPage } from "./pages/PublicPages";
import { LoginPage } from "./pages/auth/LoginPage";
import { RegisterPage } from "./pages/auth/RegisterPage";
import ErrorPage from "./pages/ErrorPage";
import { KnowledgePage } from "./components/dashboard/KnowledgePage";

// বাংলা মন্তব্য: ভারী authenticated pages lazy-load করা হলো — public bundle হালকা
// থাকবে এবং route-smoke test-গুলো এই মডিউলগুলোর module-level side-effect থেকে
// মুক্ত থাকবে। Named/default উভয় export shape সাপোর্ট করা হয়েছে।
const UserDashboard = lazy(() =>
  import("./components/customer/UserDashboard").then((m) => ({ default: m.UserDashboard ?? m.default })),
);
const AdminShell = lazy(() =>
  import("./pages/admin/AdminShell").then((m) => ({ default: m.AdminShell ?? m.default })),
);
const AIStudio = lazy(() =>
  import("./pages/user/AIStudio").then((m) => ({ default: m.AIStudio ?? m.default })),
);

setupGlobalFetchInterceptor();

const EMPTY_DEFENSE: SwarmDefenseState = {
  activeClaims: 0,
  claimRejections: 0,
  rateLimitCapacity: 10,
  taskVelocityPerHour: 0,
};

export const OperatorCockpit: React.FC = () => {
  const { streamStatus } = useServerStream();
  const [armed] = React.useState(false);
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
          <ConsensusWidget responses={[]} consensusCount={0} onRerun={() => {}} />
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
      </main>
    </div>
  );
};

export const LiveChatPage: React.FC = () => (
  <PublicLayout>
    <PublicHeader />
    <div className="pt-24 px-4 pb-12 max-w-4xl mx-auto">
      <GuestChat />
    </div>
  </PublicLayout>
);

const RouteFallback: React.FC = () => (
  <div className="flex items-center justify-center min-h-screen bg-[var(--sa-bg-dark,#030712)] text-slate-400">
    <div className="animate-pulse">Loading…</div>
  </div>
);

export const App: React.FC = () => {
  return (
    <GlobalConfigInitializer>
      <ThemeSyncProvider>
        <TranslationProvider>
          <AdminHostEntry>
            {/* বাংলা: global CommandBar — App.tsx-এ একবারই মাউন্ট (PANEL_OPEN_EVENT contract) */}
            <CommandBar />
            <Routes>
              {/* ═══ Public Visitor Funnel (Cosmic — Refs #859) ═══ */}
              <Route path="/" element={<LandingPage />} />
              <Route path="/about" element={<OurStoryPage />} />
              <Route path="/chat" element={<LiveChatPage />} />
              <Route path="/live" element={<LiveChatPage />} />

              {/* ═══ Public feature/info pages (no auth wall) ═══ */}
              <Route path="/features" element={<FeaturesPage />} />
              <Route path="/models" element={<ModelsPage />} />
              <Route path="/pricing" element={<PricingPage />} />
              <Route path="/docs" element={<DocsPage />} />
              <Route path="/contact" element={<PublicInfoPage kind="contact" />} />

              {/* ═══ Knowledge (Task-12 — real backend wiring) ═══ */}
              <Route path="/knowledge" element={<KnowledgePage />} />

              {/* ═══ Auth (Refs #876 — these were MISSING and broke every auth button) ═══ */}
              <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
              <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />

              {/* ═══ Authenticated workspace ═══ */}
              <Route
                path="/workspace"
                element={
                  <ProtectedRoute>
                    <WorkspaceLayout>
                      <Suspense fallback={<RouteFallback />}>
                        <UserDashboard />
                      </Suspense>
                    </WorkspaceLayout>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/workspace/live"
                element={
                  <ProtectedRoute>
                    <WorkspaceLayout>
                      <Suspense fallback={<RouteFallback />}>
                        <AIStudio />
                      </Suspense>
                    </WorkspaceLayout>
                  </ProtectedRoute>
                }
              />

              {/* ═══ Admin console (AdminShell — NOT OperatorCockpit; Refs #876) ═══ */}
              <Route
                path="/admin/*"
                element={
                  <ProtectedRoute>
                    <RoleGuard requiredRole="admin">
                      <Suspense fallback={<RouteFallback />}>
                        <AdminShell />
                      </Suspense>
                    </RoleGuard>
                  </ProtectedRoute>
                }
              />

              {/* ═══ Operator / internal telemetry (cockpit stays internal-only) ═══ */}
              <Route path="/cockpit" element={<OperatorCockpit />} />
              <Route path="/telemetry" element={<OperatorCockpit />} />

              {/* ═══ Tier-S feature routes — BEFORE the catch-all (per workspaceFeatureRoutes guide) ═══ */}
              {workspaceFeatureRoutes.map((r, i) => (
                <Route key={i} path={r.path!} element={r.element} />
              ))}

              {/* ═══ Honest catch-all 404 (silent '/' bounce hides routing bugs — #876) ═══ */}
              <Route path="*" element={<ErrorPage code={404} />} />
            </Routes>
          </AdminHostEntry>
        </TranslationProvider>
      </ThemeSyncProvider>
    </GlobalConfigInitializer>
  );
};

export default App;
