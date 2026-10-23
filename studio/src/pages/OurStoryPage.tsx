import React from 'react';
import { useNavigate } from 'react-router-dom';
import { LandingHeader } from './LandingPage';

export const OurStoryPage: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-purple-500/30">
      <LandingHeader />

      <main className="mx-auto max-w-4xl px-6 py-20">
        <div className="text-center mb-16">
          <span className="text-xs font-mono uppercase tracking-widest text-emerald-400">Origins & Evolution</span>
          <h1 className="mt-3 text-4xl font-extrabold sm:text-5xl text-white">Our Story</h1>
          <p className="mt-4 text-slate-400 text-lg">From isolated AI scripts to a resilient, zero-admin sovereign federation.</p>
        </div>

        {/* 3-Step Flow: Ask -> Review -> Ship */}
        <section className="mb-20">
          <h2 className="text-2xl font-bold text-white mb-8">The Sovereign Loop: Ask &rarr; Review &rarr; Ship</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6">
              <span className="text-3xl font-black text-emerald-400">01</span>
              <h3 className="mt-3 font-bold text-white text-lg">Ask with Context</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                Connect once through the MCP Control Tower. Every agent operates with localized knowledge and zero-credential security.
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6">
              <span className="text-3xl font-black text-purple-400">02</span>
              <h3 className="mt-3 font-bold text-white text-lg">Review with Proof</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                3-Tier verification: reflection rationale, smoke validations, and automated regression tests enforce every boundary.
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6">
              <span className="text-3xl font-black text-cyan-400">03</span>
              <h3 className="mt-3 font-bold text-white text-lg">Autonomous Ship</h3>
              <p className="mt-2 text-sm text-slate-400 leading-relaxed">
                The Landing pipeline squashes, validates, slices, and dispatches landed commits to satellites with zero admin drag (&le; 0.01%).
              </p>
            </div>
          </div>
        </section>

        {/* Founder note (Bangla + English) */}
        <section className="rounded-2xl border border-emerald-500/20 bg-emerald-950/10 p-8 backdrop-blur-xl">
          <h3 className="font-bold text-emerald-300 text-lg mb-2">Founder Note / আমাদের লক্ষ্য</h3>
          <p className="text-sm text-slate-300 leading-relaxed mb-4">
            সুপ্রিমএআই শুধুমাত্র আরেকটি এআই টুল নয়; এটি এমন একটি সার্বভৌম সিস্টেম যা স্বয়ংক্রিয়ভাবে নিজের সমস্যা নিরাময় করে এবং সর্বনিম্ন পরিশ্রমে সর্বোচ্চ শক্তি প্রদান করে। সিম্পল কিন্তু চূড়ান্ত শক্তিশালী—এটাই আমাদের একমাত্র দর্শন।
          </p>
          <p className="text-sm text-slate-400 leading-relaxed italic">
            "SupremeAI is built on the law of minimal elegance: simple + effective &gt; clever + complex. Systems guard boundaries so intelligence can build freely."
          </p>
        </section>

        <div className="mt-12 text-center">
          <button
            type="button"
            onClick={() => navigate('/chat')}
            className="rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-6 py-3 font-semibold text-white shadow-lg hover:opacity-90 transition-opacity"
          >
            Experience the Live Chat &rarr;
          </button>
        </div>
      </main>
    </div>
  );
};

export default OurStoryPage;
