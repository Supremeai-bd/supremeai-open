import { create } from 'zustand';
import { getWebSocketBaseUrl, getApiBaseUrl } from '../utils/api';
import { getRawToken } from '../services/apiClient';
import { createSecureEventSource } from '../lib/secureSse';

export type SujonState =
  | 'idle'
  | 'scanning'
  | 'executing'
  | 'circuit_open'
  | 'self_healing'
  | 'awaiting_human'
  | 'success'
  | 'failed'
  | 'processing';

export interface LogEntry {
  id: string;
  ts: string;
  log_type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  payload: any;
}

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'directory';
  status: 'new' | 'modified' | 'deleted' | 'unchanged';
}

export interface ReasoningEntry {
  id: string;
  ts: string;
  token: string;
}

interface SessionCockpitState {
  sessionId: string | null;
  // We use a normal array but we will cap it at 10,000 in our mutations
  logBuffer: LogEntry[];
  // Zustand isn't great with Maps in reactive state if they mutate often,
  // but for the sake of the store structure we define it.
  // The actual FileTreePanel uses a useRef<Map> for performance.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fileTreeData: any;
  reasoningChain: ReasoningEntry[];
  agentState: SujonState;
  controlMode: 'agent' | 'human';
  sseRef: EventSource | null;
  wsRef: WebSocket | null;

  resetSessionState: () => void;
  connectSSE: (sessionId: string) => void;
  disconnectSSE: () => void;
  connectTakeoverWS: (sessionId: string, token: string) => void;
  disconnectTakeoverWS: () => void;

  // Buffers
  addLog: (log: LogEntry) => void;
  addReasoningEntry: (entry: ReasoningEntry) => void;
}

const MAX_LOGS = 10000;
const MAX_REASONING = 200;

export const useSessionCockpitStore = create<SessionCockpitState>((set, get) => ({
  sessionId: null,
  logBuffer: [],
  fileTreeData: null,
  reasoningChain: [],
  agentState: 'idle',
  controlMode: 'agent',
  sseRef: null,
  wsRef: null,

  resetSessionState: () => {
    const { sseRef, wsRef } = get();
    if (sseRef) {
      sseRef.close();
    }
    if (wsRef) {
      wsRef.close();
    }
    set({
      sessionId: null,
      logBuffer: [],
      fileTreeData: null,
      reasoningChain: [],
      agentState: 'idle',
      controlMode: 'agent',
      sseRef: null,
      wsRef: null,
    });
  },

  connectSSE: (sessionId: string) => {
    get().disconnectSSE(); // Ensure previous is closed
    const token = getRawToken();
    const sse = createSecureEventSource(`${getApiBaseUrl()}/api/session/${sessionId}/stream`, token, {
      onMessage: (event) => {
        try {
          const parsed = JSON.parse(event.data);
          if (parsed.channel === 'logs') {
            get().addLog(parsed.data);
          } else if (parsed.channel === 'state') {
            set({ agentState: parsed.data.current_state });
          } else if (parsed.channel === 'reasoning') {
            // বাংলা: Phase 1 — এজেন্টের চিন্তা-প্রক্রিয়া এখন ReasoningLog-এ দৃশ্যমান।
            // এজেন্ট সাইড (core/observability/reasoning_stream.py) থেকে
            // log_type: "reasoning_step" ইভেন্ট এই চ্যানেলে আসে।
            const d = parsed.data || {};
            get().addReasoningEntry({
              id: `${d.step ?? get().reasoningChain.length}-${Date.now()}`,
              ts: d.ts ?? new Date().toISOString(),
              token: d.token ?? d.content ?? '',
            });
          }
        } catch (err) {
          console.error("SSE parse error", err);
        }
      }
    });
    set({ sseRef: sse as unknown as EventSource, sessionId });
  },

  disconnectSSE: () => {
    const { sseRef } = get();
    if (sseRef) {
      (sseRef as EventSource).close();
      set({ sseRef: null });
    }
  },

  connectTakeoverWS: (sessionId: string, token: string) => {
    get().disconnectTakeoverWS();
    // বাংলা মন্তব্য: প্রোডাকশন ক্লাউড সার্ভারের সাথে WSS সংযোগ স্থাপনের জন্য getWebSocketBaseUrl ব্যবহার
    const baseUrl = getWebSocketBaseUrl();
    const ws = new WebSocket(`${baseUrl}/ws/session/${sessionId}/takeover`);

    ws.onopen = () => {
      // First-message authentication for WebSocket
      ws.send(JSON.stringify({ type: 'auth', token }));
      set({ controlMode: 'human' });
    };
    ws.onclose = () => {
      set({ controlMode: 'agent' });
    };
    set({ wsRef: ws });
  },

  disconnectTakeoverWS: () => {
    const { wsRef } = get();
    if (wsRef) {
      wsRef.close();
      set({ wsRef: null });
    }
  },

  addLog: (log: LogEntry) => {
    set((state) => {
      const newBuffer = [...state.logBuffer, log];
      if (newBuffer.length > MAX_LOGS) {
        return { logBuffer: newBuffer.slice(newBuffer.length - MAX_LOGS) };
      }
      return { logBuffer: newBuffer };
    });
  },

  addReasoningEntry: (entry: ReasoningEntry) => {
    // বাংলা: reasoning chain ক্যাপ করা হয়েছে (200) — দীর্ঘ সেশনে unbounded
    // growth রোধ করে সর্বশেষ ২০০টি চিন্তা-স্টেপ দৃশ্যমান থাকে।
    set((state) => {
      const next = [...state.reasoningChain, entry];
      return { reasoningChain: next.length > MAX_REASONING ? next.slice(next.length - MAX_REASONING) : next };
    });
  }
}));
