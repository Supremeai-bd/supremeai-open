import type { ProjectFile, VersionSnapshot, InjectedPackage } from '../types/worldclass';

export const INITIAL_PROJECT_FILES: ProjectFile[] = [
  {
    path: 'src/App.tsx',
    name: 'App.tsx',
    language: 'typescript',
    content: `import React, { useState } from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { DishGrid } from './components/DishGrid';
import { CartDrawer } from './components/CartDrawer';

export default function App() {
  const [cartOpen, setCartOpen] = useState(false);
  const [cartCount, setCartCount] = useState(2);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-emerald-500/30 selection:text-emerald-200">
      <Navbar cartCount={cartCount} onOpenCart={() => setCartOpen(true)} />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10">
        <Hero onCtaClick={() => setCartOpen(true)} />
        <DishGrid onAddToCart={() => setCartCount(c => c + 1)} />
      </main>
      <CartDrawer isOpen={cartOpen} onClose={() => setCartOpen(false)} />
    </div>
  );
}`,
  },
  {
    path: 'src/components/Navbar.tsx',
    name: 'Navbar.tsx',
    language: 'typescript',
    content: `import React from 'react';

interface NavbarProps {
  cartCount: number;
  onOpenCart: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ cartCount, onOpenCart }) => {
  return (
    <header className="sticky top-0 z-40 bg-slate-950/80 backdrop-blur-md border-b border-white/[0.08]">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center font-bold text-white shadow-lg shadow-emerald-500/20">
            G
          </div>
          <div>
            <span className="font-bold text-base text-white tracking-tight">Gusteau's Kitchen</span>
            <span className="text-[11px] text-emerald-400 block font-mono">Organic & Farm-to-Table</span>
          </div>
        </div>

        <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-slate-300">
          <a href="#dishes" className="hover:text-emerald-400 transition-colors">Artisan Bowls</a>
          <a href="#pasta" className="hover:text-emerald-400 transition-colors">Handmade Pasta</a>
          <a href="#story" className="hover:text-emerald-400 transition-colors">Our Farms</a>
        </nav>

        <button 
          onClick={onOpenCart}
          className="relative px-4 py-2 bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-xs font-semibold rounded-xl shadow-md shadow-emerald-600/30 transition-all flex items-center gap-2"
        >
          <span>Cart</span>
          <span className="w-5 h-5 rounded-full bg-white text-emerald-950 text-[10px] font-bold flex items-center justify-center font-mono">
            {cartCount}
          </span>
        </button>
      </div>
    </header>
  );
};`,
  },
  {
    path: 'src/components/Hero.tsx',
    name: 'Hero.tsx',
    language: 'typescript',
    content: `import React from 'react';

interface HeroProps {
  onCtaClick: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onCtaClick }) => {
  return (
    <section className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-emerald-950/60 via-slate-900 to-slate-950 border border-white/[0.08] p-8 sm:p-12 shadow-2xl">
      <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
      
      <div className="relative z-10 max-w-2xl space-y-4">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/80 border border-emerald-800/80 text-[11px] font-mono text-emerald-300">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>FAST DELIVERY · 25-35 MINS</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight leading-tight">
          Artisanal Organic Bowls <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-300 to-teal-200">
            Crafted for Pure Health
          </span>
        </h1>

        <p className="text-sm text-slate-300 leading-relaxed max-w-xl">
          Harvested daily from certified organic local growers. Zero artificial additives, cold-pressed dressings, and chef-curated nutrition macros.
        </p>

        <div className="pt-2 flex flex-wrap items-center gap-4">
          <button 
            id="hero-cta"
            onClick={onCtaClick}
            className="px-6 py-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 active:scale-95 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/30 transition-all cursor-pointer"
          >
            Order Hot Bowl Now
          </button>
          <span className="text-xs text-slate-400 font-mono">
            ★ 4.9/5 Rating (1,420+ Reviews)
          </span>
        </div>
      </div>
    </section>
  );
};`,
  },
  {
    path: 'src/components/DishGrid.tsx',
    name: 'DishGrid.tsx',
    language: 'typescript',
    content: `import React from 'react';

interface DishGridProps {
  onAddToCart: () => void;
}

export const DishGrid: React.FC<DishGridProps> = ({ onAddToCart }) => {
  const dishes = [
    {
      id: 1,
      title: 'Pacific Salmon Quinoa Bowl',
      desc: 'Wild-caught salmon, organic tricolor quinoa, Hass avocado, edamame, and toasted sesame ginger vinaigrette.',
      price: '$16.50',
      calories: '540 kcal · 38g Protein',
    },
    {
      id: 2,
      title: 'Truffle Porcini Pappardelle',
      desc: 'Fresh handmade egg pasta, summer black truffle ragu, and 24-month aged Parmigiano Reggiano.',
      price: '$18.00',
      calories: '620 kcal · Vegetarian',
    },
    {
      id: 3,
      title: 'Spiced Crisp Falafel Harvest',
      desc: 'Golden chickpea patties, sumac roasted cauliflower, pickled radishes, and lemon tahini drizzle.',
      price: '$14.00',
      calories: '480 kcal · 100% Vegan',
    },
  ];

  return (
    <section id="dishes" className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white tracking-tight">Today's Curated Harvest</h2>
          <p className="text-xs text-slate-400">Prepared fresh upon order</p>
        </div>
        <span className="text-xs font-mono text-emerald-400 font-semibold">3 Featured Dishes</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {dishes.map((dish) => (
          <div 
            key={dish.id} 
            className="group bg-slate-900/60 hover:bg-slate-900/90 border border-white/[0.08] hover:border-emerald-500/40 rounded-2xl p-5 transition-all duration-300 flex flex-col justify-between shadow-xl"
          >
            <div>
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-bold text-sm text-white group-hover:text-emerald-300 transition-colors">
                  {dish.title}
                </h3>
                <span className="font-mono text-emerald-400 font-bold text-sm">{dish.price}</span>
              </div>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">{dish.desc}</p>
            </div>

            <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
              <span className="text-slate-500 font-mono text-[11px]">{dish.calories}</span>
              <button
                onClick={onAddToCart}
                className="px-3 py-1.5 bg-slate-800 hover:bg-emerald-600 text-slate-200 hover:text-white rounded-lg font-semibold transition-all shadow-sm active:scale-95"
              >
                + Add
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
};`,
  },
  {
    path: 'src/components/CartDrawer.tsx',
    name: 'CartDrawer.tsx',
    language: 'typescript',
    content: `import React from 'react';

interface CartDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CartDrawer: React.FC<CartDrawerProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-fadeIn">
      <div className="w-full max-w-md bg-slate-900 border-l border-white/[0.08] h-full p-6 flex flex-col justify-between shadow-2xl">
        <div>
          <div className="flex items-center justify-between pb-4 border-b border-slate-800">
            <h3 className="font-bold text-base text-white">Your Order (2 items)</h3>
            <button 
              onClick={onClose}
              className="text-slate-400 hover:text-white text-xs font-mono p-1 rounded hover:bg-slate-800"
            >
              [ Close ✕ ]
            </button>
          </div>

          <div className="py-4 space-y-3 text-xs font-mono">
            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center">
              <div>
                <span className="text-white font-sans font-semibold block">Pacific Salmon Bowl</span>
                <span className="text-slate-500 text-[11px]">Qty: 1 · Extra Avocado</span>
              </div>
              <span className="text-emerald-400 font-bold">$16.50</span>
            </div>

            <div className="p-3 bg-slate-950 rounded-xl border border-slate-800 flex justify-between items-center">
              <div>
                <span className="text-white font-sans font-semibold block">Truffle Pappardelle</span>
                <span className="text-slate-500 text-[11px]">Qty: 1 · Regular</span>
              </div>
              <span className="text-emerald-400 font-bold">$18.00</span>
            </div>
          </div>
        </div>

        <div className="pt-4 border-t border-slate-800 space-y-3 text-xs">
          <div className="flex justify-between text-slate-300 font-mono">
            <span>Subtotal</span>
            <span className="text-white font-bold">$34.50</span>
          </div>
          <div className="flex justify-between text-slate-400 font-mono text-[11px]">
            <span>Delivery Fee</span>
            <span className="text-emerald-400">FREE</span>
          </div>
          <button 
            className="w-full py-3 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 active:scale-95 text-slate-950 font-bold rounded-xl shadow-lg shadow-emerald-500/20 transition-all text-xs"
          >
            Proceed to Checkout ($34.50)
          </button>
        </div>
      </div>
    </div>
  );
};`,
  },
  {
    path: 'src/styles/theme.css',
    name: 'theme.css',
    language: 'css',
    content: `@import "tailwindcss";

:root {
  --color-primary: #10b981;
  --color-surface: #030712;
  --glass-border: rgba(255, 255, 255, 0.08);
}

body {
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
  background-color: var(--color-surface);
}`,
  },
];

export const VERSION_SNAPSHOTS: VersionSnapshot[] = [
  {
    id: 'snap-1',
    version: 'v1.0',
    title: 'Initial Food Delivery Architecture',
    timestamp: '4 mins ago',
    author: 'JARVIS Agent',
    summary: 'Initialized responsive layout with Farm-to-Table branding and 3 starter dishes.',
    files: {},
    diffSummary: { added: 142, removed: 0, filesChanged: 3 },
  },
  {
    id: 'snap-2',
    version: 'v1.1',
    title: 'Added Interactive Cart Drawer & Counter',
    timestamp: '3 mins ago',
    author: 'JARVIS Agent',
    summary: 'Mounted sliding Cart Drawer with real-time items count and checkout totals.',
    files: {},
    diffSummary: { added: 68, removed: 4, filesChanged: 2 },
  },
  {
    id: 'snap-3',
    version: 'v1.2',
    title: 'WCAG AA Optical Contrast & Micro-Shadows',
    timestamp: '2 mins ago',
    author: 'Developer',
    summary: 'Enhanced high-contrast emerald gradients and fixed mobile layout constraints.',
    files: {},
    diffSummary: { added: 24, removed: 12, filesChanged: 2 },
  },
  {
    id: 'snap-4',
    version: 'v1.3 (Current)',
    title: 'Deep Space Glassmorphism & Gold Accent Button',
    timestamp: 'Just now',
    author: 'JARVIS Agent',
    summary: 'Injected 3D glass borders, spring transitions, and interactive Click-to-Edit targets.',
    files: {},
    diffSummary: { added: 18, removed: 2, filesChanged: 1 },
  },
];

export const POPULAR_PACKAGES: InjectedPackage[] = [
  {
    name: 'lucide-react',
    version: '0.546.0',
    cdnUrl: 'https://cdn.jsdelivr.net/npm/lucide@latest/dist/umd/lucide.js',
    installed: true,
    category: 'Icons',
  },
  {
    name: 'canvas-confetti',
    version: '1.9.4',
    cdnUrl: 'https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.4/dist/confetti.browser.min.js',
    installed: true,
    category: 'Animation',
  },
  {
    name: 'motion',
    version: '12.23.24',
    cdnUrl: 'https://cdn.jsdelivr.net/npm/motion@12.23.24/dist/motion.js',
    installed: true,
    category: 'Animation',
  },
  {
    name: 'three.js',
    version: '0.170.0',
    cdnUrl: 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.min.js',
    installed: false,
    category: 'UI',
  },
];
