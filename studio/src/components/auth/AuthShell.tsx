import React from 'react';
import { Link } from 'react-router-dom';
import { ServiceHealthBar } from './ServiceHealthBar';
import { BrandMark } from '../../concept/components/BrandMark';
import { ShieldCheck, Cpu, Terminal, ArrowUpRight } from 'lucide-react';
import { NeuralConstellationCanvas } from '../common/NeuralConstellationCanvas';

export const AuthShell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#080b12] text-slate-100 selection:bg-cyan-500/30">
      {/* Living Neural Constellation Background Canvas Animation */}
      <NeuralConstellationCanvas />

      {/* Ambient background glows */}
      <div className="ambient ambient-a" aria-hidden="true" style={{ top: '0%', right: '10%' }} />
      <div className="ambient ambient-b" aria-hidden="true" style={{ bottom: '10%', left: '5%' }} />

      <div className="relative z-10 mx-auto flex min-h-screen w-full max-w-7xl flex-col justify-between px-4 py-4 sm:px-6 lg:px-8">
        {/* Top Header */}
        <header className="flex items-center justify-between border-b border-white/10 pb-3">
          <Link to="/" className="flex items-center gap-3" aria-label="SupremeAI home">
            <BrandMark />
          </Link>
          <div className="flex items-center gap-3">
            <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-emerald-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
              Autonomous Mesh Active
            </span>
            <Link
              to="/"
              className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 hover:border-cyan-500/30 hover:text-white transition-colors"
            >
              <span>← Back to Home</span>
            </Link>
          </div>
        </header>

        {/* Center Grid - Balanced to fill screen without vertical overflow */}
        <div className="my-auto grid flex-1 items-center gap-8 py-6 lg:grid-cols-12 lg:gap-12 lg:py-8">
          {/* Left Column: Architectural Hero */}
          <section className="hidden lg:col-span-7 lg:block space-y-6 pr-6">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/20 bg-cyan-500/10 px-3 py-1 text-xs font-mono text-cyan-300">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                Sovereign Intelligence Network
              </div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white xl:text-4xl leading-tight">
                One signal.<br />
                <span className="bg-gradient-to-r from-cyan-400 via-indigo-400 to-lime-300 bg-clip-text text-transparent">
                  Every workspace.
                </span>
              </h1>
              <p className="max-w-lg text-sm text-slate-400 leading-relaxed">
                Connect your IDE, Terminal, and Studio to the SupremeAI federation with fail-closed security and instant multi-model consensus.
              </p>
            </div>

            {/* Micro feature cards with theme styling */}
            <div className="grid grid-cols-2 gap-3 max-w-lg">
              <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3.5 backdrop-blur-md">
                <div className="flex items-center gap-2 text-cyan-400 mb-1.5">
                  <ShieldCheck size={16} />
                  <span className="text-xs font-bold tracking-wider font-mono uppercase">Zero-Leak Guard</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-normal">Fail-closed CAS authorization and cryptographically signed session tokens.</p>
              </div>

              <div className="rounded-xl border border-white/10 bg-slate-900/60 p-3.5 backdrop-blur-md">
                <div className="flex items-center gap-2 text-lime-400 mb-1.5">
                  <Cpu size={16} />
                  <span className="text-xs font-bold tracking-wider font-mono uppercase">Multi-Model Squad</span>
                </div>
                <p className="text-[11px] text-slate-400 leading-normal">Autonomous substitution between Gemini, Groq, Mistral & OpenRouter.</p>
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-gradient-to-r from-cyan-950/20 via-slate-900/50 to-purple-950/20 p-3.5 backdrop-blur-md max-w-lg">
              <div className="flex items-center justify-between text-xs font-mono text-slate-400 mb-1.5">
                <span className="flex items-center gap-2 text-slate-300">
                  <Terminal size={14} className="text-cyan-400" /> CLI Ingress Available
                </span>
                <span className="text-emerald-400">0 behind main</span>
              </div>
              <code className="block text-[11px] font-mono text-cyan-300/90 bg-black/40 rounded-lg p-2 border border-white/5">
                $ agy login --session-sync
              </code>
            </div>
          </section>

          {/* Right Column: Card Slot */}
          <section className="w-full lg:col-span-5 max-w-md mx-auto">
            <div className="mb-3">
              <ServiceHealthBar />
            </div>
            <div className="rounded-2xl border border-white/15 bg-slate-900/80 p-5 shadow-2xl shadow-cyan-950/40 backdrop-blur-xl sm:p-7">
              {children}
            </div>
          </section>
        </div>

        {/* Footer */}
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 py-4 text-xs text-slate-500">
          <span>SupremeAI · Golden 6-Domain Federated Topology</span>
          <div className="flex items-center gap-4">
            <Link to="/docs" className="hover:text-cyan-400 transition-colors">Documentation</Link>
            <Link to="/about" className="hover:text-cyan-400 transition-colors">Federation Status</Link>
          </div>
        </footer>
      </div>
    </main>
  );
};

export default AuthShell;
