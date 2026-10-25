import React from 'react';
import { Link } from 'react-router-dom';
import { ServiceHealthBar } from './ServiceHealthBar';

// ROOT-CAUSE UNIFY FIX (owner request: "login and signup 2 rokom na ase — jekono
// akta r moto thakbe, sudu likha and box change hobe"):
// বাংলা মন্তব্য: আগে LoginPage split-screen (hero + card) ছিল, কিন্তু RegisterPage
// ছিল মাঝখানে সিঙ্গেল সেন্টার্ড কার্ড — দুটো পেজ দেখতে সম্পূর্ণ আলাদা লাগত।
// এখন দুটো auth পেজই এই একই AuthShell শেয়ার করে: aurora wash + header +
// বাম দিকের brand hero + ServiceHealthBar + ডান দিকের glass card + footer।
// পেজভেদে পার্থক্য শুধু children (কার্ডের ভেতরের লেখা ও ইনপুট বক্স) —
// ভবিষ্যতে কখনো আর আলাদা দেখাবে না। কোনো logic এখানে নেই, শুধু লেআউট।
export const AuthShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <main className="relative min-h-screen overflow-hidden bg-slate-950 px-4 py-6 text-slate-100 sm:px-6 lg:px-12">
      {/* Cosmic aurora wash (same family as LandingPage / guest chat) */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(168,85,247,0.16)_0%,transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(16,185,129,0.10)_0%,transparent_50%)]" />

      <div className="relative mx-auto flex min-h-[calc(100vh-3rem)] max-w-dash flex-col">
        <header className="flex items-center justify-between gap-4 py-2">
          <Link to="/" className="flex items-center gap-3" aria-label="SupremeAI home">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-400 via-indigo-500 to-purple-600 text-sm font-bold text-white shadow-lg shadow-purple-500/20">S</span>
            <span className="font-semibold tracking-tight">SupremeAI</span>
          </Link>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Secure workspace access</span>
        </header>

        <div className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[1fr_minmax(0,26rem)] lg:gap-16 lg:py-12">
          {/* Brand hero — identical on both auth pages, desktop-only */}
          <section className="hidden max-w-xl lg:block">
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.2em] text-emerald-400">Your command center</p>
            <h1 className="max-w-lg text-3xl font-semibold leading-tight tracking-[-0.04em] bg-gradient-to-b from-white via-slate-100 to-slate-400 bg-clip-text text-transparent xl:text-5xl">Turn intent into reliable action.</h1>
            <p className="mt-6 max-w-md text-base leading-7 text-slate-400">Coordinate agents, automate repeatable work, and keep every important decision in view.</p>
            <div className="mt-10 grid max-w-md grid-cols-3 gap-3" aria-label="SupremeAI capabilities">
              {['Agents', 'Automations', 'Oversight'].map((item) => <div key={item} className="rounded-2xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.6))] p-4 text-xs font-medium text-slate-300 backdrop-blur-md">{item}</div>)}
            </div>
          </section>

          {/* Auth card slot — children differ per page (text + boxes only) */}
          <section className="w-full">
            <div className="mb-4"><ServiceHealthBar /></div>
            <div className="rounded-3xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.75))] p-6 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.25))] backdrop-blur-md sm:p-9">
              {children}
            </div>
          </section>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 py-5 text-[10px] text-slate-500"><span>Private by design.</span><span className="font-mono">Build {typeof __APP_BUILD_TIME__ !== 'undefined' ? __APP_BUILD_TIME__ : 'Dev'}</span></footer>
      </div>
    </main>
  );
};

export default AuthShell;
