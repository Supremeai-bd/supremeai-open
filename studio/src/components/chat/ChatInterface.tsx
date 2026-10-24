// apps/studio-client/src/components/chat/ChatInterface.tsx
// Primary Agent Chat Interface
// বাংলা মন্তব্য: মূল এজেন্ট চ্যাট ইন্টারফেস, যা useStore থেকে চ্যাট হিস্ট্রি ব্যবহার করে।

import React, { useState, useRef, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { UnifiedChatBubble } from './UnifiedChatBubble';
import { controlPlane } from '../../services/controlPlane';
import { useEventBus } from '../../hooks/useEventBus';
import { eventBus, Events } from '../../lib/componentEventBus';
import { getApiBaseUrl } from '../../utils/api';
import { getAdminToken, getUserToken } from '../../services/tokenStorage';
import { AudioPlaybackService } from '../../services/audio/AudioPlaybackService';
import { BrainCircuit, Download, FileCode2, Volume2, VolumeX, Share2 } from 'lucide-react';

import { ShareDialog } from '../share/ShareDialog';
import { ImageUploadButton } from './ImageUploadButton';
import ExportMenu from '../export/ExportMenu';
import BranchButton from '../branch/BranchButton';
import { SlashCommandMenu } from '../commands/SlashCommandMenu';
import { ChatSearchDialog } from '../search/ChatSearchDialog';
import { ThinkingPanel } from '../reasoning/ThinkingPanel';
import { ArtifactsPanel } from '../artifacts/ArtifactsPanel';
// Issue #1525 (MEDIUM): while the orchestration round-trip is in flight the
// thread used to go visually dead — the user message just sat there with no
// acknowledgement. The branded typing indicator now renders for the whole
// await window (it already existed as a component but was never mounted here).
import { TypingIndicator } from './TypingIndicator';
import type { CapabilityExecutionResult } from '../../services/controlPlane';
import {
  useTierSStore,
  type Artifact as WorkspaceArtifact,
  type ReasoningStep,
} from '../../store/workspaceUiStateStore';

// M10 (issue #453) বাংলা: backend orchestration response-এ চুক্তি-অনুযায়ী ফিল্ড
// এলে সেগুলোই S2/S3 স্টোরে যাবে — টাইপ-গার্ড ছাড়া কিছুই গ্রহণ করা হবে না।
// ফিল্ড অনুপস্থিত থাকলে কিছুই বানানো হয় না (false-assurance doctrine)।
function isReasoningStep(value: unknown): value is ReasoningStep {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ReasoningStep).content === 'string'
  );
}

function isWorkspaceArtifact(value: unknown): value is WorkspaceArtifact {
  const candidate = value as WorkspaceArtifact;
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof candidate.id === 'string' &&
    typeof candidate.title === 'string' &&
    typeof candidate.content === 'string' &&
    typeof candidate.version === 'number' &&
    ['html', 'react', 'svg', 'mermaid', 'code'].includes(candidate.artifact_type)
  );
}

export const ChatInterface: React.FC = () => {
  const { chatHistory, addMessage, isOrchestrating, triggerOrchestration } = useStore();
  const {
    shareDialogOpen, shareConversationId, closeShareDialog, openShareDialog,
    slashMenuOpen, closeSlashMenu, slashFilter, slashPosition, openSlashMenu,
    searchDialogOpen, closeSearchDialog, openSearchDialog,
    // S2: Reasoning
    reasoningSteps, isThinking, showReasoning, toggleReasoning, setReasoningSteps,
    // S3: Artifacts
    artifacts, activeArtifactId, artifactsPanelOpen,
    addArtifact, selectArtifact, toggleArtifactsPanel, setArtifactsPanelOpen,
  } = useTierSStore();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [voiceEnabled, setVoiceEnabled] = useState(false);
  // Issue #1457/#1486 (HIGH): chat failure affordances — offline banner,
  // retry button for the last failed message, auto-retry on reconnect.
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [failedPrompt, setFailedPrompt] = useState<string | null>(null);
  // Ref mirror so event listeners can read/act on the latest failed prompt
  // without stale closures (and without side effects inside state updaters).
  const failedPromptRef = useRef<string | null>(null);
  const setFailed = (prompt: string | null) => {
    failedPromptRef.current = prompt;
    setFailedPrompt(prompt);
  };
  // M14 P-C: zero-cost ব্রাউজার-TTS playback (capability-detection সহ)।
  const playbackRef = useRef<AudioPlaybackService | null>(null);
  useEffect(() => {
    playbackRef.current = new AudioPlaybackService();
  }, []);
  // M10 (issue #453) বাংলা: "current_conv" নকল প্লেসহোল্ডারের বদলে সত্যিকার
  // conversation identity। ক্লায়েন্ট UUID তৈরি করে প্রতিটি orchestration
  // payload-এ conversation_id হিসেবে পাঠায় — backend ConversationCommand
  // ক্লায়েন্ট-সরবরাহকৃত conversation_id গ্রহণ করে (gateway_center.py:79)।
  // কথোপকথন শুরুর আগে share/export/branch সৎভাবে disabled থাকে — কোনো ভুয়া
  // id কখনো পাঠানো হয় না।
  const [conversationId, setConversationId] = useState<string | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  useEventBus(Events.SYSTEM_ALERT, (payload: unknown) => {
    const alertData = payload as { message?: string } | undefined;
    addMessage({
      role: 'system',
      content: `[SYSTEM ALERT] ${alertData?.message || JSON.stringify(payload)}`
    });
  });

  // Listen for browser context sharing
  useEventBus(Events.CHAT_MESSAGE_SENT, (data: unknown) => {
    const chatData = data as { source?: string; content?: string } | undefined;
    if (chatData?.source === 'browser_context' && chatData.content) {
      setInput(chatData.content);  // Pre-fill with browser URL/context
    }
  });

  // Issue #452 fix: the voice toggle previously emitted TTS_GENERATED into
  // the void — no component anywhere subscribed to 'tts:generated', so
  // "voice responses" did nothing for user chat.  Deliver it for real:
  // M14 P-C zero-cost first-path: browser speechSynthesis (কী-বিহীন, backend
  // ব্যয় শূন্য) উপলব্ধ হলে সেটাই প্রথম-পছন্দ; অনুপস্থিত হলে backend-এর
  // streaming TTS endpoint (ElevenLabs → edge-tts chain, honest failure)।
  // কোনোটাই সম্ভব না হলে স্পষ্ট অসমর্থন-বার্তা — ভাঙা-বোতাম নয়।
  useEventBus(
    Events.TTS_GENERATED,
    async (payload: unknown) => {
      const data = payload as { text?: string } | undefined;
      const text = (data?.text || '').trim();
      if (!text) return;

      // ১) শূন্য-ব্যয় ব্রাউজার TTS (capability-detection প্রমাণসহ)
      if (playbackRef.current?.ttsSupported && playbackRef.current.play(text)) {
        return;
      }

      // ২) fallback: backend TTS (auth header সহ fetch + blob playback)
      try {
        // Issue #521: tokenStorage (sessionStorage-first, legacy localStorage swept).
        const token =
          getUserToken() ||
          getAdminToken();
        const res = await fetch(
          `${getApiBaseUrl()}/api/voice/stream_audio?text=${encodeURIComponent(text.slice(0, 1000))}`,
          { headers: token ? { Authorization: `Bearer ${token}` } : undefined }
        );
        if (!res.ok) {
          addMessage({
            role: 'system',
            content: `[VOICE] Voice response unavailable (HTTP ${res.status}) — the TTS provider may not be configured.`,
          });
          return;
        }
        const blob = await res.blob();
        if (!blob.size) {
          addMessage({
            role: 'system',
            content: '[VOICE] Voice synthesis returned no audio — TTS provider unavailable.',
          });
          return;
        }
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        audio.onerror = () => URL.revokeObjectURL(url);
        await audio.play();
      } catch (err) {
        console.error('[voice] TTS playback failed:', err);
        addMessage({
          role: 'system',
          content: '[VOICE] Voice playback failed — see console for details.',
        });
      }
    },
    []
  );

  // S6: Keyboard Shortcut - Cmd+K for Chat Search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        if (searchDialogOpen) closeSearchDialog(); else openSearchDialog();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [searchDialogOpen, openSearchDialog, closeSearchDialog]);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    // S5: Slash command detection
    const slashMatch = value.match(/(^|\s)\/(\S*)$/);
    if (slashMatch) {
      const rect = e.target.getBoundingClientRect();
      openSlashMenu(slashMatch[2], {
        top: rect.top - 10,
        left: rect.left + 20,
      });
    } else {
      closeSlashMenu();
    }
  };

  // Issue #1520 (HIGH): the Send button wires `onClick={handleSend}` directly,
  // so React passed the MouseEvent in as `retryPrompt` and `(event ?? input).trim`
  // threw — button-clicked messages never sent at all (Enter still worked).
  // The parameter is now type-guarded: a real string retry prompt is honored,
  // any non-string (event object) falls back to the composer input.
  const handleSend = async (retryPrompt?: unknown) => {
    const retryText = typeof retryPrompt === 'string' ? retryPrompt : undefined;
    const userMessage = (retryText ?? input).trim();
    if (!userMessage) return;
    if (!retryText) setInput('');

    // M10 বাংলা: প্রথম মেসেজেই স্থায়ী conversation identity তৈরি হয় এবং
    // পরের প্রতিটি কলে একই id বজায় থাকে।
    const activeConversationId = conversationId ?? crypto.randomUUID();
    if (!conversationId) setConversationId(activeConversationId);

    // Add user message
    addMessage({ role: 'user', content: userMessage });

    // Emit message sent event (for billing, cost tracking, etc.)
    eventBus.emit(Events.CHAT_MESSAGE_SENT, {
      role: 'user',
      content: userMessage,
      timestamp: Date.now(),
      estimatedTokens: Math.ceil(userMessage.length / 4),
      source: 'chat_interface',
    });

    // Trigger orchestration
    triggerOrchestration(true);

    try {
      const response = await controlPlane.executeCapability({
        capability: 'conversation.orchestrate',
        source: 'chat',
        payload: {
          prompt: userMessage,
          conversation_id: activeConversationId,
          metadata: { idempotency_key: crypto.randomUUID() },
        },
      });

      const responseMap = response as CapabilityExecutionResult;
      const assistantResponse =
        (typeof responseMap.response === 'string' && responseMap.response) ||
        (typeof responseMap.error === 'string' && responseMap.error) ||
        JSON.stringify(responseMap);
      // Add assistant response
      addMessage({
        role: 'assistant',
        content: assistantResponse
      });

      // M10 বাংলা: চুক্তি-অনুযায়ী ফিল্ড এলেই S2/S3 স্টোর সত্য তথ্যে ভরা হয়।
      // CapabilityExecutionResult.data (unknown) হলো এক্সটেনশন পয়েন্ট —
      // টাইপ-গার্ড পাস না করলে কিছুই গ্রহণ করা হয় না।
      const data = responseMap.data as Record<string, unknown> | undefined;
      if (data && Array.isArray(data.reasoning_steps)) {
        setReasoningSteps(data.reasoning_steps.filter(isReasoningStep));
      }
      if (data && Array.isArray(data.artifacts)) {
        for (const artifact of data.artifacts) {
          if (isWorkspaceArtifact(artifact)) addArtifact(artifact);
        }
      }

      // Request TTS if voice enabled
      if (voiceEnabled && assistantResponse) {
        eventBus.emit(Events.TTS_GENERATED, {
          text: assistantResponse,
          timestamp: Date.now(),
        });
      }
    } catch (error: unknown) {
      const detail = error instanceof Error ? error.message : 'Failed to get response';
      addMessage({
        role: 'assistant',
        content: `⚠️ ${detail} — your message was not delivered.`,
      });
      // Issue #1457: keep the failed prompt so the user gets an explicit
      // Retry affordance (and auto-retry when the connection restores).
      setFailed(userMessage);
    } finally {
      triggerOrchestration(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      handleSend();
    }
  };

  // Issue #1457: track connectivity; auto-retry the failed message when the
  // connection restores (single-message queue — the last failed prompt).
  useEffect(() => {
    const goOnline = () => {
      setIsOffline(false);
      const prompt = failedPromptRef.current;
      if (prompt) {
        setFailed(null);
        void handleSend(prompt);
      }
    };
    const goOffline = () => setIsOffline(true);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar area */}
      <div className="flex justify-end p-2 border-b border-slate-800 gap-2 items-center">
        {/* S1: Share Button — conversation শুরুর আগে সৎভাবে disabled (M10) */}
        <button
          onClick={() => {
            if (conversationId) openShareDialog(conversationId);
          }}
          disabled={!conversationId}
          className={`p-2 rounded-lg transition-colors ${
            conversationId
              ? 'text-slate-400 hover:bg-slate-800'
              : 'text-slate-600 cursor-not-allowed opacity-60'
          }`}
          title={conversationId ? 'Share Conversation' : 'Start a conversation first'}
        >
          <Share2 size={18} />
        </button>

        {/* S7: Export Menu — conversation না থাকলে সৎ disabled placeholder */}
        {conversationId ? (
          <ExportMenu conversationId={conversationId} />
        ) : (
          <button
            disabled
            className="p-2 rounded-lg transition-colors text-slate-600 cursor-not-allowed opacity-60"
            title="Start a conversation first"
          >
            <Download size={18} />
          </button>
        )}

        {/* S2: Reasoning panel toggle */}
        <button
          onClick={toggleReasoning}
          aria-pressed={showReasoning}
          className={`p-2 rounded-lg transition-colors ${
            showReasoning ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800'
          }`}
          title="Toggle reasoning panel"
        >
          <BrainCircuit size={18} />
        </button>

        {/* S3: Artifacts panel toggle */}
        <button
          onClick={toggleArtifactsPanel}
          aria-pressed={artifactsPanelOpen}
          className={`p-2 rounded-lg transition-colors ${
            artifactsPanelOpen ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-800'
          }`}
          title="Toggle artifacts panel"
        >
          <FileCode2 size={18} />
        </button>

        <button
          onClick={() => {
            setVoiceEnabled(!voiceEnabled);
            eventBus.emit(Events.VOICE_TOGGLED, {
              enabled: !voiceEnabled,
              timestamp: Date.now(),
            });
          }}
          className={`p-2 rounded-lg transition-colors ${voiceEnabled ? 'bg-blue-600 text-white' : 'text-slate-400 hover:bg-slate-800'}`}
          title={voiceEnabled ? 'Disable voice responses' : 'Enable voice responses'}
        >
          {voiceEnabled ? <Volume2 size={18} /> : <VolumeX size={18} />}
        </button>
      </div>

      {/* Issue #1457: prominent offline banner — the user must know WHY the
          chat is silent instead of guessing. */}
      {isOffline && (
        <div
          role="status"
          className="flex items-center gap-2 border-b border-amber-700/40 bg-amber-500/10 px-4 py-2 text-sm text-amber-300"
          data-testid="chat-offline-banner"
        >
          <span aria-hidden>📡</span>
          You are offline — messages cannot be sent right now. They will retry automatically when the connection returns.
        </div>
      )}

      {/* Messages Area + S3 Artifacts side panel */}
      <div className="relative flex flex-1 min-h-0">
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {chatHistory.map((msg) => (
            <div key={msg.id} className="relative group">
              <UnifiedChatBubble
                text={msg.content}
                sender={msg.role === 'user' ? 'user' : 'system'}
                timestamp={msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
              />

              {/* S11: Branch Button — সত্যিকার conversation_id থাকলেই রেন্ডার হয় */}
              {conversationId && (
                <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  <BranchButton
                    conversationId={conversationId}
                    messageId={msg.id ?? `message-${msg.timestamp ?? 'unknown'}`}
                    onBranchCreated={(newId) => { void newId; }}
                  />
                </div>
              )}

              {voiceEnabled && msg.role === 'assistant' && 'audioUrl' in msg && typeof (msg as { audioUrl?: unknown }).audioUrl === 'string' && (
                <audio
                  controls
                  src={(msg as { audioUrl: string }).audioUrl}
                  className="mt-2"
                  preload="none"
                />
              )}
            </div>
          ))}
          {/* Issue #1525: assistant-is-thinking affordance while awaiting the
              orchestration response — removed automatically in the finally. */}
          {isOrchestrating && <TypingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        {artifactsPanelOpen && (
          <div className="w-72 shrink-0 border-l border-slate-800 lg:w-80 max-md:absolute max-md:inset-y-0 max-md:right-0 max-md:z-20 max-md:w-[85%] max-md:bg-[#0b0d14] max-md:shadow-2xl" data-testid="artifacts-panel-container">
            <ArtifactsPanel
              artifacts={artifacts}
              activeArtifactId={activeArtifactId ?? undefined}
              onSelect={(artifact) => selectArtifact(artifact.id)}
              onClose={() => setArtifactsPanelOpen(false)}
              onNew={() => selectArtifact(null)}
            />
          </div>
        )}
      </div>

      {/* S2: Reasoning panel — thinking চলছে বা ধাপ থাকলেই দেখা যায় */}
      {showReasoning && (isThinking || reasoningSteps.length > 0) && (
        <div className="px-4 pb-2" data-testid="thinking-panel-container">
          <ThinkingPanel steps={reasoningSteps} isThinking={isThinking} />
        </div>
      )}

      {/* Input Area */}
      <div className="p-4 border-t border-slate-800">
        {failedPrompt && !isOffline && (
          <div
            className="mb-3 flex items-center justify-between gap-3 rounded-lg border border-red-800/60 bg-red-500/10 px-3 py-2 text-sm text-red-300"
            data-testid="chat-retry-bar"
          >
            <span className="truncate">Last message failed to send.</span>
            <button
              onClick={() => {
                const prompt = failedPromptRef.current;
                setFailed(null);
                void handleSend(prompt ?? undefined);
              }}
              className="shrink-0 rounded-md bg-red-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-red-500"
            >
              ↻ Retry
            </button>
          </div>
        )}
        {/* Issue #1526 (LOW): on narrow viewports the fixed 18px-icon button,
            textarea, and Send button fought for one row and the composer
            overflowed horizontally. flex-wrap + min-w-0 lets the composer
            reflow; the textarea keeps priority via flex growth. */}
        <div className="flex flex-wrap items-end gap-2">
          {/* S4: Image Upload */}
          <ImageUploadButton
            onUpload={(attachment) => { void attachment; }}
          />

          <textarea
            value={input}
            onChange={handleInputChange}
            onKeyPress={handleKeyPress}
            placeholder="Type your message to the AI agent..."
            className="min-w-0 flex-[1_1_12rem] bg-slate-800 text-white rounded-lg p-3 resize-none focus:outline-none focus:ring-2 focus:ring-blue-500"
            rows={2}
            disabled={isOrchestrating}
          />
          <button
            onClick={handleSend}
            disabled={isOrchestrating || !input.trim()}
            className="shrink-0 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isOrchestrating ? 'Sending...' : 'Send'}
          </button>
        </div>
      </div>

      {/* Dialogs & Menus */}
      {shareDialogOpen && shareConversationId && (
        <ShareDialog
          conversationId={shareConversationId}
          isOpen={shareDialogOpen}
          onClose={closeShareDialog}
        />
      )}
      <ChatSearchDialog isOpen={searchDialogOpen} onClose={closeSearchDialog} />
      <SlashCommandMenu
        isOpen={slashMenuOpen}
        position={slashPosition}
        filter={slashFilter}
        onClose={closeSlashMenu}
        onSelect={(cmd) => {
          setInput(prev => prev.replace(/(^|\s)\/\S*$/, `$1${cmd} `));
          closeSlashMenu();
        }}
      />
    </div>
  );
};

export default ChatInterface;
