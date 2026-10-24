// বাংলা মন্তব্য: সেশন (Devin-স্টাইল টাস্ক/চ্যাট সেশন) — localStorage + ব্যাকএন্ড API সিঙ্ক
// VaultPage.tsx-এর মত ব্যাকএন্ড API কল করে ডেটা পার্সিস্ট করা হয় (Firestore-ভিত্তিক সেশন সিঙ্ক)
import { apiClient } from '../../services/apiClient';

export interface SessionMessage {
  id: number;
  sender: 'User' | 'SupremeAI';
  text: string;
  timestamp: string;
}

export type SessionStatus = 'running' | 'finished' | 'error';

export interface DashboardSession {
  id: string;
  title: string;
  status: SessionStatus;
  created_at: string;
  updated_at: string;
  messages: SessionMessage[];
}

const STORAGE_KEY = 'supremeai_dashboard_sessions';
// বাংলা মন্তব্য: সেশন আপডেট হলে অন্য পেজ (যেমন সেশন ডিটেইল ভিউ) যাতে রিফ্রesh করতে পারে সেজন্য কাস্টম ইভেন্ট
export const SESSIONS_UPDATED_EVENT = 'supremeai:sessions-updated';

// বাংলা মন্তব্য: লোকাল ক্যাশে — ব্যাকএন্ড API কল ব্যর্থ হলে localStorage-এ ফলব্যাক
function loadLocalSessions(): DashboardSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveLocalSessions(sessions: DashboardSession[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch (err) {
    // বাংলা মন্তব্য: স্টোরেজ কোটা শেষ হলে বা ব্যর্থ হলে সতর্কবার্তা দেওয়া হলো
    console.error("[Storage] Failed to save sessions locally:", err);
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('supremeai-toast', {
        detail: { message: 'Local storage quota exceeded. Changes might not persist!', type: 'error' }
      }));
    }
  }
}

// বাংলা মন্তব্য: ব্যাকএন্ড থেকে সেশন লোড করে, ব্যর্থ হলে localStorage থেকে পড়ে
export async function loadSessions(): Promise<DashboardSession[]> {
  try {
    const data = await apiClient.get<{ sessions: DashboardSession[] }>('/api/browser/sessions');
    const sessions = data.sessions || [];
    // বাংলা মন্তব্য: ব্যাকএন্ড ডেটা localStorage-এ ক্যাশে করে রাখি
    saveLocalSessions(sessions);
    return sessions;
  } catch {
    // বাংলা মন্তব্য: API কল ব্যর্থ — localStorage ফলব্যাক
    return loadLocalSessions();
  }
}

// বাংলা মন্তব্য: ব্যাকএন্ডে সেশন সেভ/আপডেট করে, ব্যর্থ হলে pending-sync কিউতে জমা করে
export async function saveSessions(sessions: DashboardSession[]): Promise<void> {
  let hasFailed = false;

  for (const session of sessions) {
    try {
      await apiClient.put(`/api/browser/sessions/${session.id}`, session);
    } catch {
      try {
        await apiClient.post('/api/browser/sessions', session);
      } catch (err) {
        hasFailed = true;
        console.error(`[API] Failed to save session ${session.id} on backend:`, err);
      }
    }
  }

  if (hasFailed) {
    // বাংলা মন্তব্য: ব্যর্থ সেশনগুলোকে লোকাল পেন্ডিং কিউতে জমা করি এবং ব্যবহারকারীকে জানাই
    try {
      localStorage.setItem('supremeai_pending_sessions', JSON.stringify(sessions));
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('supremeai-toast', {
          detail: { message: 'Saved locally. Changes will sync once back online.', type: 'warning' }
        }));
      }
    } catch (e) {
      console.error("[Storage] Failed to save pending sessions to queue:", e);
    }
  } else {
    try {
      localStorage.removeItem('supremeai_pending_sessions');
    } catch (cleanupErr) {
      console.warn('[Storage] Could not clear pending sessions queue:', cleanupErr);
    }
  }

  // বাংলা মন্তব্য: সর্বদা localStorage-এ ক্যাশে আপডেট করি
  saveLocalSessions(sessions);
}

export function createSession(prompt: string): DashboardSession {
  const now = new Date().toISOString();
  return {
    id: `sess-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title: prompt.length > 60 ? `${prompt.slice(0, 60)}…` : prompt,
    status: 'running',
    created_at: now,
    updated_at: now,
    messages: [
      {
        id: Date.now(),
        sender: 'User',
        text: prompt,
        timestamp: new Date().toLocaleTimeString(),
      },
    ],
  };
}

export async function upsertSession(session: DashboardSession): Promise<DashboardSession[]> {
  const sessions = await loadSessions();
  const idx = sessions.findIndex((s) => s.id === session.id);
  const updated = { ...session, updated_at: new Date().toISOString() };
  if (idx >= 0) sessions[idx] = updated;
  else sessions.unshift(updated);
  await saveSessions(sessions);
  window.dispatchEvent(new CustomEvent(SESSIONS_UPDATED_EVENT));
  return sessions;
}

export async function deleteSession(id: string): Promise<DashboardSession[]> {
  const sessions = await loadSessions();
  const filtered = sessions.filter((s) => s.id !== id);
  try {
    await apiClient.delete(`/api/browser/sessions/${id}`);
    // বাংলা মন্তব্য: সফলভাবে মুছলে pending-delete কিউ থেকেও সরিয়ে দিই
    try {
      const pending = JSON.parse(localStorage.getItem('supremeai_pending_deletes') || '[]') as string[];
      const updated = pending.filter((pid) => pid !== id);
      localStorage.setItem('supremeai_pending_deletes', JSON.stringify(updated));
    } catch (e) {
      console.warn('[Storage] Could not clean pending-delete queue:', e);
    }
  } catch (err) {
    // বাংলা মন্তব্য: API delete ব্যর্থ — pending-delete কিউতে id জমা করি, পরে sync হবে
    console.warn(`[API] Failed to delete session ${id} on server. Queuing for retry.`, err);
    try {
      const pending = JSON.parse(localStorage.getItem('supremeai_pending_deletes') || '[]') as string[];
      if (!pending.includes(id)) {
        pending.push(id);
        localStorage.setItem('supremeai_pending_deletes', JSON.stringify(pending));
      }
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('supremeai-toast', {
          detail: { message: 'Session delete is pending sync with server.', type: 'warning' }
        }));
      }
    } catch (queueErr) {
      console.warn('[Storage] Could not save pending-delete queue:', queueErr);
    }
  }
  saveLocalSessions(filtered);
  window.dispatchEvent(new CustomEvent(SESSIONS_UPDATED_EVENT));
  return filtered;
}

// বাংলা মন্তব্য: pending-delete কিউ reconcile করার ফাংশন — saveSessions বা app init থেকে কল করা যায়
export async function reconcilePendingDeletes(): Promise<void> {
  try {
    const pending = JSON.parse(localStorage.getItem('supremeai_pending_deletes') || '[]') as string[];
    if (pending.length === 0) return;
    const stillPending: string[] = [];
    for (const id of pending) {
      try {
        await apiClient.delete(`/api/browser/sessions/${id}`);
        console.warn(`[Sync] Pending delete reconciled for session ${id}`);
      } catch {
        stillPending.push(id);
      }
    }
    localStorage.setItem('supremeai_pending_deletes', JSON.stringify(stillPending));
  } catch (e) {
    // বাংলা মন্তব্য: reconcile ব্যর্থ হলে debug লগ দিই; পরের save-এ আবার চেষ্টা হবে
    console.warn('[Storage] reconcilePendingDeletes failed, will retry on next save:', e);
  }
}
