---
name: zero-auth-ui-engine
description: Design, prototype, and build production UI components locally without any external accounts, login, or cloud API keys. Covers shadcn/ui patterns, Tailwind CSS animations, Radix primitives, glassmorphism, responsive dashboards, and interactive mock state.
---

# Zero-Auth Local UI Engine

This skill equips Antigravity to build high-end Web and Desktop UIs directly in your workspace with **zero logins, zero API tokens, and zero cloud subscriptions required**.

## 🚀 1. What This Skill Delivers (Completely Offline & Free)
1. **Shadcn/UI & Radix-Style Primitives:** Accessible, headless, and styled modal, drawer, tabs, accordion, popover, and dropdown components.
2. **Interactive Mock State:** Realistic clientside state simulation (simulated latency, live pagination, optimistic updates, toggleable themes) without needing an external database.
3. **Tailwind CSS Aesthetic Kits:**
   - Dark Cyberdeck / Glassmorphic surfaces (`backdrop-blur-md bg-zinc-950/70 border border-white/10`).
   - Clean SaaS / Minimalist light & dark palettes.
   - Smooth status indicators and pulsating telemetry pills.
4. **Lucide Icon Integration:** Pre-mapped standard SVG icons with semantic labeling and zero layout shift.

---

## 🎨 2. Quick Component Recipes (Copy-Paste Ready)

### A. Glassmorphic Stat / Metric Card
```tsx
export function MetricCard({ label, value, change, isPositive }: { label: string; value: string; change: string; isPositive: boolean }) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-white/10 bg-zinc-900/60 p-5 backdrop-blur-xl transition-all duration-200 hover:border-white/20 hover:shadow-lg">
      <div className="text-xs font-medium uppercase tracking-wider text-zinc-400">{label}</div>
      <div className="mt-2 text-3xl font-bold tracking-tight text-white">{value}</div>
      <div className={`mt-2 inline-flex items-center text-xs font-semibold ${isPositive ? 'text-emerald-400' : 'text-rose-400'}`}>
        {isPositive ? '↑' : '↓'} {change} <span className="ml-1 text-zinc-500 font-normal">vs last cycle</span>
      </div>
    </div>
  );
}
```

### B. Segmented Navigation Bar
```tsx
export function SegmentedTabs<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  active: T;
  onChange: (id: T) => void;
}) {
  return (
    <div className="inline-flex rounded-xl border border-white/10 bg-black/40 p-1 backdrop-blur-md">
      {tabs.map((tab) => {
        const isActive = active === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`rounded-lg px-4 py-1.5 text-xs font-medium transition-all duration-150 ${
              isActive
                ? 'bg-emerald-500 text-black shadow-sm font-semibold'
                : 'text-zinc-400 hover:text-white hover:bg-white/5'
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
```

### C. Zero-Dependency Modal / Dialog
```tsx
export function Dialog({
  isOpen,
  onClose,
  title,
  children,
}: {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm transition-opacity" onClick={onClose} />
      {/* Dialog Box */}
      <div className="relative w-full max-w-lg rounded-2xl border border-white/15 bg-zinc-900 p-6 shadow-2xl backdrop-blur-2xl">
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="rounded-lg p-1 text-zinc-400 hover:bg-white/10 hover:text-white">✕</button>
        </div>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}
```

---

## 🛠️ 3. Rules & Best Practices
- **No External CDN/Auth:** Never inject remote third-party scripts that require an account. Use local npm packages or inline SVG/Tailwind styles.
- **Immediate Preview:** Code should be immediately runnable in Vite (`npm run dev`) or local preview without setting environment credentials.

