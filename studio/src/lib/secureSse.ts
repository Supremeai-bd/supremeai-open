import { fetchEventSource } from '@microsoft/fetch-event-source';

export interface SecureSseOptions {
  onMessage?: (event: { data: string, type: string }) => void;
  onOpen?: () => void;
  onError?: (err: unknown) => void;
  onClose?: () => void;
}

export function createSecureEventSource(
  url: string,
  token: string | null | undefined,
  options: SecureSseOptions
) {
  const controller = new AbortController();

  fetchEventSource(url, {
    method: 'GET',
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal: controller.signal,
    onopen: async (response) => {
      if (response.ok) {
        options.onOpen?.();
      } else {
        const err = new Error(`Failed to connect to SSE: ${response.status}`);
        options.onError?.(err);
        throw err;
      }
    },
    onmessage: (msg) => {
      // Mock Event structure to match native EventSource signature
      options.onMessage?.({ data: msg.data, type: msg.event || 'message' });
    },
    onclose: () => {
      options.onClose?.();
    },
    onerror: (err) => {
      options.onError?.(err);
      // বাংলা মন্তব্য: @microsoft/fetch-event-source-এর আসল rule উল্টো — throw করলে
      // library retry বন্ধ করে caller-কে control দেয়; throw না করলে library নিজেই
      // internal exponential backoff দিয়ে অনন্তকাল retry করতে থাকে। আগের কমেন্ট
      // (এবং কোড) এই behavior উল্টো ধরে নিয়েছিল, ফলে useServerStream.ts-এর
      // নিজস্ব manual backoff/max-attempts logic-এর সাথে library-এর নিজস্ব
      // internal retry loop একসাথে চলছিল — দুটো compound হয়ে হাজার হাজার
      // request/CORS error তৈরি করছিল। তাই এখানে অবশ্যই throw করতে হবে যাতে
      // library retry বন্ধ করে এবং কেবলমাত্র useServerStream.ts-এর controlled
      // reconnect logic কাজ করে।
      throw err;
    },
  }).catch((err) => {
    // বাংলা মন্তব্য: fetchEventSource()-এর রিটার্ন করা promise টা কোথাও await/catch করা হচ্ছিল না।
    // onerror-এ throw করালে (উপরের ফিক্স) এই promise reject হয়, আর caller (useServerStream.ts,
    // ThemeSyncProvider ইত্যাদি) সেটা কখনো ধরে না — ফলে ব্রাউজার কনসোলে/টেস্টে "Unhandled Promise
    // Rejection" হিসেবে দেখা যায়। error আগেই options.onError দিয়ে রিপোর্ট করা হয়ে গেছে, তাই এখানে
    // শুধু swallow করে দেওয়া হলো (যদি abort()-এর কারণে reject হয়, সেটাও নিরাপদে ignore করা হয়)।
    if (err?.name !== 'AbortError') {
      console.error('[secureSse] SSE stream terminated:', err);
    }
  });

  return {
    close: () => {
      controller.abort();
    },
  };
}
