// SupremeAI — GlobalHeader (single-frontend migration, roadmap Phase 3)
// বাংলা মন্তব্য: User ও Admin — দুই context-ই একই কাঠামোর header দেখে; শুধু contextual
// কনটেন্ট (role pill, identity, logout handler) বদলায়। দ্বিতীয় কোনো global header তৈরি
// নিষিদ্ধ (roadmap Rule 8: "No duplicate global shells")।
//
// Role pill শুধু navigation shortcut — এটি কখনো role/privilege set করে না
// (roadmap §16: "click Admin → set role='admin' → gain privilege" নিষিদ্ধ)।

import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Command, LogOut, Moon, Sun, Bell, ChevronDown, Wifi, WifiOff } from 'lucide-react';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { useStore } from '../../store/useStore';
import { useTheme } from '../../contexts/useTheme';
import { useWorkspaceSettings } from '../../hooks/useWorkspaceSettings';
import { useMobileNav } from '../../hooks/useMobileNav';
import { canAccessAdminContext, resolveLandingPath } from '../../auth/identity';
import { PANEL_OPEN_EVENT } from './shellEvents';

export interface HeaderNotification {
  id: string;
  title: string;
  description?: string;
  time?: string;
}

export interface GlobalHeaderProps {
  /** Which runtime context this header instance serves. */
  context: 'user' | 'admin';
  /** Context-specific logout (admin passes handleAdminLogout). */
  onLogout?: () => void;
  /** Optional contextual notifications (admin modules may feed operational alerts). */
  notifications?: HeaderNotification[];
  /** Optional right-side slot (contextual actions, status pills). */
  actions?: React.ReactNode;
}

const HeaderAvatar: React.FC<{ label: string; className?: string }> = ({ label, className }) => (
  <div className={`w-8 h-8 rounded-full bg-accent-primary/90 flex items-center justify-center text-black text-xs font-bold shrink-0 ${className || ''}`}>
    {label.slice(0, 2).toUpperCase()}
  </div>
);

export function GlobalHeader({ context, onLogout, notifications = [], actions }: GlobalHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const user = useAuthStore((s) => s.user);
  const isServerOnline = useStore((s) => s.isServerOnline);
  // #972 UX contract: honest "CHECKING…" label while the first health probe
  // (useServerStream → /api/v1/health) is still in flight, instead of a
  // misleading "SYSTEM UNAVAILABLE" during cold start.
  const isServerStatusChecking = useStore((s) => s.isServerStatusChecking);
  const { isSidebarCollapsed, toggleSidebar } = useWorkspaceSettings();
  // Issue #1526: mobile drawer state — GlobalHeader's sidebar button opens the
  // overlay nav below md; DashboardLayout closes it on route change/backdrop.
  const { isMobileNavOpen, toggleMobileNav } = useMobileNav();

  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const headerRef = useRef<HTMLDivElement>(null);

  // বাংলা: dropdown-এর বাইরে ক্লিক করলে বন্ধ — প্রতি dropdown-এ আলাদা listener ছড়ানোর বদলে একটাই।
  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (headerRef.current && !headerRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
        setProfileOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const adminAuthorized = canAccessAdminContext();
  const identityLabel = user?.email || (context === 'admin' ? 'operator' : 'user');
  const initials = identityLabel.split('@')[0] || 'SU';

  const handleUserLogout = () => {
    setProfileOpen(false);
    if (onLogout) {
      onLogout();
      return;
    }
    // বাংলা: canonical user logout — authStore.logout() সব contextual state পরিষ্কার করে।
    import('../../store/authStore').then(({ useAuthStore: store }) => {
      store.getState().logout();
      navigate('/login');
    });
  };

  const openCommandPalette = () => {
    // বাংলা: global CommandBar (App.tsx-এ একবারই মাউন্ট করা) এই event শুনে খোলে —
    // দ্বিতীয় palette instance তৈরি করা হয় না।
    window.dispatchEvent(new CustomEvent(PANEL_OPEN_EVENT));
  };

  const isActiveContext = (ctx: 'user' | 'admin') =>
    ctx === 'admin' ? location.pathname.startsWith('/admin') : !location.pathname.startsWith('/admin');

  return (
    <div ref={headerRef} className="h-14 flex items-center gap-3 px-4 border-b border-border">
      {/* Sidebar collapse toggle — shared collapse state, দুই context-এই কাজ করে。
          Issue #1526: below md the sidebar is an overlay drawer, so the same
          button toggles the mobile drawer instead of the desktop collapse
          state (checked at click time, not render time). */}
      <button
        type="button"
        onClick={() => {
          if (typeof window !== 'undefined' && window.innerWidth < 768) {
            toggleMobileNav();
          } else {
            toggleSidebar();
          }
        }}
        aria-label={isSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-expanded={isMobileNavOpen ? true : undefined}
        className="h-9 w-9 shrink-0 rounded-lg hover:surface-2 text-secondary hover:text-text flex items-center justify-center transition-colors"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <line x1="9" y1="4" x2="9" y2="20" className={isSidebarCollapsed ? 'opacity-40' : ''} />
        </svg>
      </button>

      {/* Brand */}
      <button
        type="button"
        onClick={() => navigate(resolveLandingPath(useAuthStore.getState().status === AuthStatus.LOGGED_IN))}
        className="flex items-center gap-2 shrink-0"
        aria-label="SupremeAI home"
      >
        <div className="w-6 h-6 rounded-md bg-accent-primary flex items-center justify-center shadow-[0_0_12px_rgba(168,85,247,0.4)]">
          <span className="text-black font-black text-xs">S</span>
        </div>
        <span className="font-sans font-bold tracking-wider text-text hidden sm:inline">
          Supreme<span className="text-accent-primary">AI</span>
        </span>
      </button>

      {/* Role context pills — navigation only; Admin pill শুধুমাত্র authorized identity-কেই দেখায় */}
      {adminAuthorized && (
        <div className="hidden md:flex items-center rounded-lg border border-border overflow-hidden text-xs font-semibold" role="navigation" aria-label="Role context">
          <button
            type="button"
            onClick={() => navigate('/workspace?viewAs=user')}
            className={`px-3 py-1.5 transition-colors ${isActiveContext('user') ? 'surface-3 text-accent-primary' : 'text-secondary hover:text-text hover:surface-2'}`}
          >
            View as user
          </button>
          <button
            type="button"
            onClick={() => navigate('/admin')}
            className={`px-3 py-1.5 transition-colors ${isActiveContext('admin') ? 'surface-3 text-accent-primary' : 'text-secondary hover:text-text hover:surface-2'}`}
          >
            Admin console
          </button>
        </div>
      )}

      {adminAuthorized && context === 'user' && (
        <div className="flex items-center gap-2 rounded-full border border-amber-500/40 bg-amber-500/10 px-3 py-1 text-[11px] font-mono text-amber-400 shadow-[0_0_12px_rgba(245,158,11,0.15)]">
          <span className="h-2 w-2 rounded-full bg-amber-400 animate-pulse" aria-hidden="true" />
          <span className="hidden sm:inline">Customer Preview Mode</span>
          <button type="button" onClick={() => navigate('/admin')} className="font-semibold underline underline-offset-2 hover:text-white ml-1">
            Return to Admin &rarr;
          </button>
        </div>
      )}

      <div className="flex-1" />

      {/* Server connectivity status — shared global status */}
      <span
        className="hidden lg:flex items-center gap-1.5 text-[11px] font-mono text-secondary"
        title={isServerOnline ? 'Core backend online' : 'Core backend unreachable'}
      >
        {isServerOnline ? <Wifi size={13} className="text-emerald-400" /> : <WifiOff size={13} className="text-rose-400" />}
        {isServerStatusChecking
          ? 'CHECKING…'
          : isServerOnline
            ? 'SYSTEM OPERATIONAL'
            : 'SYSTEM UNAVAILABLE'}
      </span>

      {actions}

      {/* Command palette trigger */}
      <button
        type="button"
        onClick={openCommandPalette}
        aria-label="Open command palette (Ctrl+K)"
        title="Ctrl+K"
        className="h-9 w-9 rounded-lg hover:surface-2 text-secondary hover:text-text flex items-center justify-center transition-colors"
      >
        <Command size={17} />
      </button>

      {/* Notifications — shared dropdown infrastructure (admin modules may feed it) */}
      <div className="relative">
        <button
          type="button"
          onClick={() => { setNotifOpen((v) => !v); setProfileOpen(false); }}
          aria-label="Notifications"
          className="relative h-9 w-9 rounded-lg hover:surface-2 text-secondary hover:text-text flex items-center justify-center transition-colors"
        >
          <Bell size={17} />
          {notifications.length > 0 && (
            <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-rose-500" />
          )}
        </button>
        {notifOpen && (
          <div className="absolute right-0 mt-2 w-80 rounded-xl border border-border bg-surface-2 shadow-xl z-50 overflow-hidden">
            <div className="px-4 py-2.5 text-xs font-bold uppercase tracking-widest text-muted border-b border-border">
              Notifications
            </div>
            <div className="max-h-72 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="px-4 py-6 text-sm text-secondary text-center">No notifications</div>
              ) : (
                notifications.map((n) => (
                  <div key={n.id} className="px-4 py-3 border-b border-border/60 last:border-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium text-text">{n.title}</span>
                      {n.time && <span className="text-[10px] font-mono text-muted shrink-0">{n.time}</span>}
                    </div>
                    {n.description && <p className="mt-0.5 text-xs text-secondary">{n.description}</p>}
                  </div>
                ))
              )}
            </div>
          </div>
        )}
      </div>

      {/* Theme toggle — cycles the shared ThemeProvider (dark → light → sunset → matrix) */}
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={`Current theme: ${theme}. Change theme`}
        className="h-9 w-9 rounded-lg hover:surface-2 text-secondary hover:text-text flex items-center justify-center transition-colors"
      >
        {theme === 'light' ? <Sun size={17} /> : <Moon size={17} />}
      </button>

      {/* Profile / identity */}
      <div className="relative">
        <button
          type="button"
          data-testid="account-menu-btn"
          onClick={() => { setProfileOpen((v) => !v); setNotifOpen(false); }}
          aria-label="Account menu"
          className="flex items-center gap-2 rounded-lg hover:surface-2 px-1.5 py-1 transition-colors"
        >
          <HeaderAvatar label={initials} />
          <ChevronDown size={14} className="text-secondary hidden sm:block" />
        </button>
        {profileOpen && (
          <div className="absolute right-0 mt-2 w-64 rounded-xl border border-border bg-surface-2 shadow-xl z-50 overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <div className="flex items-center gap-3">
                <HeaderAvatar label={initials} />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-text truncate">{identityLabel}</div>
                  <div className="text-[11px] font-mono uppercase tracking-wider text-muted">
                    {context === 'admin' ? 'Admin context' : 'User context'}
                  </div>
                </div>
              </div>
            </div>
            <button
              type="button"
              data-testid="logout-btn"
              onClick={handleUserLogout}
              className="w-full flex items-center gap-2.5 px-4 py-3 text-sm text-rose-400 hover:surface-3 transition-colors"
            >
              <LogOut size={15} />
              {context === 'admin' ? 'Exit Admin Session' : 'Log out'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
