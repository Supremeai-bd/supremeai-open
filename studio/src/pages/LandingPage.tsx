import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export const LandingHeader: React.FC = () => {
  const navigate = useNavigate();
  return (
    <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between border-b border-white/10 bg-slate-950/70 px-6 backdrop-blur-xl">
      <div className="flex items-center gap-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-400 via-indigo-500 to-purple-600 font-bold text-white shadow-lg shadow-purple-500/20">
          S
        </span>
        <span className="text-lg font-bold tracking-tight text-white">SupremeAI</span>
      </div>

      <nav className="hidden md:flex items-center gap-6 text-sm text-slate-300">
        <a href="#features" className="hover:text-emerald-400 transition-colors">Features</a>
        <a href="#demo" className="hover:text-emerald-400 transition-colors">Live Demo</a>
        <button type="button" onClick={() => navigate('/about')} className="hover:text-emerald-400 transition-colors">
          Our Story
        </button>
      </nav>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate('/login')}
          className="rounded-lg px-3.5 py-1.5 text-sm font-medium text-slate-300 hover:text-white transition-colors"
        >
          Sign In
        </button>
        <button
          type="button"
          onClick={() => navigate('/register')}
          className="rounded-lg bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-1.5 text-sm font-semibold text-white shadow-md shadow-emerald-500/20 hover:opacity-95 transition-opacity"
        >
          Get Started
        </button>
      </div>
    </header>
  );
};

export const LandingPage: React.FC = () => {
  const navigate = useNavigate();
  const [typedText, setTypedText] = useState('');
  const fullText = 'What is the current health status of our AI swarm across satellites?';

  useEffect(() => {
    let index = 0;
    const interval = setInterval(() => {
      setTypedText(fullText.slice(0, index));
      index = (index + 1) % (fullText.length + 15);
    }, 75);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-purple-500/30">
      <LandingHeader />

      {/* Hero Section */}
      <section className="relative overflow-hidden px-6 pt-20 pb-28 md:pt-32 md:pb-36">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(168,85,247,0.18)_0%,transparent_60%)] pointer-events-none" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(16,185,129,0.12)_0%,transparent_50%)] pointer-events-none" />

        <div className="mx-auto max-w-5xl text-center relative z-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-1 text-xs font-mono text-emerald-300 mb-6 backdrop-blur-md">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            Cosmic Architecture 2.0 Live
          </div>

          <h1 className="text-4xl font-extrabold tracking-tight sm:text-6xl md:text-7xl bg-gradient-to-b from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
            Sovereign Intelligence.<br />Zero-Admin Federation.
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base sm:text-lg text-slate-400 leading-relaxed">
            Autonomous multi-model intelligence network with self-healing bridges, fail-closed security, and native provider consensus.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              type="button"
              onClick={() => navigate('/workspace/live')}
              className="w-full sm:w-auto rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-6 py-3 font-semibold text-white shadow-lg shadow-emerald-500/25 hover:shadow-emerald-500/40 transition-all"
            >
              Try Live Guest Chat →
            </button>
            <button
              type="button"
              onClick={() => navigate('/signup')}
              className="w-full sm:w-auto rounded-xl border border-white/10 bg-slate-900/80 px-6 py-3 font-semibold text-slate-200 hover:bg-slate-800 hover:text-white transition-all backdrop-blur-md"
            >
              Create Free Account
            </button>
          </div>
        </div>

        {/* Live-typed demo */}
        <div id="demo" className="mx-auto mt-16 max-w-3xl rounded-2xl border border-white/10 bg-slate-900/60 p-5 shadow-2xl backdrop-blur-xl">
          <div className="flex items-center justify-between border-b border-white/10 pb-3 mb-4">
            <div className="flex items-center gap-2">
              <span className="h-3 w-3 rounded-full bg-rose-500/80" />
              <span className="h-3 w-3 rounded-full bg-amber-500/80" />
              <span className="h-3 w-3 rounded-full bg-emerald-500/80" />
            </div>
            <span className="text-xs font-mono text-slate-400">SupremeAI Native Relay</span>
          </div>
          <div className="space-y-3 font-mono text-sm">
            <div className="rounded-xl bg-purple-950/40 border border-purple-500/20 p-3 text-purple-200">
              <span className="text-xs text-purple-400 font-bold block mb-1">User</span>
              {typedText}
              <span className="inline-block w-2 h-4 bg-purple-400 ml-1 animate-pulse" />
            </div>
            <div className="rounded-xl bg-slate-800/50 border border-white/10 p-3 text-emerald-300">
              <span className="text-xs text-emerald-400 font-bold block mb-1">SupremeAI Mesh</span>
              ⚡ 12 Satellites nominal. Consensus achieved across Gemini, Groq, and Mistral in 38ms.
            </div>
          </div>
        </div>
      </section>

      {/* Feature Cards */}
      <section id="features" className="border-t border-white/10 px-6 py-24 bg-slate-950/50">
        <div className="mx-auto max-w-6xl">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-white">Engineered for Sovereign Resilience</h2>
            <p className="mt-3 text-slate-400">Three pillars of the federated architecture</p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-6 backdrop-blur-md hover:border-emerald-500/30 transition-all">
              <div className="h-10 w-10 rounded-xl bg-emerald-500/20 flex items-center justify-center text-emerald-400 mb-4 font-bold">
                01
              </div>
              <h3 className="text-lg font-bold text-white">Understands Your Entire Federation</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                Single-door public ingress with automated slice dispatch across 12 satellite repositories.
              </p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-6 backdrop-blur-md hover:border-purple-500/30 transition-all">
              <div className="h-10 w-10 rounded-xl bg-purple-500/20 flex items-center justify-center text-purple-400 mb-4 font-bold">
                02
              </div>
              <h3 className="text-lg font-bold text-white">Multi-Model Consensus & Auto-Healing</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                Dynamically routes through 6 LLM providers with automatic player substitution and fail-closed security.
              </p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-slate-900/40 p-6 backdrop-blur-md hover:border-cyan-500/30 transition-all">
              <div className="h-10 w-10 rounded-xl bg-cyan-500/20 flex items-center justify-center text-cyan-400 mb-4 font-bold">
                03
              </div>
              <h3 className="text-lg font-bold text-white">Zero Admin Overhead (&le; 0.01%)</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                Autonomous CI gates, pre-push verification, and automated landing pipelines run 24/7.
              </p>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default LandingPage;
