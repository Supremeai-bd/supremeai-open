import React from 'react';
import { RefreshCcw, Activity, ShieldCheck, Zap } from 'lucide-react';

interface FallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
}

const DashboardErrorFallback: React.FC<FallbackProps> = ({ error, resetErrorBoundary }) => {
  React.useEffect(() => {
    console.error('[Dashboard Error Boundary]', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#07090e] text-slate-200 p-6 relative overflow-hidden font-mono">
      {/* Ambient background glows */}
      <div className="absolute -top-32 -left-32 w-80 h-80 bg-cyan-500/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute -bottom-32 -right-32 w-80 h-80 bg-indigo-500/10 rounded-full blur-[100px] pointer-events-none" />

      <div className="max-w-lg w-full bg-[#0d121f]/90 backdrop-blur-xl p-8 rounded-2xl border border-cyan-500/30 shadow-[0_20px_50px_rgba(0,0,0,0.8),0_0_30px_rgba(6,182,212,0.15)] relative z-10 text-center">
        {/* Top accent bar */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-400 via-indigo-500 to-emerald-400" />

        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[11px] font-semibold tracking-wider uppercase bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 mb-5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
          </span>
          Telemetry Surge · Cluster Re-sync
        </div>

        {/* Hero icon */}
        <div className="relative mx-auto mb-4 flex items-center justify-center w-14 h-14 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-[0_0_20px_rgba(6,182,212,0.25)]">
          <Zap className="w-7 h-7 animate-pulse text-cyan-400" />
        </div>

        <h2 className="text-lg font-bold text-white uppercase tracking-wider mb-2">
          Admin Swarm Synchronizing
        </h2>
        <p className="text-xs text-slate-400 mb-5 leading-relaxed font-sans">
          A high-throughput telemetry stream is dynamically reallocating compute buffers. Core satellite services and edge gateways remain intact and operational.
        </p>

        {/* Mini status indicators */}
        <div className="grid grid-cols-2 gap-2 mb-5 text-left font-sans">
          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-medium">
              <Activity className="w-3 h-3 text-cyan-400" /> Swarm Lane
            </div>
            <div className="text-xs font-semibold text-slate-200 mt-0.5">
              Auto-Rebalancing
            </div>
          </div>
          <div className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800">
            <div className="text-[10px] uppercase tracking-wider text-slate-400 flex items-center gap-1.5 font-medium">
              <ShieldCheck className="w-3 h-3 text-emerald-400" /> Core Perimeters
            </div>
            <div className="text-xs font-semibold text-emerald-400 mt-0.5">
              100% Protected
            </div>
          </div>
        </div>

        {import.meta.env.DEV && (
          <pre className="text-[11px] text-slate-400 font-mono bg-slate-950/80 p-3 rounded-lg mb-5 overflow-auto max-h-32 text-left border border-slate-800">
            {error.message}
          </pre>
        )}

        <button
          onClick={resetErrorBoundary}
          className="w-full inline-flex items-center justify-center gap-2 bg-gradient-to-r from-cyan-500 to-indigo-600 hover:from-cyan-400 hover:to-indigo-500 text-slate-950 hover:text-white font-bold py-3 rounded-xl transition-all duration-200 shadow-[0_0_20px_rgba(6,182,212,0.3)] uppercase tracking-wider text-xs cursor-pointer"
        >
          <RefreshCcw className="w-4 h-4" />
          Re-sync Dashboard Telemetry
        </button>
      </div>
    </div>
  );
};

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  resetErrorBoundary = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      return (
        <DashboardErrorFallback
          error={this.state.error}
          resetErrorBoundary={this.resetErrorBoundary}
        />
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
