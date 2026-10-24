import { describe, it, expect, vi, beforeEach } from 'vitest';
import { browserService } from './browserService';
import { apiClient } from './apiClient';

vi.mock('./apiClient', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('browserService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('createSession calls POST /api/browser/automation/sessions', async () => {
    const mockSession = { session_id: 'sess-123', status: 'ready', url: 'about:blank' };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockSession);

    const result = await browserService.createSession();
    expect(apiClient.post).toHaveBeenCalledWith('/api/browser/automation/sessions', {});
    expect(result).toEqual(mockSession);
  });

  it('listSessions calls GET /api/browser/automation/sessions', async () => {
    const mockSessions = {
      sessions: [{ session_id: 'sess-1', status: 'active', url: 'https://example.com' }],
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockSessions);

    const result = await browserService.listSessions();
    expect(apiClient.get).toHaveBeenCalledWith('/api/browser/automation/sessions');
    expect(result).toEqual(mockSessions);
  });

  it('closeSession calls DELETE /api/browser/automation/sessions/:id with encoding', async () => {
    vi.mocked(apiClient.delete).mockResolvedValueOnce({ success: true });

    const result = await browserService.closeSession('sess/abc?123');
    expect(apiClient.delete).toHaveBeenCalledWith('/api/browser/automation/sessions/sess%2Fabc%3F123');
    expect(result).toEqual({ success: true });
  });

  it('execute executes a navigation action', async () => {
    const mockResult = { success: true, action: 'navigate', url: 'https://github.com' };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResult);

    const result = await browserService.execute('sess-1', {
      action: 'navigate',
      url: 'https://github.com',
    });

    expect(apiClient.post).toHaveBeenCalledWith('/api/browser/automation/actions', {
      session_id: 'sess-1',
      action: 'navigate',
      url: 'https://github.com',
    });
    expect(result).toEqual(mockResult);
  });

  it('execute executes a click action', async () => {
    const mockResult = { success: true, action: 'click', url: 'https://github.com' };
    vi.mocked(apiClient.post).mockResolvedValueOnce(mockResult);

    const result = await browserService.execute('sess-1', {
      action: 'click',
      selector: '#submit-btn',
    });

    expect(apiClient.post).toHaveBeenCalledWith('/api/browser/automation/actions', {
      session_id: 'sess-1',
      action: 'click',
      selector: '#submit-btn',
    });
    expect(result).toEqual(mockResult);
  });
});
