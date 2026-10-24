import React, { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import type { Theme } from "../../contexts/ThemeConstants";

// বাংলা মন্তব্য: Header global search — CommandBar (⌘K) open করে। Shared event-driven trigger.
const openCommandPalette = () => {
  window.dispatchEvent(new CustomEvent('supremeai-open-command-palette'));
};

interface HeaderProps {
  title: string;
  onToggleSidebar: () => void;
  onToggleTheme: () => void;
  // Theme (৪-মান union) — DashboardLayout ThemeProvider থেকে 'matrix'/'sunset'-ও আসতে পারে;
  // ভেতরের 'dark' চেক অন্য মানগুলোকে non-dark branch-এ ঠিকভাবেই ফেলে দেয়।
  theme: Theme;
}

export const Header: React.FC<HeaderProps> = ({
  title,
  onToggleSidebar,
  onToggleTheme,
  theme
}) => {
  const user = useAuthStore((s) => s.user);
  const [showNotifications, setShowNotifications] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const pathname = location.pathname;

  const isAdmin = pathname.startsWith('/admin');

  return (
    <header className="bg-white/70 dark:bg-slate-950/70 backdrop-blur-xl border-b border-gray-200/60 dark:border-white/10 px-6 py-3.5 sticky top-0 z-30 shadow-[0_4px_30px_rgba(0,0,0,0.1)]">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={onToggleSidebar}
            aria-label="Toggle Sidebar"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800/80 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="h-5 w-5 text-gray-600 dark:text-slate-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm0 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
                clipRule="evenodd"
              />
            </svg>
          </button>
          
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold bg-gradient-to-r from-cyan-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">
              {title}
            </h1>

            {/* Live Swarm Telemetry Pulse Radar */}
            <div
              className="hidden lg:flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-900/80 border border-cyan-500/20 text-[11px] font-mono text-cyan-300 shadow-[0_0_12px_rgba(0,243,255,0.15)]"
              title="Autonomous Swarm Active Mesh"
              data-testid="swarm-radar"
            >
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500"></span>
              </span>
              <span>⚡ 42ms • Swarm Online</span>
            </div>
          </div>
        </div>

        {/* Center Section: Global Search + Morphing Role Switcher (User | Admin) */}
        <div className="flex items-center space-x-3">
          {/* Global Search Button */}
          <button
            onClick={openCommandPalette}
            aria-label="Search"
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-slate-800 bg-gray-50 dark:bg-slate-900/80 text-sm text-gray-500 dark:text-slate-400 hover:border-cyan-500/50 hover:shadow-[0_0_12px_rgba(0,243,255,0.15)] transition-all"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 10a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <span>Search...</span>
            <kbd className="ml-2 rounded bg-gray-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-gray-400 dark:text-slate-400 border border-slate-700">
              ⌘K
            </kbd>
          </button>

          {/* Morphing Sliding Role Switcher */}
          <div
            className="relative flex items-center rounded-lg bg-gray-100 dark:bg-slate-900/90 p-1 border border-gray-200 dark:border-slate-800 shadow-inner"
            role="tablist"
            aria-label="Portal Role Switcher"
          >
            <button
              role="tab"
              aria-selected={!isAdmin}
              onClick={() => navigate('/workspace')}
              className={`relative z-10 px-3.5 py-1 text-xs font-semibold rounded-md transition-all duration-300 ${
                !isAdmin
                  ? "bg-purple-600/30 text-purple-300 border border-purple-500/40 shadow-[0_0_15px_rgba(168,85,247,0.35)]"
                  : "text-gray-500 dark:text-slate-400 hover:text-slate-200"
              }`}
            >
              User
            </button>
            <button
              role="tab"
              aria-selected={isAdmin}
              onClick={() => navigate('/admin')}
              className={`relative z-10 px-3.5 py-1 text-xs font-semibold rounded-md transition-all duration-300 ${
                isAdmin
                  ? "bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 shadow-[0_0_15px_rgba(0,243,255,0.35)]"
                  : "text-gray-500 dark:text-slate-400 hover:text-slate-200"
              }`}
            >
              Admin
            </button>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Theme Toggle Button */}
          <button
            onClick={onToggleTheme}
            aria-label="Toggle Theme"
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800/80 transition-colors"
          >
            {theme === 'dark' ? (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 text-yellow-400 drop-shadow-[0_0_8px_rgba(250,204,21,0.4)]"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"
                  clipRule="evenodd"
                />
              </svg>
            ) : (
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 text-gray-600"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"
                />
              </svg>
            )}
          </button>

          {/* Notifications Dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              aria-label="Notifications"
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-800/80 transition-colors relative"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 text-gray-600 dark:text-slate-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  d="M10 2a6 6 0 00-6 6v3.586l-.707.707A1 1 0 004 14h12a1 1 0 00.707-1.707L16 11.586V8a6 6 0 00-6-6zM10 18a3 3 0 01-3-3h6a3 3 0 01-3 3z"
                />
              </svg>
              <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
            </button>
            {showNotifications && (
              <div className="absolute right-0 mt-2 w-72 bg-slate-900/95 backdrop-blur-xl rounded-xl shadow-2xl border border-white/10 p-4 z-50 animate-in fade-in zoom-in-95 duration-200">
                <div className="flex items-center justify-between mb-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-300">Live Telemetry Alerts</p>
                  <span className="text-[10px] font-mono text-cyan-400">All Clear</span>
                </div>
                <div className="text-xs text-slate-400 space-y-2">
                  <div className="p-2 rounded-lg bg-slate-800/60 border border-white/5">
                    <p className="font-medium text-slate-200">Swarm Health 100%</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">All 52 knowledge cards and reasoning engines active.</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* User Profile Avatar */}
          <div className="flex items-center space-x-2 pl-2 border-l border-gray-200 dark:border-slate-800">
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-cyan-500 to-purple-600 flex items-center justify-center shadow-[0_0_10px_rgba(0,243,255,0.3)]">
              <span className="text-white font-bold text-xs">
                {user ? user.name.charAt(0).toUpperCase() : 'A'}
              </span>
            </div>
            <span className="text-sm font-medium text-gray-700 dark:text-slate-300 hidden md:block">
              {user ? user.name : 'Alex (Admin)'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
