---
name: css-animation-fx
description: Create zero-dependency pure CSS and Tailwind micro-animations, loading states, shimmer skeletons, particle effects, holographic glows, and interactive hover transitions without any external libraries or login credentials.
---

# Pure CSS & Tailwind Animation FX (Zero-Login / Zero-Dependency)

This skill enables creating slick modern UI animations and visual feedback purely using native CSS and Tailwind classes.

## ✨ 1. Key Animation Patterns

### A. Holographic Pulse Glow (Cyberpunk / Futuristic AI State)
```html
<div className="relative flex items-center justify-center">
  <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-emerald-500 to-cyan-500 opacity-75 blur-md animate-pulse"></div>
  <div className="relative rounded-full bg-zinc-950 p-4 ring-1 ring-white/20">
    <!-- Icon or Avatar -->
  </div>
</div>
```

### B. Shimmer Loading Skeleton
```html
<div className="relative overflow-hidden rounded-lg bg-zinc-800/60 p-4">
  <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent"></div>
  <div className="h-4 w-3/4 rounded bg-zinc-700/50"></div>
  <div className="mt-2 h-3 w-1/2 rounded bg-zinc-700/30"></div>
</div>
```

### C. Floating Hologram Effect (Subtle Hover Wave)
```css
@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-6px); }
}

.animate-float {
  animation: float 3.5s ease-in-out infinite;
}
```

---

## 🎯 Usage
Use this whenever crafting AI chat avatars, loading screens, telemetry radars, or interactive buttons to make the UI look high-budget and responsive without installing bulky 3D or animation runtimes.

