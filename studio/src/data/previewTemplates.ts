export interface PreviewTemplate {
  id: string;
  nameBn: string;
  nameEn: string;
  category: string;
  tag: string;
  html: string;
}

export const PREVIEW_TEMPLATES: PreviewTemplate[] = [
  {
    id: 'food-delivery',
    nameBn: 'ফুড ডেলিভারি ও রেস্তোরাঁ প্ল্যাটফর্ম',
    nameEn: 'Artisan Food Delivery Web App',
    category: 'E-Commerce & Food',
    tag: 'Popular',
    html: `
<div class="max-w-4xl mx-auto p-4 sm:p-6 space-y-6">
  <!-- Top Navigation -->
  <header class="flex items-center justify-between pb-4 border-b border-slate-800">
    <div class="flex items-center gap-2">
      <div class="w-8 h-8 rounded-lg bg-emerald-600 flex items-center justify-center font-bold text-white text-sm">G</div>
      <div>
        <span class="font-bold text-lg text-white tracking-tight">Gusteau's Kitchen</span>
        <span class="text-[10px] text-emerald-400 block font-mono">Organic & Farm-to-Table</span>
      </div>
    </div>
    <div class="flex items-center gap-3 text-xs">
      <span class="text-emerald-400 font-semibold font-mono">● 25-35 min delivery</span>
      <button class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg transition-colors shadow-sm">
        Order Now
      </button>
    </div>
  </header>

  <!-- Hero Banner -->
  <div class="relative bg-gradient-to-r from-emerald-950/80 via-slate-900 to-slate-950 border border-emerald-900/40 rounded-2xl p-6 sm:p-8 overflow-hidden shadow-2xl">
    <div class="space-y-3 max-w-lg">
      <div class="inline-flex items-center gap-2 px-2.5 py-0.5 rounded-full bg-emerald-950 border border-emerald-800 text-[10px] font-mono text-emerald-400 uppercase tracking-widest">
        <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
        Farm-to-Table Experience
      </div>
      <h1 class="text-2xl sm:text-4xl font-extrabold text-white tracking-tight leading-tight">Fresh Hand-Crafted Bowls & Organic Pasta</h1>
      <p class="text-xs sm:text-sm text-slate-300 leading-relaxed">Artisanal cuisine prepared with 100% locally sourced organic ingredients and delivered hot to your doorstep.</p>
      <div class="pt-2">
        <button id="hero-order-cta" class="px-5 py-2.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-slate-950 font-bold text-xs rounded-xl shadow-lg shadow-emerald-500/20 active:scale-95 transition-all">
          Order Hot Bowl Now
        </button>
      </div>
    </div>
  </div>

  <!-- Menu Filter Bar -->
  <div class="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
    <button class="px-3.5 py-1.5 bg-emerald-600 text-white font-semibold rounded-lg shrink-0">All Dishes (18)</button>
    <button class="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg shrink-0 border border-slate-800">Fresh Bowls</button>
    <button class="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg shrink-0 border border-slate-800">Handmade Pasta</button>
    <button class="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg shrink-0 border border-slate-800">Artisan Beverages</button>
  </div>

  <!-- Dish Cards Grid -->
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    <div class="bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex flex-col justify-between transition-colors">
      <div>
        <div class="flex justify-between items-start mb-2">
          <h3 class="font-bold text-sm text-white">Wild Salmon Quinoa Bowl</h3>
          <span class="font-mono text-emerald-400 font-bold text-sm">$16.50</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed mb-3">Pacific wild-caught salmon, organic tricolor quinoa, Hass avocado, edamame, and toasted sesame ginger vinaigrette.</p>
      </div>
      <div class="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
        <span class="text-slate-500 font-mono">540 kcal · 38g Protein</span>
        <button class="px-2.5 py-1 bg-slate-800 hover:bg-emerald-600 text-white rounded font-medium transition-colors">+ Add</button>
      </div>
    </div>

    <div class="bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex flex-col justify-between transition-colors">
      <div>
        <div class="flex justify-between items-start mb-2">
          <h3 class="font-bold text-sm text-white">Truffle Pappardelle Pasta</h3>
          <span class="font-mono text-emerald-400 font-bold text-sm">$18.00</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed mb-3">Freshly rolled egg pappardelle with wild porcini ragu, 24-month aged Parmigiano Reggiano, and black summer truffle oil.</p>
      </div>
      <div class="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
        <span class="text-slate-500 font-mono">620 kcal · Vegetarian</span>
        <button class="px-2.5 py-1 bg-slate-800 hover:bg-emerald-600 text-white rounded font-medium transition-colors">+ Add</button>
      </div>
    </div>

    <div class="bg-slate-900/70 border border-slate-800 hover:border-slate-700 rounded-xl p-4 flex flex-col justify-between transition-colors">
      <div>
        <div class="flex justify-between items-start mb-2">
          <h3 class="font-bold text-sm text-white">Mediterranean Falafel Bowl</h3>
          <span class="font-mono text-emerald-400 font-bold text-sm">$14.00</span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed mb-3">Crisp chickpea falafel patties, roasted sumac cauliflower, pickled turnips, lemon tahini drizzle, and warm pita wedges.</p>
      </div>
      <div class="flex items-center justify-between pt-3 border-t border-slate-800/80 text-xs">
        <span class="text-slate-500 font-mono">480 kcal · 100% Vegan</span>
        <button class="px-2.5 py-1 bg-slate-800 hover:bg-emerald-600 text-white rounded font-medium transition-colors">+ Add</button>
      </div>
    </div>
  </div>
</div>
`
  },
  {
    id: 'saas-glassmorphism',
    nameBn: 'SaaS ল্যান্ডিং পেজ (গ্লাসমরফিজম)',
    nameEn: 'SaaS Landing Page with Glassmorphism Header',
    category: 'Landing & SaaS',
    tag: 'Tier 1 Mandate',
    html: `
<div class="max-w-4xl mx-auto p-4 sm:p-6 space-y-8 font-sans">
  <!-- Top Glassmorphism Nav -->
  <header class="sticky top-0 z-30 bg-slate-900/70 backdrop-blur-xl border border-white/[0.1] rounded-2xl px-5 py-3 flex items-center justify-between shadow-xl">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-500 to-purple-500 flex items-center justify-center text-white font-bold text-sm shadow-md shadow-indigo-500/30">
        ⚡
      </div>
      <span class="font-bold text-base text-white tracking-tight">Krypton AI</span>
    </div>
    <nav class="hidden md:flex items-center gap-6 text-xs font-medium text-slate-300">
      <a href="#features" class="hover:text-indigo-400 transition-colors">Platform</a>
      <a href="#benchmarks" class="hover:text-indigo-400 transition-colors">Benchmarks</a>
      <a href="#enterprise" class="hover:text-indigo-400 transition-colors">Enterprise</a>
      <a href="#pricing" class="hover:text-indigo-400 transition-colors">Pricing</a>
    </nav>
    <div class="flex items-center gap-2">
      <button class="px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white transition-colors">Sign in</button>
      <button id="saas-cta" class="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold rounded-xl transition-all shadow-md shadow-indigo-600/30 active:scale-95">
        Start Free Trial
      </button>
    </div>
  </header>

  <!-- Hero Section -->
  <section class="text-center space-y-4 py-8 relative">
    <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/80 border border-indigo-700/60 text-xs font-mono text-indigo-300 mb-2">
      <span class="w-2 h-2 rounded-full bg-indigo-400 animate-ping"></span>
      <span>INTRODUCING AUTONOMOUS AGENTS V3.0</span>
    </div>
    <h1 class="text-3xl sm:text-5xl font-extrabold text-white tracking-tight leading-tight max-w-2xl mx-auto">
      The Intelligent Cockpit for <br/>
      <span class="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-300 to-pink-400">
        Frontier Engineering Teams
      </span>
    </h1>
    <p class="text-xs sm:text-sm text-slate-400 max-w-xl mx-auto leading-relaxed">
      Federate 140+ MCP micro-tools, automate continuous code deployment to Cloudflare Edge, and inspect runtime DOM trees in seconds.
    </p>
    <div class="flex items-center justify-center gap-3 pt-3">
      <button class="px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-indigo-600/30 transition-all active:scale-95">
        Claim 14-Day Free Sandbox
      </button>
      <button class="px-5 py-3 bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-800 font-semibold text-xs rounded-xl transition-colors">
        View Live Interactive Demo →
      </button>
    </div>
  </section>

  <!-- Ticker Metrics -->
  <div class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
    <div class="p-4 bg-slate-900/60 rounded-2xl border border-white/[0.08] backdrop-blur-sm">
      <span class="text-slate-500 block font-sans">Active Federation Nodes</span>
      <span class="text-2xl font-bold text-white tabular-nums">1,480+</span>
      <span class="text-[10px] text-emerald-400 block mt-1">● 99.99% Uptime</span>
    </div>
    <div class="p-4 bg-slate-900/60 rounded-2xl border border-white/[0.08] backdrop-blur-sm">
      <span class="text-slate-500 block font-sans">Time to First Byte</span>
      <span class="text-2xl font-bold text-indigo-400 tabular-nums">28ms</span>
      <span class="text-[10px] text-emerald-400 block mt-1">● Global Anycast</span>
    </div>
    <div class="p-4 bg-slate-900/60 rounded-2xl border border-white/[0.08] backdrop-blur-sm">
      <span class="text-slate-500 block font-sans">Autonomous PR Solves</span>
      <span class="text-2xl font-bold text-white tabular-nums">42,910</span>
      <span class="text-[10px] text-purple-400 block mt-1">● Zero human friction</span>
    </div>
    <div class="p-4 bg-slate-900/60 rounded-2xl border border-white/[0.08] backdrop-blur-sm">
      <span class="text-slate-500 block font-sans">Cost Efficiency</span>
      <span class="text-2xl font-bold text-emerald-400 tabular-nums">84%</span>
      <span class="text-[10px] text-slate-400 block mt-1">● vs Legacy Clouds</span>
    </div>
  </div>
</div>
`
  },
  {
    id: 'fintech-analytics',
    nameBn: 'রিয়েলটাইম ফিনান্সিয়াল অ্যানালিটিক্স',
    nameEn: 'Realtime Financial Analytics Chart',
    category: 'Finance & Trading',
    tag: 'Tier 1 Mandate',
    html: `
<div class="max-w-4xl mx-auto p-4 sm:p-6 space-y-6 font-mono text-xs">
  <!-- Header Bar -->
  <div class="flex items-center justify-between pb-4 border-b border-slate-800">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-emerald-950 border border-emerald-700/60 flex items-center justify-center font-bold text-emerald-400 text-sm">
        $
      </div>
      <div>
        <h2 class="text-sm font-bold text-white tracking-tight font-sans">Apex Liquidity Terminal</h2>
        <span class="text-[10px] text-slate-400">Order Routing: London LND-4 · FIX 4.4 Engine</span>
      </div>
    </div>
    <div class="flex items-center gap-2">
      <span class="px-2 py-0.5 rounded text-[11px] bg-emerald-950 text-emerald-400 border border-emerald-800">LIVE FEED</span>
      <span class="text-slate-400 text-[11px] tabular-nums">14:28:44 UTC</span>
    </div>
  </div>

  <!-- Portfolio Metric Cards -->
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
    <div class="p-4 bg-slate-900/80 rounded-xl border border-slate-800">
      <span class="text-slate-400 block font-sans text-[11px]">Total Net Liquidity</span>
      <span class="text-2xl font-bold text-white tabular-nums tracking-tight font-mono">$1,842,950.40</span>
      <span class="text-[10px] text-emerald-400 block mt-1">▲ +$48,120.00 (+2.68%) 24h</span>
    </div>
    <div class="p-4 bg-slate-900/80 rounded-xl border border-slate-800">
      <span class="text-slate-400 block font-sans text-[11px]">Unrealized P&L</span>
      <span class="text-2xl font-bold text-emerald-400 tabular-nums tracking-tight font-mono">+$184,320.15</span>
      <span class="text-[10px] text-slate-400 block mt-1">Margin Utilization: 24.2%</span>
    </div>
    <div class="p-4 bg-slate-900/80 rounded-xl border border-slate-800">
      <span class="text-slate-400 block font-sans text-[11px]">Sharpe Ratio</span>
      <span class="text-2xl font-bold text-indigo-400 tabular-nums tracking-tight font-mono">3.42</span>
      <span class="text-[10px] text-emerald-400 block mt-1">Max Drawdown: -1.8%</span>
    </div>
  </div>

  <!-- Candlestick Visualizer Mock Frame -->
  <div class="p-4 bg-slate-900/90 rounded-2xl border border-slate-800 space-y-3">
    <div class="flex items-center justify-between text-[11px]">
      <div class="flex items-center gap-3">
        <span class="font-bold text-white text-xs">BTC/USD PERP</span>
        <span class="text-emerald-400 font-bold">$68,420.50</span>
        <span class="text-slate-500">Vol: $4.2B</span>
      </div>
      <div class="flex gap-1 text-[10px]">
        <button class="px-2 py-0.5 rounded bg-slate-800 text-white">1m</button>
        <button class="px-2 py-0.5 rounded bg-indigo-600 text-white font-bold">5m</button>
        <button class="px-2 py-0.5 rounded bg-slate-800 text-slate-400">1h</button>
        <button class="px-2 py-0.5 rounded bg-slate-800 text-slate-400">1D</button>
      </div>
    </div>

    <!-- Trend Visual Bars -->
    <div class="h-36 flex items-end gap-1.5 pt-4 border-b border-slate-800/80 px-2">
      <div class="flex-1 bg-emerald-500/40 hover:bg-emerald-400 rounded-t h-[40%] transition-all"></div>
      <div class="flex-1 bg-emerald-500/60 hover:bg-emerald-400 rounded-t h-[55%] transition-all"></div>
      <div class="flex-1 bg-rose-500/50 hover:bg-rose-400 rounded-t h-[45%] transition-all"></div>
      <div class="flex-1 bg-emerald-500/70 hover:bg-emerald-400 rounded-t h-[68%] transition-all"></div>
      <div class="flex-1 bg-emerald-500/80 hover:bg-emerald-400 rounded-t h-[82%] transition-all"></div>
      <div class="flex-1 bg-rose-500/60 hover:bg-rose-400 rounded-t h-[60%] transition-all"></div>
      <div class="flex-1 bg-emerald-500/90 hover:bg-emerald-400 rounded-t h-[92%] transition-all"></div>
      <div class="flex-1 bg-emerald-400 rounded-t h-[100%] shadow-lg shadow-emerald-500/20"></div>
    </div>

    <div class="flex justify-between text-[10px] text-slate-500">
      <span>14:00</span>
      <span>14:10</span>
      <span>14:20</span>
      <span>14:30 (Current)</span>
    </div>
  </div>
</div>
`
  },
  {
    id: 'kanban-workflow',
    nameBn: 'ইন্টারঅ্যাক্টিভ কানবান ওয়ার্কফ্লো',
    nameEn: 'Interactive KanBan Workflow Board',
    category: 'Productivity & Agile',
    tag: 'Tier 1 Mandate',
    html: `
<div class="max-w-4xl mx-auto p-4 sm:p-6 space-y-5 font-sans">
  <!-- KanBan Header -->
  <div class="flex items-center justify-between pb-3 border-b border-slate-800">
    <div class="flex items-center gap-3">
      <div class="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center font-bold text-white text-sm">
        📋
      </div>
      <div>
        <h2 class="text-sm font-bold text-white tracking-tight">SupremeAI Sprint 42 (Q4 Roadmap)</h2>
        <span class="text-[10px] text-slate-400 font-mono">14 issues · 3 assignees · Velocity: 84 pts</span>
      </div>
    </div>
    <button class="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-lg transition-colors shadow-sm">
      + New Task
    </button>
  </div>

  <!-- Columns Grid -->
  <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
    <!-- Column 1: Backlog -->
    <div class="bg-slate-900/60 rounded-xl border border-slate-800 p-3 space-y-2.5">
      <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-[11px] font-mono">
        <span class="font-bold text-slate-300">TODO / BACKLOG</span>
        <span class="px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">4</span>
      </div>
      <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 hover:border-slate-700 transition-colors cursor-pointer">
        <span class="px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 text-[10px] font-mono font-bold">API</span>
        <h4 class="font-semibold text-white">Integrate WebSocket bridge for Live MCP streaming</h4>
        <div class="flex justify-between items-center text-[10px] text-slate-500 pt-1">
          <span>Est: 3h</span>
          <span class="w-5 h-5 rounded-full bg-slate-700 flex items-center justify-center text-white text-[9px]">ZH</span>
        </div>
      </div>
      <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 hover:border-slate-700 transition-colors cursor-pointer">
        <span class="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[10px] font-mono font-bold">FE</span>
        <h4 class="font-semibold text-white">Optimize tablet 768px responsive viewport breakpoints</h4>
        <div class="flex justify-between items-center text-[10px] text-slate-500 pt-1">
          <span>Est: 1h</span>
          <span class="w-5 h-5 rounded-full bg-indigo-700 flex items-center justify-center text-white text-[9px]">AI</span>
        </div>
      </div>
    </div>

    <!-- Column 2: In Progress -->
    <div class="bg-slate-900/60 rounded-xl border border-slate-800 p-3 space-y-2.5">
      <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-[11px] font-mono">
        <span class="font-bold text-amber-400">IN PROGRESS</span>
        <span class="px-1.5 py-0.2 rounded bg-amber-950 text-amber-300">2</span>
      </div>
      <div class="bg-slate-950 p-3 rounded-lg border border-amber-800/40 space-y-2 hover:border-amber-600 transition-colors cursor-pointer">
        <span class="px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 text-[10px] font-mono font-bold">AUTONOMY</span>
        <h4 class="font-semibold text-white">Wire Render 512MB RAM sentinel & cache purger</h4>
        <div class="flex justify-between items-center text-[10px] text-slate-500 pt-1">
          <span class="text-amber-400 font-mono">Active solve...</span>
          <span class="w-5 h-5 rounded-full bg-amber-700 flex items-center justify-center text-white text-[9px]">JV</span>
        </div>
      </div>
    </div>

    <!-- Column 3: Completed / Done -->
    <div class="bg-slate-900/60 rounded-xl border border-slate-800 p-3 space-y-2.5">
      <div class="flex items-center justify-between pb-1 border-b border-slate-800 text-[11px] font-mono">
        <span class="font-bold text-emerald-400">DONE (VERIFIED)</span>
        <span class="px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-300">8</span>
      </div>
      <div class="bg-slate-950 p-3 rounded-lg border border-slate-800 space-y-2 opacity-80 hover:opacity-100 transition-opacity cursor-pointer">
        <span class="px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-300 text-[10px] font-mono font-bold">INSPECTOR</span>
        <h4 class="font-semibold text-slate-300 line-through">Click-to-Edit Visual Element Inspector with micro-prompt</h4>
        <div class="flex justify-between items-center text-[10px] text-emerald-400 pt-1">
          <span>✓ Shipped v1.3</span>
          <span class="w-5 h-5 rounded-full bg-emerald-700 flex items-center justify-center text-white text-[9px]">✓</span>
        </div>
      </div>
    </div>
  </div>
</div>
`
  }
];
