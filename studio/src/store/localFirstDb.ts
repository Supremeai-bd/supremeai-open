import Dexie, { type Table } from 'dexie';

// #1835: the offline-first background-sync machinery (syncQueue table,
// startBackgroundSync, exponential-retry flush loop) is REMOVED — it was
// inert: startBackgroundSync had zero callers and the /api/v1/sync/{table}
// endpoints it targeted never existed, so any queued write would retry a
// 404 eight times and be silently stranded. Honest deletion over a dead
// promise. The Dexie stores + scope helpers stay: authStore uses them for
// per-user data isolation, and the local tables remain available for
// future real offline features.

export interface ChatMessage {
  id?: number;
  scope: string;
  conversationId: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  createdAt: number;
  syncedAt?: number | null;
}

export interface Conversation {
  id?: number;
  scope: string;
  externalId?: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  syncedAt?: number | null;
}

export interface UserPreference {
  key: string;
  scope: string;
  value: unknown;
  updatedAt: number;
  syncedAt?: number | null;
}

let activeScope: string | null = null;

export const setLocalDataScope = (scope: string | null): void => {
  activeScope = scope?.trim() || null;
};

export const getLocalDataScope = (): string | null => activeScope;

export const clearLocalDataScope = async (): Promise<void> => {
  const scope = activeScope;
  activeScope = null;
  if (!scope || typeof indexedDB === 'undefined') return;
  await localDb.transaction('rw', localDb.chats, localDb.conversations, localDb.preferences, async () => {
    await Promise.all([
      localDb.chats.where('scope').equals(scope).delete(),
      localDb.conversations.where('scope').equals(scope).delete(),
      localDb.preferences.where('scope').equals(scope).delete(),
    ]);
  });
};

class SupremeAILocalDB extends Dexie {
  conversations!: Table<Conversation, number>;
  chats!: Table<ChatMessage, number>;
  preferences!: Table<UserPreference, string>;

  constructor() {
    super('SupremeAI');
    this.version(1).stores({
      conversations: '++id, externalId, updatedAt, syncedAt',
      chats: '++id, conversationId, createdAt, syncedAt',
      preferences: 'key, updatedAt, syncedAt',
      syncQueue: '++id, table, recordId, queuedAt, attempts',
    });
    this.version(2).stores({
      conversations: '++id, [scope+id], [scope+externalId], scope, updatedAt, syncedAt',
      chats: '++id, [scope+conversationId], scope, createdAt, syncedAt',
      preferences: '[scope+key], scope, updatedAt, syncedAt',
      syncQueue: '++id, [scope+table], [scope+recordId], scope, queuedAt, attempts, nextAttemptAt',
    }).upgrade(async (tx) => {
      for (const table of [tx.table('conversations'), tx.table('chats'), tx.table('preferences')]) {
        await table.toCollection().modify((record) => { record.scope = 'legacy:unscoped'; });
      }
    });
    // #1835: the syncQueue table is deleted — its only writer (the removed
    // sync machinery) never shipped a working backend to flush it.
    this.version(3).stores({
      syncQueue: null,
    });
  }
}

export const localDb = new SupremeAILocalDB();
