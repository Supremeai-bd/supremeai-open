// Chat API Service for SupremeAI 2.0
// বাংলা মонтаব্য: চ্যাট ইন্টারফেস ও স্ট্রিমিং এপিআই এর সাথে যোগাযোগের জন্য ব্যবহৃত সার্ভিস। Prompt-to-Action সাপোর্ট সহ।

import { apiClient } from './apiClient';

import type { UnifiedChatMessage } from '../types/chat';

export type ChatMessage = UnifiedChatMessage;

export interface ChatResponse {
  response: string;
  tokens_used?: number;
  provider?: string;
  duration?: number;
  action?: {
    type: string;
    target?: string;
    label?: string;
    icon?: string;
    confidence?: number;
    requires_confirmation?: boolean;
    payload?: Record<string, unknown>;
  };
}

// বাংলা মন্তব্য: ফাংশন ডিক্লেয়ারেশন সিনট্যাক্স এরর ঠিক করা হলো
export async function sendMessageStream(
  message: string,
  onToken: (token: string) => void,
  onDone: (action?: ChatResponse['action']) => void,
  onError: (error: string) => void,
  abortSignal?: AbortSignal,
  history?: { role: string; content: string }[],
): Promise<void> {

  try {
    // 🔒 SECURITY FIX: Now includes authentication headers (previously missing)
    // FIX (API-contract audit): migrated to the hardened SSE pipeline
    // (POST /api/v1/stream/chat) — state machine, 15s heartbeat, chunk
    // sanitization. Body sends { message, messages }; backend harmonizes to `prompt`.
    // ROOT-CAUSE FIX (#2725): include history tail (last 20 messages) so
    // multi-turn references resolve correctly. Previously only { message } was
    // sent — follow-up like "that function" had no referent.
    const bodyPayload: Record<string, unknown> = { message };
    if (history && history.length > 0) {
      bodyPayload.messages = history.slice(-20);
    }
    const res = await apiClient.stream('/api/v1/stream/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bodyPayload),
      signal: abortSignal,
    });

    if (!res.ok) {
      onError(`HTTP ${res.status}: ${res.statusText}`);
      return;
    }

    const reader = res.body?.getReader();
    if (!reader) {
      onError('No stream body available');
      return;
    }

    const decoder = new TextDecoder();
    let _fullText = '';
    let pending = '';

    const consumeLine = (line: string) => {
      const normalized = line.trim();
      if (!normalized) return;
      const payload = normalized.startsWith('data:') ? normalized.slice(5).trim() : normalized;
      if (!payload || payload === '[DONE]') return;
      try {
        const parsed = JSON.parse(payload) as { token?: string; delta?: string; content?: string; response?: string; result?: string };
        const token = parsed.token ?? parsed.delta ?? parsed.content ?? parsed.response ?? parsed.result;
        if (token) {
          _fullText += token;
          onToken(token);
        }
      } catch {
        _fullText += payload;
        onToken(payload);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
      const lines = pending.split(/\r?\n/);
      pending = lines.pop() ?? '';
      lines.forEach(consumeLine);
      if (done) break;
    }
    if (pending) consumeLine(pending);
    // Prompt-to-Action metadata fallback (legacy path only)
    // Issue #2522: raw fetch → apiClient.post — auth, timeout, queue, error mapping ক্লায়েন্টেই।
    try {
      const actionData = await apiClient.post<{ action?: ChatResponse['action'] }>('/api/chat/prompt-action', { message });
      onDone(actionData.action);
    } catch {
      onDone(undefined);
    }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } catch (err: any) {
    if (err.name !== 'AbortError') {
      onError(err.message);
    }
  }
};

export const chatService = {
  sendMessage: async (message: string, history: ChatMessage[] = []): Promise<ChatResponse> => {
    // FIX (API-contract audit): TaskRequest requires `task`; `history` maps to
    // `messages`. The old {message, history} shape hit Pydantic 422.
    return apiClient.post<ChatResponse>('/api/task/execute', {
      task: message,
      messages: history,
    });
  },

  sendMessageStream,

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  getVoices: async (): Promise<any[]> => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return apiClient.get<any[]>('/api/voice/voices');
  },
};

export async function getAethelResponse(message: string, history: ChatMessage[] = []): Promise<string> {
  const response = await apiClient.post<{ result: string }>('/api/task/execute', {
    task: message,
    task_type: 'general',
    messages: history,
  });
  return response.result || 'No response from AI backend.';
}
