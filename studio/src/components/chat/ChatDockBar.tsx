/**
 * ChatDockBar — RC-3 root fix (frontend research report §6.4 / Table 8 P1).
 *
 * ডকড অ্যাকশন বার: চ্যাট শেলের নিচে স্থায়ী, in-flow অংশ — চ্যাট প্যানেলের
 * একই গ্রিডে (max-w-[46rem] কলাম) বাউন্ডেড। fixed/floating নয়, তাই ১৩৬৬px
 * ল্যাপটপেও কম্পোজারের ওপর চাপিয়ে পড়ার সম্ভাবনাই নেই (flex flow এটা
 * স্ট্রাকচারালি অসম্ভব করে দেয়)।
 *
 * Layout (report §6.4): left = Jarvis mini-orb (state-dot সহ), middle =
 * প্রসঙ্গভিত্তিক অ্যাকশন (contextual, consumer-supplied), right = Apps-মেনু
 * (user-published overlay — কোনো অটো-পপআপ নেই)।
 *
 * z-policy (report §6.4 three buckets): this bar is shell-layer and stays
 * IN FLOW (no fixed positioning, no z of its own); the Apps popover is
 * user-published and sits at z-30 — strictly below the z-40+ overlay bucket.
 *
 * Touch targets: every interactive element is 44×44px minimum (WCAG 2.2
 * target-size / report §7.2).
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { LayoutGrid } from 'lucide-react';

export interface DockAction {
  id: string;
  label: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
}

export interface DockApp {
  id: string;
  label: string;
  /** react-router path (in-app navigation) */
  to: string;
  description?: string;
}

interface ChatDockBarProps {
  /** Left slot — Jarvis mini-orb (or any branding element). */
  left?: React.ReactNode;
  /** Middle contextual actions (e.g. preview/mobile toggle in AIStudio). */
  actions?: DockAction[];
  /** Right Apps menu entries. Menu hides when empty/omitted. */
  apps?: DockApp[];
}

export const ChatDockBar: React.FC<ChatDockBarProps> = ({ left, actions = [], apps = [] }) => {
  const [appsOpen, setAppsOpen] = React.useState(false);
  const appsBtnRef = React.useRef<HTMLButtonElement>(null);

  /* Esc closes the user-published popover and returns focus to the trigger. */
  React.useEffect(() => {
    if (!appsOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setAppsOpen(false);
        appsBtnRef.current?.focus();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [appsOpen]);

  const hasApps = apps.length > 0;

  return (
    // একই গ্রিড: model row + message list + composer সব max-w-[46rem] — ডকও সেটাই।
    <div
      data-testid="chat-dock-bar"
      className="relative mx-auto flex h-11 w-full max-w-[46rem] shrink-0 items-center gap-1.5"
    >
      {left && <div className="flex items-center gap-1.5">{left}</div>}
      {/* middle: contextual actions centered in the remaining space */}
      <div className="flex min-w-0 flex-1 items-center justify-center gap-1">
        {actions.map(({ id, label, icon: Icon, onClick, disabled, title }) => (
          <button
            key={id}
            type="button"
            onClick={onClick}
            disabled={disabled}
            title={title ?? label}
            aria-label={label}
            data-testid={`dock-action-${id}`}
            className="flex h-11 min-w-[44px] items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/70 px-2.5 text-xs font-medium text-slate-300 transition hover:border-purple-400/40 hover:bg-slate-800 hover:text-white disabled:opacity-50"
          >
            <Icon size={16} className="text-slate-400" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>
      {/* right: Apps menu (user-published overlay) */}
      {hasApps && (
        <div className="relative flex items-center">
          {appsOpen && (
            // click-catcher: transparent, closes on any outside click
            <div
              aria-hidden="true"
              className="fixed inset-0 z-20"
              onClick={() => setAppsOpen(false)}
            />
          )}
          <button
            ref={appsBtnRef}
            type="button"
            onClick={() => setAppsOpen((v) => !v)}
            aria-haspopup="menu"
            aria-expanded={appsOpen}
            aria-label="Open Apps menu"
            data-testid="dock-apps-button"
            className="flex h-11 min-w-[44px] items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-slate-900/70 px-2.5 text-xs font-medium text-slate-300 transition hover:border-purple-400/40 hover:bg-slate-800 hover:text-white"
          >
            <LayoutGrid size={16} className="text-slate-400" />
            <span className="hidden sm:inline">Apps</span>
          </button>
          {appsOpen && (
            <div
              role="menu"
              aria-label="Apps"
              data-testid="dock-apps-menu"
              className="absolute bottom-full right-0 z-30 mb-2 w-64 overflow-hidden rounded-xl border border-white/10 bg-[#0d121f]/95 shadow-2xl shadow-black/50 backdrop-blur-xl"
            >
              {apps.map((app) => (
                <Link
                  key={app.id}
                  to={app.to}
                  role="menuitem"
                  onClick={() => setAppsOpen(false)}
                  className="block border-b border-white/5 px-3 py-2.5 transition last:border-b-0 hover:bg-white/[0.04]"
                >
                  <span className="block text-sm font-medium text-slate-200">{app.label}</span>
                  {app.description && (
                    <span className="mt-0.5 block text-xs leading-5 text-slate-500">{app.description}</span>
                  )}
                </Link>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ChatDockBar;
