// SupremeAI — ThemePicker (#4138 Phase 1 follow-up)
// বাংলা মন্তব্য: GlobalHeader-এর আগের একক toggle-বাটন ৮টি থিমে "সাইকেল" করত —
// পছন্দের থিমে পৌঁছাতে ৮বার ক্লিক লাগত। এখন dropdown থেকে সরাসরি যেকোনো থিম
// বেছে নেওয়া যায়। নাম-তালিকার SSOT = ThemeConstants.THEME_META (label/isDark);
// এখানে কোনো থিম-নাম হার্ডকোড নেই — নতুন থিম যোগ হলে এই মেনু নিজেই বড় হবে।
//
// ডিজাইন-সিদ্ধান্ত (repo convention):
// - নিজস্ব dropdown-primitive নেই (নতুন dep/parallel system নয়) — GlobalHeader-র
//   profile/notif dropdown-এর একই প্যাটার্ন: relative container + absolute panel
//   + document mousedown (নিজস্ব ref-scoped listener, unmount-এ cleanup)।
// - lucide-react icons (react-icons নয় — codebase convention)।
// - swatch রং presentation-only, লোকাল — এগুলো "লক্ষ্য-থিমের পরিচয়", সক্রিয়
//   থিমের CSS-var অনুসরণ করবে না, তাই static hex ইচ্ছাকৃত।
// - a11y: role="menu"/"menuitemradio" + aria-checked + Escape-বন্ধ + focus-return।

import React, { useEffect, useRef, useState } from 'react';
import { Check, Palette } from 'lucide-react';
import { useTheme } from '../../contexts/useTheme';
import { THEME_META, THEME_ORDER } from '../../contexts/ThemeConstants';
import type { Theme } from '../../contexts/ThemeConstants';

/** বাংলা: প্রতিটি থিমের পরিচয়-সোয়াচ (মেনুতে রঙ-বিন্দু) — শুধু দেখার জন্য। */
const THEME_SWATCH: Record<Theme, string> = {
  dark: '#0e1420',
  light: '#f8fafc',
  synthwave: '#ff2e88',
  cyberpunk: '#f9d423',
  minimal: '#e2e8f0',
  sunset: '#f97316',
  matrix: '#22c55e',
  emerald: '#10b981',
};

export function ThemePicker() {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  // বাংলা: বাইরে ক্লিক বা Escape চাপলে বন্ধ — listener প্রতি mount-এ একবারই,
  // cleanup-সহ (GlobalHeader-র dropdown প্যাটার্নের মতোই)।
  useEffect(() => {
    if (!open) return;
    const onDocMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        triggerRef.current?.focus(); // focus ফেরত — keyboard-user হারিয়ে যায় না
      }
    };
    document.addEventListener('mousedown', onDocMouseDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const activeMeta = THEME_META[theme];

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Theme: ${activeMeta?.label ?? theme}. Choose theme`}
        title="Choose theme"
        className="h-9 w-9 rounded-lg hover:surface-2 text-secondary hover:text-text flex items-center justify-center transition-colors"
      >
        <Palette size={17} />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Color themes"
          className="absolute right-0 mt-2 w-52 rounded-xl border border-border bg-surface-2 shadow-xl z-modal overflow-hidden py-1"
        >
          {THEME_ORDER.map((t) => {
            const meta = THEME_META[t];
            const isActive = t === theme;
            return (
              <button
                key={t}
                type="button"
                role="menuitemradio"
                aria-checked={isActive}
                onClick={() => {
                  setTheme(t);
                  setOpen(false);
                  triggerRef.current?.focus();
                }}
                className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm transition-colors ${
                  isActive ? 'text-text bg-surface-3' : 'text-secondary hover:surface-3 hover:text-text'
                }`}
              >
                <span
                  aria-hidden="true"
                  className="h-3.5 w-3.5 shrink-0 rounded-full border border-border"
                  style={{ backgroundColor: THEME_SWATCH[t] }}
                />
                <span className="flex-1 text-left">{meta.label}</span>
                {isActive && <Check size={14} aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
