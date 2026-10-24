import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useLocation } from 'react-router-dom';
import { useMobileNav } from '../../hooks/useMobileNav';

export interface DashboardLayoutProps {
  header?: React.ReactNode;
  sidebar?: React.ReactNode;
  children: React.ReactNode;
  isSidebarCollapsed?: boolean;
}

const SIDEBAR_SPRING = { type: 'spring', stiffness: 320, damping: 32 } as const;

export function DashboardLayout({ header, sidebar, children, isSidebarCollapsed = false }: DashboardLayoutProps) {
  // Issue #1526 (LOW): the sidebar used to render at a fixed 256px on every
  // viewport — on phones it swallowed most of the screen and the content
  // overlapped. Below md it now becomes an overlay drawer: closed by default,
  // opened from the header toggle, closed by backdrop tap, Escape, or route
  // change. Desktop (md+) keeps the exact collapse behavior it had.
  const { isMobileNavOpen, setMobileNavOpen } = useMobileNav();
  const location = useLocation();

  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, setMobileNavOpen]);

  useEffect(() => {
    if (!isMobileNavOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileNavOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isMobileNavOpen, setMobileNavOpen]);

  return (
    <div className="dashboard-live-shell surface-0 h-screen w-full flex flex-col overflow-hidden text-text font-sans">
      <div className="dashboard-live-orb dashboard-live-orb-one" aria-hidden="true" />
      <div className="dashboard-live-orb dashboard-live-orb-two" aria-hidden="true" />
      {header && (
        <header className="surface-1 z-30 shrink-0">
          {header}
        </header>
      )}

      <div className="flex-1 flex overflow-hidden relative">
        {sidebar && (
          <motion.aside
            initial={false}
            animate={{ width: isSidebarCollapsed ? 64 : 256 }}
            transition={SIDEBAR_SPRING}
            className="surface-1 border-r border-border hidden md:flex flex-col z-20 shrink-0 overflow-hidden"
          >
            {sidebar}
          </motion.aside>
        )}

        {/* Issue #1526: mobile overlay drawer — rendered only below md while open */}
        <AnimatePresence>
          {sidebar && isMobileNavOpen && (
            <>
              <motion.div
                key="mobile-nav-backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.18 }}
                onClick={() => setMobileNavOpen(false)}
                className="fixed inset-0 z-30 bg-black/60 md:hidden"
                aria-hidden="true"
              />
              <motion.aside
                key="mobile-nav-drawer"
                initial={{ x: '-100%' }}
                animate={{ x: 0 }}
                exit={{ x: '-100%' }}
                transition={SIDEBAR_SPRING}
                className="surface-1 border-r border-border fixed inset-y-0 left-0 z-40 flex flex-col w-64 max-w-[85vw] overflow-hidden md:hidden"
                aria-label="Navigation drawer"
              >
                {sidebar}
              </motion.aside>
            </>
          )}
        </AnimatePresence>

        <main className="flex-1 min-w-0 overflow-hidden relative z-10 flex flex-col">
          {children}
        </main>
      </div>
    </div>
  );
}
