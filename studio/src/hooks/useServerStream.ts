import { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import { getApiBaseUrl } from '../utils/api';
import { getRawToken, AUTH_CHANGED_EVENT } from '../services/apiClient';

import { createSecureEventSource } from '../lib/secureSse';

export type ServerStreamStatus = 'connecting' | 'connected' | 'disconnected';

export const useServerStream = () => {
  const { setServerStatus, fetchGateStatus } = useStore();
  const [streamStatus, setStreamStatus] = useState<ServerStreamStatus>('connecting');

  useEffect(() => {
    const API_BASE_URL = getApiBaseUrl();
    const sseEndpoint = `${API_BASE_URL}/api/task/stream`;
    let eventSource: { close: () => void } | null = null;
    let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    let isMounted = true;

    // বাংলা মন্তব্য: SSE ওপেন না হলে (backend 503/ডাউন) UI চিরকাল "Initializing..."-এ আটকে থাকে।
    // তাই সরাসরি /api/v1/health পোল করে ব্যাকএন্ড সত্যিই রিচেবল কিনা তা স্বাধীনভাবে যাচাই করি
    // (SSE-এর বাইরে) — 50x পেলে isServerOnline=false করে স্পষ্ট OFFLINE ব্যানার দেখায়।
    let healthTimer: ReturnType<typeof setInterval> | null = null;
    const probeHealth = async () => {
      if (!isMounted) return;
      try {
        const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
          method: 'GET',
          headers: { Accept: 'application/json' },
          credentials: 'include',
        });
        // বাংলা মন্তব্য: 2xx মানে ব্যাকএন্ড জাগ্রত; SSE নিজেই পরে onopen করে অনলাইন সেট করবে।
        if (res.ok || res.status < 500) {
          setServerStatus(true);
        } else if (res.status >= 500) {
          // বাংলা মন্তব্য: 503/502/504 = সার্ভার ডাউন বা কোল্ড স্টার্ট — স্পষ্ট OFFLINE দেখাও।
          setServerStatus(false);
          setStreamStatus('disconnected');
        }
      } catch {
        // বাংলা মন্তব্য: নেটওয়ার্ক ব্যর্থতা = ব্যাকএন্ড অপ্রাপ্ত।
        setServerStatus(false);
        setStreamStatus('disconnected');
      }
    };

    const connect = () => {
      if (!isMounted) return;
      // বাংলা মন্তব্য: ROOT-CAUSE FIX — এই hook App root-এ globally mount থাকে,
      // তাই /login-এর মতো পাবলিক পেজেও চলে। token না থাকলে authenticated
      // /api/task/stream কল করার কোনো মানে নেই — শুধু 401 → backend rate
      // limiter-এ 429 storm তৈরি করে। token না থাকলে connect স্কিপ করে
      // AUTH_CHANGED_EVENT-এর অপেক্ষায় থাকি (নিচে দেখুন)।
      const token = getRawToken();
      if (!token) {
        setStreamStatus('disconnected');
        return;
      }
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        console.error("🔴 Max SSE reconnect attempts reached. Giving up.");
        setServerStatus(false);
        setStreamStatus('disconnected');
        return;
      }

      console.warn("🔌 Initializing SupremeAI Unified Lifespan SSE Stream...");
      setStreamStatus(reconnectAttempts > 0 ? 'connecting' : 'connecting');
      eventSource = createSecureEventSource(sseEndpoint, token, {
        onOpen: () => {
          if (!isMounted) return;
          console.warn("🟢 SSE Stream connected.");
          setServerStatus(true);
          setStreamStatus('connected');
          fetchGateStatus();
          reconnectAttempts = 0;
        },
        onMessage: (e) => {
          if (e.data && (e.data.includes('auth_error') || e.data.includes('401'))) {
             console.error("🔴 SSE Auth Error: Closing stream to prevent storm.");
             eventSource?.close();
             if (isMounted) {
               setServerStatus(false);
               setStreamStatus('disconnected');
             }
          }
        },
        onError: (err) => {
          eventSource?.close();
          if (!isMounted) return;
          console.error("🔴 [SYSTEM CRITICAL] SSE Stream severed. SupremeAI Server is OFFLINE.", err);
          setServerStatus(false);
          setStreamStatus('disconnected');
          reconnectAttempts++;
          const backoff = Math.min(1000 * 2 ** reconnectAttempts, 30000);
          const jitter = Math.random() * 500;
          console.warn(`🔄 SSE Reconnecting in ${(backoff + jitter) / 1000}s (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);

          if (isMounted) {
            setStreamStatus('connecting'); // Transition back to connecting during wait
            reconnectTimeout = setTimeout(connect, backoff + jitter);
          }
        }
      });
    };

    // বাংলা মন্তব্য: প্রথমেই একবার হেলথ প্রোব (৫০x সনাক্তকরণের জন্য) এবং পরে ১৫ সেকেন্ড পরপর পোল করবে।
    probeHealth();
    healthTimer = setInterval(probeHealth, 15000);

    connect();

    // বাংলা মন্তব্য: login/logout হলে (একই SPA session-এ, remount ছাড়াই) token
    // আসে/যায় — সেই মুহূর্তে reactively (re)connect বা disconnect করার জন্য।
    const onAuthChanged = (e: Event) => {
      const hasToken = (e as CustomEvent<{ hasToken: boolean }>).detail?.hasToken;
      if (hasToken) {
        reconnectAttempts = 0;
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        connect();
      } else {
        if (reconnectTimeout) clearTimeout(reconnectTimeout);
        eventSource?.close();
        eventSource = null;
        setStreamStatus('disconnected');
      }
    };
    window.addEventListener(AUTH_CHANGED_EVENT, onAuthChanged);

    return () => {
      isMounted = false;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (healthTimer) clearInterval(healthTimer);
      window.removeEventListener(AUTH_CHANGED_EVENT, onAuthChanged);
      console.warn("🔌 Cleaning up SSE Stream...");
      eventSource?.close();
    };
  }, [setServerStatus, fetchGateStatus]);

  return { streamStatus };
};
