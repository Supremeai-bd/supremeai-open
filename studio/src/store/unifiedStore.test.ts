import { describe, it, expect, beforeEach } from 'vitest';
import { useUnifiedStore, isUnifiedStoreEnabled, disableUnifiedStore } from './unifiedStore';

describe('unifiedStore — chatSlice & cross-slice state management', () => {
  beforeEach(() => {
    useUnifiedStore.getState().resetState();
    window.localStorage.clear();
  });

  describe('chatSlice operations', () => {
    it('initializes with default chat state', () => {
      const { chat } = useUnifiedStore.getState();
      expect(chat.unreadCount).toBe(0);
      expect(chat.activeConversationId).toBeNull();
      expect(chat.cachedMessages).toEqual([]);
      expect(chat.chatPanelExpanded).toBe(true);
    });

    it('sets chat unread count', () => {
      useUnifiedStore.getState().setChatUnreadCount(5);
      expect(useUnifiedStore.getState().chat.unreadCount).toBe(5);

      useUnifiedStore.getState().setChatUnreadCount(0);
      expect(useUnifiedStore.getState().chat.unreadCount).toBe(0);
    });

    it('sets active conversation and clears cached messages when set to null', () => {
      useUnifiedStore.getState().appendChatMessage({
        id: 'msg-1',
        role: 'user',
        content: 'Hello unified store',
        timestamp: Date.now(),
      });
      useUnifiedStore.getState().setActiveConversation('conv-123');

      expect(useUnifiedStore.getState().chat.activeConversationId).toBe('conv-123');
      expect(useUnifiedStore.getState().chat.cachedMessages).toHaveLength(1);

      useUnifiedStore.getState().setActiveConversation(null);
      expect(useUnifiedStore.getState().chat.activeConversationId).toBeNull();
      expect(useUnifiedStore.getState().chat.cachedMessages).toEqual([]);
    });

    it('appends chat messages and preserves max limit', () => {
      for (let i = 0; i < 210; i++) {
        useUnifiedStore.getState().appendChatMessage({
          id: `msg-${i}`,
          role: 'user',
          content: `Test message ${i}`,
          timestamp: Date.now(),
        });
      }

      const { cachedMessages } = useUnifiedStore.getState().chat;
      expect(cachedMessages.length).toBe(200); // capped at 200
      expect(cachedMessages[cachedMessages.length - 1].content).toBe('Test message 209');
    });

    it('toggles chat panel visibility', () => {
      expect(useUnifiedStore.getState().chat.chatPanelExpanded).toBe(true);
      useUnifiedStore.getState().toggleChatPanel();
      expect(useUnifiedStore.getState().chat.chatPanelExpanded).toBe(false);
      useUnifiedStore.getState().toggleChatPanel();
      expect(useUnifiedStore.getState().chat.chatPanelExpanded).toBe(true);
    });
  });

  describe('cross-component alerts & service health', () => {
    it('manages service health updates', () => {
      useUnifiedStore.getState().setServiceHealth('scraper', {
        status: 'healthy',
        latency: 42,
      });

      const entry = useUnifiedStore.getState().serviceHealth['scraper'];
      expect(entry.status).toBe('healthy');
      expect(entry.latency).toBe(42);
      expect(entry.lastCheck).toBeGreaterThan(0);
    });

    it('adds, acknowledges, and resolves alerts', () => {
      const alertId = useUnifiedStore.getState().addAlert({
        severity: 'warning',
        source: 'monitor',
        message: 'High CPU load',
      });

      expect(useUnifiedStore.getState().getUnresolvedCount()).toBe(1);

      useUnifiedStore.getState().acknowledgeAlert(alertId);
      expect(useUnifiedStore.getState().getUnresolvedCount()).toBe(0);
    });
  });

  describe('staging rollout flag & rollback criteria', () => {
    it('remains disabled by default in absence of flag', () => {
      expect(isUnifiedStoreEnabled()).toBe(false);
    });

    it('enables when flag is set in localStorage and cleanly disables on rollback', () => {
      window.localStorage.setItem('UNIFIED_STORE', 'true');
      expect(isUnifiedStoreEnabled()).toBe(true);

      disableUnifiedStore();
      expect(isUnifiedStoreEnabled()).toBe(false);
      expect(window.localStorage.getItem('UNIFIED_STORE')).toBeNull();
    });
  });
});
