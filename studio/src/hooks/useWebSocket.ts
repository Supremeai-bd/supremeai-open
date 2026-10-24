import { useState, useEffect, useRef, useCallback } from 'react';
import { getWebSocketBaseUrl } from '../utils/api';

type ConnectionStatus = 'connecting' | 'open' | 'closed' | 'error';

interface UseWebSocketOptions {
  url?: string;
  autoConnect?: boolean;
  reconnectAttempts?: number;
  reconnectInterval?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  onMessage?: (data: any) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (error: Event) => void;
}

interface UseWebSocketReturn {
  status: ConnectionStatus;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data: any | null;
  send: (message: unknown) => void;
  connect: () => void;
  disconnect: () => void;
  lastMessage: MessageEvent | null;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url,
    autoConnect = false,
    reconnectAttempts = 5,
    reconnectInterval = 3000,
    onMessage,
    onOpen,
    onClose,
    onError,
  } = options;

  const [status, setStatus] = useState<ConnectionStatus>('closed');
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<any | null>(null);
  const [lastMessage, setLastMessage] = useState<MessageEvent | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  // বাংলা মন্তব্য: P2 Fix — reconnectAttempts এবং reconnectInterval কে ref এ রাখা হয়েছে যাতে useCallback dependency list পরিবর্তন না হয়
  const reconnectAttemptsRef = useRef(reconnectAttempts);
  const reconnectIntervalRef = useRef(reconnectInterval);

  // Sync refs when options change
  useEffect(() => {
    reconnectAttemptsRef.current = reconnectAttempts;
    reconnectIntervalRef.current = reconnectInterval;
  }, [reconnectAttempts, reconnectInterval]);

  const resolveUrl = useCallback(() => {
    if (url) return url;
    return `${getWebSocketBaseUrl()}/ws`;
  }, [url]);

  // বাংলা মন্তব্য: Callbacks কে ref এ সংরক্ষণ করা হয় (immutability fix)
  // এভাবে connect function এর dependency list থেকে callbacks সরানো যায়
  const onMessageRef = useRef(onMessage);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  const onErrorRef = useRef(onError);

  // Keep refs updated when callbacks change
  useEffect(() => {
    onMessageRef.current = onMessage;
    onOpenRef.current = onOpen;
    onCloseRef.current = onClose;
    onErrorRef.current = onError;
  }, [onMessage, onOpen, onClose, onError]);

  // বাংলা মন্তব্য: connectRef এ connect function এর রেফারেন্স রাখা হয়,
  // যাতে reconnect টাইমআউটে রেফারেন্স থাকে
  const connectRef = useRef<(() => void) | null>(null);

  // বাংলা মন্তব্য: connect function এর dependency list থেকে callbacks সরানো হয়েছে
  // কারণ callbacks গুলো ref এ সংরক্ষিত আছে
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      setStatus('connecting');
      const socketUrl = resolveUrl();
      const ws = new WebSocket(socketUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        attemptsRef.current = 0;
        setStatus('open');
        onOpenRef.current?.();

        // বাংলা মন্তব্য: P2 Fix — Heartbeat ping প্রতি 30s এ পাঠানো হয় zombie connections detect করতে।
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
          }
        }, 30000);
      };

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;
        setLastMessage(event);
        try {
          const parsed = JSON.parse(event.data);
          setData(parsed);
          onMessageRef.current?.(parsed);
        } catch {
          setData(event.data);
          onMessageRef.current?.(event.data);
        }
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        if (heartbeatRef.current) {
          clearInterval(heartbeatRef.current);
          heartbeatRef.current = null;
        }
        setStatus('closed');
        onCloseRef.current?.();

        if (attemptsRef.current < reconnectAttemptsRef.current) {
          attemptsRef.current += 1;
          reconnectTimerRef.current = setTimeout(() => {
            if (mountedRef.current) connectRef.current?.();
          }, reconnectIntervalRef.current * attemptsRef.current);
        }
      };

      ws.onerror = (event: Event) => {
        if (!mountedRef.current) return;
        setStatus('error');
        onErrorRef.current?.(event);
      };
    } catch {
      if (!mountedRef.current) return;
      setStatus('error');
    }
  }, [resolveUrl]);

  // Update connectRef after connect is defined (not inside the callback)
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
    attemptsRef.current = reconnectAttemptsRef.current;
    if (wsRef.current) {
      if (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close(1000, 'Component unmounted');
      }
    }
    wsRef.current = null;
    setStatus('closed');
  }, []);

  const send = useCallback((message: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const payload = typeof message === 'string' ? message : JSON.stringify(message);
      wsRef.current.send(payload);
    } else {
      console.warn('WebSocket is not connected. Cannot send message.');
    }
  }, []);

  // বাংলা মন্তব্য: autoConnect এর জন্য useEffect ব্যবহার করা হয়,
  // connect() কে useEffect এর ভিতরে কল করা হয়, যা set-state-in-effect এর সমস্যা তৈরি করে
  // এটি একটি স্বচ্ছতা নীতি ভঙ্গি, তবে এটি একটি ব্যবস্থামান্য প্যাটার্ন
  useEffect(() => {
    mountedRef.current = true;
    if (autoConnect) {
      connect();
    }
    return () => {
      mountedRef.current = false;
      disconnect();
    };
  }, [autoConnect, connect, disconnect]);

  return { status, data, send, connect, disconnect, lastMessage };
}
