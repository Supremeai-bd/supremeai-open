import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';

export interface HeaderNotification {
  id: string;
  title: string;
  message?: string;
  read?: boolean;
}

export interface GlobalHeaderProps {
  title?: string;
  context?: 'user' | 'admin' | 'guest';
  onToggleSidebar?: () => void;
  actions?: React.ReactNode;
  onLogout?: () => void;
  notifications?: HeaderNotification[];
}

export const SwarmRadar: React.FC = () => (
  <div
    className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-900/80 border border-emerald-500/20 text-[11px] font-mono text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.15)]"
    title="Autonomous Swarm Active Mesh"
    data-testid="swarm-radar"
  >
    <span className="relative flex h-2 w-2">
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
      <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
    </span>
    <span>⚡ 42ms • Swarm Online</span>
  </div>
);

export const GlobalHeader: React.FC<GlobalHeaderProps> = ({
  title = 'SupremeAI',
  context = 'user',
  onToggleSidebar,
  actions,
}) => {
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const isAdmin = context === 'admin' || location.pathname.startsWith('/admin');

  return (
    <header className="sticky top-0 z-30 flex h-14 w-full items-center justify-between border-b border-white/10 bg-slate-950/80 px-4 md:px-6 backdrop-blur-xl transition-all">
      <div className="flex items-center gap-3">
        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label="Toggle Navigation"
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800/80 hover:text-white transition-colors"
          >
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M3 5h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2zm0 4h14a1 1 0 010 2H3a1 1 0 010-2z" clipRule="evenodd" />
            </svg>
          </button>
        )}
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-tr from-emerald-500 to-purple-600 font-bold text-white text-xs shadow-md">
            S
          </span>
          <span className="font-semibold text-white tracking-tight">{title}</span>
        </div>
        <SwarmRadar />
      </div>

      <div className="flex items-center gap-3">
        {/* Context role switch */}
        <div className="flex items-center rounded-lg bg-slate-900/90 p-0.5 border border-white/10 text-xs">
          <button
            type="button"
            onClick={() => navigate('/workspace')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              !isAdmin ? 'bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            User
          </button>
          <button
            type="button"
            onClick={() => navigate('/admin')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              isAdmin ? 'bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 shadow-sm' : 'text-slate-400 hover:text-white'
            }`}
          >
            Admin
          </button>
        </div>

        {actions}

        {/* Global Search trigger */}
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent('supremeai-open-command-palette'))}
          aria-label="Search"
          className="hidden sm:flex items-center gap-2 rounded-lg border border-white/10 bg-slate-900/80 px-2.5 py-1 text-xs text-slate-400 hover:border-emerald-500/40 hover:text-white transition-all"
        >
          <span>Search...</span>
          <kbd className="rounded border border-slate-700 bg-slate-800 px-1 py-0.5 font-mono text-[10px]">⌘K</kbd>
        </button>
      </div>
    </header>
  );
};

export default GlobalHeader;
