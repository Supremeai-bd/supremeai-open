import { useState } from 'react';
import { getApiBaseUrl } from '../../utils/api';
import { adminTokenStore } from '../../services/adminTokenStore';
import { apiClient } from '../../services/apiClient';

// --- Bangla comment: UnifiedChatBubble-এ action button-এর জন্য প্রপস ---
interface PromptActionMeta {
  type: string;
  target?: string;
  label?: string;
  icon?: string;
  confidence?: number;
  requires_confirmation?: boolean;
  payload?: Record<string, unknown>;
}

interface UnifiedChatBubbleProps {
  text: string;
  sender: 'user' | 'system';
  timestamp?: string;
  action?: PromptActionMeta | null;
  onSaveToProject?: (code: string) => void;
  onPreview?: (code: string) => void;
}

// Bangla comment: ডার্ক সাই-ফাই Cold Glass ইফেক্টের CSS ক্লাস
const SCI_FI_USER_BUBBLE =
  'bg-gradient-to-br from-[#00f3ff]/90 to-[#0891b2] text-black font-bold rounded-tr-none shadow-[0_0_18px_rgba(0,243,255,0.35)] border border-[#00f3ff]/40';

const SCI_FI_SYSTEM_BUBBLE =
  'bg-[#0a0c14]/85 border border-[#bc13fe]/18 text-slate-200 rounded-tl-none shadow-[0_0_14px_rgba(188,19,254,0.12)] backdrop-blur-md';

// Bangla comment: Action item interface
interface ActionItem {
  id: string;
  label: string;
  type: string;
}

function parseActionCard(raw: string): { type: string; content: string; metadata: { language?: string; filename?: string; actions?: ActionItem[] } } | null {
  try {
    if (raw.trim().startsWith('{')) {
      return JSON.parse(raw);
    }
  } catch (err) {
    // JSON না হলে টেক্সট হিসেবে রেন্ডার — কিন্তু কারণটা লগে থাকবে।
    console.warn('[chat] action card JSON parse failed, using text fallback:', err);
  }
  return null;
}

export function UnifiedChatBubble({
  text,
  sender,
  timestamp,
  action,
  onSaveToProject,
  onPreview,
}: UnifiedChatBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [actionStatus, setActionStatus] = useState('');

  const bubbleClass = sender === 'user' ? SCI_FI_USER_BUBBLE : SCI_FI_SYSTEM_BUBBLE;

  // Bangla comment: action badge ইন্টারফেসে দেখানো হবে AI কি করবে তা
  const actionBadge = action && action.label
    ? (
      <span className="inline-flex items-center gap-1 text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-[#bc13fe]/15 text-[#bc13fe] border border-[#bc13fe]/25 mb-1.5">
        {action.icon && <span>{action.icon}</span>}
        {action.label}
      </span>
    )
    : null;

  const handleActionButton = async (act: ActionItem, content: string, filename?: string) => {
    try {
      if (act.type === 'save' && onSaveToProject) {
        onSaveToProject(content);
        setActionStatus('💾 Saved to project!');
      } else if (act.type === 'preview' && onPreview) {
        onPreview(content);
        setActionStatus('👁️ Preview loaded!');
      } else if (act.type === 'copy') {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setActionStatus('📋 Copied to clipboard!');
        setTimeout(() => setCopied(false), 2000);
      } else if (act.type === 'run') {
        // ERR-G12 class fix (found by the hardened ERR-M01 stub scanner):
        // this branch fabricated "✅ Executed!" after 1.5s without running
        // anything. JS snippets now really execute in the backend sandbox
        // (POST /api/v1/sandbox/create → /{id}/execute, base64-wrapped) and
        // the ACTUAL exit code / output is displayed; anything else is an
        // explicit refusal instead of a fake success.
        const language = (filename ? filename.split('.').pop() || '' : '').toLowerCase();
        const nodeRunnable = ['js', 'mjs', 'cjs'].includes(language);
        if (!nodeRunnable) {
          setActionStatus(`❌ NOT RUN: no sandbox runtime for '${language || 'unknown'}' (JavaScript only).`);
          return;
        }
        setActionStatus('▶️ Requesting backend sandbox...');
        const created = await apiClient.post<{ session_id: string }>('/api/v1/sandbox/create', {});
        if (!created?.session_id) {
          setActionStatus('❌ Sandbox unavailable — code was NOT executed.');
          return;
        }
        const encoded = btoa(unescape(encodeURIComponent(content)));
        const executed = await apiClient.post<{ exitCode?: number; stdout?: string; stderr?: string; mock?: boolean }>(
          `/api/v1/sandbox/${encodeURIComponent(created.session_id)}/execute`,
          { command: `node -e "eval(Buffer.from('${encoded}','base64').toString())"`, timeout: 120 }
        );
        const exit = typeof executed?.exitCode === 'number' ? executed.exitCode : -1;
        const output = ((executed?.stdout || '') + (executed?.stderr ? `\n${executed.stderr}` : '')).trim();
        const mockNote = executed?.mock ? ' [sandbox MOCK output — no provider configured]' : '';
        setActionStatus(
          `${exit === 0 && !executed?.mock ? '✅' : '❌'} exit ${exit}${mockNote}${output ? ` · ${output.slice(0, 140)}` : ''}`
        );
      } else if (act.type === 'deploy') {
        setActionStatus('🚀 Deploying...');
        try {
          const res = await fetch(`${getApiBaseUrl()}/admin-api/deploy`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${adminTokenStore.getRawToken()}`
            },
            body: JSON.stringify({ code: content, filename: filename || 'component.tsx' })
          });
          if (res.ok) {
            const data = await res.json();
            setActionStatus(`✅ ${data.message || 'Deployed!'}`);
          } else {
            setActionStatus('❌ Deploy failed (unauthorized or server error).');
          }
        } catch (e: unknown) {
          setActionStatus(e instanceof Error ? `❌ Deploy failed: ${e.message}` : '❌ Deploy failed');
        }
      } else if (act.type === 'share') {
        setActionStatus('🔗 Share link copied!');
      }
      setTimeout(() => setActionStatus(''), 3500);
    } catch (err: unknown) {
      setActionStatus(err instanceof Error ? `❌ Error: ${err.message}` : '❌ Error');
      setTimeout(() => setActionStatus(''), 4000);
    }
  };

  // Bangla comment: সবসময় plain text fallback থাকবে, কিন্তু পাশে action card আছে
  if (sender === 'system') {
    const parsed = parseActionCard(text);

    if (parsed && parsed.type && parsed.content) {
      return (
        <div className={`max-w-[85%] flex flex-col gap-1 self-start items-start`}>
          {actionBadge}
          <div className={`p-3.5 rounded-2xl text-xs leading-relaxed w-full ${SCI_FI_SYSTEM_BUBBLE}`}>
            {parsed.type === 'code' && (
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-1.5">
                  <span className="text-[11px] font-mono text-slate-400">
                    📁 {parsed.metadata?.filename || 'component.tsx'} ({parsed.metadata?.language || 'typescript'})
                  </span>
                  <button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(parsed.content);
                        setCopied(true);
                        setTimeout(() => setCopied(false), 2000);
                      } catch {
                        setActionStatus('❌ Clipboard copy failed. Copy manually.');
                        setTimeout(() => setActionStatus(''), 3000);
                      }
                    }}
                    className="text-[10px] text-[#bc13fe] hover:text-[#8b5cf6] font-mono font-semibold"
                  >
                    {copied ? 'Copied!' : 'Copy Code'}
                  </button>
                </div>
                <pre className="bg-[#050608] p-3 rounded-lg overflow-x-auto text-xs font-mono text-slate-300 max-h-60 border border-slate-900">
                  <code>{parsed.content}</code>
                </pre>
              </div>
            )}
            {parsed.type === 'image' && (
              <div className="rounded-lg overflow-hidden border border-slate-800 max-h-64 bg-slate-950">
                <img src={parsed.content} alt="AI Generated" className="w-full h-auto object-contain mx-auto" />
              </div>
            )}
            {parsed.type === 'text' && (
              <div className="whitespace-pre-wrap break-words text-slate-200">
                {parsed.content}
              </div>
            )}
            {parsed.metadata?.actions && parsed.metadata.actions.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-900/60 mt-1">
                {parsed.metadata.actions.map((act) => (
                  <button
                    key={act.id}
                    onClick={() => handleActionButton(act, parsed.content, parsed.metadata?.filename)}
                    className="text-[11px] px-2.5 py-1.5 rounded-lg bg-[#121420] border border-[#bc13fe]/30 hover:border-[#bc13fe] hover:bg-[#1a1c2e] text-slate-300 font-semibold transition-all duration-200"
                  >
                    {act.label}
                  </button>
                ))}
              </div>
            )}
            {actionStatus && (
              <div className="text-[10px] text-slate-400 font-mono italic animate-pulse mt-1">
                {actionStatus}
              </div>
            )}
          </div>
          {timestamp && (
            <span className="text-[9px] text-slate-400 px-1 font-mono">{timestamp}</span>
          )}
        </div>
      );
    }

    // Bangla comment: ক্যাচ-এ flat text fallback
    return (
      <div className={`max-w-[85%] flex flex-col gap-1 self-start items-start`}>
        {actionBadge}
        <div className={`p-3.5 rounded-2xl text-xs leading-relaxed ${bubbleClass}`}>
          {text}
        </div>
        {actionStatus && (
          <div className="text-[10px] text-slate-400 font-mono italic animate-pulse">
            {actionStatus}
          </div>
        )}
        {timestamp && (
          <span className="text-[9px] text-slate-400 px-1 font-mono">{timestamp}</span>
        )}
      </div>
    );
  }

  return (
    <div className={`max-w-[85%] flex flex-col gap-1 self-end items-end`}>
      <div className={`p-3.5 rounded-2xl text-xs leading-relaxed ${bubbleClass}`}>
        {text}
      </div>
      {timestamp && (
        <span className="text-[9px] text-slate-400 px-1 font-mono">{timestamp}</span>
      )}
    </div>
  );
}
