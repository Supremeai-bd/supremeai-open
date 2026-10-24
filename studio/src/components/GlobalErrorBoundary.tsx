import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCcw } from 'lucide-react';
import { getApiBaseUrl } from '../utils/api';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class GlobalErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Uncaught error:', error, errorInfo);

    try {
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
        <div className="min-h-screen flex items-center justify-center bg-gray-900 text-gray-100 p-4 font-sans">
          <div className="max-w-md w-full bg-gray-800 rounded-xl shadow-2xl p-8 text-center border border-gray-700/50">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-red-500/10 mb-6">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>

            <h1 className="text-2xl font-bold text-white mb-3">
              Application Error
            </h1>

            <p className="text-gray-400 mb-6 text-sm leading-relaxed">
              We encountered an unexpected error. This has been logged and our team will investigate.
            </p>

            {import.meta.env.DEV && this.state.error && (
              <div className="mb-8 text-left bg-gray-900/50 p-4 rounded-lg border border-gray-700 overflow-auto max-h-32 text-xs font-mono text-red-400">
                {this.state.error.message}
              </div>
            )}

            <button
              onClick={this.handleReload}
              className="inline-flex items-center justify-center px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded-lg transition-colors duration-200 gap-2 w-full"
            >
              <RefreshCcw className="w-4 h-4" />
              Reload Application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
