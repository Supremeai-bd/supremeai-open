// frontend/src/components/dashboard/OneLinerMCPConnect.tsx
//
// ⚡ 1-Line Connect (old plan, Feature 1)
// একটি মাত্র URL/Token ইনপুটে MCP Server, AI Provider বা Webhook সংযুক্ত
// করার ১-লাইন UX। Backend: POST /api/v1/integrations/discover
// (auto-detect: MCP handshake → AI provider pattern → webhook fallback)।

import React, { useCallback, useState } from 'react';
import { apiClient } from '../../services/apiClient';

export interface MCPConnectResult {
  id: string;
  name: string;
  type: 'mcp' | 'ai_provider' | 'webhook' | 'unknown';
  status: 'connected' | 'failed';
  capabilities?: string[];
  endpoint?: string;
  error?: string;
}

const TYPE_LABELS: Record<MCPConnectResult['type'], string> = {
  mcp: 'MCP Server',
  ai_provider: 'AI Provider',
  webhook: 'Webhook',
  unknown: 'Unknown',
};

export const OneLinerMCPConnect: React.FC = () => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<MCPConnectResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleConnect = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // POST to backend discovery endpoint (auto-detect + register)
      const res = await apiClient.post<MCPConnectResult>(
        '/api/v1/integrations/discover',
        { url: trimmed, register: true },
      );
      if (res?.status === 'failed') {
        setError(res.error || 'Connection failed');
      } else {
        setResult(res);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Connection failed');
    } finally {
      setLoading(false);
    }
  }, [url, loading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      void handleConnect();
    }
  };

  return (
    <div className="glass-panel p-6 space-y-4" data-testid="one-liner-mcp-connect">
      <h2 className="text-lg font-bold text-[#00F3FF]">⚡ 1-Line Connect</h2>
      <p className="text-sm text-[#94A3B8]">
        MCP Server URL, AI Provider endpoint, বা Webhook — একটি URL হলেই যথেষ্ট।
      </p>

      <div className="flex gap-2">
        <input
          id="mcp-url-input"
          className="glass-input flex-1 px-4 py-3 text-sm"
          placeholder="https://your-mcp-server.com/mcp  or  https://api.openai.com/v1"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          aria-label="Integration URL"
        />
        <button
          id="mcp-connect-btn"
          onClick={() => void handleConnect()}
          disabled={loading || !url.trim()}
          className="px-5 py-3 rounded-xl bg-[#00F3FF] text-[#06070B] font-bold text-sm
                     disabled:opacity-40 hover:bg-cyan-300 transition-all pulse-ring"
          data-testid="mcp-connect-btn"
        >
          {loading ? '⏳' : '🔗 Connect'}
        </button>
      </div>

      {result && (
        <div
          className="glass-panel p-4 border-[#22C55E]/30 bg-green-900/10"
          data-testid="mcp-connect-success"
        >
          <p className="text-[#22C55E] font-semibold">
            ✅ {result.name} ({TYPE_LABELS[result.type] ?? result.type})
          </p>
          <p className="text-xs text-[#94A3B8] mt-1">
            Type: {result.type} · Capabilities:{' '}
            {(result.capabilities && result.capabilities.length > 0
              ? result.capabilities
              : ['none']
            ).join(', ')}
          </p>
        </div>
      )}
      {error && (
        <div className="glass-panel p-4 border-red-500/30 bg-red-900/10" data-testid="mcp-connect-error">
          <p className="text-red-400 text-sm">❌ {error}</p>
        </div>
      )}
    </div>
  );
};

export default OneLinerMCPConnect;
