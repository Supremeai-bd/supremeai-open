// SupremeAI — RoleAwareNavRail (single-frontend migration, roadmap Phase 3/6)
// বাংলা মন্তব্য: একটাই sidebar framework — User ও Admin দুই context-ই এটি ব্যবহার করে।
// কনটেন্ট NAVIGATION_REGISTRY থেকে generate হয়; দ্বিতীয় কোনো nav definition নেই।

import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { PanelLeft, PanelLeftClose } from 'lucide-react';
import { getNavigationForContext, type NavEntry } from '../../config/navigationRegistry';
import { useAuthStore } from '../../store/authStore';
import { useWorkspaceSettings } from '../../hooks/useWorkspaceSettings';
import { getCanonicalRole } from '../../auth/identity';

export interface RoleAwareNavRailProps {
  context: 'user' | 'admin';
  collapsed: boolean;
  /** Admin context: currently active subtab id (drives action-item active state). */
  activeActionId?: string;
  /** Admin context: handler for action items (admin subtab switch). */
  onAction?: (actionId: string) => void;
  onToggleCollapsed?: () => void;
}

export function RoleAwareNavRail({ context, collapsed, activeActionId, onAction, onToggleCollapsed }: RoleAwareNavRailProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const role = useAuthStore((state) => state.role);
  const permissions = useAuthStore((state) => state.permissions);
  const enabledModules = useWorkspaceSettings((state) => state.enabledModules);
  // 🛡️ ISSUE #496: অ্যাডমিন কনটেক্সটে সর্বদাই 'admin' রোল সক্রিয় থাকবে যাতে সব সাবট্যাব অপরিবর্তিত থাকে
  const effectiveRole = context === 'admin' ? 'admin' : (role || getCanonicalRole());
  const groups = getNavigationForContext(context, { role: effectiveRole, permissions }).map((group) => ({
    ...group,
    items: group.items.filter((item) => item.id !== 'nav-ide' || enabledModules.includes('code')),
  })).filter((group) => group.items.length > 0);

  // বাংলা: আগের UserSidebar-এর active semantics হুবহু — exact match, অথবা non-root
  // path-এর জন্য prefix match।
  const isRouteActive = (path: string) =>
    location.pathname === path || (path !== '/workspace' && location.pathname.startsWith(path));

  const renderEntry = (item: NavEntry) => {
    const iconEl = (
      <item.icon
        size={18}
        className={item.kind === 'action' && activeActionId === item.actionId ? 'text-accent-primary' : 'text-secondary'}
      />
    );
    const labelEl = !collapsed ? <span>{item.label}</span> : null;
    const baseCls =
      'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60';
    const titleAttr = collapsed ? item.label : undefined;

    if (item.kind === 'route') {
      const active = isRouteActive(item.path);
      return (
        <Link
          key={item.id}
          to={item.path}
          onClick={(event) => {
            event.preventDefault();
            navigate(item.path);
          }}
          title={titleAttr}
          className={`${baseCls} ${active
            ? 'surface-3 text-accent-primary border-l-2 border-accent-primary shadow-[0_0_18px_rgba(34,211,238,0.14)]'
            : 'text-secondary hover:surface-2 hover:text-text hover:shadow-[0_0_16px_rgba(34,211,238,0.12)]'}`}
        >
          {iconEl}
          {labelEl}
        </Link>
      );
    }

    const active = activeActionId === item.actionId;
    return (
      <button
        key={item.id}
        type="button"
        // Part-9 QA instrumentation: stable sub-tab selector, e.g.
        // admin-overview-tab / admin-tenants-rbac-tab (context-scoped action id).
        data-testid={`${context}-${item.actionId}-tab`}
        title={titleAttr}
        onClick={() => onAction?.(item.actionId)}
        className={`${baseCls} ${active
          ? 'surface-3 text-accent-primary border-l-2 border-accent-primary'
          : 'text-secondary hover:surface-2 hover:text-text'}`}
      >
        {iconEl}
        {labelEl}
      </button>
    );
  };

  return (
    <nav aria-label={`${context === 'admin' ? 'Admin' : 'Workspace'} navigation`} className="flex h-full w-full flex-col overflow-y-auto bg-surface-1 py-4 max-md:bg-surface-1/95 max-md:backdrop-blur-xl">
      <div className={`mb-4 flex items-center ${collapsed ? 'justify-center' : 'justify-end'} px-3`}><button type="button" onClick={onToggleCollapsed} className="rounded-lg p-2 text-secondary transition hover:bg-surface-2 hover:text-accent-primary" aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>{collapsed ? <PanelLeft size={16} /> : <PanelLeftClose size={16} />}</button></div>
      <div className="flex-1 px-3 space-y-5">
        {groups.map((group) => (
          <div key={group.id} className="space-y-1">
            {!collapsed && (
              <div className="px-3 mb-2 text-[10px] font-bold text-muted uppercase tracking-widest">
                {group.label}
              </div>
            )}
            {group.items.map(renderEntry)}
          </div>
        ))}
      </div>

      {!collapsed && context === 'admin' && (
        <div className="px-6 border-t border-border pt-4 mt-4">
          <div className="text-[9px] text-muted text-center font-mono">
            CTRL+K for command menu
          </div>
        </div>
      )}
    </nav>
  );
}
