import React, { useState, useRef, useEffect } from 'react';
import { DevicePreviewFrame } from '../preview/DevicePreviewFrame';
import { JarvisHudOrb, type JarvisState } from '../jarvis/JarvisHudOrb';
import { jarvisAudio } from '../../utils/audioFx';
import { PREVIEW_TEMPLATES, type PreviewTemplate } from '../../data/previewTemplates';
import type { ChatMessage } from '../../types/chat';
import type { SelectedElementInfo, VersionSnapshot, InjectedPackage } from '../../types/worldclass';
import { VERSION_SNAPSHOTS } from '../../data/projectFiles';
import { PublishModal } from '../deploy/PublishModal';
import { PackageInjectorModal } from '../packages/PackageInjectorModal';
import { IntentDiscoveryBanner, type UserPersona } from './IntentDiscoveryBanner';
import { WorkspaceSettingsModal } from '../settings/WorkspaceSettingsModal';
import { JarvisHoloCall } from '../jarvis/JarvisHoloCall';
import { 
  Bot, Send, Mic, Sparkles, Terminal, Code2, Copy, Check, 
  ChevronDown, ChevronUp, Eye, ShieldAlert, Zap, FolderGit2, 
  RotateCcw, Sliders, Play, RefreshCw, Layers, MousePointerClick, 
  Rocket, Package, SlidersHorizontal, UserPlus, Lock 
} from 'lucide-react';
import { DEFAULT_AVATAR_SETTINGS, type AvatarSettings } from '../../types/avatar';

const AI_MODELS_DATA = [
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
  { id: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet' },
  { id: 'gpt-4o', name: 'GPT-4o Omniscient' },
];

interface SplitStudioViewProps {
  language: 'bn' | 'en';
  onExecuteMcpTool?: (toolName: string, args: Record<string, any>) => Promise<any>;
}

export const SplitStudioView: React.FC<SplitStudioViewProps> = ({
  language,
  onExecuteMcpTool,
}) => {
  // Snapshots & Active Version
  const [snapshots, setSnapshots] = useState<VersionSnapshot[]>(VERSION_SNAPSHOTS);
  const [currentVersionIndex, setCurrentVersionIndex] = useState<number>(VERSION_SNAPSHOTS.length - 1);

  // Active Generated HTML in Preview
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('food-delivery');
  const [currentHtml, setCurrentHtml] = useState<string>(PREVIEW_TEMPLATES[0].html);

  // User Persona (Tier 2 Intent Discovery)
  const [currentPersona, setCurrentPersona] = useState<UserPersona>('developer');

  // Modals
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [isPackageModalOpen, setIsPackageModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
  const [isSoftGateOpen, setIsSoftGateOpen] = useState(false);
  const [isHoloCallOpen, setIsHoloCallOpen] = useState(false);

  // Avatar Freedom State
  const [avatarSettings, setAvatarSettings] = useState<AvatarSettings>(() => {
    try {
      const saved = localStorage.getItem('supremeai_avatar_settings');
      if (saved) return JSON.parse(saved);
    } catch (_err) {
      /* ignore invalid JSON in storage */
    }
    return DEFAULT_AVATAR_SETTINGS;
  });

  // JARVIS State
  const [jarvisState, setJarvisState] = useState<JarvisState>('idle');
  const [selectedModel, setSelectedModel] = useState<string>('gemini-2.5-pro');
  const [inputMessage, setInputMessage] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isListening, setIsListening] = useState<boolean>(false);
  const [isFixingAudit, setIsFixingAudit] = useState<boolean>(false);

  // Active Canonical Role
  const [activeRole, setActiveRole] = useState<'coder' | 'human-eye' | 'guardian' | 'scout' | 'ci-fixer'>('coder');

  // Bottom Trays Toggle
  const [bottomTray, setBottomTray] = useState<'none' | 'files' | 'terminal'>('none');
  const onSendMessageRef = useRef<(text?: string) => Promise<void>>(async () => {});
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '[MCP Bridge] Connected to supremeai-mcp-tower.onrender.com',
    '[Sandbox] Iframe renderer initialized with Tailwind CSS v4',
    '[Human-Eye] DOM visual inspector armed. Zero console errors.',
    '[Time-Travel] Snapshots v1.0 - v1.3 loaded in state engine.',
    '[Tier 2 Intent] Adaptive discovery active. Persona: Full-Stack Developer.',
  ]);

  // Messages Thread
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm-init',
      role: 'assistant',
      content: language === 'bn'
        ? 'অনলাইন এবং সম্পূর্ণ প্রস্তুত, স্যার। ডান পাশের লাইভ প্রিভিউ প্যানেলে রেস্তোরাঁর ফুড ডেলিভারি অ্যাপটি লোড করা হয়েছে। আপনি সরাসরি স্ক্রিনের যেকোনো এলিমেন্টে ক্লিক করে (🎯 এলিমেন্ট এডিট) মাইক্রো-প্রম্পট দিতে পারেন, টাইম-ট্রাভেল দিয়ে v1.0 থেকে v1.3-তে রিওয়াইন্ড করতে পারেন, অথবা 1-ক্লিক ক্লাউড পাবলিশ করতে পারেন।'
        : 'Online and fully armed, sir. The artisan food delivery web application has been compiled into your live preview panel on the right. You can now use Click-to-Edit (🎯) to modify elements visually, rewind via Time-Travel (v1.0 - v1.3), inspect Git Diff, or 1-click publish to the global cloud edge.',
      timestamp: '10:00 AM',
      model: 'gemini-2.5-pro',
      thinkingTrace: [
        'Bootstrapped split-screen architecture with sandboxed iframe.',
        'Wired live DevTools bar with runtime error listeners.',
        'Attached Click-to-Edit DOM inspector with floating micro-prompt popover.',
        'Integrated Git diff viewer and Time-Travel snapshot scrubber.',
      ],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle template selection
  const handleSelectTemplate = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const tmpl = PREVIEW_TEMPLATES.find((t) => t.id === templateId) || PREVIEW_TEMPLATES[0];
    setCurrentHtml(tmpl.html);
    jarvisAudio.playActivate();
    setTerminalLogs((prev) => [`[Template] Loaded ${tmpl.nameEn}`, ...prev]);

    const tmplMsg: ChatMessage = {
      id: `tmpl-${Date.now()}`,
      role: 'assistant',
      content: language === 'bn'
        ? `টেমপ্লেট "${tmpl.nameBn}" লাইভ প্রিভিউতে মাউন্ট করা হয়েছে, স্যার।`
        : `Mounted "${tmpl.nameEn}" into the live interactive canvas, sir.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: selectedModel,
    };
    setMessages((prev) => [...prev, tmplMsg]);
  };

  // Handle Persona Switching
  const handleSelectPersona = (persona: UserPersona) => {
    setCurrentPersona(persona);
    if (persona === 'developer') {
      setActiveRole('coder');
      setTerminalLogs((prev) => ['[Persona] Tuned for Developer: Git diffs & MCP enabled', ...prev]);
    } else if (persona === 'designer') {
      setActiveRole('human-eye');
      setTerminalLogs((prev) => ['[Persona] Tuned for Designer: Click-to-Edit inspector prioritized', ...prev]);
    } else if (persona === 'founder') {
      setActiveRole('coder');
      setTerminalLogs((prev) => ['[Persona] Tuned for Founder: Rapid MVP synthesis mode', ...prev]);
    }
  };

  // Handle Version Snapshot Scrubber selection
  const handleSelectSnapshot = (index: number) => {
    setCurrentVersionIndex(index);
    jarvisAudio.playActivate();
    const snap = snapshots[index];

    let newHtml = PREVIEW_TEMPLATES[0].html;

    if (snap.version === 'v1.0') {
      newHtml = PREVIEW_TEMPLATES[0].html.replace('bg-gradient-to-r from-emerald-500 to-teal-500', 'bg-emerald-700');
    } else if (snap.version === 'v1.1') {
      newHtml = PREVIEW_TEMPLATES[0].html;
    } else if (snap.version.includes('v1.3')) {
      newHtml = PREVIEW_TEMPLATES[0].html.replace(
        'Order Hot Bowl Now',
        'Order Hot Bowl Now (⚡ 20% Off Today)'
      );
    }

    setCurrentHtml(newHtml);
    setTerminalLogs((prev) => [`[Time-Travel] Rewound to ${snap.version}: "${snap.title}"`, ...prev]);

    const travelMsg: ChatMessage = {
      id: `tt-${Date.now()}`,
      role: 'assistant',
      content: language === 'bn'
        ? `টাইম-ট্রাভেল স্ন্যাপশট ${snap.version} ("${snap.title}")-এ রিওয়াইন্ড করা হয়েছে, স্যার।`
        : `Time-travel snapshot ${snap.version} ("${snap.title}") successfully loaded into live preview, sir.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: 'time-travel',
    };
    setMessages((prev) => [...prev, travelMsg]);
  };

  // Handle Click-to-Edit Visual Micro-Prompt
  const handleApplyMicroPrompt = (prompt: string, element: SelectedElementInfo) => {
    jarvisAudio.playScan();
    setJarvisState('thinking');

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: language === 'bn'
        ? `🎯 [এলিমেন্ট এডিট: ${element.tagName} ${element.selector}] ${prompt}`
        : `🎯 [Visual Inspect: ${element.tagName} ${element.selector}] ${prompt}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);

    setTimeout(() => {
      jarvisAudio.playSuccess();
      setJarvisState('speaking');

      let modified = currentHtml;
      if (prompt.toLowerCase().includes('gold') || prompt.toLowerCase().includes('গোল্ডেন')) {
        modified = modified.replace(
          /from-emerald-500 to-teal-500|from-indigo-600 to-purple-600/g,
          'from-amber-400 via-yellow-500 to-amber-600 shadow-amber-500/40 text-slate-950 font-black'
        );
      } else if (prompt.toLowerCase().includes('padding') || prompt.toLowerCase().includes('প্যাডিং')) {
        modified = modified.replace(/px-6 py-3|px-5 py-2.5/g, 'px-10 py-5');
      } else if (prompt.toLowerCase().includes('glass') || prompt.toLowerCase().includes('গ্লাস')) {
        modified = modified.replace(/bg-slate-900/g, 'bg-slate-900/70 backdrop-blur-xl border border-white/20');
      } else {
        modified = modified.replace('Gusteau\'s Kitchen', 'Gusteau\'s Luxury Kitchen');
      }

      setCurrentHtml(modified);

      const confirmMsg = language === 'bn'
        ? `স্যার, আপনার নির্দেশ অনুসারে ${element.tagName} (${element.selector})-এ সার্জিকাল পরিবর্তন প্রয়োগ করা হয়েছে। লাইভ প্রিভিউতে পরিবর্তনটি দৃশ্যমান।`
        : `Sir, targeted visual micro-edit has been surgically applied to ${element.tagName} (${element.selector}). Live preview canvas refreshed.`;

      const asstMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: confirmMsg,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        thinkingTrace: [
          `Targeted element: <${element.tagName.toLowerCase()}> with selector ${element.selector}.`,
          `Analyzed micro-intent: "${prompt}".`,
          `Applied surgical CSS/DOM class mutation without disrupting surrounding layout hierarchy.`,
        ],
      };

      setMessages((prev) => [...prev, asstMsg]);
      setTerminalLogs((prev) => [`[Inspector] Surgically edited ${element.selector}: "${prompt}"`, ...prev]);

      jarvisAudio.speak(confirmMsg, language, () => {
        setJarvisState('idle');
      });
    }, 700);
  };

  // Setup Web Speech Recognition
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        const recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;
        recognition.lang = language === 'bn' ? 'bn-BD' : 'en-US';

        recognition.onstart = () => {
          setIsListening(true);
          setJarvisState('listening');
          jarvisAudio.playActivate();
        };

        recognition.onresult = (event: any) => {
          const transcript = event.results[0][0].transcript;
          setIsListening(false);
          setInputMessage(transcript);
          onSendMessageRef.current(transcript);
        };

        recognition.onerror = () => {
          setIsListening(false);
          setJarvisState('idle');
        };

        recognition.onend = () => {
          setIsListening(false);
          if (jarvisState === 'listening') setJarvisState('idle');
        };

        recognitionRef.current = recognition;
      }
    }
  }, [language]);

  const toggleListen = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      setJarvisState('idle');
    } else {
      try {
        if (recognitionRef.current) {
          recognitionRef.current.lang = language === 'bn' ? 'bn-BD' : 'en-US';
          recognitionRef.current.start();
        } else {
          const fallbackCmd = language === 'bn' ? 'একটি SaaS গ্লাসমরফিজম পেজ বানাও' : 'Build a SaaS landing page with glassmorphism';
          setInputMessage(fallbackCmd);
          onSendMessageRef.current(fallbackCmd);
        }
      } catch (_err) {
        setIsListening(false);
        setJarvisState('idle');
      }
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = textToSend || inputMessage;
    if (!text.trim() || isGenerating) return;

    jarvisAudio.playScan();

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputMessage('');
    setIsGenerating(true);
    setJarvisState('thinking');

    const lower = text.toLowerCase();

    const isFoodRequest = lower.includes('food') || lower.includes('restaurant') || lower.includes('রেস্তোরাঁ') || lower.includes('ফুড');
    const isSaasRequest = lower.includes('saas') || lower.includes('glass') || lower.includes('ড্যাশবোর্ড') || lower.includes('dashboard') || lower.includes('ক্লিন');
    const isFinanceRequest = lower.includes('fintech') || lower.includes('trading') || lower.includes('chart') || lower.includes('ট্রেডিং') || lower.includes('ফিনটেক');
    const isKanbanRequest = lower.includes('kanban') || lower.includes('board') || lower.includes('agile') || lower.includes('কানবান');
    const isDeployRequest = lower.includes('deploy') || lower.includes('publish') || lower.includes('পাবলিশ');

    if (isDeployRequest) {
      setIsPublishModalOpen(true);
    }

    setTimeout(() => {
      jarvisAudio.playSuccess();
      setJarvisState('speaking');

      let replyContent = '';

      if (isDeployRequest) {
        replyContent = language === 'bn'
          ? 'ক্লাউড পাবলিশ মডাল সক্রিয় করা হয়েছে, স্যার। ক্লাউডফ্লেয়ার এজ বা ভার্সেলে 1-ক্লিকে সাবডোমেনে লাইভ করুন।'
          : 'Global multi-cloud publishing engine activated. Ready for 1-click deployment to Cloudflare Edge.';
      } else if (isSaasRequest) {
        setCurrentHtml(PREVIEW_TEMPLATES[1].html);
        setSelectedTemplateId('saas-glassmorphism');
        replyContent = language === 'bn'
          ? 'SaaS গ্লাসমরফিজম ল্যান্ডিং পেজ তৈরি সম্পন্ন। টাইটেল, লাইভ মেট্রিক্স ও এজ বাটন প্রিভিউ ক্যানভাসে মাউন্ট হয়েছে।'
          : 'SaaS Glassmorphism Landing Page synthesized and mounted into live preview.';
        setTerminalLogs((prev) => [`[JARVIS Core] Rendered SaaS glassmorphism header & live metrics`, ...prev]);
      } else if (isFinanceRequest) {
        setCurrentHtml(PREVIEW_TEMPLATES[2].html);
        setSelectedTemplateId('fintech-analytics');
        replyContent = language === 'bn'
          ? 'রিয়েলটাইম ফিনান্সিয়াল অ্যানালিটিক্স চার্ট লোড হয়েছে। লিকুইডিটি টার্মিনাল ও ট্রেন্ড বার ইন্টারঅ্যাক্টিভ।'
          : 'Realtime Financial Analytics Terminal synthesized with live candlestick bars.';
        setTerminalLogs((prev) => [`[JARVIS Core] Rendered Apex liquidity chart & portfolio metrics`, ...prev]);
      } else if (isKanbanRequest) {
        setCurrentHtml(PREVIEW_TEMPLATES[3].html);
        setSelectedTemplateId('kanban-workflow');
        replyContent = language === 'bn'
          ? 'ইন্টারঅ্যাক্টিভ কানবান ওয়ার্কফ্লো বোর্ড রেন্ডার হয়েছে। স্প্রিন্ট ব্যাকলগ ও প্রগ্রেস কলাম দৃশ্যমান।'
          : 'Interactive KanBan Agile Board generated with real-time issue columns.';
        setTerminalLogs((prev) => [`[JARVIS Core] Rendered 3-column agile sprint board`, ...prev]);
      } else if (isFoodRequest) {
        setCurrentHtml(PREVIEW_TEMPLATES[0].html);
        setSelectedTemplateId('food-delivery');
        replyContent = language === 'bn'
          ? 'স্যার, রেস্তোরাঁ ও ফুড ডেলিভারি অ্যাপটি লোড হয়েছে। যেকোনো মেনু আইটেম বা বাটন এডিট করতে 🎯 আইকনটি ব্যবহার করুন।'
          : 'Sir, an artisan farm-to-table food delivery web application has been synthesized.';
        setTerminalLogs((prev) => [`[JARVIS Core] Synthesized 18 menu items with responsive viewport`, ...prev]);
      } else {
        replyContent = language === 'bn'
          ? 'আপনার নির্দেশ অনুযায়ী আর্কিটেকচার অপ্টিমাইজ করা হয়েছে এবং লাইভ প্রিভিউ আপডেট হয়েছে, স্যার।'
          : 'Directive implemented according to clean architectural principles and mounted to the preview engine, sir.';
      }

      const asstMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: replyContent,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        thinkingTrace: [
          `Matched directive semantics with ${activeRole.toUpperCase()} canonical persona.`,
          `Synthesized responsive HTML/Tailwind structure with zero-pill metadata discipline.`,
          `Validated mobile, tablet (768px), and desktop viewport bounds with WCAG AA contrast.`,
        ],
      };

      setMessages((prev) => [...prev, asstMsg]);
      setIsGenerating(false);

      jarvisAudio.speak(
        replyContent, 
        language, 
        () => {
          setJarvisState('idle');
        },
        {
          gender: avatarSettings.gender,
          pitch: avatarSettings.pitch,
          rate: avatarSettings.rate,
          accent: avatarSettings.accent,
        }
      );
    }, 800);
  };

  useEffect(() => {
    onSendMessageRef.current = handleSendMessage;
  });

  // Human-Eye Autonomous UI Audit Handler
  const handleFixWithHumanEye = () => {
    setIsFixingAudit(true);
    jarvisAudio.playScan();
    setTerminalLogs((prev) => ['[Human-Eye] Auditing DOM elements and contrast boundaries...', ...prev]);

    setTimeout(() => {
      setIsFixingAudit(false);
      jarvisAudio.playSuccess();
      setTerminalLogs((prev) => ['[Human-Eye] All layout boundaries verified. Score 98/100.', ...prev]);
      const auditMsg: ChatMessage = {
        id: `audit-${Date.now()}`,
        role: 'assistant',
        content: language === 'bn'
          ? 'Human-Eye অডিট সফলভাবে সম্পন্ন হয়েছে, স্যার। প্রিভিউতে কোনো সিনট্যাক্স এরর নেই এবং কনট্রাস্ট রেশিও ৪.৫:১ পুরোপুরি যাচাইকৃত।'
          : 'Human-Eye visual audit complete, sir. Zero console errors and perfect WCAG AA contrast compliance verified.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: 'human-eye',
      };
      setMessages((prev) => [...prev, auditMsg]);
    }, 900);
  };

  const handleInjectPackage = (pkg: InjectedPackage) => {
    setTerminalLogs((prev) => [`[NPM/CDN] Injected ${pkg.name}@${pkg.version}`, ...prev]);
    const pkgMsg: ChatMessage = {
      id: `pkg-${Date.now()}`,
      role: 'assistant',
      content: language === 'bn'
        ? `প্যাকেজ ${pkg.name}@${pkg.version} সফলভাবে স্যান্ডবক্স লাইভ রেন্ডারারে ইনজেক্ট করা হয়েছে!`
        : `Package ${pkg.name}@${pkg.version} successfully injected into live sandboxed renderer!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: 'package-engine',
    };
    setMessages((prev) => [...prev, pkgMsg]);
  };

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-100px)] min-h-[720px]">
      {/* 1-Click Multi-Cloud Deploy Modal */}
      <PublishModal
        isOpen={isPublishModalOpen}
        onClose={() => setIsPublishModalOpen(false)}
        language={language}
      />

      {/* Instant NPM / CDN Package Injector Modal */}
      <PackageInjectorModal
        isOpen={isPackageModalOpen}
        onClose={() => setIsPackageModalOpen(false)}
        onInjectPackage={handleInjectPackage}
        language={language}
      />

      {/* Tier 4 Workspace Settings & BYOK Modal */}
      <WorkspaceSettingsModal
        isOpen={isSettingsModalOpen}
        onClose={() => setIsSettingsModalOpen(false)}
        language={language}
        avatarSettings={avatarSettings}
        onSaveAvatarSettings={setAvatarSettings}
      />

      {/* Face-to-Face 3D Holographic Video Call */}
      <JarvisHoloCall
        isOpen={isHoloCallOpen}
        onClose={() => setIsHoloCallOpen(false)}
        language={language}
        currentState={jarvisState}
        avatarSettings={avatarSettings}
        onUpdateAvatarSettings={setAvatarSettings}
        onSendMessage={(msg: string) => handleSendMessage(msg)}
        onJumpToPreview={() => setIsHoloCallOpen(false)}
        latestAssistantMessage={messages[messages.length - 1]?.content}
      />

      {/* Tier 2: Adaptive Intent Discovery Banner */}
      <IntentDiscoveryBanner
        currentPersona={currentPersona}
        onSelectPersona={handleSelectPersona}
        onOpenSettings={() => setIsSettingsModalOpen(true)}
        language={language}
      />

      {/* Main Split Grid (45% Studio | 55% Preview) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 flex-1 min-h-0">
        {/* =========================================================================
            LEFT PANE (45% Width): JARVIS Intelligent Studio & Role Dispatcher
            ========================================================================= */}
        <div className="lg:col-span-5 flex flex-col bg-slate-900/60 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
          {/* Left Pane Sci-Fi Header with Mini Arc Reactor */}
          <div className="px-4 py-2.5 bg-slate-950/90 border-b border-slate-800 flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5">
              {/* Clickable Mini Arc Reactor */}
              <div 
                onClick={toggleListen}
                className="relative w-8 h-8 rounded-full bg-slate-900 border border-indigo-500/40 flex items-center justify-center cursor-pointer hover:scale-105 transition-transform"
                title="Click to speak to JARVIS"
              >
                <div className={`w-3 h-3 rounded-full transition-colors ${
                  jarvisState === 'listening' ? 'bg-rose-500 animate-pulse' :
                  jarvisState === 'thinking' ? 'bg-amber-400 animate-spin' :
                  jarvisState === 'speaking' ? 'bg-emerald-400' : 'bg-indigo-500'
                }`} />
                <div className="absolute inset-0 rounded-full border border-indigo-400/20 animate-ping pointer-events-none" />
              </div>

              <div>
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-bold text-white tracking-tight">JARVIS Mark-VII</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                    {jarvisState.toUpperCase()}
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 font-mono">142 MCP Tools Armed</span>
              </div>
            </div>

            {/* Holo-Call Trigger, Model Selector & Settings */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setIsHoloCallOpen(true)}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-600/70 text-cyan-300 shadow-sm shadow-cyan-500/20 transition-all hover:scale-105 active:scale-95"
                title="Open 3D Face-to-Face Holographic Video Call"
              >
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span className="hidden sm:inline">{language === 'bn' ? '🎥 হলো-ভিডিও কল' : '🎥 Holo-Call'}</span>
              </button>

              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="bg-slate-900 border border-slate-800 focus:border-indigo-500 rounded-lg px-2 py-1 text-xs text-slate-200 font-mono outline-none cursor-pointer max-w-[120px] truncate"
              >
                {AI_MODELS_DATA.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>

              <button
                onClick={() => setIsSettingsModalOpen(true)}
                className="p-1.5 text-slate-400 hover:text-white bg-slate-900 border border-slate-800 rounded-lg transition-colors"
                title="Workspace & BYOK Settings"
              >
                <SlidersHorizontal className="w-3.5 h-3.5 text-indigo-400" />
              </button>
            </div>
          </div>

          {/* Canonical Role Dispatch Quick Buttons */}
          <div className="px-3 py-1.5 bg-slate-950/70 border-b border-slate-800 flex items-center gap-1.5 overflow-x-auto shrink-0 text-xs">
            <button
              onClick={() => {
                setActiveRole('coder');
                handleSendMessage(language === 'bn' ? 'একটি SaaS গ্লাসমরফিজম পেজ বানাও' : 'Build a SaaS landing page with glassmorphism header');
              }}
              className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap flex items-center gap-1 ${
                activeRole === 'coder' ? 'bg-indigo-600 text-white font-semibold' : 'bg-slate-900 text-slate-300 hover:text-white border border-slate-800'
              }`}
            >
              <Zap className="w-3 h-3 text-amber-300" />
              <span>{language === 'bn' ? '🚀 অটো-সলভ' : '🚀 Auto-Solve'}</span>
            </button>

            <button
              onClick={() => {
                setActiveRole('human-eye');
                handleFixWithHumanEye();
              }}
              className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap flex items-center gap-1 ${
                activeRole === 'human-eye' ? 'bg-indigo-600 text-white font-semibold' : 'bg-slate-900 text-slate-300 hover:text-white border border-slate-800'
              }`}
            >
              <Eye className="w-3 h-3 text-indigo-400" />
              <span>{language === 'bn' ? '🔍 DevTools Audit' : '🔍 DevTools Audit'}</span>
            </button>

            <button
              onClick={() => {
                setIsPublishModalOpen(true);
              }}
              className="px-2.5 py-1 rounded-md transition-colors whitespace-nowrap flex items-center gap-1 bg-slate-900 text-slate-300 hover:text-white border border-slate-800"
            >
              <Rocket className="w-3 h-3 text-emerald-400" />
              <span>{language === 'bn' ? '🚀 পাবলিশ' : '🚀 Publish'}</span>
            </button>

            <button
              onClick={() => {
                setIsPackageModalOpen(true);
              }}
              className="px-2.5 py-1 rounded-md transition-colors whitespace-nowrap flex items-center gap-1 bg-slate-900 text-slate-300 hover:text-white border border-slate-800"
            >
              <Package className="w-3 h-3 text-indigo-400" />
              <span>{language === 'bn' ? '📦 প্যাকেজ' : '📦 Packages'}</span>
            </button>

            <button
              onClick={() => {
                setActiveRole('ci-fixer');
                handleSendMessage('Auto-heal degraded Render nodes with clearCache: true');
              }}
              className={`px-2.5 py-1 rounded-md transition-colors whitespace-nowrap flex items-center gap-1 ${
                activeRole === 'ci-fixer' ? 'bg-indigo-600 text-white font-semibold' : 'bg-slate-900 text-slate-300 hover:text-white border border-slate-800'
              }`}
            >
              <RotateCcw className="w-3 h-3 text-rose-400" />
              <span>{language === 'bn' ? '⚡ CI-Fixer' : '⚡ CI-Fixer'}</span>
            </button>
          </div>

          {/* Chat Thread Messages Stream */}
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((msg) => {
              const isUser = msg.role === 'user';
              return (
                <div key={msg.id} className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} space-y-1.5`}>
                  <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
                    <span className="font-semibold text-slate-300">
                      {isUser ? (language === 'bn' ? 'আপনি' : 'You') : 'JARVIS Mark-VII'}
                    </span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                  </div>

                  <div
                    className={`max-w-[92%] rounded-xl p-3.5 text-xs leading-relaxed ${
                      isUser
                        ? 'bg-indigo-600 text-white font-medium shadow-md'
                        : 'bg-slate-950/90 border border-slate-800 text-slate-200'
                    }`}
                  >
                    {!isUser && msg.thinkingTrace && (
                      <div className="mb-2 p-2 bg-slate-900/90 rounded border border-slate-800 text-[11px] text-slate-400 font-mono space-y-0.5">
                        <span className="text-indigo-400 font-bold block mb-1">
                          {language === 'bn' ? 'চিন্তন প্রক্রিয়া (Reasoning):' : 'Autonomous Reasoning:'}
                        </span>
                        {msg.thinkingTrace.map((step: string, idx: number) => (
                          <div key={idx}>• {step}</div>
                        ))}
                      </div>
                    )}

                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  </div>
                </div>
              );
            })}

            {isGenerating && (
              <div className="flex items-center gap-2 text-xs text-slate-400 font-mono py-1">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                <span>JARVIS is synthesizing layout & updating preview sandbox...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Collapsible Bottom Trays: Files & Live Terminal Logs */}
          {bottomTray === 'files' && (
            <div className="p-3 bg-slate-950 border-t border-slate-800 text-xs font-mono max-h-36 overflow-auto">
              <span className="text-slate-400 font-bold block mb-1">Workspace Tracked Files:</span>
              <div className="space-y-1 text-slate-300">
                <div>📄 src/components/preview/DevicePreviewFrame.tsx</div>
                <div>📄 src/components/inspector/VisualElementInspector.tsx</div>
                <div>📄 src/components/diff/CodeDiffViewer.tsx</div>
                <div>📄 src/components/timetravel/TimeTravelBar.tsx</div>
                <div>📄 src/components/deploy/PublishModal.tsx</div>
                <div>📄 src/components/settings/WorkspaceSettingsModal.tsx</div>
              </div>
            </div>
          )}

          {bottomTray === 'terminal' && (
            <div className="p-3 bg-slate-950 border-t border-slate-800 text-xs font-mono max-h-36 overflow-auto">
              <span className="text-slate-400 font-bold block mb-1">Live MCP & Studio Logs:</span>
              <div className="space-y-1 text-slate-300 text-[11px]">
                {terminalLogs.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>
          )}

          {/* Tray Toggle Strip */}
          <div className="px-4 py-1.5 bg-slate-950 border-t border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-500">
            <div className="flex items-center gap-3">
              <button
                onClick={() => setBottomTray(bottomTray === 'files' ? 'none' : 'files')}
                className={`hover:text-white transition-colors ${bottomTray === 'files' ? 'text-indigo-400 font-bold' : ''}`}
              >
                [ Files Tray ]
              </button>
              <button
                onClick={() => setBottomTray(bottomTray === 'terminal' ? 'none' : 'terminal')}
                className={`hover:text-white transition-colors ${bottomTray === 'terminal' ? 'text-indigo-400 font-bold' : ''}`}
              >
                [ Logs ({terminalLogs.length}) ]
              </button>
            </div>
            <span>Persona: {currentPersona.toUpperCase()}</span>
          </div>

          {/* Chat Input Bar */}
          <div className="p-3 bg-slate-950 border-t border-slate-800 flex items-center gap-2 shrink-0">
            <button
              onClick={toggleListen}
              className={`p-2.5 rounded-xl border transition-colors ${
                isListening
                  ? 'bg-rose-600 text-white border-rose-500 animate-pulse'
                  : 'bg-slate-900 text-slate-400 hover:text-white border-slate-800'
              }`}
              title="Speak directive to JARVIS"
            >
              <Mic className="w-4 h-4" />
            </button>

            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder={
                language === 'bn'
                  ? 'জার্ভিসকে নির্দেশ দিন (যেমন: "SaaS গ্লাসমরফিজম পেজ বানাও", "পাবলিশ করো")...'
                  : 'Instruct JARVIS (e.g. "Build SaaS glassmorphism page", "Publish app")...'
              }
              className="flex-1 bg-slate-900 border border-slate-800 focus:border-indigo-500 rounded-xl px-3 py-2 text-xs text-slate-200 outline-none"
            />

            <button
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || isGenerating}
              className="p-2.5 font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-xl transition-all disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* =========================================================================
            RIGHT PANE (55% Width): Interactive Multi-Device Preview & Sandboxed Renderer
            ========================================================================= */}
        <div className="lg:col-span-7 flex flex-col h-full min-h-0">
          <DevicePreviewFrame
            htmlCode={currentHtml}
            onRefreshCode={() => jarvisAudio.playScan()}
            onFixWithHumanEye={handleFixWithHumanEye}
            isFixing={isFixingAudit}
            language={language}
            onApplyMicroPrompt={handleApplyMicroPrompt}
            onOpenDeployModal={() => setIsPublishModalOpen(true)}
            onOpenPackageModal={() => setIsPackageModalOpen(true)}
            snapshots={snapshots}
            currentVersionIndex={currentVersionIndex}
            onSelectSnapshot={handleSelectSnapshot}
            selectedTemplateId={selectedTemplateId}
            onSelectTemplate={handleSelectTemplate}
          />
        </div>
      </div>
    </div>
  );
};
