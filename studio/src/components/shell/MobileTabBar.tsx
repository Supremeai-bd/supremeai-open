// SupremeAI — MobileTabBar (verified 2026-10-25 frontend report, P1 wave item 4)
// বাংলা মন্তব্য: মোবাইল বটম ট্যাব বার — থাম্ব-রিচ প্রাইমারি নেভিগেশন (রিপোর্ট §3:
// মোবাইল নেভ এখন ডেস্কটপ সাইডবারের ড্রয়ার-ক্লোন, বটম ট্যাব বার নেই)।
//
// এটি দ্বিতীয় কোনো nav definition নয় (roadmap Rule 8/§11): এন্ট্রি হুবহু
// RoleAwareNavRail-এর মতোই getNavigationForContext('user') থেকে derive হয় —
// মালিকানা-সিদ্ধান্ত (2026-10-24, 3-tab progressive disclosure) অনুযায়ী আজ
// Chat/Profile/Settings রেন্ডার হয়। রিপোর্টের ৫-স্তর-১ টার্গেটে গেলে কেবল
// registry/SIMPLE_VIEWER_ENTRY_IDS আপডেট করলেই বার অটো-ফলো করবে
// (ক্যাপাসিটি: ৪ ট্যাব + More = ৫ স্লট; বাকি এন্ট্রি More → ড্রয়ার = স্তর ২)।
//
// Admin context-এ বার নেই — রিপোর্ট §6.1 অনুযায়ী admin আলাদা role-shell;
// ২৫+ action subtab (route নয়, context-switch) ট্যাব-বার মডেলে খাপছাড়া।
// Admin-এর মোবাইল সারফেস আজও হেডার-টগল → ড্রয়ার (অপরিবর্তিত)।

import React from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MoreHorizontal } from 'lucide-react';
import { getNavigationForContext } from '../../config/navigationRegistry';
import { useAuthStore } from '../../store/authStore';
import { useWorkspaceSettings } from '../../hooks/useWorkspaceSettings';
import { useMobileNav } from '../../hooks/useMobileNav';
import { getCanonicalRole } from '../../auth/identity';

export function MobileTabBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const role = useAuthStore((state) => state.role);
  const permissions = useAuthStore((state) => state.permissions);
  const enabledModules = useWorkspaceSettings((state) => state.enabledModules);
  const setMobileNavOpen = useMobileNav((state) => state.setMobileNavOpen);

  // RoleAwareNavRail-এর acquisition + filtering semantics হুবহু (একক truth)।
  const routeTabs = getNavigationForContext('user', {
    role: role || getCanonicalRole(),
    permissions,
  })
    .flatMap((group) => group.items)
    .filter((item) => item.kind === 'route')
    .filter((item) => item.id !== 'nav-ide' || enabledModules.includes('code'))
    .slice(0, 4);

  // Rail-এর active semantics হুবহু — exact match, অথবা non-root path prefix।
  const isRouteActive = (path: string) =>
    location.pathname === path || (path !== '/workspace' && location.pathname.startsWith(path));

  const tabCls = (active: boolean) =>
    `flex min-h-[3.5rem] flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300/60 ${
      active ? 'text-accent-primary' : 'text-secondary hover:text-text'
    }`;

  return (
    <nav
      aria-label="Mobile navigation"
      data-testid="mobile-tab-bar"
      className="surface-1 border-t border-border fixed inset-x-0 bottom-0 z-30 flex md:hidden pb-[env(safe-area-inset-bottom)]"
    >
      {routeTabs.map((item) => {
        if (item.kind !== 'route') return null;
        const active = isRouteActive(item.path);
        return (
          <Link
            key={item.id}
            to={item.path}
            data-testid={`mobile-tab-${item.id}`}
            aria-current={active ? 'page' : undefined}
            onClick={(event) => {
              event.preventDefault();
              navigate(item.path);
            }}
            className={tabCls(active)}
          >
            <item.icon size={20} aria-hidden="true" />
            <span>{item.label}</span>
          </Link>
        );
      })}
      <button
        type="button"
        data-testid="mobile-tab-more"
        onClick={() => setMobileNavOpen(true)}
        className={tabCls(false)}
      >
        <MoreHorizontal size={20} aria-hidden="true" />
        <span>More</span>
      </button>
    </nav>
  );
}
