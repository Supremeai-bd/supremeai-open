import { useState } from 'react';
import { getApiBaseUrl } from '../../../utils/api';
import { adminTokenStore } from '../../../services/adminTokenStore';
import { apiClient } from '../../../services/apiClient';

interface Action {
  id: string;
  label: string;
  type: string;
}

interface ActionCardMetadata {
  language?: string;
  filename?: string;
  actions?: Action[];
}

interface ActionCardProps {
  rawContent: string;
  onSaveToProject?: (code: string) => void;
  onPreview?: (code: string) => void;
}

export function ActionCard({ rawContent, onSaveToProject, onPreview }: ActionCardProps) {
  const [copied, setCopied] = useState(false);
  const [actionStatus, setActionStatus] = useState('');

  // Try to parse structured AI response JSON
  let parsed: { type: string; content: string; metadata?: ActionCardMetadata } | null = null;
  try {
    if (rawContent.trim().startsWith('{')) {
      parsed = JSON.parse(rawContent);
    }
  } catch (err) {
    // Not a JSON response — log it, then fall back to text rendering.
    console.warn('[action-card] response JSON parse failed, rendering as text:', err);
  }

  const handleAction = async (action: Action, content: string) => {
    try {
      if (action.type === 'save' && onSaveToProject) {
        onSaveToProject(content);
        setActionStatus('💾 Code saved to project!');
        setTimeout(() => setActionStatus(''), 3000);
      } else if (action.type === 'preview' && onPreview) {
        onPreview(content);
        setActionStatus('👁️ Code loaded into preview!');
        setTimeout(() => setActionStatus(''), 3000);
      } else if (action.type === 'copy') {
        await navigator.clipboard.writeText(content);
        setCopied(true);
        setActionStatus('📋 Copied to clipboard!');
        setTimeout(() => {
          setCopied(false);
          setActionStatus('');
        }, 3000);
      } else if (action.type === 'run') {
        // ERR-G12 FIX (2026-09-16): this branch fabricated "✅ Code executed
        // successfully!" after a 1.5s setTimeout without executing anything.
        // JavaScript snippets now really run in the backend sandbox
        // (POST /api/v1/sandbox/create → /{id}/execute, base64-wrapped to
        // survive shell quoting) and the ACTUAL exit code / stdout / stderr
        // is displayed. Non-JS languages and mock-labeled sandbox output are
        // surfaced honestly instead of being passed off as a real run.
        const language = (metadata?.language || 'typescript').toLowerCase();
        const nodeRunnable = ['javascript', 'js', 'jsx'].includes(language);
        if (!nodeRunnable) {
          setActionStatus(`❌ NOT RUN: no sandbox runtime for '${language}' (JavaScript only).`);
          setTimeout(() => setActionStatus(''), 4000);
          return;
        }
        setActionStatus('▶️ Requesting backend sandbox...');
        const created = await apiClient.post<{ session_id: string }>('/api/v1/sandbox/create', {});
        if (!created?.session_id) {
          setActionStatus('❌ Sandbox unavailable — code was NOT executed.');
          setTimeout(() => setActionStatus(''), 4000);
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
          `${exit === 0 && !executed?.mock ? '✅' : '❌'} exit ${exit}${mockNote}${output ? ` · ${output.slice(0, 180)}` : ''}`
        );
        setTimeout(() => setActionStatus(''), 6000);
      } else if (action.type === 'deploy') {
        setActionStatus('🚀 Deploying code component...');
        try {
          const API_BASE = getApiBaseUrl();
          const res = await fetch(`${API_BASE}/admin-api/deploy`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${adminTokenStore.getRawToken()}`
            },
            body: JSON.stringify({ code: content, filename: metadata?.filename || 'component.tsx' })
          });
          if (res.ok) {
            const data = await res.json();
            // বাংলা মন্তব্য: সার্ভার মেসেজ না দিলে কৃত্রিম "deployed successfully" দাবি নিষিদ্ধ — শুধু নিরপেক্ষ সত্য (false-assurance doctrine)
            setActionStatus(`✅ ${data.message || 'Action completed.'}`);
          } else {
            setActionStatus('❌ Deploy failed (unauthorized or server error).');
          }
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : 'Unknown error';
          setActionStatus(`❌ Deploy failed: ${msg}`);
        }
        setTimeout(() => setActionStatus(''), 5000);
      } else if (action.type === 'share') {
        // ERR-G12 FIX: said "Share link copied!" without copying anything.
        // Now actually copies the current page URL, or fails honestly.
        const shareUrl = `${window.location.origin}${window.location.pathname}`;
        await navigator.clipboard.writeText(shareUrl);
        setActionStatus('🔗 Page link copied to clipboard!');
        setTimeout(() => setActionStatus(''), 3000);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setActionStatus(`❌ Error: ${msg}`);
      setTimeout(() => setActionStatus(''), 4000);
    }
  };

  if (!parsed || !parsed.type || !parsed.content) {
    // Normal text message
    return <div className="whitespace-pre-wrap break-words">{rawContent}</div>;
  }

  const { type, content, metadata } = parsed;
  const actions = metadata?.actions || [];

  return (
    <div className="flex flex-col gap-3 w-full bg-[#0a0c14] border border-[#bc13fe]/20 rounded-xl p-3.5 shadow-lg">
      {type === 'code' && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2 mb-1.5">
            <span className="text-[11px] font-mono text-slate-400">
              📁 {metadata?.filename || 'component.tsx'} ({metadata?.language || 'typescript'})
            </span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(content);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              className="text-[10px] text-[#bc13fe] hover:text-[#8b5cf6] font-mono font-semibold"
            >
              {copied ? 'Copied!' : 'Copy Code'}
            </button>
          </div>
          <pre className="bg-[#050608] p-3 rounded-lg overflow-x-auto text-xs font-mono text-slate-300 max-h-60 border border-slate-900">
            <code>{content}</code>
          </pre>
        </div>
      )}

      {type === 'image' && (
        <div className="flex flex-col gap-2">
          <div className="relative rounded-lg overflow-hidden border border-slate-800 max-h-64 bg-slate-950">
            <img src={content} alt="AI Generated" className="w-full h-auto object-contain mx-auto" />
          </div>
        </div>
      )}

      {type === 'text' && (
        <div className="whitespace-pre-wrap break-words text-slate-200">
          {content}
        </div>
      )}

      {/* Action Buttons Section */}
      {actions.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-900/60 mt-1">
          {actions.map((act) => (
            <button
              key={act.id}
              onClick={() => handleAction(act, content)}
              className="text-[11px] px-2.5 py-1.5 rounded-lg bg-[#121420] border border-[#bc13fe]/30 hover:border-[#bc13fe] hover:bg-[#1a1c2e] text-slate-300 font-semibold transition-all duration-200"
            >
              {act.label}
            </button>
          ))}
        </div>
      )}

      {actionStatus && (
        <div className="text-[10px] text-slate-400 font-mono italic animate-pulse">
          {actionStatus}
        </div>
      )}
    </div>
  );
}
