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

// Providers + global chrome (ThemeSync, i18n, CommandBar were unmounted by the regression)
import { ThemeSyncProvider } from "./providers/ThemeSyncProvider";
import { TranslationProvider } from "./i18n/I18nProvider";
import { CommandBar } from "./components/layout/CommandBar";
import { WorkspaceLayout } from "./components/layout/WorkspaceLayout";

// Public funnel (Cosmic landing lives at /; guest chat at /chat)
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

// Split auth (login/create account buttons work again)
import { LoginPage } from "./pages/auth/LoginPage";
import { RegisterPage } from "./pages/auth/RegisterPage";

// Authenticated app
import { UserDashboard } from "./components/customer/UserDashboard";
import { AIStudio } from "./pages/user/AIStudio";
import { AdminShell } from "./pages/admin/AdminShell";
import ErrorBoundary from "./components/admin/DashboardErrorBoundary";
import { KnowledgePage } from "./components/dashboard/KnowledgePage";
import { workspaceFeatureRoutes } from "./routes/workspaceFeatureRoutes";
import ErrorPage from "./pages/ErrorPage";

// Internal operator telemetry widgets (kept as-is; WO1b tokenization is separate scope)
import { SatelliteMatrix } from "./components/SatelliteMatrix";
import { ConsensusWidget } from "./components/ConsensusWidget";
import { EmergencyConsole } from "./components/EmergencyConsole";
import { RunwayVisualizer } from "./components/RunwayVisualizer";
import { SwarmDefenseGauge } from "./components/SwarmDefenseGauge";
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

const PublicPageShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <PublicLayout>
    <PublicHeader />
    <div className="pt-24 px-4 pb-12 max-w-4xl mx-auto">{children}</div>
  </PublicLayout>
);

export const LiveChatPage: React.FC = () => (
  <PublicPageShell>
    <GuestChat />
  </PublicPageShell>
);

export const App: React.FC = () => {
  return (
    <GlobalConfigInitializer>
      <ThemeSyncProvider>
        <TranslationProvider>
          <CommandBar />
          <Routes>
            {/* Public Visitor Funnel — Cosmic landing at / (guests only; logged-in users land on /workspace) */}
            <Route path="/" element={<GuestRoute><LandingPage /></GuestRoute>} />
            <Route path="/about" element={<OurStoryPage />} />
            <Route path="/chat" element={<LiveChatPage />} />
            <Route path="/features" element={<PublicPageShell><FeaturesPage /></PublicPageShell>} />
            <Route path="/models" element={<PublicPageShell><ModelsPage /></PublicPageShell>} />
            <Route path="/pricing" element={<PublicPageShell><PricingPage /></PublicPageShell>} />
            <Route path="/docs" element={<PublicPageShell><DocsPage /></PublicPageShell>} />
            <Route path="/contact" element={<PublicPageShell><PublicInfoPage kind="contact" /></PublicPageShell>} />
            <Route path="/knowledge" element={<KnowledgePage />} />

            {/* Split auth (Refs #876) — /login + /register restored, no silent bounce */}
            <Route path="/login" element={<GuestRoute><LoginPage /></GuestRoute>} />
            <Route path="/register" element={<GuestRoute><RegisterPage /></GuestRoute>} />

            {/* Authenticated workspace */}
            <Route
              path="/workspace"
              element={
                <ProtectedRoute>
                  <WorkspaceLayout>
                    <UserDashboard />
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

            {/* Admin — AdminShell (OTP/TOTP step-up preserved), NOT OperatorCockpit */}
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
        </TranslationProvider>
      </ThemeSyncProvider>
    </GlobalConfigInitializer>
  );
};

export default App;
