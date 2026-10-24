import { apiClient } from './apiClient';

export interface BrowserSession {
  session_id: string;
  status: string;
  url: string;
}

export interface SavedBrowserSession {
  id: string;
  tenant_id: string;
  owner_id: string;
  label: string;
  url: string;
  session_id: string | null;
  revoked: boolean;
}

export interface BrowserActionResult {
  success: boolean;
  action: string;
  url: string;
  content?: string;
  screenshot?: string;
}

export type BrowserAction =
  | { action: 'navigate'; url: string }
  | { action: 'click'; selector: string }
  | { action: 'fill' | 'type'; selector: string; value: string }
  | { action: 'screenshot'; full_page?: boolean }
  | { action: 'content' | 'extract' };

export const browserService = {
  createSession: (payload?: { label?: string; saved_url?: string }) => apiClient.post<BrowserSession>('/api/browser/automation/sessions', payload ?? {}),
  listSessions: () => apiClient.get<{ sessions: BrowserSession[] }>('/api/browser/automation/sessions'),
  listSavedSessions: () => apiClient.get<{ sessions: SavedBrowserSession[] }>('/api/browser/automation/saved-sessions'),
  saveSession: (payload: { label: string; url: string; session_id?: string }) => apiClient.post<{ session: SavedBrowserSession }>('/api/browser/automation/saved-sessions', payload),
  revokeSavedSession: (sessionId: string) => apiClient.delete<{ success: boolean }>(`/api/browser/automation/saved-sessions/${encodeURIComponent(sessionId)}`),
  closeSession: (sessionId: string) =>
    apiClient.delete<{ success: boolean }>(`/api/browser/automation/sessions/${encodeURIComponent(sessionId)}`),
  execute: (sessionId: string, action: BrowserAction) =>
    apiClient.post<BrowserActionResult>('/api/browser/automation/actions', {
      session_id: sessionId,
      ...action,
    }),
};

export default browserService;
