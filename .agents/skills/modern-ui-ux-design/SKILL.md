---
name: modern-ui-ux-design
description: Design and implement high-aesthetic, production-grade Web and Desktop UIs using Tailwind CSS, React 19, Lucide icons, glassmorphism, fluid typography, dark/light modes, micro-interactions, and responsive layouts. Use whenever crafting dashboards, landing pages, component libraries, or visual polish.
---

# Modern UI/UX Design & Component Crafting Skill

This skill provides design systems, component blueprints, and styling standards for SupremeAI web and desktop products.

## 🎨 1. Core Visual Principles
- **Atmospheric Depth:** Layered surfaces using subtle borders (`border-white/10` or `border-zinc-800`), glassmorphic backdrops (`backdrop-blur-md bg-zinc-950/70`), and radial gradients.
- **Visual Hierarchy & Typography:** High-contrast headings, muted secondary labels (`text-zinc-400`), tight uppercase badges (`text-xs font-semibold tracking-wider uppercase`).
- **Tactile Micro-Interactions:** Subtle scale transitions on hover (`active:scale-95 transition-all duration-150`), smooth status glows, and focused rings for keyboard accessibility.
- **Fluid Layouts:** Flex and CSS Grid with resilient defaults, zero horizontal overflow, and auto-collapsing sidebars for compact desktop or mobile views.

## 🧩 2. Standard SupremeAI Component Tokens

### Surface & Cards
```tsx
<div className="rounded-xl border border-white/10 bg-zinc-900/60 p-5 shadow-2xl backdrop-blur-md transition-all hover:border-white/20">
  {/* Content */}
</div>
```

### Action Buttons
```tsx
// Primary CTA
<button className="flex items-center gap-2 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-medium text-black transition-all hover:bg-emerald-400 active:scale-95">
  <Play className="h-4 w-4" /> Run Action
</button>

// Subtle Secondary
<button className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-sm font-medium text-zinc-300 hover:bg-white/10 active:scale-95">
  Cancel
</button>
```

### Status & Live Telemetry Pills
```tsx
<span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2.5 py-0.5 text-xs font-medium text-emerald-400">
  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
  Live System
</span>
```

## 📐 3. Rules to Always Follow
1. **No Layout Clutter:** Prioritize whitespace; separate content decks using tabs or segmented pills instead of one endless vertical list.
2. **Accessible Contrast:** Never use low-contrast text on dark backgrounds (minimum 4.5:1 ratio).
3. **Responsive by Default:** Always handle small viewport widths (`w-full overflow-hidden`, scroll areas with custom styled scrollbars).

