import React from 'react';

interface FallbackProps {
  error: Error;
  resetErrorBoundary: () => void;
}

const DashboardErrorFallback: React.FC<FallbackProps> = ({ error, resetErrorBoundary }) => {
  React.useEffect(() => {
    console.error('[Dashboard Error Boundary]', error);
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950 text-slate-200 p-6">
      <div className="sci-fi-glass-panel max-w-lg w-full p-8 rounded-2xl border border-[#ff0055]/40">
        <h2 className="text-xl font-mono font-bold text-[#ff0055] uppercase tracking-widest mb-2">
          Dashboard Module Failure
        </h2>
        <p className="text-sm text-slate-400 font-mono mb-4">
          A critical module in the admin dashboard has crashed. The rest of the system remains intact.
        </p>
        <pre className="text-xs text-slate-400 font-mono bg-slate-900/80 p-3 rounded-lg mb-6 overflow-auto max-h-40">
          {error.message}
        </pre>
        <button
          onClick={resetErrorBoundary}
          className="w-full bg-[#00f3ff]/20 hover:bg-[#00f3ff]/40 text-[#00f3ff] hover:text-white font-mono font-bold py-2.5 rounded-lg transition-colors border border-[#00f3ff] uppercase tracking-widest text-xs"
        >
          Reboot Dashboard Module
        </button>
      </div>
    </div>
  );
};

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: Error | null }> {
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
      return <DashboardErrorFallback error={this.state.error} resetErrorBoundary={this.resetErrorBoundary} />;
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
