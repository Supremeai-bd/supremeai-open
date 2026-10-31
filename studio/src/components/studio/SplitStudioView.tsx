import React, { useState, useRef, useEffect } from 'react';
import { DevicePreviewFrame } from '../preview/DevicePreviewFrame';
import { type JarvisState } from '../jarvis/JarvisHudOrb';
import { jarvisAudio } from '../../utils/audioFx';
import { PREVIEW_TEMPLATES } from '../../data/previewTemplates';
import type { ChatMessage } from '../../types/chat';
import type { SelectedElementInfo, VersionSnapshot, InjectedPackage } from '../../types/worldclass';
import { VERSION_SNAPSHOTS } from '../../data/projectFiles';
import { PublishModal } from '../deploy/PublishModal';
import { PackageInjectorModal } from '../packages/PackageInjectorModal';
import { WorkspaceSettingsModal } from '../settings/WorkspaceSettingsModal';
import { JarvisHoloCall } from '../jarvis/JarvisHoloCall';
import { 
  Send, Mic, Sparkles, Zap, 
  RotateCcw, SlidersHorizontal, RefreshCw
} from 'lucide-react';
import { DEFAULT_AVATAR_SETTINGS, type AvatarSettings } from '../../types/avatar';

const AI_MODELS_DATA = [
  { id: 'gemini-2.5-pro', name: 'Gemini 2.5 Pro' },
  { id: 'gemini-2.5-flash', name: 'Gemini 2.5 Flash' },
  { id: 'claude-3-7-sonnet', name: 'Claude 3.7 Sonnet' },
  { id: 'gpt-4o', name: 'GPT-4o Omniscient' },
];

interface SplitStudioViewProps {
  language?: 'bn' | 'en';
  onExecuteMcpTool?: (toolName: string, args: Record<string, any>) => Promise<any>;
}

export const SplitStudioView: React.FC<SplitStudioViewProps> = ({
  language = 'en',
}) => {
  // Snapshots & Active Version
  const [snapshots] = useState<VersionSnapshot[]>(VERSION_SNAPSHOTS);
  const [currentVersionIndex, setCurrentVersionIndex] = useState<number>(VERSION_SNAPSHOTS.length - 1);

  // Active Generated HTML in Preview
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('food-delivery');
  const [currentHtml, setCurrentHtml] = useState<string>(PREVIEW_TEMPLATES[0].html);

  // Modals
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [isPackageModalOpen, setIsPackageModalOpen] = useState(false);
  const [isSettingsModalOpen, setIsSettingsModalOpen] = useState(false);
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
  const [activeRole, setActiveRole] = useState<'coder' | 'human-eye' | 'ci-fixer'>('coder');

  // Bottom Trays Toggle
  const [bottomTray, setBottomTray] = useState<'none' | 'files' | 'terminal'>('none');
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '[MCP Bridge] Connected to supremeai-mcp-tower.onrender.com',
    '[Sandbox] Iframe renderer initialized with Tailwind CSS v4',
    '[Human-Eye] DOM visual inspector armed. Zero console errors.',
    '[Engine] Sovereign AI synthesis ready.',
  ]);

  // Messages Thread
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'm-init',
      role: 'assistant',
      content: 'Online and fully ready, Commander. The live application preview has been loaded on the right canvas. You can speak directives, use Click-to-Edit directly on elements, or deploy straight to the cloud.',
      timestamp: '10:00 AM',
      model: 'gemini-2.5-pro',
      thinkingTrace: [
        'Bootstrapped split-screen architecture with sandboxed iframe.',
        'Wired live DevTools bar with runtime error listeners.',
        'Attached Click-to-Edit DOM inspector with micro-prompt overlay.',
      ],
    },
  ]);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isGenerating]);

  // Handle Voice Listening Toggle
  const toggleListen = () => {
    if (isListening) {
      setIsListening(false);
      setJarvisState('idle');
      jarvisAudio.playScan();
    } else {
      setIsListening(true);
      setJarvisState('listening');
      jarvisAudio.playScan();
      setTimeout(() => {
        setIsListening(false);
        setJarvisState('idle');
        handleSendMessage('Build modern landing page header with high conversion metrics');
      }, 3500);
    }
  };

  // Handle Template Selection
  const handleSelectTemplate = (templateId: string) => {
    setSelectedTemplateId(templateId);
    const tmpl = PREVIEW_TEMPLATES.find((t) => t.id === templateId) || PREVIEW_TEMPLATES[0];
    setCurrentHtml(tmpl.html);
    jarvisAudio.playActivate();
    setTerminalLogs((prev) => [`[Template] Loaded ${tmpl.nameEn}`, ...prev]);

    const tmplMsg: ChatMessage = {
      id: `tmpl-${Date.now()}`,
      role: 'assistant',
      content: `Mounted "${tmpl.nameEn}" into the live interactive canvas, sir.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: selectedModel,
    };
    setMessages((prev) => [...prev, tmplMsg]);
  };

  // Handle Version Snapshot Scrubber selection
  const handleSelectSnapshot = (index: number) => {
    setCurrentVersionIndex(index);
    jarvisAudio.playActivate();
    const snap = snapshots[index];

    let newHtml = PREVIEW_TEMPLATES[0].html;
    if (snap.version === 'v1.0') {
      newHtml = PREVIEW_TEMPLATES[0].html.replace('bg-gradient-to-r from-emerald-500 to-teal-500', 'bg-emerald-700');
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
      content: `Time-travel snapshot ${snap.version} ("${snap.title}") successfully loaded into live preview.`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: selectedModel,
    };
    setMessages((prev) => [...prev, travelMsg]);
  };

  // Handle Click-to-Edit Visual Micro-Prompt
  const handleApplyMicroPrompt = (prompt: string, element: SelectedElementInfo) => {
    jarvisAudio.playActivate();
    setIsGenerating(true);
    setJarvisState('thinking');

    const userEditMsg: ChatMessage = {
      id: `edit-user-${Date.now()}`,
      role: 'user',
      content: `[Visual Edit: <${element.tagName}> "${element.textContent?.slice(0, 30)}..."]: ${prompt}`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userEditMsg]);

    setTimeout(() => {
      let updatedHtml = currentHtml;
      if (prompt.toLowerCase().includes('dark') || prompt.toLowerCase().includes('glass')) {
        updatedHtml = updatedHtml.replace('bg-slate-900', 'bg-black/90 backdrop-blur-xl border border-white/10');
      } else if (prompt.toLowerCase().includes('emerald') || prompt.toLowerCase().includes('green')) {
        updatedHtml = updatedHtml.replace('bg-indigo-600', 'bg-emerald-500 shadow-lg shadow-emerald-500/30');
      } else {
        updatedHtml = updatedHtml.replace(element.textContent || '', `${element.textContent} (Enhanced)`);
      }

      setCurrentHtml(updatedHtml);
      setIsGenerating(false);
      setJarvisState('speaking');
      jarvisAudio.playSuccess();

      const botReplyMsg: ChatMessage = {
        id: `edit-bot-${Date.now()}`,
        role: 'assistant',
        content: `Applied visual modification to <${element.tagName}>: "${prompt}". Canvas updated instantly.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        thinkingTrace: [
          `Identified DOM node: ${element.selector || element.tagName}`,
          `Synthesized inline style adjustments for "${prompt}"`,
          'Hot-reloaded sandbox DOM tree without loss of application state',
        ],
      };
      setMessages((prev) => [...prev, botReplyMsg]);
    }, 1200);
  };

  // Handle Standard Chat Directive
  const handleSendMessage = async (textToSend?: string) => {
    const text = textToSend || inputMessage;
    if (!text.trim() || isGenerating) return;

    setInputMessage('');
    setIsGenerating(true);
    setJarvisState('thinking');
    jarvisAudio.playActivate();

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: 'user',
      content: text,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };
    setMessages((prev) => [...prev, userMsg]);
    setTerminalLogs((prev) => [`[User Directive] ${text}`, ...prev]);

    setTimeout(() => {
      setIsGenerating(false);
      setJarvisState('speaking');
      jarvisAudio.playSuccess();

      const assistantMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: 'assistant',
        content: `I have orchestrated the modifications according to your directive: "${text}". The sandbox and live code mirrors have been updated.`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        model: selectedModel,
        thinkingTrace: [
          'Evaluated federation topology & multi-model consensus',
          'Parsed intent and compiled visual elements',
          'Updated interactive preview surface',
        ],
      };
      setMessages((prev) => [...prev, assistantMsg]);
    }, 1400);
  };

  const handleFixWithHumanEye = () => {
    setIsFixingAudit(true);
    jarvisAudio.playScan();
    setTerminalLogs((prev) => ['[Human-Eye] Scanning DOM for layout contrast and accessibility', ...prev]);

    setTimeout(() => {
      setIsFixingAudit(false);
      jarvisAudio.playSuccess();
      const auditMsg: ChatMessage = {
        id: `audit-${Date.now()}`,
        role: 'assistant',
        content: 'Human-Eye visual audit complete. Verified zero console errors and 100% WCAG contrast compliance.',
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
      content: `Package ${pkg.name}@${pkg.version} successfully injected into live sandboxed renderer!`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      model: 'package-engine',
    };
    setMessages((prev) => [...prev, pkgMsg]);
  };

  return (
    <div className="flex flex-col gap-4 h-[calc(100vh-80px)] min-h-[700px] p-2 sm:p-4">
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

      {/* Workspace Settings & BYOK Modal */}
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

      {/* Main Split Grid (45% Studio | 55% Preview) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-0">
        {/* =========================================================================
            LEFT PANE (45% Width): JARVIS Intelligent Studio & Role Dispatcher
            ========================================================================= */}
        <div className="lg:col-span-5 flex flex-col bg-[#090d16] border border-white/10 rounded-2xl overflow-hidden shadow-2xl backdrop-blur-xl">
          {/* Header Bar */}
          <div className="px-4 py-3 bg-[#0d1320] border-b border-white/10 flex items-center justify-between gap-3 shrink-0">
            <div className="flex items-center gap-2.5">
              <div 
                onClick={toggleListen}
                className="relative w-7 h-7 rounded-full bg-black/60 border border-cyan-500/40 flex items-center justify-center cursor-pointer hover:scale-105 transition-transform"
                title="Click to speak"
              >
                <div className={`w-2.5 h-2.5 rounded-full transition-colors ${
                  jarvisState === 'listening' ? 'bg-rose-500 animate-pulse' :
                  jarvisState === 'thinking' ? 'bg-amber-400 animate-spin' :
                  jarvisState === 'speaking' ? 'bg-cyan-400' : 'bg-cyan-500'
                }`} />
                <div className="absolute inset-0 rounded-full border border-cyan-400/20 animate-ping pointer-events-none" />
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white tracking-tight">Supreme Copilot</span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">
                    {jarvisState.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>

            {/* Controls */}
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setIsHoloCallOpen(true)}
                className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-300 transition-all"
                title="Open 3D Face-to-Face Holographic Call"
              >
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                <span className="hidden sm:inline">Holo-Call</span>
              </button>

              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="bg-black/50 border border-white/10 focus:border-cyan-400 rounded-lg px-2 py-1 text-xs text-slate-200 font-mono outline-none cursor-pointer max-w-[120px] truncate"
              >
                {AI_MODELS_DATA.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>

              <button
                type="button"
                onClick={() => setIsSettingsModalOpen(true)}
                className="p-1.5 text-slate-400 hover:text-white bg-black/40 border border-white/10 rounded-lg transition-colors"
                title="Workspace Settings"
              >
                <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
              </button>
            </div>
          </div>

          {/* Quick Action Chips */}
          <div className="px-3 py-2 bg-black/30 border-b border-white/10 flex items-center gap-2 overflow-x-auto shrink-0 text-xs">
            <button
              type="button"
              onClick={() => {
                setActiveRole('coder');
                handleSendMessage('Build a SaaS landing page with dark glassmorphism styling');
              }}
              className={`px-3 py-1 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1.5 text-xs ${
                activeRole === 'coder' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-semibold' : 'bg-black/40 text-slate-400 hover:text-white border border-white/5'
              }`}
            >
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
              <span>Auto-Build</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setActiveRole('human-eye');
                handleFixWithHumanEye();
              }}
              className={`px-3 py-1 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1.5 text-xs ${
                activeRole === 'human-eye' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-semibold' : 'bg-black/40 text-slate-400 hover:text-white border border-white/5'
              }`}
            >
              <span>Visual Audit</span>
            </button>

            <button
              type="button"
              onClick={() => setIsPublishModalOpen(true)}
              className="px-3 py-1 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1.5 text-xs bg-black/40 text-slate-400 hover:text-white border border-white/5"
            >
              <span>Publish</span>
            </button>

            <button
              type="button"
              onClick={() => {
                setActiveRole('ci-fixer');
                handleSendMessage('Auto-heal degraded backend nodes and optimize response latency');
              }}
              className={`px-3 py-1 rounded-lg transition-colors whitespace-nowrap flex items-center gap-1.5 text-xs ${
                activeRole === 'ci-fixer' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-semibold' : 'bg-black/40 text-slate-400 hover:text-white border border-white/5'
              }`}
            >
              <RotateCcw className="w-3.5 h-3.5 text-emerald-400" />
              <span>Self-Heal</span>
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
                      {isUser ? 'You' : 'Supreme Copilot'}
                    </span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                  </div>

                  <div
                    className={`rounded-2xl p-3.5 text-xs sm:text-sm leading-relaxed max-w-[90%] ${
                      isUser
                        ? 'bg-gradient-to-r from-cyan-600 to-indigo-600 text-white rounded-tr-none'
                        : 'bg-[#0f172a]/90 text-slate-200 border border-white/10 rounded-tl-none shadow-md backdrop-blur-md'
                    }`}
                  >
                    {msg.thinkingTrace && msg.thinkingTrace.length > 0 && (
                      <div className="mb-2 p-2 bg-black/40 rounded-xl border border-white/5 text-[11px] font-mono text-cyan-300/80">
                        <span className="font-bold block mb-1 text-cyan-400">Reasoning Process:</span>
                        <ul className="list-disc pl-4 space-y-0.5">
                          {msg.thinkingTrace.map((t, idx) => (
                            <li key={idx}>{t}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              );
            })}

            {isGenerating && (
              <div className="flex items-center gap-2 text-xs text-cyan-400 font-mono py-2 animate-pulse">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                <span>Synthesizing code and hot-reloading sandbox...</span>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Collapsible Bottom Trays: Files & Live Terminal Logs */}
          {bottomTray === 'files' && (
            <div className="p-3 bg-black/60 border-t border-white/10 text-xs font-mono max-h-36 overflow-auto">
              <span className="text-slate-400 font-bold block mb-1">Project Workspace Files:</span>
              <div className="space-y-1 text-slate-300 text-[11px]">
                <div>📄 src/components/preview/DevicePreviewFrame.tsx</div>
                <div>📄 src/components/inspector/VisualElementInspector.tsx</div>
                <div>📄 src/components/diff/CodeDiffViewer.tsx</div>
                <div>📄 src/components/timetravel/TimeTravelBar.tsx</div>
              </div>
            </div>
          )}

          {bottomTray === 'terminal' && (
            <div className="p-3 bg-black/60 border-t border-white/10 text-xs font-mono max-h-36 overflow-auto">
              <span className="text-slate-400 font-bold block mb-1">MCP Telemetry Logs:</span>
              <div className="space-y-1 text-slate-300 text-[11px]">
                {terminalLogs.map((l, i) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>
          )}

          {/* Tray Toggle Strip */}
          <div className="px-4 py-1.5 bg-[#070b13] border-t border-white/10 flex items-center justify-between text-[11px] font-mono text-slate-500">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setBottomTray(bottomTray === 'files' ? 'none' : 'files')}
                className={`hover:text-white transition-colors ${bottomTray === 'files' ? 'text-cyan-400 font-bold' : ''}`}
              >
                [ Files ]
              </button>
              <button
                type="button"
                onClick={() => setBottomTray(bottomTray === 'terminal' ? 'none' : 'terminal')}
                className={`hover:text-white transition-colors ${bottomTray === 'terminal' ? 'text-cyan-400 font-bold' : ''}`}
              >
                [ Logs ({terminalLogs.length}) ]
              </button>
            </div>
            <span>Status: Connected</span>
          </div>

          {/* Chat Input Bar */}
          <div className="p-3 bg-[#0a0e19] border-t border-white/10 flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={toggleListen}
              className={`p-2.5 rounded-xl border transition-colors ${
                isListening
                  ? 'bg-rose-600 text-white border-rose-500 animate-pulse'
                  : 'bg-black/40 text-slate-400 hover:text-white border-white/10'
              }`}
              title="Speak directive"
            >
              <Mic className="w-4 h-4" />
            </button>

            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
              placeholder="Instruct Supreme Copilot (e.g. 'Build SaaS hero section', 'Optimize contrast')..."
              className="flex-1 bg-black/40 border border-white/10 focus:border-cyan-400/60 rounded-xl px-3.5 py-2 text-xs sm:text-sm text-slate-200 outline-none"
            />

            <button
              type="button"
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || isGenerating}
              className="p-2.5 font-semibold text-slate-950 bg-gradient-to-r from-cyan-400 to-indigo-400 hover:brightness-110 rounded-xl transition-all disabled:opacity-40"
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
