import React, { Component, useState, useEffect } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { Zap, RefreshCcw, Activity, ShieldCheck, ChevronDown, ChevronUp } from 'lucide-react';
import { getApiBaseUrl } from '../utils/api';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

interface FallbackProps {
  error: Error | null;
  onReload: () => void;
}

const GlobalErrorFallback: React.FC<FallbackProps> = ({ error, onReload }) => {
  const [countdown, setCountdown] = useState(6);
  const [isPaused, setIsPaused] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  useEffect(() => {
    if (isPaused || countdown <= 0) return;
    const timer = setTimeout(() => {
      if (countdown === 1) {
        onReload();
      } else {
        setCountdown((prev) => prev - 1);
      }
    }, 1000);
    return () => clearTimeout(timer);
  }, [countdown, isPaused, onReload]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#080B11] text-gray-100 p-4 font-sans relative overflow-hidden selection:bg-cyan-500/30">
      {/* Ambient futuristic glows */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-indigo-600/15 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-cyan-500/15 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-purple-600/10 rounded-full blur-[160px] pointer-events-none" />

      <div className="max-w-md w-full bg-[#0F1422]/90 backdrop-blur-2xl rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.7),0_0_40px_rgba(99,102,241,0.15)] p-7 text-center border border-indigo-500/20 relative z-10 transition-all">
        {/* Radiant top edge accent */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-400 via-indigo-500 to-purple-500" />

        {/* High Demand Surge Pill */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 mb-5 shadow-[0_0_15px_rgba(99,102,241,0.2)]">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
          </span>
          High Demand Surge · Swarm Auto-Scaling
        </div>

        {/* Hero Glowing Icon */}
        <div className="relative mx-auto mb-5 flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-cyan-500/20 border border-indigo-500/30 shadow-[0_0_25px_rgba(99,102,241,0.25)]">
          <Zap className="w-8 h-8 text-cyan-400 animate-pulse" />
        </div>

        {/* Title */}
        <h1 className="text-2xl font-bold text-white tracking-tight mb-2.5">
          High Demand Across the Swarm
        </h1>

        {/* Reassuring Marketing Copy */}
        <p className="text-gray-300 mb-6 text-sm leading-relaxed">
          SupremeAI is currently experiencing heavy global traffic. Neural compute nodes are auto-scaling to allocate dedicated capacity for your session.
        </p>

        {/* Live Swarm Micro-Stats */}
        <div className="grid grid-cols-2 gap-2.5 mb-6 text-left">
          <div className="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/80">
            <div className="text-[10px] uppercase tracking-wider text-gray-400 flex items-center gap-1.5 font-medium">
              <Activity className="w-3 h-3 text-cyan-400" /> Swarm Status
            </div>
            <div className="text-xs font-semibold text-gray-200 mt-1">
              Auto-Balancing Nodes
            </div>
          </div>
          <div className="p-2.5 rounded-xl bg-gray-900/60 border border-gray-800/80">
            <div className="text-[10px] uppercase tracking-wider text-gray-400 flex items-center gap-1.5 font-medium">
              <ShieldCheck className="w-3 h-3 text-emerald-400" /> Satellites
            </div>
            <div className="text-xs font-semibold text-emerald-400 mt-1">
              100% Operational
            </div>
          </div>
        </div>

        {/* Auto-reconnect Countdown Progress Bar */}
        <div className="mb-6 p-3.5 rounded-xl bg-indigo-950/30 border border-indigo-800/30">
          <div className="flex items-center justify-between text-xs text-indigo-200 mb-2 font-medium">
            <span className="flex items-center gap-2">
              <RefreshCcw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
              Reconnecting to compute cluster
            </span>
            <span className="font-mono text-cyan-300 font-bold bg-cyan-950/50 px-2 py-0.5 rounded border border-cyan-500/20">
              {countdown}s
            </span>
          </div>
          <div className="w-full bg-gray-800/80 h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-gradient-to-r from-cyan-400 via-indigo-500 to-purple-500 h-full transition-all duration-1000 ease-linear rounded-full"
              style={{ width: `${Math.min(100, Math.max(0, ((6 - countdown) / 6) * 100))}%` }}
            />
          </div>
        </div>

        {/* CTA Buttons */}
        <button
          onClick={onReload}
          className="w-full inline-flex items-center justify-center px-6 py-3.5 bg-gradient-to-r from-indigo-600 via-indigo-500 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold rounded-xl transition-all duration-200 gap-2 shadow-[0_0_25px_rgba(99,102,241,0.4)] cursor-pointer transform hover:scale-[1.01] active:scale-[0.99]"
        >
          <RefreshCcw className="w-4 h-4" />
          Reconnect Now
        </button>

        <button
          onClick={() => {
            window.location.href = '/';
          }}
          className="mt-2.5 w-full inline-flex items-center justify-center px-4 py-2 text-xs font-medium text-gray-400 hover:text-gray-200 transition-colors cursor-pointer"
        >
          Return to Platform Overview
        </button>

        {/* Developer Diagnostics Stack (collapsible in DEV mode only) */}
        {import.meta.env.DEV && error && (
          <div className="mt-5 pt-4 border-t border-gray-800/80 text-left">
            <button
              onClick={() => {
                setShowDiagnostics(!showDiagnostics);
                setIsPaused(true);
              }}
              className="text-xs text-gray-500 hover:text-gray-400 font-mono inline-flex items-center gap-1.5 transition-colors cursor-pointer"
            >
              {showDiagnostics ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
              {showDiagnostics ? 'Hide Diagnostic Stack' : 'Show Diagnostic Stack (Dev Only)'}
            </button>
            {showDiagnostics && (
              <div className="mt-2.5 bg-gray-950/80 p-3 rounded-lg border border-red-500/20 overflow-auto max-h-36 text-xs font-mono text-red-400">
                <div className="font-bold text-red-300 mb-1">
                  {error.name}: {error.message}
                </div>
                {error.stack && (
                  <div className="text-[10px] text-gray-500 whitespace-pre-wrap leading-relaxed">
                    {error.stack}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export class GlobalErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);

    try {
      // Justified raw fetch (Issue #2522): keepalive:true unload-beacon —
      // apiClient-এর concurrency queue দিয়ে গেলে page unload-এ কল কখনোই আগুন
      // নাও জ্বলতে পারে; error-report নীরব fire-and-forget-ই সঠিক প্রিমিটিভ।
      fetch(`${getApiBaseUrl()}/api/telemetry/frontend-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          module: 'frontend_global_error_boundary',
          error_type: error.name,
          message: error.message.slice(0, 500),
          stack: (error.stack || '').slice(0, 2000),
          component_stack: (errorInfo.componentStack || '').slice(0, 2000),
          url: window.location.href,
          severity: 'ERROR',
        }),
        keepalive: true,
      }).catch((telemetryError) => {
        console.warn('[telemetry] Failed to report frontend error:', telemetryError);
      });
    } catch (reportError) {
      console.warn('[GlobalErrorBoundary] Error reporting telemetry failed:', reportError);
    }
  }

  private handleReload = () => {
    window.location.reload();
  };

  public render() {
    if (this.state.hasError) {
      return (
        <GlobalErrorFallback
          error={this.state.error}
          onReload={this.handleReload}
        />
      );
    }

    return this.props.children;
  }
}
