import React, { useState, useEffect, useRef } from 'react';
import { 
  Play, Sparkles, Terminal, Cpu, ArrowRight, Zap, Check, Copy, Code, 
  Calculator, FileJson, RefreshCw, Monitor, Tablet, Smartphone, Download, 
  ExternalLink, Layers, Volume2, ShieldCheck, Eye, RotateCcw, Heart
} from 'lucide-react';
import { jarvisAudio } from '../../utils/audioFx';
import type { AvatarSettings } from '../../types/avatar';

const AI_MODELS_DATA = [
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro', provider: 'Google', contextWindow: '2,000,000 tokens', speedMs: 140, costPer1MTokens: '$1.25 / $5.00' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash', provider: 'Google', contextWindow: '1,000,000 tokens', speedMs: 65, costPer1MTokens: '$0.075 / $0.30' },
  { id: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet', provider: 'Anthropic', contextWindow: '200,000 tokens', speedMs: 180, costPer1MTokens: '$3.00 / $15.00' },
  { id: 'gpt-4o', name: 'GPT-4o Omniscient', provider: 'OpenAI', contextWindow: '128,000 tokens', speedMs: 160, costPer1MTokens: '$2.50 / $10.00' },
];

interface GuestDashboardProps {
  language: 'bn' | 'en';
  onSwitchToUser: () => void;
  avatarSettings?: AvatarSettings;
}

type DeviceType = 'desktop' | 'tablet' | 'mobile';

interface SandboxTemplate {
  id: string;
  nameBn: string;
  nameEn: string;
  badge: string;
  code: string;
}

const SANDBOX_TEMPLATES: SandboxTemplate[] = [
  {
    id: 'saas-landing',
    nameBn: 'আধুনিক এআই SaaS ল্যান্ডিং পেজ',
    nameEn: 'Modern AI SaaS Landing Page',
    badge: 'Popular',
    code: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen antialiased selection:bg-indigo-500 selection:text-white">
  <!-- Navigation -->
  <header class="border-b border-slate-800/80 bg-slate-950/70 backdrop-blur-md sticky top-0 z-50">
    <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-500 to-cyan-400 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25">S</div>
        <span class="font-bold tracking-tight text-white text-base">Supreme SaaS</span>
      </div>
      <div class="hidden md:flex items-center gap-6 text-sm text-slate-300">
        <a href="#features" class="hover:text-white transition">Features</a>
        <a href="#pricing" class="hover:text-white transition">Pricing</a>
        <a href="#benchmark" class="hover:text-white transition">Benchmarks</a>
      </div>
      <button class="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition shadow-lg shadow-indigo-600/30">
        Get Started Free
      </button>
    </div>
  </header>

  <!-- Hero Section -->
  <main class="max-w-6xl mx-auto px-6 pt-16 pb-20">
    <div class="text-center max-w-3xl mx-auto space-y-6">
      <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-950/60 border border-indigo-700/50 text-indigo-300 text-xs font-medium">
        <span class="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
        <span>Version 4.0 Autonomous Engine Online</span>
      </div>

      <h1 class="text-4xl sm:text-6xl font-extrabold tracking-tight text-white leading-tight">
        Build Software at the <br>
        <span class="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-cyan-400 to-emerald-400">
          Speed of Natural Thought
        </span>
      </h1>

      <p class="text-slate-300 text-base sm:text-lg leading-relaxed">
        The complete fullstack engineering workspace with living 3D hologram copilot, zero-friction sandboxing, and instant edge deployments.
      </p>

      <div class="flex flex-wrap items-center justify-center gap-4 pt-4">
        <button onclick="alert('Starting interactive generation...')" class="px-6 py-3.5 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold rounded-2xl shadow-xl shadow-indigo-600/30 transition transform hover:-translate-y-0.5">
          Launch Live Sandbox ⚡
        </button>
        <button class="px-6 py-3.5 bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 font-semibold rounded-2xl transition">
          View Interactive Tour
        </button>
      </div>
    </div>

    <!-- Feature Cards Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mt-20" id="features">
      <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-indigo-500/50 transition">
        <div class="w-10 h-10 rounded-xl bg-indigo-950 flex items-center justify-center text-indigo-400 font-bold mb-4">01</div>
        <h3 class="text-lg font-bold text-white mb-2">Living Hologram Companion</h3>
        <p class="text-sm text-slate-400 leading-relaxed">Biological saccadic eye movements, natural blinking, and speech viseme lip-sync directly in browser.</p>
      </div>

      <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-cyan-500/50 transition">
        <div class="w-10 h-10 rounded-xl bg-cyan-950 flex items-center justify-center text-cyan-400 font-bold mb-4">02</div>
        <h3 class="text-lg font-bold text-white mb-2">Multi-Device Sandboxing</h3>
        <p class="text-sm text-slate-400 leading-relaxed">Instantly preview across Desktop, iPad, and iPhone frames with real-time DOM element telemetry.</p>
      </div>

      <div class="p-6 rounded-2xl bg-slate-900/60 border border-slate-800 hover:border-emerald-500/50 transition">
        <div class="w-10 h-10 rounded-xl bg-emerald-950 flex items-center justify-center text-emerald-400 font-bold mb-4">03</div>
        <h3 class="text-lg font-bold text-white mb-2">MCP Federation Sync</h3>
        <p class="text-sm text-slate-400 leading-relaxed">Seamless real-time handshake with MCP Tower syncing 142 autonomous engineering tools.</p>
      </div>
    </div>
  </main>
</body>
</html>`,
  },
  {
    id: 'agent-terminal',
    nameBn: 'অটোনোমাস এজেন্ট কন্ট্রোল টার্মিনাল',
    nameEn: 'Autonomous Agent Control Terminal',
    badge: 'Terminal',
    code: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-[#030712] text-emerald-400 font-mono min-h-screen p-6 antialiased">
  <div class="max-w-4xl mx-auto space-y-5">
    <div class="flex items-center justify-between border-b border-emerald-900/60 pb-4">
      <div class="flex items-center gap-2">
        <span class="w-3 h-3 rounded-full bg-emerald-400 animate-ping"></span>
        <span class="font-bold text-white tracking-widest text-sm">AUTONOMOUS SWARM SENTINEL // v4.2</span>
      </div>
      <span class="text-xs bg-emerald-950/80 px-3 py-1 rounded-full border border-emerald-700/60 text-emerald-300">
        LATENCY: 14ms · RAM: 242MB / 512MB
      </span>
    </div>

    <!-- Active Task Matrix -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div class="bg-slate-950 border border-emerald-900/40 p-4 rounded-xl">
        <span class="text-slate-500 text-xs block">ACTIVE LEASE</span>
        <span class="text-white font-bold text-lg">Agent-Alpha-09</span>
        <span class="text-emerald-400 text-xs block mt-1">Status: Executing Task #89</span>
      </div>
      <div class="bg-slate-950 border border-emerald-900/40 p-4 rounded-xl">
        <span class="text-slate-500 text-xs block">CACHE INTEGRITY</span>
        <span class="text-white font-bold text-lg">99.88% Safe</span>
        <span class="text-cyan-400 text-xs block mt-1">Purge Buffer: Clean</span>
      </div>
      <div class="bg-slate-950 border border-emerald-900/40 p-4 rounded-xl">
        <span class="text-slate-500 text-xs block">MCP FEDERATION</span>
        <span class="text-white font-bold text-lg">142 Tools</span>
        <span class="text-indigo-400 text-xs block mt-1">Server: Render Hosted</span>
      </div>
    </div>

    <!-- Console Log Stream -->
    <div class="bg-slate-950/90 border border-emerald-800/50 rounded-2xl p-4 text-xs leading-relaxed space-y-2">
      <div class="text-slate-500">[22:18:04] Initializing SupremeAI Autonomous Core...</div>
      <div class="text-cyan-400">[22:18:05] Handshake verified with https://supremeai-mcp-tower.onrender.com/mcp</div>
      <div class="text-emerald-300">[22:18:06] Verified tools: [run_command, git_sync, test_runner, db_inspector]</div>
      <div class="text-amber-400">[22:18:07] Sentinel memory load: 47.2% within 512MB safety ceiling</div>
      <div class="text-emerald-400 flex items-center gap-2">
        <span class="animate-pulse">❯</span>
        <span class="text-white">Awaiting directive: system ready for autonomous execution...</span>
      </div>
    </div>
  </div>
</body>
</html>`,
  },
  {
    id: 'glass-store',
    nameBn: 'গ্লাস সাইবারপাঙ্ক স্টোর ফ্রন্ট',
    nameEn: 'Cyberpunk Glass E-Commerce',
    badge: 'Storefront',
    code: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen p-6 antialiased">
  <div class="max-w-5xl mx-auto space-y-8">
    <div class="flex items-center justify-between border-b border-slate-800 pb-5">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-rose-500 to-amber-500 flex items-center justify-center font-black text-white">N</div>
        <h1 class="text-xl font-bold text-white tracking-wide">NEO DRONE LABS</h1>
      </div>
      <div class="flex items-center gap-2">
        <span class="px-3 py-1.5 rounded-xl bg-slate-900 border border-slate-700 text-xs font-semibold text-rose-400">
          Cart (3 Items)
        </span>
      </div>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <div class="bg-slate-900/60 border border-slate-800 rounded-3xl p-5 space-y-4 hover:border-rose-500/40 transition">
        <div class="h-44 rounded-2xl bg-gradient-to-tr from-slate-950 to-indigo-950/80 border border-slate-800 flex items-center justify-center text-4xl">🛸</div>
        <div>
          <span class="text-xs font-mono text-rose-400 font-semibold">MARK-VII PROTO</span>
          <h3 class="text-lg font-bold text-white">Neural Scout Drone</h3>
          <p class="text-xs text-slate-400 mt-1">Autonomous lidar mapping with 4K HDR live telepresence.</p>
        </div>
        <div class="flex items-center justify-between pt-2">
          <span class="font-bold text-white text-lg">$1,299</span>
          <button onclick="alert('Added to cart!')" class="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-semibold transition">Add Cart</button>
        </div>
      </div>

      <div class="bg-slate-900/60 border border-slate-800 rounded-3xl p-5 space-y-4 hover:border-amber-500/40 transition">
        <div class="h-44 rounded-2xl bg-gradient-to-tr from-slate-950 to-amber-950/40 border border-slate-800 flex items-center justify-center text-4xl">🔮</div>
        <div>
          <span class="text-xs font-mono text-amber-400 font-semibold">CORE MODULE</span>
          <h3 class="text-lg font-bold text-white">Quantum Power Cell</h3>
          <p class="text-xs text-slate-400 mt-1">Solid-state battery delivering 48 hours continuous flight.</p>
        </div>
        <div class="flex items-center justify-between pt-2">
          <span class="font-bold text-white text-lg">$449</span>
          <button onclick="alert('Added to cart!')" class="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-xl text-xs font-semibold transition">Add Cart</button>
        </div>
      </div>

      <div class="bg-slate-900/60 border border-slate-800 rounded-3xl p-5 space-y-4 hover:border-cyan-500/40 transition">
        <div class="h-44 rounded-2xl bg-gradient-to-tr from-slate-950 to-cyan-950/40 border border-slate-800 flex items-center justify-center text-4xl">👓</div>
        <div>
          <span class="text-xs font-mono text-cyan-400 font-semibold">HOLOGRAPHIC HUD</span>
          <h3 class="text-lg font-bold text-white">Cyber Vision Visor</h3>
          <p class="text-xs text-slate-400 mt-1">Zero-latency neural link with retinal HUD projection.</p>
        </div>
        <div class="flex items-center justify-between pt-2">
          <span class="font-bold text-white text-lg">$899</span>
          <button onclick="alert('Added to cart!')" class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-xl text-xs font-semibold transition">Add Cart</button>
        </div>
      </div>
    </div>
  </div>
</body>
</html>`,
  },
  {
    id: 'living-portfolio',
    nameBn: 'লিভিং হলোগ্রাফিক পোর্টফোলিও',
    nameEn: 'Holographic Living Portfolio',
    badge: 'Creative',
    code: `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-950 text-slate-200 min-h-screen p-6 antialiased flex items-center justify-center">
  <div class="max-w-xl w-full bg-slate-900/80 border border-cyan-500/40 rounded-3xl p-8 space-y-6 shadow-2xl backdrop-blur-xl">
    <div class="flex items-center gap-5">
      <div class="relative w-20 h-20 rounded-full border-2 border-cyan-400 shadow-lg shadow-cyan-500/30 flex items-center justify-center text-3xl bg-slate-950">
        👨‍💻
      </div>
      <div>
        <div class="flex items-center gap-2">
          <h2 class="text-2xl font-extrabold text-white">Alex Mercer</h2>
          <span class="text-xs font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-700">Lead Architect</span>
        </div>
        <p class="text-xs text-slate-400 mt-1">Autonomous Web Systems & Real-time AI Interfaces</p>
      </div>
    </div>

    <div class="space-y-2 text-xs text-slate-300 leading-relaxed">
      <p>Building high-performance software engineering cockpits powered by Web Audio, Canvas shaders, and multi-model reasoning pipelines.</p>
    </div>

    <div class="grid grid-cols-3 gap-3 text-center">
      <div class="p-3 bg-slate-950/80 rounded-2xl border border-slate-800">
        <span class="text-xl font-bold text-white block">142+</span>
        <span class="text-[10px] text-slate-400">Tools Shipped</span>
      </div>
      <div class="p-3 bg-slate-950/80 rounded-2xl border border-slate-800">
        <span class="text-xl font-bold text-emerald-400 block">60 FPS</span>
        <span class="text-[10px] text-slate-400">Canvas Engine</span>
      </div>
      <div class="p-3 bg-slate-950/80 rounded-2xl border border-slate-800">
        <span class="text-xl font-bold text-cyan-400 block">100%</span>
        <span class="text-[10px] text-slate-400">Uptime</span>
      </div>
    </div>

    <button onclick="alert('Connecting with Alex Mercer...')" class="w-full py-3 bg-gradient-to-r from-cyan-600 to-indigo-600 text-white rounded-2xl font-semibold text-xs transition shadow-lg shadow-cyan-600/25">
      Collaborate on Next Project 🚀
    </button>
  </div>
</body>
</html>`,
  },
];

export const GuestDashboard: React.FC<GuestDashboardProps> = ({
  language,
  onSwitchToUser,
  avatarSettings,
}) => {
  const [activeMainTab, setActiveMainTab] = useState<'sandbox' | 'models' | 'tokens' | 'json'>('sandbox');
  const [device, setDevice] = useState<DeviceType>('desktop');
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('saas-landing');
  const [editorCode, setEditorCode] = useState<string>(SANDBOX_TEMPLATES[0].code);
  const [liveRenderHtml, setLiveRenderHtml] = useState<string>(SANDBOX_TEMPLATES[0].code);
  const [isCopied, setIsCopied] = useState<boolean>(false);
  const [domCount, setDomCount] = useState<number>(34);

  // Benchmarks & Secondary Tool States
  const [selectedModel, setSelectedModel] = useState<string>('gemini-2.5-flash');
  const [promptInput, setPromptInput] = useState<string>(
    'Write a production TypeScript function to calculate cosine similarity between two vector embeddings.'
  );
  const [isRunningPrompt, setIsRunningPrompt] = useState<boolean>(false);
  const [promptOutput, setPromptOutput] = useState<string>('');
  const [calcInput, setCalcInput] = useState('100000');
  const [calcOutput, setCalcOutput] = useState('20000');
  const [jsonRaw, setJsonRaw] = useState('{"service":"supremeai","models":["gemini-2.5-pro","claude-3-7"],"active":true}');
  const [jsonFormatted, setJsonFormatted] = useState('');

  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Switch Template
  const handleSelectTemplate = (id: string) => {
    const t = SANDBOX_TEMPLATES.find(temp => temp.id === id);
    if (!t) return;
    setSelectedTemplateId(id);
    setEditorCode(t.code);
    setLiveRenderHtml(t.code);
    jarvisAudio.playScan();
  };

  // Run / Re-evaluate Code
  const handleRunCode = () => {
    setLiveRenderHtml(editorCode);
    jarvisAudio.playActivate();
  };

  // Reset Template
  const handleResetCode = () => {
    const t = SANDBOX_TEMPLATES.find(temp => temp.id === selectedTemplateId);
    if (t) {
      setEditorCode(t.code);
      setLiveRenderHtml(t.code);
      jarvisAudio.playScan();
    }
  };

  // Copy Code
  const handleCopyCode = () => {
    navigator.clipboard.writeText(editorCode);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  // Download Single HTML File
  const handleDownloadHtml = () => {
    const blob = new Blob([editorCode], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `supremeai-sandbox-${selectedTemplateId}.html`;
    a.click();
    URL.revokeObjectURL(url);
    jarvisAudio.playSuccess();
  };

  // Listen to Audio Companion Guide
  const handlePlayVoiceGuide = () => {
    jarvisAudio.playActivate();
    const companionName = avatarSettings?.name || 'JARVIS';
    const textBn = `স্বাগতম গেস্ট স্যান্ডবক্সে! আমি ${companionName}। এখানে আপনি কোনো লগইন ছাড়াই সরাসরি ডেস্কটপ, ট্যাবলেট ও মোবাইলে লাইভ ইউআই কোড টেস্ট ও ডাউনলোড করতে পারবেন।`;
    const textEn = `Welcome to the Guest Sandbox! I am ${companionName}. Here you can test, modify and export live UI components in real-time across Desktop, Tablet, and Mobile frames with zero signup.`;
    
    jarvisAudio.speak(
      language === 'bn' ? textBn : textEn,
      language,
      undefined,
      {
        gender: avatarSettings?.gender,
        pitch: avatarSettings?.pitch,
        rate: avatarSettings?.rate,
        accent: avatarSettings?.accent,
      }
    );
  };

  // Inspect DOM count from iframe
  useEffect(() => {
    const timer = setTimeout(() => {
      try {
        if (iframeRef.current?.contentDocument) {
          const count = iframeRef.current.contentDocument.querySelectorAll('*').length;
          if (count > 0) setDomCount(count);
        }
      } catch {}
    }, 600);
    return () => clearTimeout(timer);
  }, [liveRenderHtml]);

  return (
    <div className="space-y-6">
      {/* Hero Welcome Bar with Quick Voice Companion & Tier Stats */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-5 sm:p-7 relative overflow-hidden backdrop-blur-md">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex items-center gap-2 text-xs font-semibold text-cyan-400">
              <Sparkles className="w-4 h-4 text-cyan-400" />
              <span>{language === 'bn' ? 'পাবলিক ও গেস্ট ওয়ার্কবেঞ্চ' : 'Public & Guest AI Workbench'}</span>
              <span aria-hidden="true">·</span>
              <span className="text-emerald-400 font-mono font-bold">Zero Signup Required</span>
            </div>

            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
              {language === 'bn'
                ? 'ইন্টারেক্টিভ মাল্টি-ডিভাইস লাইভ কোড স্যান্ডবক্স'
                : 'Interactive Multi-Device Live Code Sandbox'}
            </h1>

            <p className="text-xs sm:text-sm text-slate-300 leading-relaxed">
              {language === 'bn'
                ? 'কোনো অ্যাকাউন্ট খোলার ঝামেলা ছাড়াই সরাসরি কোড এডিট করুন, তাৎক্ষণিক লাইভ প্রিভিউ দেখুন এবং তৈরি করা কোড ১-ক্লিকে ডাউনলোড করুন।'
                : 'Instantly build, inspect and test production-grade UI components across Desktop, Tablet and Mobile frames without any sign-up hurdles.'}
            </p>

            <div className="pt-2 flex flex-wrap items-center gap-3">
              <button
                onClick={handlePlayVoiceGuide}
                className="px-3.5 py-1.5 text-xs font-semibold text-cyan-200 bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-700/60 rounded-xl transition flex items-center gap-1.5 shadow-sm"
              >
                <Volume2 className="w-3.5 h-3.5 text-cyan-400" />
                <span>{language === 'bn' ? 'সহকারীর অডিও গাইড শুনুন' : 'Listen to Audio Guide'}</span>
              </button>

              <button
                onClick={onSwitchToUser}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition flex items-center gap-1.5 shadow-md shadow-indigo-600/30"
              >
                <span>{language === 'bn' ? 'ইউজার ওয়ার্কস্পেস খুলুন' : 'Open User Workspace'}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Quick Sandbox Telemetry Card */}
          <div className="bg-slate-950/90 border border-slate-800 rounded-2xl p-4 min-w-[240px] text-xs space-y-2.5">
            <div className="flex items-center justify-between pb-2 border-b border-slate-800">
              <span className="font-semibold text-slate-300">Sandbox Telemetry</span>
              <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-800">
                ACTIVE
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">DOM Nodes:</span>
              <span className="font-mono text-cyan-400 font-semibold">{domCount} Elements</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Rendering Engine:</span>
              <span className="font-mono text-slate-200">Isolated Blob Iframe</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Tailwind CSS:</span>
              <span className="font-mono text-emerald-400 font-semibold">Pre-Injected</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Device Frame:</span>
              <span className="font-mono text-indigo-400 uppercase">{device}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Tabs: Sandbox (Centerpiece), Benchmarks, Token Calc, JSON */}
      <div className="flex items-center justify-between gap-4 flex-wrap pb-1">
        <div className="flex items-center gap-1 p-1 bg-slate-900 border border-slate-800 rounded-2xl">
          <button
            onClick={() => setActiveMainTab('sandbox')}
            className={`px-4 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 ${
              activeMainTab === 'sandbox'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Code className="w-4 h-4" />
            <span>{language === 'bn' ? '⚡ লাইভ কোড স্যান্ডবক্স' : '⚡ Live Sandbox'}</span>
          </button>

          <button
            onClick={() => setActiveMainTab('models')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 ${
              activeMainTab === 'models'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Cpu className="w-4 h-4" />
            <span>{language === 'bn' ? 'মডেল বেঞ্চমার্ক' : 'Model Benchmarks'}</span>
          </button>

          <button
            onClick={() => setActiveMainTab('tokens')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 ${
              activeMainTab === 'tokens'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <Calculator className="w-4 h-4" />
            <span>{language === 'bn' ? 'টোকেন ক্যালকুলেটর' : 'Token Calculator'}</span>
          </button>

          <button
            onClick={() => setActiveMainTab('json')}
            className={`px-3.5 py-2 text-xs font-semibold rounded-xl transition-all flex items-center gap-2 ${
              activeMainTab === 'json'
                ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/30'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            <FileJson className="w-4 h-4" />
            <span>JSON</span>
          </button>
        </div>

        {/* Quick Export / Download Button */}
        {activeMainTab === 'sandbox' && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadHtml}
              className="px-3.5 py-2 text-xs font-semibold text-emerald-300 bg-emerald-950/80 hover:bg-emerald-900 border border-emerald-700/60 rounded-xl transition flex items-center gap-1.5 shadow-sm"
              title="Download HTML file directly"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{language === 'bn' ? 'HTML ডাউনলোড' : 'Download HTML'}</span>
            </button>
          </div>
        )}
      </div>

      {/* TAB 1: INTERACTIVE LIVE SANDBOX (CENTERPIECE) */}
      {activeMainTab === 'sandbox' && (
        <div className="space-y-4 animate-fadeIn">
          {/* Cockpit Toolbar: Template Selector & Device Toggles */}
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-3 flex flex-col md:flex-row items-center justify-between gap-4">
            {/* Template Selector Dropdown */}
            <div className="flex items-center gap-2 w-full md:w-auto">
              <span className="text-xs text-slate-400 font-semibold shrink-0">
                {language === 'bn' ? 'টেমপ্লেট:' : 'Template:'}
              </span>
              <select
                value={selectedTemplateId}
                onChange={(e) => handleSelectTemplate(e.target.value)}
                className="bg-slate-950 border border-slate-800 focus:border-indigo-500 rounded-xl px-3 py-1.5 text-xs text-white font-medium outline-none cursor-pointer"
              >
                {SANDBOX_TEMPLATES.map((t) => (
                  <option key={t.id} value={t.id}>
                    {language === 'bn' ? t.nameBn : t.nameEn} ({t.badge})
                  </option>
                ))}
              </select>
            </div>

            {/* Device Viewport Selector */}
            <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-xl">
              <button
                onClick={() => setDevice('desktop')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ${
                  device === 'desktop' ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                }`}
                title="Desktop 100% Fluid"
              >
                <Monitor className="w-3.5 h-3.5" />
                <span>Desktop</span>
              </button>
              <button
                onClick={() => setDevice('tablet')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ${
                  device === 'tablet' ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                }`}
                title="Tablet 768px"
              >
                <Tablet className="w-3.5 h-3.5" />
                <span>Tablet (768px)</span>
              </button>
              <button
                onClick={() => setDevice('mobile')}
                className={`px-3 py-1 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ${
                  device === 'mobile' ? 'bg-indigo-600 text-white font-bold' : 'text-slate-400 hover:text-white'
                }`}
                title="Mobile iPhone 375px"
              >
                <Smartphone className="w-3.5 h-3.5" />
                <span>Mobile (375px)</span>
              </button>
            </div>

            {/* Run & Reset Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleRunCode}
                className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition"
              >
                <Play className="w-3.5 h-3.5" />
                <span>{language === 'bn' ? 'কোড রান করুন' : 'Run Code'}</span>
              </button>

              <button
                onClick={handleResetCode}
                className="p-1.5 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-800 rounded-xl transition"
                title="Reset to default template"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>

              <button
                onClick={handleCopyCode}
                className="p-1.5 bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-white border border-slate-800 rounded-xl transition"
                title="Copy Code"
              >
                {isCopied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              </button>
            </div>
          </div>

          {/* Split Workstation: Left Code Editor + Right Live Device Frame */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-[640px]">
            {/* Left: Code Editor (5 Columns) */}
            <div className="lg:col-span-5 bg-slate-950 border border-slate-800 rounded-3xl p-4 flex flex-col justify-between overflow-hidden">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-xs text-slate-400">
                <span className="font-semibold text-slate-300 flex items-center gap-1.5">
                  <Code className="w-3.5 h-3.5 text-indigo-400" />
                  <span>index.html (HTML + Tailwind)</span>
                </span>
                <span className="font-mono text-[11px] text-slate-500">
                  {editorCode.split('\n').length} lines · {(editorCode.length / 1024).toFixed(1)} KB
                </span>
              </div>

              <textarea
                value={editorCode}
                onChange={(e) => setEditorCode(e.target.value)}
                rows={24}
                className="w-full flex-1 bg-transparent text-slate-200 font-mono text-[11px] leading-relaxed p-2 outline-none resize-none overflow-y-auto selection:bg-indigo-600/40"
                spellCheck={false}
              />

              <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                <span>Tip: Edit any code and click "Run Code" to hot-render.</span>
                <span className="text-emerald-400 font-mono">UTF-8 Ready</span>
              </div>
            </div>

            {/* Right: Live Sandboxed Device Viewport (7 Columns) */}
            <div className="lg:col-span-7 bg-slate-900/60 border border-slate-800 rounded-3xl p-4 flex flex-col items-center justify-center overflow-hidden">
              {/* Responsive Container Framing */}
              <div 
                className={`transition-all duration-300 ease-out bg-slate-950 border border-slate-800 shadow-2xl overflow-hidden flex flex-col ${
                  device === 'desktop'
                    ? 'w-full h-full min-h-[600px] rounded-2xl'
                    : device === 'tablet'
                    ? 'w-[480px] h-[600px] rounded-[32px] border-[8px] border-slate-800'
                    : 'w-[320px] h-[580px] rounded-[38px] border-[10px] border-slate-800'
                }`}
              >
                {/* Mobile / Tablet Notch & Header Bar */}
                {device !== 'desktop' && (
                  <div className="h-6 bg-slate-900 flex items-center justify-center shrink-0">
                    <div className="w-16 h-3 bg-slate-950 rounded-full" />
                  </div>
                )}

                {/* Device Window Header for Desktop */}
                {device === 'desktop' && (
                  <div className="h-9 px-4 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between shrink-0 text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
                      <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
                    </div>
                    <div className="font-mono text-[11px] text-slate-400 px-3 py-0.5 rounded-md bg-slate-950 border border-slate-800">
                      https://sandbox.supremeai.local/preview
                    </div>
                    <div className="text-[10px] font-mono text-emerald-400">
                      LIVE
                    </div>
                  </div>
                )}

                {/* Actual Sandboxed Iframe */}
                <iframe
                  ref={iframeRef}
                  srcDoc={liveRenderHtml}
                  title="Guest Live Sandbox"
                  sandbox="allow-scripts allow-modals"
                  className="w-full flex-1 bg-white border-0"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: MODEL BENCHMARKS */}
      {activeMainTab === 'models' && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 space-y-6 animate-fadeIn">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Cpu className="w-4 h-4 text-indigo-400" />
              <span>{language === 'bn' ? 'ফাউন্ডেশনাল এআই মডেল তুলনা ও ল্যাটেন্সি' : 'Foundation AI Model Benchmarks'}</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              {language === 'bn'
                ? 'বিভিন্ন মডেলের রিয়েল-টাইম স্পিড, কনটেক্সট উইন্ডো ও ইন্টেলিজেন্স স্কোর।'
                : 'Benchmark frontier model latencies, context capacities, and benchmark scores.'}
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {AI_MODELS_DATA.map((m) => (
              <div key={m.id} className="p-4 rounded-2xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white text-xs">{m.name}</span>
                  <span className="text-[10px] font-mono text-indigo-400 px-2 py-0.5 rounded bg-indigo-950/60 border border-indigo-800">
                    {m.provider}
                  </span>
                </div>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Context Window:</span>
                    <span className="text-slate-200 font-mono">{m.contextWindow}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Median Latency:</span>
                    <span className="text-emerald-400 font-mono font-semibold">{m.speedMs}ms</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Cost per 1M:</span>
                    <span className="text-slate-200 font-mono">{m.costPer1MTokens}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 3: TOKEN CALCULATOR */}
      {activeMainTab === 'tokens' && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 space-y-6 animate-fadeIn">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Calculator className="w-4 h-4 text-indigo-400" />
              <span>{language === 'bn' ? 'টোকেন ও কস্ট ক্যালকুলেটর' : 'Token & API Cost Calculator'}</span>
            </h3>
            <p className="text-xs text-slate-400 mt-1">
              Calculate projected prompt and completion token costs across major providers.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-xl">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Input Tokens:</label>
              <input
                type="number"
                value={calcInput}
                onChange={(e) => setCalcInput(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white font-mono outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Output Tokens:</label>
              <input
                type="number"
                value={calcOutput}
                onChange={(e) => setCalcOutput(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-xs text-white font-mono outline-none"
              />
            </div>
          </div>

          <div className="p-4 bg-slate-950 border border-slate-800 rounded-2xl max-w-xl text-xs space-y-2">
            <span className="font-semibold text-slate-300 block">Estimated Cost:</span>
            <div className="flex justify-between">
              <span className="text-slate-400">Gemini 2.5 Flash:</span>
              <span className="text-emerald-400 font-mono font-bold">$0.0125</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Claude 3.7 Sonnet:</span>
              <span className="text-indigo-400 font-mono font-bold">$0.4500</span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: JSON VALIDATOR */}
      {activeMainTab === 'json' && (
        <div className="bg-slate-900/60 border border-slate-800 rounded-3xl p-6 space-y-4 animate-fadeIn">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileJson className="w-4 h-4 text-indigo-400" />
              <span>JSON Formatter & Validator</span>
            </h3>
          </div>
          <textarea
            rows={6}
            value={jsonRaw}
            onChange={(e) => setJsonRaw(e.target.value)}
            className="w-full bg-slate-950 border border-slate-800 rounded-2xl p-3 text-xs text-slate-200 font-mono outline-none"
          />
          <button
            onClick={() => {
              try {
                const parsed = JSON.parse(jsonRaw);
                setJsonFormatted(JSON.stringify(parsed, null, 2));
              } catch (e: any) {
                setJsonFormatted(`Invalid JSON: ${e.message}`);
              }
            }}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl text-xs font-semibold"
          >
            Format & Validate JSON
          </button>
          {jsonFormatted && (
            <pre className="p-4 bg-slate-950 border border-slate-800 rounded-2xl text-xs font-mono text-cyan-300 overflow-auto max-h-60">
              {jsonFormatted}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};
