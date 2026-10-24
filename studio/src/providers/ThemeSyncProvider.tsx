import React, { useEffect } from 'react';
import { ThemeSyncContext } from './ThemeSyncContext';
import { getApiBaseUrl } from '../utils/api';
import { getRawToken, AUTH_CHANGED_EVENT } from '../services/apiClient';
import { eventBus, Events } from '../lib/componentEventBus';


import { createSecureEventSource } from '../lib/secureSse';

// বাংলা মন্তব্য: ThemeSyncContext একে অপর ফাইল থেকে ইম্পোর্ট করা হয়েছে, যাতে react-refresh সতর্কতা দূর হয়
// useThemeSync hook একে অপর ফাইলে সরানো হয়েছে (useThemeSync.ts)
export const ThemeSyncProvider: React.FC<{ children: React.ReactNode; userId?: string }> = ({
  children,
  userId = 'default'
}) => {
  useEffect(() => {
    // বাংলা মন্তব্য: ROOT-CAUSE FIX — ThemeSyncProvider App root-এ (login page-সহ)
    // globally mount থাকে। token না থাকলে authenticated /api/preferences/.../stream
    // কল করার দরকার নেই (শুধু 401 log হয়), তাই সেক্ষেত্রে skip করা হচ্ছে —
    // login হলে AUTH_CHANGED_EVENT ধরে reactively connect করবে।
    let eventSource: { close: () => void } | null = null;

    const connect = () => {
      const token = getRawToken();
      if (!token) return;
      eventSource = createSecureEventSource(`${getApiBaseUrl()}/api/preferences/${userId}/stream`, token, {
        onMessage: (event) => {
          try {
            const data = JSON.parse(event.data);
            // fetchEventSource passes event.type via event.type property now if we matched it, or we check data.event
            if ((event.type === 'theme_changed' || data.event === 'theme_changed') && data.theme) {
              eventBus.emit(Events.THEME_CHANGED, {
                theme: data.theme,
                isDark: data.theme === 'dark' || data.theme === 'matrix',
                timestamp: Date.now(),
                source: 'theme_sync_sse',
              });
            }
          } catch (err) {
            console.error('[ThemeSync] Error parsing SSE message:', err);
          }
        },
        onOpen: () => {
          console.warn('[ThemeSync] Connected to SSE Stream for user:', userId);
        },
        onError: (err) => {
          console.error('[ThemeSync] SSE Connection Error:', err);
        }
      });
    };

    connect();

    const onAuthChanged = (e: Event) => {
      const hasToken = (e as CustomEvent<{ hasToken: boolean }>).detail?.hasToken;
      if (hasToken && !eventSource) {
        connect();
      } else if (!hasToken && eventSource) {
        eventSource.close();
        eventSource = null;
      }
    };
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);

    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
      eventSource?.close();
    };
  }, [userId]);

  // ThemeProvider is the only owner of theme state and DOM classes.
  // This provider only bridges remote SSE changes and preserves the legacy API.
  const setTheme = async (newTheme: string) => {
    eventBus.emit(Events.THEME_CHANGED, {
      theme: newTheme,
      isDark: newTheme === 'dark' || newTheme === 'matrix',
      timestamp: Date.now(),
      source: 'theme_sync_bridge',
    });
  };

  return (
    <ThemeSyncContext.Provider value={{ theme: 'dark', setTheme }}>
      {children}
    </ThemeSyncContext.Provider>
  );
};
