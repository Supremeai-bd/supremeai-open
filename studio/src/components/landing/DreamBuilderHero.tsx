import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, ArrowRight, Compass, ShieldCheck, Zap, Rocket, HeartHandshake, Eye, CheckCircle2, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface VisionPillar {
  id: string;
  badge: string;
  title: string;
  prompt: string;
  tagline: string;
  story: string;
  highlights: { label: string; value: string; hint: string }[];
  accentColor: string;
  gradient: string;
  userPowers: string[];
}

const VISION_PILLARS: VisionPillar[] = [
  {
    id: 'dream-to-reality',
    badge: '✨ Turn Ideas Into Reality',
    title: 'From Imagination to Reality in Minutes',
    prompt: 'I have a vision for a breakthrough business. Turn my concept into a living, breathing reality...',
    tagline: 'Your thoughts are the blueprint. SupremeAI brings them to life.',
    story: 'You no longer need a massive team, endless funding, or months of technical struggle. Just speak your dream, and watch the platform orchestrate the design, the code, the intelligence, and the execution seamlessly.',
    highlights: [
      { label: 'Time to First Launch', value: 'Instant', hint: 'Go live today' },
      { label: 'Creative Freedom', value: '100%', hint: 'Zero technical barriers' },
      { label: 'Execution Speed', value: '10x Faster', hint: 'Continuous momentum' },
    ],
    accentColor: '#00f5ff',
    gradient: 'from-cyan-500/20 via-indigo-500/20 to-purple-600/20',
    userPowers: [
      'Turn raw thoughts into polished, working apps',
      'Design modern interfaces without touching boilerplate',
      'Iterate freely with intelligent guidance at every step',
    ],
  },
  {
    id: 'unstoppable-growth',
    badge: '🚀 Unstoppable Growth',
    title: 'Grow Your Venture While You Sleep',
    prompt: 'Scale my platform across thousands of customers while keeping quality flawless...',
    tagline: 'Never worry about running out of hours in a day.',
    story: 'Your digital empire never rests. SupremeAI handles the heavy lifting, monitors every heartbeat, and keeps your services running at peak performance so you can focus on leading and dreaming bigger.',
    highlights: [
      { label: 'System Resilience', value: '99.99%', hint: 'Autonomous 24/7 care' },
      { label: 'Growth Multiplier', value: 'Limitless', hint: 'Ready for any scale' },
      { label: 'Peace of Mind', value: 'Total', hint: 'Zero firefighting' },
    ],
    accentColor: '#10b981',
    gradient: 'from-emerald-500/20 via-teal-500/20 to-cyan-500/20',
    userPowers: [
      'Scale effortlessly from your first user to millions',
      'Automated intelligence that fixes issues before you notice',
      'More time to focus on your family, creativity, and life',
    ],
  },
  {
    id: 'sovereign-control',
    badge: '🛡️ Your Vision, Fully Protected',
    title: '100% Owned by You, Forever Private',
    prompt: 'Protect my intellectual property and ensure my data never leaks to competitors...',
    tagline: 'True sovereignty. Your code, your data, your rules.',
    story: 'Big tech should never own your life’s work. With SupremeAI, every asset you create remains strictly yours. Private, secure, and independent from predatory cloud monopolies.',
    highlights: [
      { label: 'Data Sovereignty', value: 'Guaranteed', hint: 'Zero vendor lock-in' },
      { label: 'Privacy Standard', value: 'Zero-Leak', hint: 'Encrypted isolation' },
      { label: 'Ownership', value: '100% Yours', hint: 'Export & migrate freely' },
    ],
    accentColor: '#bd79ff',
    gradient: 'from-purple-500/20 via-pink-500/20 to-rose-500/20',
    userPowers: [
      'Complete ownership of everything you build',
      'Private brain architecture that protects your secret sauce',
      'Never locked into any single cloud or corporate silo',
    ],
  },
  {
    id: 'commander-cockpit',
    badge: '👑 Be The Commander',
    title: 'Lead Like a Visionary, Not a Maintainer',
    prompt: 'Give me a unified command cockpit where my entire universe is at my fingertips...',
    tagline: 'You are the visionary. SupremeAI is your executive team.',
    story: 'Forget juggling twenty different tools and getting bogged down in low-level chores. Sit in the captain’s seat with full visibility over every project, agent, and milestone in real-time.',
    highlights: [
      { label: 'One Unified Cockpit', value: 'Single Door', hint: 'Everything in one view' },
      { label: 'Focus on Strategy', value: 'Maximum', hint: 'Eliminate grunt work' },
      { label: 'Voice & AI Companions', value: 'Built-in', hint: 'Command by voice or chat' },
    ],
    accentColor: '#f59e0b',
    gradient: 'from-amber-500/20 via-orange-500/20 to-yellow-500/20',
    userPowers: [
      'Real-time overview of your digital operations',
      'Collaborate with AI companions that understand your vision',
      'Make high-impact decisions with clear, actionable insights',
    ],
  },
];

export const DreamBuilderHero: React.FC = () => {
  const navigate = useNavigate();
  const [selectedPillarId, setSelectedPillarId] = useState<string>(VISION_PILLARS[0].id);
  const [typedPrompt, setTypedPrompt] = useState<string>('');
  const [isTyping, setIsTyping] = useState<boolean>(true);

  const activePillar = VISION_PILLARS.find((p) => p.id === selectedPillarId) || VISION_PILLARS[0];

  // Typing effect that mirrors user's input/prompt dynamically
  useEffect(() => {
    let index = 0;
    const targetText = activePillar.prompt;
    setTypedPrompt('');
    setIsTyping(true);

    const interval = setInterval(() => {
      index++;
      setTypedPrompt(targetText.slice(0, index));
      if (index >= targetText.length) {
        setIsTyping(false);
        clearInterval(interval);
      }
    }, 28);

    return () => clearInterval(interval);
  }, [activePillar.prompt]);

  return (
    <div className="relative w-full overflow-hidden px-4 py-12 sm:px-6 md:py-20 lg:px-8">
      {/* 🌟 Emotional Vision Banner */}
      <div className="mx-auto max-w-4xl text-center">
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-950/40 px-4 py-1.5 text-xs font-semibold text-cyan-300 backdrop-blur-md shadow-lg shadow-cyan-950/50"
        >
          <Sparkles size={14} className="text-cyan-400 animate-spin" style={{ animationDuration: '6s' }} />
          <span>YOUR VISION · OUR ENGINE</span>
          <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping" />
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="mt-6 text-3xl font-extrabold tracking-tight text-white sm:text-5xl md:text-6xl"
        >
          Build Your Dream.{' '}
          <span className="block bg-gradient-to-r from-cyan-400 via-teal-300 to-indigo-300 bg-clip-text text-transparent">
            We Are Here To Make It True.
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mx-auto mt-5 max-w-2xl text-base text-slate-300 sm:text-lg sm:leading-relaxed"
        >
          No complex jargon, no gatekeepers, and no limits on what you can build.
          Step into a sovereign platform designed to turn your boldest ideas into living reality.
        </motion.p>

        {/* 🎯 Interactive Inspiration Chips */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-2.5">
          {VISION_PILLARS.map((pillar) => {
            const isSelected = pillar.id === activePillar.id;
            return (
              <button
                key={pillar.id}
                type="button"
                onClick={() => setSelectedPillarId(pillar.id)}
                className={`relative rounded-xl px-4 py-2 text-xs font-medium transition-all duration-300 sm:text-sm ${isSelected
                    ? 'border border-cyan-400/80 bg-cyan-500/15 text-white shadow-lg shadow-cyan-500/20 backdrop-blur-md'
                    : 'border border-white/10 bg-slate-900/60 text-slate-300 hover:border-white/25 hover:bg-slate-800/80'
                  }`}
              >
                <span>{pillar.badge}</span>
                {isSelected && (
                  <motion.div
                    layoutId="activePillarTab"
                    className="absolute inset-0 -z-10 rounded-xl bg-gradient-to-r from-cyan-500/20 to-indigo-500/20"
                    transition={{ type: 'spring', bounce: 0.2, duration: 0.4 }}
                  />
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* 🎬 Video-Inspired Dynamic Frame Stage (Constellation -> Live Prompt Bar -> Floating Glass Card) */}
      <div className="mx-auto mt-12 max-w-6xl">
        <div className="relative rounded-3xl border border-white/10 bg-slate-950/70 p-4 shadow-2xl backdrop-blur-xl sm:p-8">
          {/* Subtle Ambient Radial Glow */}
          <div
            className={`absolute -top-24 left-1/2 -z-10 h-72 w-96 -translate-x-1/2 rounded-full bg-gradient-to-tr ${activePillar.gradient} blur-3xl opacity-40 transition-all duration-700`}
          />

          <div className="grid grid-cols-1 gap-8 lg:grid-cols-12 lg:items-center">
            {/* Left 7 Columns: Story, Interactive Prompt Box & Capability Hints */}
            <div className="lg:col-span-7 flex flex-col justify-between space-y-6">
              <div>
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-cyan-400">
                  <span className="h-2 w-2 rounded-full bg-cyan-400 animate-pulse" />
                  {activePillar.tagline}
                </div>
                <h2 className="mt-2 text-2xl font-bold text-white sm:text-3xl">
                  {activePillar.title}
                </h2>
                <p className="mt-3 text-sm text-slate-300 leading-relaxed sm:text-base">
                  {activePillar.story}
                </p>
              </div>

              {/* 💬 Live Prompt Card (Inspired by the Video Prompt Bar) */}
              <div className="rounded-2xl border border-white/15 bg-slate-900/80 p-4 shadow-xl backdrop-blur-md">
                <div className="flex items-center justify-between border-b border-white/10 pb-2 mb-3">
                  <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span>Imagine and command</span>
                  </div>
                  <span className="text-[11px] font-mono text-cyan-400/90">Autonomous Voice & Prompt Ready</span>
                </div>

                <div className="min-h-[64px] font-mono text-sm sm:text-base text-slate-100 flex items-start">
                  <span>{typedPrompt}</span>
                  <span
                    className={`ml-1 inline-block h-5 w-2 bg-cyan-400 ${isTyping ? 'animate-pulse' : 'opacity-70'
                      }`}
                  />
                </div>

                <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-3 text-xs">
                  <div className="flex items-center gap-2 text-slate-400">
                    <Rocket size={14} className="text-cyan-400" />
                    <span>Select different pillars above to preview capabilities</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => navigate('/playground')}
                    className="flex items-center gap-1.5 rounded-lg bg-cyan-500/20 px-3 py-1 font-semibold text-cyan-300 hover:bg-cyan-500/30 transition-all"
                  >
                    <span>Launch in Sandbox</span>
                    <ArrowRight size={13} />
                  </button>
                </div>
              </div>

              {/* 🌟 What You Can Do (User Hints) */}
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  What you can do right now:
                </h4>
                <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {activePillar.userPowers.map((power, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2.5 rounded-xl border border-white/5 bg-slate-900/40 p-2.5 text-xs text-slate-200 backdrop-blur-sm"
                    >
                      <CheckCircle2 size={15} className="shrink-0 text-emerald-400" />
                      <span>{power}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Right 5 Columns: The Floating Glass Inspector Card (From Video Frame 3 & 4) */}
            <div className="lg:col-span-5">
              <AnimatePresence mode="wait">
                <motion.div
                  key={activePillar.id}
                  initial={{ opacity: 0, x: 20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  transition={{ duration: 0.35, ease: 'easeOut' }}
                  className="rounded-3xl border border-white/15 bg-gradient-to-b from-slate-900/90 to-slate-950/90 p-6 shadow-2xl backdrop-blur-2xl"
                >
                  <div className="flex items-center justify-between border-b border-white/10 pb-4">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-widest text-cyan-400">
                        Sovereign Advantage
                      </span>
                      <h3 className="text-lg font-bold text-white">Your Dream, Empowered</h3>
                    </div>
                    <span className="rounded-full bg-cyan-400/10 p-2 text-cyan-300">
                      <Sparkles size={18} />
                    </span>
                  </div>

                  {/* Highlights / KPIs */}
                  <div className="mt-6 space-y-4">
                    {activePillar.highlights.map((h, i) => (
                      <div
                        key={i}
                        className="rounded-2xl border border-white/5 bg-white/[0.03] p-4 transition-all hover:bg-white/[0.06]"
                      >
                        <div className="text-xs font-medium text-slate-400">{h.label}</div>
                        <div className="mt-1 flex items-baseline justify-between">
                          <span className="text-2xl font-bold tracking-tight text-white">
                            {h.value}
                          </span>
                          <span className="text-xs font-semibold text-emerald-400">
                            {h.hint}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>

                  {/* Emotional Promise & Action */}
                  <div className="mt-6 border-t border-white/10 pt-5">
                    <p className="text-xs italic text-slate-400">
                      &quot;You bring the spark. We provide the infinite engine to make it last.&quot;
                    </p>
                    <div className="mt-5 flex flex-col gap-2.5">
                      <button
                        type="button"
                        onClick={() => navigate('/playground')}
                        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-cyan-400 to-indigo-500 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/25 transition-all hover:brightness-110 active:scale-[0.99]"
                      >
                        <Sparkles size={16} />
                        <span>Try Instant Guest Sandbox &rarr;</span>
                      </button>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => navigate('/login')}
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-950/40 py-2.5 text-xs font-semibold text-cyan-300 transition-all hover:bg-cyan-900/50"
                        >
                          <span>Sign in</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => navigate('/chat')}
                          className="flex flex-1 items-center justify-center gap-1.5 rounded-xl border border-white/10 bg-slate-800/60 py-2.5 text-xs font-semibold text-slate-200 transition-all hover:bg-slate-700/80"
                        >
                          <span>Live Chat</span>
                          <ChevronRight size={14} />
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
