// studio/src/services/JarvisService.ts
// Jarvis LLM orchestration bridge (issue #1520).
//
// Wraps the backend chat/completion endpoint so the admin console can move
// from pure rule-based responses to live LLM-backed answers, while degrading
// gracefully to the local rule engine when the backend is unreachable.

import { apiClient } from './apiClient';

export interface JarvisReply {
  text: string;
  source: 'llm' | 'rule' | 'fallback';
}

export interface JarvisServiceOptions {
  /** Backend endpoint that accepts { prompt, context? } and returns { reply }. */
  endpoint?: string;
  /** Hard timeout (ms) before falling back to the rule engine. */
  timeoutMs?: number;
}

const DEFAULT_ENDPOINT = '/api/jarvis/ask';
const DEFAULT_TIMEOUT = 8000;

export class JarvisService {
  private endpoint: string;
  private timeoutMs: number;

  constructor(opts: JarvisServiceOptions = {}) {
    this.endpoint = opts.endpoint ?? DEFAULT_ENDPOINT;
    this.timeoutMs = opts.timeoutMs ?? DEFAULT_TIMEOUT;
  }

  /**
   * Ask the backend LLM for a reply. Returns null on any failure so the
   * caller can fall back to the deterministic rule engine.
   */
  async ask(prompt: string, context?: Record<string, unknown>): Promise<JarvisReply | null> {
    if (!prompt || !prompt.trim()) return null;
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), this.timeoutMs);
      const res = await apiClient.post<{ reply?: string; text?: string }>(
        this.endpoint,
        { prompt, context: context ?? {} },
      );
      clearTimeout(timer);
      const text = (res?.reply ?? res?.text ?? '').trim();
      if (!text) return null;
      return { text, source: 'llm' };
    } catch {
      return null;
    }
  }
}

export const jarvisService = new JarvisService();

export default jarvisService;
