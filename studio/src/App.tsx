/**
 * SupremeAI Studio — Production Application Router & Public Landing Page
 */
import React from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import "./styles/tokens.css";
import { GlobalConfigInitializer } from "./components/core/GlobalConfigInitializer";
import { SatelliteMatrix } from "./components/SatelliteMatrix";
import { ConsensusWidget } from "./components/ConsensusWidget";
import { EmergencyConsole } from "./components/EmergencyConsole";
import { RunwayVisualizer } from "./components/RunwayVisualizer";
import { SwarmDefenseGauge } from "./components/SwarmDefenseGauge";
import { useServerStream } from "./hooks/useServerStream";
import { setupGlobalFetchInterceptor } from "./utils/apiInterceptor";
import type { SatelliteHealth, RunwayEntry, SwarmDefenseState } from "./types/federation";

import { LandingPage } from "./pages/LandingPage";
import { OurStoryPage } from "./pages/OurStoryPage";
import { GuestChat, PublicLayout, PublicHeader } from "./pages/PublicPages";

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

export const LiveChatPage: React.FC = () => (
  <PublicLayout>
    <PublicHeader />
    <div className="pt-24 px-4 pb-12 max-w-4xl mx-auto">
      <GuestChat />
    </div>
  </PublicLayout>
);

export const App: React.FC = () => {
  return (
    <GlobalConfigInitializer>
      <Routes>
        {/* Public Visitor Funnel */}
        <Route path="/" element={<LandingPage />} />
        <Route path="/about" element={<OurStoryPage />} />
        <Route path="/chat" element={<LiveChatPage />} />
        <Route path="/workspace/live" element={<LiveChatPage />} />
        <Route path="/live" element={<LiveChatPage />} />
        <Route path="/models" element={<LiveChatPage />} />
        <Route path="/pricing" element={<LiveChatPage />} />

        {/* Operator / Internal Telemetry Cockpit */}
        <Route path="/cockpit" element={<OperatorCockpit />} />
        <Route path="/admin" element={<OperatorCockpit />} />
        <Route path="/telemetry" element={<OperatorCockpit />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </GlobalConfigInitializer>
  );
};

export default App;
