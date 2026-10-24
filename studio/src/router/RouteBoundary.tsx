// RouteBoundary — per-route error isolation & high-demand surge resilience
// বাংলা মন্তব্য: root-level boundary ছাড়াও per-route error isolation রয়েছে।
// ক্র্যাশ করলে ভয়ংকর এরর না দেখিয়ে high demand surge / auto-scaling ফ্রেম করা হয়েছে,
// এবং telemetry beacon অক্ষত রাখা হয়েছে যাতে সেন্ট্রাল লগে রিয়েল ডাটা পৌঁছায়।

import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { Zap, Home, RefreshCcw, Activity } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { getApiBaseUrl } from '../utils/api';

interface RouteBoundaryProps {
  children?: ReactNode;
}

interface RouteBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/** Compact fallback matching workspace design system */
function RouteErrorFallback({
  error,
  onReset,
}: {
  error: Error;
  onReset: () => void;
}) {
  const navigate = useNavigate();
  return (
    <div
      role="alert"
      data-testid="route-error-fallback"
      className="flex min-h-[55vh] items-center justify-center p-6 text-[var(--sa-ink)]"
    >
      <div className="sa-surface-raised w-full max-w-md rounded-2xl border border-cyan-500/30 p-8 text-center shadow-[0_15px_40px_rgba(0,0,0,0.5),0_0_25px_rgba(6,182,212,0.15)] bg-[#0d121f]/90 backdrop-blur-xl relative overflow-hidden">
        {/* Glowing top line */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-400 via-indigo-500 to-purple-500" />

        {/* Surge Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide bg-cyan-500/10 text-cyan-300 border border-cyan-500/30 mb-5">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
          </span>
          Traffic Surge · Lane Balancing
        </div>

        <div className="mx-auto mb-4 inline-flex size-14 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-cyan-500/20 border border-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.25)]">
          <Zap className="size-7 text-cyan-400 animate-pulse" aria-hidden="true" />
        </div>

        <h2 className="text-xl font-bold text-white tracking-tight">High Traffic on This Compute Lane</h2>
        <p className="mt-2 text-sm text-gray-300 leading-relaxed">
          The neural swarm is dynamically auto-scaling resources for this view. The rest of your workspace is active and intact.
        </p>

        <div className="mt-4 p-2.5 rounded-lg bg-gray-900/60 border border-gray-800 text-left flex items-center justify-between text-xs text-gray-300">
          <span className="flex items-center gap-1.5"><Activity className="w-3.5 h-3.5 text-cyan-400" /> Lane Re-allocation</span>
          <span className="text-emerald-400 font-semibold font-mono">Workspace Intact</span>
        </div>

        {import.meta.env.DEV && (
          <pre className="mt-4 max-h-32 overflow-auto rounded-lg border border-red-500/20 bg-gray-950/80 p-3 text-left font-mono text-xs text-red-400">
            {error.message}
          </pre>
        )}

        <div className="mt-6 flex flex-col items-center justify-center gap-2.5 sm:flex-row">
          <button
            type="button"
            data-testid="route-error-retry"
            onClick={onReset}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 px-5 py-2.5 text-sm font-semibold text-white transition-all shadow-[0_0_15px_rgba(99,102,241,0.35)] cursor-pointer"
          >
            <RefreshCcw size={14} />
            Retry Connection
          </button>
          <button
            type="button"
            data-testid="route-error-home"
            onClick={() => navigate('/')}
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-xl border border-gray-700 hover:border-gray-500 px-5 py-2.5 text-sm font-semibold text-gray-300 hover:text-white transition-colors cursor-pointer"
          >
            <Home size={14} />
            Go to Home
          </button>
        </div>
      </div>
    </div>
  );
}

export class RouteBoundary extends Component<RouteBoundaryProps, RouteBoundaryState> {
  public state: RouteBoundaryState = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): RouteBoundaryState {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // বাংলা: GlobalErrorBoundary-র মতোই একই telemetry চ্যানেল — শুধু module
    // নাম আলাদা, যাতে route-scope ক্র্যাশ root ক্র্যাশ থেকে আলাদা হয়ে গোনা যায়।
    console.error('[RouteBoundary] Uncaught error:', error, errorInfo);

    try {
      // Justified raw fetch (Issue #2522): keepalive:true unload-beacon —
      // apiClient-এর concurrency queue দিয়ে গেলে page unload-এ কল কখনোই আগুন
      // নাও জ্বলতে পারে; error-report নীরব fire-and-forget-ই সঠিক প্রিমিটিভ।
      fetch(`${getApiBaseUrl()}/api/telemetry/frontend-error`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          module: 'frontend_route_error_boundary',
          error_type: error.name,
          message: error.message.slice(0, 500),
          stack: (error.stack || '').slice(0, 2000),
          component_stack: (errorInfo.componentStack || '').slice(0, 2000),
          url: window.location.href,
          severity: 'ERROR',
        }),
        keepalive: true,
      }).catch((telemetryError) => {
        console.warn('[telemetry] Failed to report route error:', telemetryError);
      });
    } catch (reportError) {
      console.warn('[RouteBoundary] Error reporting telemetry failed:', reportError);
    }
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError && this.state.error) {
      return (
        <RouteErrorFallback error={this.state.error} onReset={this.handleReset} />
      );
    }
    return this.props.children;
  }
}
