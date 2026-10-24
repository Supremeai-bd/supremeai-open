/* eslint-disable @typescript-eslint/no-explicit-any */
import { useEffect, useState, useMemo, useRef } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  Background,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import './admin-hud.css';
import {
  Cpu,
  Send,
  Mic,
  Settings,
  Activity,
  Shield,
  LifeBuoy,
  FileText,
  Sun,
  Moon,
  Flame,
  Binary,
  MessageSquare,
  Globe,
  TerminalSquare,
  X,
  Eye,
  EyeOff
} from 'lucide-react';
import SciFiFlowNode from './SciFiFlowNode';
import { AdminBrowserPanel as CrownJewelBrowser } from './AdminBrowserPanel';
import { useAdminStore } from '../../store/adminStore';
import { useTheme } from '../../contexts/useTheme';
import { AudioRecorderService } from '../../services/audio/AudioRecorderService';
import { AudioPlaybackService } from '../../services/audio/AudioPlaybackService';
import { WaveformVisualizer } from '../audio/WaveformVisualizer';
import { ServiceHealthMetrics } from './infra/ServiceHealthMetrics';
import { getAethelResponse } from '../../services/chatService';
import type { ChatMessage as ApiChatMessage } from '../../services/chatService';
import { getWebSocketBaseUrl } from '../../utils/api';

// বাংলা মন্তব্য: চ্যাট এবং ভয়েস ওভাররাইডের জন্য ডামি কথোপকথন ডাটা ডিক্লেয়ার করা হচ্ছে
const initialChat = [
  { id: 1, sender: 'Admin', text: 'Execute deployment check on Node 47.' },
  { id: 2, sender: 'SupremeAI', text: 'Analyzing Node 47 (Analytics). Status: Nominal. Load: 38%. Connected.' },
  { id: 3, sender: 'System', text: 'Optimizing cluster nodes...' },
];

export function CommandCenter() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges] = useEdgesState<Edge>([]);
  const [chatMessages, setChatMessages] = useState(initialChat);
  const [chatInput, setChatInput] = useState('');
  const [isCentralPanelOpen, setIsCentralPanelOpen] = useState(false);

  // বাংলা মন্তব্য: ৩টি প্যানেলের (চ্যাট, ব্রাউজার, টার্মিনাল) ভিজিবিলিটি স্টেট
  const [showChat, setShowChat] = useState(true);
  const [showBrowser, setShowBrowser] = useState(true);
  const [showTerminal, setShowTerminal] = useState(true);
  const [terminalHistory, setTerminalHistory] = useState<string[]>(['$ SupremeAI Terminal v3.0 — Ready.', '$ Type a command and press Enter...']);
  const [terminalInput, setTerminalInput] = useState('');
  const [browserUrl, setBrowserUrl] = useState(import.meta.env.VITE_ADMIN_FRONTEND_URL || '');
  const setAdminSubTab = useAdminStore(state => state.setAdminSubTab);
  const { theme, toggleTheme } = useTheme();

  // Audio Engine State
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const recorderRef = useRef<AudioRecorderService | null>(null);
  const [playbackService, setPlaybackService] = useState<AudioPlaybackService | null>(null);

  useEffect(() => {
    // Initialize Audio Services
    const service = new AudioPlaybackService();
    setPlaybackService(service);

    // FIX (API-contract audit): backend serves the voice WS at /ws/voice
    // (websocket_voice.py, prefix /ws). The old /api/voice/ws/voice path never
    // existed — the connection silently failed.
    const wsUrl = `${getWebSocketBaseUrl()}/ws/voice`;
    recorderRef.current = new AudioRecorderService(wsUrl);

    recorderRef.current.onTranscript((text) => {
      setChatMessages(prev => [
        ...prev,
        { id: Date.now(), sender: 'Admin', text: text }
      ]);
    });

    const handleAethelSpeak = (e: any) => {
      const text = e.detail;
      setIsSpeaking(true);
      setChatMessages(prev => [
        ...prev,
        { id: Date.now(), sender: 'SupremeAI', text: text }
      ]);
      service.play(text);

      // Rough estimation to stop visualizer (in a real app, bind to onend)
      setTimeout(() => setIsSpeaking(false), text.length * 50 + 1000);
    };

    window.addEventListener('supremeai_speak', handleAethelSpeak);
    return () => {
      window.removeEventListener('supremeai_speak', handleAethelSpeak);
    };

  }, []);

  const toggleVoiceRecording = async () => {
    if (!recorderRef.current) return;

    if (isRecording) {
      recorderRef.current.stopRecording();
      setIsRecording(false);
    } else {
      await recorderRef.current.startRecording();
      setIsRecording(true);
    }
  };

  // Custom node types for ReactFlow
  const nodeTypes = useMemo(() => ({ aethel: SciFiFlowNode }), []);

  // বাংলা মন্তব্য: টার্মিনাল কমান্ড সাবমিট হ্যান্ডলার
  const handleTerminalSubmit = () => {
    if (!terminalInput.trim()) return;
    const cmd = terminalInput.trim();
    setTerminalHistory(prev => [...prev, `$ ${cmd}`, `[SupremeAI] Executing: "${cmd}"...`, `[SupremeAI] Command completed.`]);
    setTerminalInput('');
  };

  const handleSendChat = async () => {
    if (!chatInput.trim()) return;
    const msgText = chatInput.trim();

    const requestId = Date.now();
    const placeholderId = requestId + 1;
    const nextMessages = [
      ...chatMessages,
      { id: requestId, sender: 'Admin', text: msgText },
      { id: placeholderId, sender: 'SupremeAI', text: 'Thinking... Please wait.' }
    ];

    setChatMessages(nextMessages);
    setChatInput('');

    const history: ApiChatMessage[] = nextMessages
      .filter(message => message.sender !== 'SupremeAI' || message.id !== placeholderId)
      .map(message => ({
        role: message.sender === 'Admin' ? 'user' : 'assistant',
        content: message.text,
      }));

    if (recorderRef.current && typeof recorderRef.current.isConnected === 'function' && recorderRef.current.isConnected()) {
      recorderRef.current.sendText(msgText);
    }

    try {
      const responseText = await getAethelResponse(msgText, history);
      setChatMessages(prev => prev.map(msg => msg.id === placeholderId ? { ...msg, text: responseText } : msg));
    } catch (error: any) {
      setChatMessages(prev => prev.map(msg => msg.id === placeholderId ? {
        ...msg,
        text: `AI backend error: ${error?.message || 'Unable to reach the model.'}`,
      } : msg));
    }
  };

  const handleNodeClick = (_: React.MouseEvent, node: { id: string; data?: { type?: string } }) => {
    if (node.id === 'central-orb') {
      setIsCentralPanelOpen(prev => !prev);
    } else if (node.data?.type) {
      // বাংলা মন্তব্য: নোড ক্লিকে সরাসরি সংশ্লিষ্ট ট্যাবে নেভিগেট করা হচ্ছে
      const typeMap: Record<string, string> = {
        'model-router': 'model-router',
        'provider-map': 'model-router',
        'skills': 'skills',
        'memory': 'memory',
        'real-time-logs': 'logs',
        'observability': 'observability',
        'threats': 'threats',
        'rules': 'rules',
        'rate-limits': 'rate-limits',
        'cloud': 'cloud',
        'cicd': 'cicd',
        'github': 'github',
        'backups': 'backups',
        'sandbox': 'sandbox',
        'costs': 'costs',
        'users': 'users',
        'config': 'config'
      };
      if (typeMap[node.data.type]) {
        // সরাসরি ট্যাবে নেভিগেট — চ্যাট প্যানেল ওপেন করার দরকার নেই
        setAdminSubTab(typeMap[node.data.type]);
      }
    }
  };

  useEffect(() => {
    const initialNodes = [
      {
        id: 'central-orb',
        type: 'aethel',
        position: { x: 450, y: 250 },
        data: { label: 'SUPREMEAI CENTRAL ORC', isCentral: true },
      },
      // Cluster 1: AI & Brain (Top Left)
      { id: 'node-router', type: 'aethel', position: { x: 250, y: 100 }, data: { label: 'Model Router', type: 'model-router' } },
      { id: 'node-provider', type: 'aethel', position: { x: 150, y: 200 }, data: { label: 'Provider Map', type: 'provider-map' } },
      { id: 'node-skills', type: 'aethel', position: { x: 200, y: 300 }, data: { label: 'Skills', type: 'skills' } },
      { id: 'node-memory', type: 'aethel', position: { x: 300, y: 380 }, data: { label: 'Memory', type: 'memory' } },

      // Cluster 2: Security & Ops (Top Right)
      { id: 'node-logs', type: 'aethel', position: { x: 650, y: 100 }, data: { label: 'Real-time Logs', type: 'real-time-logs' } },
      { id: 'node-observability', type: 'aethel', position: { x: 750, y: 200 }, data: { label: 'Observability', type: 'observability' } },
      { id: 'node-threats', type: 'aethel', position: { x: 700, y: 300 }, data: { label: 'Threats', type: 'threats' } },
      { id: 'node-rules', type: 'aethel', position: { x: 600, y: 380 }, data: { label: 'Rules', type: 'rules' } },
      { id: 'node-rate-limits', type: 'aethel', position: { x: 800, y: 350 }, data: { label: 'Rate Limits', type: 'rate-limits' } },

      // Cluster 3: DevOps & Infra (Bottom Left)
      { id: 'node-cloud', type: 'aethel', position: { x: 150, y: 450 }, data: { label: 'Cloud Mesh', type: 'cloud' } },
      { id: 'node-cicd', type: 'aethel', position: { x: 250, y: 550 }, data: { label: 'CI/CD Pipelines', type: 'cicd' } },
      { id: 'node-github', type: 'aethel', position: { x: 100, y: 550 }, data: { label: 'GitHub Sync', type: 'github' } },
      { id: 'node-backups', type: 'aethel', position: { x: 350, y: 600 }, data: { label: 'Backups', type: 'backups' } },
      { id: 'node-sandbox', type: 'aethel', position: { x: 200, y: 650 }, data: { label: 'Orchestrator Sandbox', type: 'sandbox' } },

      // Cluster 4: Management & Finance (Bottom Right)
      { id: 'node-costs', type: 'aethel', position: { x: 750, y: 450 }, data: { label: 'Cost Auditor', type: 'costs' } },
      { id: 'node-users', type: 'aethel', position: { x: 650, y: 550 }, data: { label: 'User Manager', type: 'users' } },
      { id: 'node-config', type: 'aethel', position: { x: 750, y: 650 }, data: { label: 'Config Editor', type: 'config' } }
    ];

    const initialEdges = [
      // Cluster 1 Edges (AI/Brain) - Cyan
      { id: 'e-nexus-router', source: 'central-orb', target: 'node-router', animated: true, style: { stroke: '#00f3ff', strokeWidth: 1.5 } },
      { id: 'e-nexus-provider', source: 'central-orb', target: 'node-provider', animated: true, style: { stroke: '#00f3ff', strokeWidth: 1.5 } },
      { id: 'e-nexus-skills', source: 'central-orb', target: 'node-skills', animated: true, style: { stroke: '#00f3ff', strokeWidth: 1.5 } },
      { id: 'e-nexus-memory', source: 'central-orb', target: 'node-memory', animated: true, style: { stroke: '#00f3ff', strokeWidth: 1.5 } },

      // Cluster 2 Edges (Security) - Green/Red
      { id: 'e-nexus-logs', source: 'central-orb', target: 'node-logs', animated: true, style: { stroke: '#10b981', strokeWidth: 1.5 } },
      { id: 'e-nexus-obs', source: 'central-orb', target: 'node-observability', animated: true, style: { stroke: '#10b981', strokeWidth: 1.5 } },
      { id: 'e-nexus-threats', source: 'central-orb', target: 'node-threats', animated: true, style: { stroke: '#ef4444', strokeWidth: 2 } },
      { id: 'e-nexus-rules', source: 'central-orb', target: 'node-rules', animated: true, style: { stroke: '#10b981', strokeWidth: 1.5 } },
      { id: 'e-nexus-ratelimits', source: 'central-orb', target: 'node-rate-limits', animated: true, style: { stroke: '#10b981', strokeWidth: 1.5 } },

      // Cluster 3 Edges (DevOps) - Blue/Purple
      { id: 'e-nexus-cloud', source: 'central-orb', target: 'node-cloud', animated: true, style: { stroke: '#8b5cf6', strokeWidth: 2 } },
      { id: 'e-nexus-cicd', source: 'central-orb', target: 'node-cicd', animated: true, style: { stroke: '#8b5cf6', strokeWidth: 1.5 } },
      { id: 'e-nexus-github', source: 'central-orb', target: 'node-github', animated: true, style: { stroke: '#8b5cf6', strokeWidth: 1.5 } },
      { id: 'e-nexus-backups', source: 'central-orb', target: 'node-backups', animated: true, style: { stroke: '#3b82f6', strokeWidth: 1.5 } },
      { id: 'e-nexus-sandbox', source: 'central-orb', target: 'node-sandbox', animated: true, style: { stroke: '#3b82f6', strokeWidth: 2 } },

      // Cluster 4 Edges (Management) - Yellow
      { id: 'e-nexus-costs', source: 'central-orb', target: 'node-costs', animated: true, style: { stroke: '#f59e0b', strokeWidth: 1.5 } },
      { id: 'e-nexus-users', source: 'central-orb', target: 'node-users', animated: true, style: { stroke: '#f59e0b', strokeWidth: 1.5 } },
      { id: 'e-nexus-config', source: 'central-orb', target: 'node-config', animated: true, style: { stroke: '#f59e0b', strokeWidth: 1.5 } }
    ];

    setNodes(initialNodes);
    setEdges(initialEdges);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex-grow flex flex-col overflow-hidden bg-[var(--bg-main)] text-[var(--text-main)] scanline relative h-screen font-mono p-4 transition-colors duration-500">
      {/* ── TOP HUD HEADER BAR ────────────────────────────────────── */}
      <header className="flex justify-between items-center border-b border-[var(--border-accent)] pb-2 mb-4 transition-colors duration-500">
        <div className="flex items-center gap-2">
          <span className="text-[var(--accent-primary)] animate-pulse">▲</span>
          <span className="text-xs font-bold tracking-widest text-[var(--accent-primary)] uppercase">SUPREMEAI ORCHESTRATOR | ADM-01</span>
        </div>
        <div className="text-sm font-bold tracking-widest text-[var(--accent-primary)] uppercase flex items-center gap-4">
          SUPREMEAI CORE
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-full bg-[var(--bg-panel)] border border-[var(--border-accent)] hover:scale-110 transition-transform cursor-pointer"
            title="Cycle Theme"
          >
            {theme === 'dark' && <Sun size={14} className="text-yellow-400" />}
            {theme === 'light' && <Flame size={14} className="text-orange-500" />}
            {theme === 'sunset' && <Binary size={14} className="text-emerald-400" />}
            {theme === 'matrix' && <Moon size={14} className="text-indigo-400" />}
          </button>
        </div>
        <div className="flex items-center gap-4 text-[10px] text-[var(--accent-primary)] font-bold">
          <span
            onClick={useAdminStore(state => state.handleAdminLogout)}
            className="cursor-pointer hover:opacity-80 transition-opacity"
            title="Return to Login"
          >
            14:32 | OCT 26
          </span>
          <span className="text-[var(--accent-secondary)]">📶 SYSTEM ONLINE</span>
        </div>
      </header>

      {/* ── MAIN WORKSPACE CONTENT ────────────────────────────────── */}
      <div className="flex-1 flex flex-row gap-4 overflow-hidden mb-4">

        {/* Core React Flow Telemetry Canvas */}
        <div className="flex-1 bg-[var(--bg-panel)] border border-[var(--border-accent)] rounded-xl relative overflow-hidden flex flex-col transition-colors duration-500">
          <div className="flex-1 w-full h-full relative">
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              fitView
              zoomOnScroll={false}
              zoomOnDoubleClick={false}
              preventScrolling={true}
              panOnDrag={false}
              nodesDraggable={true}
              onNodeClick={handleNodeClick}
              className={theme === 'dark' ? 'dark' : 'light'}
            >
              <Background color="var(--accent-primary)" gap={24} style={{ opacity: theme === 'dark' ? 0.03 : 0.1 }} />
            </ReactFlow>
          </div>

          {/* Java Worker Metrics Widget Overlay — ক্লিক ইভেন্ট ReactFlow-এ যাবে না */}
          <div className="absolute top-4 left-4 w-80 z-20" onPointerDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
            <ServiceHealthMetrics />
          </div>

          {/* Floating Telemetry Waveform Panel at Bottom of Canvas */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 w-[380px] bg-[var(--waveform-bg)] border border-[var(--border-accent)] rounded-lg p-3 shadow-lg backdrop-blur-md z-20 flex flex-col items-center transition-colors duration-500">
            <div className="flex justify-between w-full text-[9px] text-[var(--text-secondary)] font-bold mb-1">
              <span>CMD | v3.0</span>
              <button
                onClick={toggleVoiceRecording}
                className="flex items-center gap-1.5 hover:opacity-80 p-1 rounded transition-colors"
              >
                <Mic size={10} className={isRecording ? 'text-[var(--danger)] animate-pulse' : 'text-[var(--accent-primary)]'} />
                <span className={isRecording ? 'text-[var(--danger)]' : 'text-[var(--text-secondary)]'}>
                  {isRecording ? 'RECORDING...' : 'VOICE CONTROLS'}
                </span>
              </button>
            </div>

            {/* Glowing Waveform representation */}
            <div className="flex items-center justify-center h-8 my-1 w-full">
              <WaveformVisualizer
                analyser={playbackService ? playbackService.getAnalyser() : null}
                isActive={isRecording || isSpeaking}
                color={isRecording ? '#ef4444' : '#00f3ff'}
              />
            </div>

            <div className="flex justify-between w-full text-[8px] text-[var(--text-secondary)] font-bold mt-1">
              <span className={isRecording ? "text-[var(--danger)]" : "text-[var(--accent-secondary)]"}>
                {isRecording ? "Voice Recognition: Listening..." : "Voice Recognition: Standby"}
              </span>
              <span>CPU: 74% MEM: 68%</span>
            </div>
          </div>
        </div>

        {/* ═══ CENTRAL ORC WORKSPACE — চ্যাট, ব্রাউজার, টার্মিনাল ═══ */}
        {isCentralPanelOpen && (
          <div className="absolute inset-0 z-50 flex flex-col bg-[var(--bg-main)]/95 backdrop-blur-xl" onPointerDown={e => e.stopPropagation()} onClick={e => e.stopPropagation()}>
            {/* Header Bar */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-[var(--border-accent)] bg-[var(--bg-cell)] transition-colors duration-500">
              <div className="flex items-center gap-2">
                <Cpu size={14} className="text-[var(--accent-primary)] animate-pulse" />
                <span className="text-xs font-black tracking-widest text-[var(--accent-primary)] uppercase">SUPREMEAI CENTRAL ORC</span>
              </div>

              {/* Panel Toggle Buttons */}
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setShowChat(current => !current)} className={`flex items-center gap-1 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider transition-all ${showChat ? 'bg-[var(--accent-primary)]/20 text-[var(--accent-primary)] border border-[var(--accent-primary)]/30' : 'text-[var(--text-secondary)] border border-transparent hover:border-[var(--border-accent)]'}`} title="Toggle Chat">
                  <MessageSquare size={10} />
                  {showChat ? <Eye size={9} /> : <EyeOff size={9} />}
                  Chat
                </button>
                <button type="button" onClick={() => setShowBrowser(current => !current)} className={`flex items-center gap-1 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider transition-all ${showBrowser ? 'bg-[var(--accent-primary)]/20 text-[var(--accent-primary)] border border-[var(--accent-primary)]/30' : 'text-[var(--text-secondary)] border border-transparent hover:border-[var(--border-accent)]'}`} title="Toggle Browser">
                  <Globe size={10} />
                  {showBrowser ? <Eye size={9} /> : <EyeOff size={9} />}
                  Browser
                </button>
                <button type="button" onClick={() => setShowTerminal(current => !current)} className={`flex items-center gap-1 px-2 py-1 rounded text-[9px] font-bold uppercase tracking-wider transition-all ${showTerminal ? 'bg-[var(--accent-primary)]/20 text-[var(--accent-primary)] border border-[var(--accent-primary)]/30' : 'text-[var(--text-secondary)] border border-transparent hover:border-[var(--border-accent)]'}`} title="Toggle Terminal">
                  <TerminalSquare size={10} />
                  {showTerminal ? <Eye size={9} /> : <EyeOff size={9} />}
                  Terminal
                </button>
              </div>

              <button onClick={() => setIsCentralPanelOpen(false)} className="p-1.5 hover:opacity-80 rounded-lg transition-colors" title="Close Workspace">
                <X size={16} className="text-[var(--text-secondary)] hover:text-red-500" />
              </button>
            </div>

            {/* Panels Container */}
            <div className="flex-1 flex gap-2 p-2 overflow-hidden">

              {/* CHAT PANEL */}
              {showChat && (
                <div className="flex-1 flex flex-col bg-[var(--bg-panel)] border border-[var(--border-accent)] rounded-xl overflow-hidden transition-all duration-300">
                  <div className="px-3 py-2 border-b border-[var(--border-accent)] bg-[var(--bg-cell)] flex items-center gap-2">
                    <MessageSquare size={12} className="text-[var(--accent-primary)]" />
                    <span className="text-[10px] font-bold text-[var(--accent-primary)] uppercase tracking-wider">AI Chat</span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3 space-y-3">
                    {chatMessages.map(msg => (
                      <div key={msg.id} className="text-[11px] leading-relaxed border-b border-[var(--border-accent)] pb-2">
                        <span className={`font-bold tracking-wider mr-1.5 ${msg.sender === 'Admin' ? 'text-[var(--text-secondary)]' : msg.sender === 'SupremeAI' ? 'text-[var(--accent-primary)]' : 'text-[var(--accent-secondary)]'}`}>
                          {msg.sender}:
                        </span>
                        <span className="text-[var(--text-secondary)]">{msg.text}</span>
                      </div>
                    ))}
                  </div>
                  <div className="p-2 border-t border-[var(--border-accent)] bg-[var(--bg-cell)] flex gap-2">
                    <input
                      type="text"
                      value={chatInput}
                      onChange={e => setChatInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleSendChat()}
                      placeholder="Ask SupremeAI..."
                      className="flex-grow bg-[var(--chat-input-bg)] border border-[var(--border-accent)] focus:border-[var(--accent-primary)] rounded-lg px-3 py-1.5 text-[11px] text-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] font-mono transition-colors"
                    />
                    <button onClick={handleSendChat} className="text-[var(--accent-primary)] p-1.5 rounded-lg hover:opacity-80 transition-all">
                      <Send size={14} />
                    </button>
                  </div>
                </div>
              )}

              {/* BROWSER PREVIEW PANEL */}
              {showBrowser && (
                <div className="flex-1 flex flex-col bg-[var(--bg-panel)] border border-[var(--border-accent)] rounded-xl overflow-hidden transition-all duration-300">
                  <CrownJewelBrowser 
                    initialUrl={browserUrl} 
                    onUrlChange={setBrowserUrl}
                    showAIAssistant={true}
                    showDevTools={true}
                  />
                </div>
              )}

              {/* TERMINAL PANEL */}
              {showTerminal && (
                <div className="flex-1 flex flex-col bg-[#0a0a0a] border border-[var(--border-accent)] rounded-xl overflow-hidden transition-all duration-300">
                  <div className="px-3 py-2 border-b border-[var(--border-accent)] bg-[#111] flex items-center gap-2">
                    <TerminalSquare size={12} className="text-green-400" />
                    <span className="text-[10px] font-bold text-green-400 uppercase tracking-wider">Terminal</span>
                    <div className="flex gap-1 ml-auto">
                      <span className="w-2 h-2 rounded-full bg-red-500"></span>
                      <span className="w-2 h-2 rounded-full bg-yellow-500"></span>
                      <span className="w-2 h-2 rounded-full bg-green-500"></span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3 font-mono text-[11px] text-green-400 space-y-0.5">
                    {terminalHistory.map((line, i) => (
                      <div key={i} className={line.startsWith('$') ? 'text-green-300' : 'text-green-500/70'}>{line}</div>
                    ))}
                  </div>
                  <div className="p-2 border-t border-green-900/30 bg-[#0d0d0d] flex items-center gap-2">
                    <span className="text-green-400 text-[11px] font-mono">$</span>
                    <input
                      type="text"
                      value={terminalInput}
                      onChange={e => setTerminalInput(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleTerminalSubmit()}
                      placeholder="Enter command..."
                      className="flex-grow bg-transparent border-none text-[11px] text-green-400 outline-none placeholder:text-green-800 font-mono"
                    />
                  </div>
                </div>
              )}

              {/* কোনো প্যানেল নেই — সব হাইড করা অবস্থায় */}
              {!showChat && !showBrowser && !showTerminal && (
                <div className="flex-1 flex items-center justify-center text-[var(--text-secondary)] text-sm font-mono">
                  All panels hidden. Use the toggle buttons above to show them.
                </div>
              )}

            </div>
          </div>
        )}

      </div>

      {/* ── BOTTOM DECK CONTROLLER / ICON PANELS ──────────────────── */}
      <footer className="flex justify-between items-center border-t border-[var(--border-accent)] pt-2 text-[10px] text-[var(--text-secondary)] font-bold transition-colors duration-500">
        {/* Left Deck Actions */}
        <div className="flex gap-4">
          <button onClick={() => setAdminSubTab('config')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <Settings size={12} className="text-[var(--accent-primary)]" />
            <span>Settings</span>
          </button>
          <button onClick={() => setAdminSubTab('observability')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <Activity size={12} className="text-[var(--accent-secondary)]" />
            <span>Metrics</span>
          </button>
          <button onClick={() => setAdminSubTab('logs')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <FileText size={12} className="text-[var(--warning)]" />
            <span>Logs</span>
          </button>
        </div>

        {/* Right Deck Status Indicator */}
        <div className="flex gap-4">
          <button onClick={() => setAdminSubTab('costs')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <FileText size={12} className="text-[var(--accent-primary)]" />
            <span>Costs</span>
          </button>
          <button onClick={() => setAdminSubTab('threats')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <Shield size={12} className="text-[var(--accent-secondary)]" />
            <span>Security</span>
          </button>
          <button onClick={() => setAdminSubTab('health')} className="flex items-center gap-1.5 hover:text-[var(--text-main)] transition-colors">
            <LifeBuoy size={12} className="text-[var(--warning)]" />
            <span>Health</span>
          </button>
        </div>
      </footer>
    </div>
  );
}

