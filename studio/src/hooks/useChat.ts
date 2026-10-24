import { useState, useCallback, useRef, useEffect } from 'react';
import { useStore } from '../store/useStore';
import type { ChatMessage } from '../types/customer';
import { getApiBaseUrl } from '../utils/api';
// বাংলা মন্তব্য: getAuthHeaders import — streaming fetch এ Authorization header মিসিং ছিল, এখন যোগ হলো
import { getAuthHeaders } from '../services/apiClient';


interface UseChatOptions {
  projectId?: string;
  streaming?: boolean;
}

interface UseChatReturn {
  messages: ChatMessage[];
  input: string;
  setInput: (val: string) => void;
  send: () => Promise<void>;
  loading: boolean;
  error: string | null;
  clear: () => void;
}

export function useChat(options: UseChatOptions = {}): UseChatReturn {
  const { projectId, streaming = true } = options;
  // FIX(triple-write): this hook used to mirror every message into BOTH
  // useStore.chatHistory and customerStore.chatHistory in addition to its own
  // local state — three copies of the same message with no single source of
  // truth. Messages now live ONLY in the hook's local `messages` state, which
  // is what consumers render. (Nothing read those mirrored copies: the only
  // other chat UI, ChatInterface, manages useStore.chatHistory itself.)
  const { triggerOrchestration } = useStore();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(loading);

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const send = useCallback(async () => {
    if (!input.trim() || loadingRef.current) return;

    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: input.trim(),
      timestamp: Date.now(),
      project_id: projectId,
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setError(null);
    triggerOrchestration(true);

    if (streaming) {
      abortRef.current = new AbortController();

      try {
        const res = await fetch(`${getApiBaseUrl()}/api/chat/stream`, {
          method: 'POST',
          // বাংলা মন্তব্য: await getAuthHeaders() যোগ — আগে streaming fetch তে Authorization header Promise Unhandled ছিল
          headers: { ...(await getAuthHeaders()), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userMsg.content,
            project_id: projectId,
            idempotency_key: crypto.randomUUID(),
          }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) throw new Error(`Chat request failed: ${res.status}`);

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let assistantContent = '';
        let pending = '';
        const assistantId = crypto.randomUUID();
        const applyPayload = (payload: string) => {
          if (!payload || payload === '[DONE]') return;
          let token = payload;
          try {
            const parsed = JSON.parse(payload) as { token?: string; delta?: string; content?: string; response?: string };
            token = parsed.token ?? parsed.delta ?? parsed.content ?? parsed.response ?? '';
          } catch (parseError) {
            // Plain-text SSE payloads are valid fallbacks.
            console.debug('[v0] Received plain-text chat stream payload', parseError);
          }
          assistantContent += token;
        };

        if (reader) {
          while (true) {
            const { done, value } = await reader.read();
            pending += decoder.decode(value ?? new Uint8Array(), { stream: !done });
            const lines = pending.split(/\r?\n/);
            pending = lines.pop() ?? '';
            lines.forEach((line) => {
              if (line.startsWith('data:')) applyPayload(line.slice(5).trim());
            });
            if (done) break;

            const partialMsg: ChatMessage = {
              id: assistantId,
              role: 'assistant',
              content: assistantContent,
              timestamp: Date.now(),
              project_id: projectId,
            };

            setMessages(prev => {
              const existing = prev.findIndex(m => m.id === assistantId);
              if (existing >= 0) {
                const updated = [...prev];
                updated[existing] = partialMsg;
                return updated;
              }
              return [...prev, partialMsg];
            });
          }
          if (pending.startsWith('data:')) applyPayload(pending.slice(5).trim());
        }

        const finalMsg: ChatMessage = {
          id: assistantId,
          role: 'assistant',
          content: assistantContent || 'No response received.',
          timestamp: Date.now(),
          project_id: projectId,
        };

        // Finalize the streamed message in local state (it was added as a
        // partial during streaming; update in place, append only if missing).
        setMessages(prev => {
          const existing = prev.findIndex(m => m.id === assistantId);
          if (existing >= 0) {
            const updated = [...prev];
            updated[existing] = finalMsg;
            return updated;
          }
          return [...prev, finalMsg];
        });
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } catch (err: any) {
        if (err.name !== 'AbortError') {
          setError(err.message || 'Unknown error occurred');
        }
      } finally {
        setLoading(false);
        triggerOrchestration(false);
        abortRef.current = null;
      }
    } else {
      try {
        const res = await fetch(`${getApiBaseUrl()}/api/chat`, {
          method: 'POST',
          // বাংলা মন্তব্য: non-streaming path এও await auth header যোগ হলো
          headers: { ...(await getAuthHeaders()), 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: userMsg.content,
            project_id: projectId,
          }),
        });

        if (!res.ok) throw new Error(`Chat request failed: ${res.status}`);

        const data = await res.json();
        const assistantMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.response || data.message || 'No response received.',
          timestamp: Date.now(),
          project_id: projectId,
          metadata: { model: data.model, tokens: data.tokens },
        };

        setMessages(prev => [...prev, assistantMsg]);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } catch (err: any) {
        setError(err.message || 'Unknown error occurred');
      } finally {
        setLoading(false);
        triggerOrchestration(false);
      }
    }
  }, [input, projectId, streaming, triggerOrchestration]);

  const clear = useCallback(() => {
    setMessages([]);
    setInput('');
    setError(null);
  }, []);

  return { messages, input, setInput, send, loading, error, clear };
}
