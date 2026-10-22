import React from "react";
import { GlobalConfigInitializer } from "./components/core/GlobalConfigInitializer";
import { SatelliteMatrix } from "./components/SatelliteMatrix";
import { ConsensusWidget } from "./components/ConsensusWidget";
import { EmergencyConsole } from "./components/EmergencyConsole";
import { RunwayVisualizer } from "./components/RunwayVisualizer";
import { SwarmDefenseGauge } from "./components/SwarmDefenseGauge";
import { useServerStream } from "./hooks/useServerStream";
import { setupGlobalFetchInterceptor } from "./utils/apiInterceptor";
import type { SatelliteHealth, RunwayEntry, SwarmDefenseState } from "./types/federation";

setupGlobalFetchInterceptor();

const EMPTY_DEFENSE: SwarmDefenseState = {
  activeClaims: 0,
  claimRejections: 0,
  rateLimitCapacity: 10,
  taskVelocityPerHour: 0,
};

export const App: React.FC = () => {
  const { streamStatus } = useServerStream();
  const [armed, setArmed] = React.useState(false);
  const [satellites] = React.useState<SatelliteHealth[]>([]);
  const [runway] = React.useState<RunwayEntry[]>([]);
  const [defense] = React.useState<SwarmDefenseState>(EMPTY_DEFENSE);

  return (
    <GlobalConfigInitializer>
      <div className="min-h-screen bg-[#0d0f12] text-slate-100 p-6">
        <header className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold tracking-tight">SupremeAI Studio</h1>
          <span className="text-xs text-slate-400">stream: {streamStatus}</span>
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
    </GlobalConfigInitializer>
  );
};

export default App;
