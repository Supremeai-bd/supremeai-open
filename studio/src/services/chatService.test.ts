import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../utils/api', () => ({
  getApiBaseUrl: () => 'https://api.test',
}));

vi.mock('./apiClient', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    stream: vi.fn(),
  },
  getAuthHeaders: vi.fn(async () => ({ Authorization: 'Bearer x' })),
}));

import { chatService, getAethelResponse, sendMessageStream } from './chatService';
import { apiClient, getAuthHeaders } from './apiClient';

describe('chatService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    global.fetch = vi.fn();
    (getAuthHeaders as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      Authorization: 'Bearer x',
    });
  });

  it('sendMessage posts to the task execute endpoint', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      response: 'hi',
      tokens_used: 3,
    });
    const res = await chatService.sendMessage('hello', []);
    // FIX (API-contract audit): TaskRequest requires `task`; `history` maps to
    // `messages`. The old {message, history} shape hit Pydantic 422.
    expect(apiClient.post).toHaveBeenCalledWith('/api/task/execute', {
      task: 'hello',
      messages: [],
    });
    expect(res.response).toBe('hi');
  });

  it('getVoices gets the voices endpoint', async () => {
    (apiClient.get as unknown as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 'v1' },
    ]);
    const res = await chatService.getVoices();
    expect(apiClient.get).toHaveBeenCalledWith('/api/voice/voices');
    expect(res).toHaveLength(1);
  });

  it('getAethelResponse returns the result string', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
      result: 'answer',
    });
    const res = await getAethelResponse('q');
    expect(apiClient.post).toHaveBeenCalledWith('/api/task/execute', {
      task: 'q',
      task_type: 'general',
      messages: [],
    });
    expect(res).toBe('answer');
  });

  it('getAethelResponse falls back when result is missing', async () => {
    (apiClient.post as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({});
    const res = await getAethelResponse('q');
    expect(res).toBe('No response from AI backend.');
  });

  function makeStreamReader(chunks: string[]) {
    const enc = new TextEncoder();
    let i = 0;
    return {
      body: {
        getReader: () => ({
          read: async () => {
            if (i < chunks.length) {
              return { value: enc.encode(chunks[i++]), done: false };
            }
            return { value: undefined, done: true };
          },
        }),
      },
      ok: true,
    };
  }

  it('sendMessageStream emits tokens and reports the prompt action', async () => {
    const onToken = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();
    // Issue #2522: streaming now via apiClient.stream; prompt-action via apiClient.post.
    (apiClient.stream as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(makeStreamReader(['data: {"token":"Hello"}\n', 'data: [DONE]\n']));
    (apiClient.post as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ action: { type: 'open' } });
    await sendMessageStream('hi', onToken, onDone, onError);
    expect(onToken).toHaveBeenCalledWith('Hello');
    expect(onDone).toHaveBeenCalledWith({ type: 'open' });
    expect(onError).not.toHaveBeenCalled();
  });

  it('sendMessageStream reports an error when the response is not ok', async () => {
    const onToken = vi.fn();
    const onDone = vi.fn();
    const onError = vi.fn();
    (apiClient.stream as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal',
      body: null,
    });
    await sendMessageStream('hi', onToken, onDone, onError);
    expect(onError).toHaveBeenCalledWith('HTTP 500: Internal');
  });
});
