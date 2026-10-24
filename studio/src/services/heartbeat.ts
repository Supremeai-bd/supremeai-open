import { getApiBaseUrl } from '../utils/api';
import { apiClient } from './apiClient';

// বাংলা মন্তব্য: এটি একটি গ্লোবাল হার্টবিট সার্ভিস, যা প্রতি ১০ মিনিট অন্তর /api/v1/live ইনফ্রাস্ট্রাকচার প্রোব দিয়ে
// সার্ভারগুলোকে স্লিপিং মোডে যাওয়া থেকে বিরত রাখে। /health থেকে /api/v1/live তে মাইগ্রেটেড
// কারণ /api/v1/live শুধু প্রসেস লাইভনেস চেক করে, Redis/DB ডিপেন্ডেন্সি টাচ করে না তাই আরো লাইটওয়েট
export const startAntiSleepHeartbeat = () => {
  // Initial ping 10 seconds after load
  const timeoutId = setTimeout(() => {
    pingServers();
  }, 10_000);

  // Ping every 10 minutes
  const intervalId = setInterval(() => {
    pingServers();
  }, 10 * 60 * 1000);

  return { timeoutId, intervalId };
};

export const pingServers = () => {
  // বাংলা মন্তব্য: getApiBaseUrl() ব্যবহার করা হচ্ছে যাতে Firebase Hosting-এ relative path ('') পাওয়া যায়
  // এবং firebase.json proxy rewrites দিয়ে সার্ভার-সাইড প্রক্সি হয় — কোনো CORS/preflight ঝামেলা থাকে না।
  const targets = [getApiBaseUrl()];
  targets.forEach(async (url) => {
    try {
      // বাংলা: /api/v1/live প্রোব — raw fetch → apiClient (timeout + queue + cold-start retry)।
      // non-ok হলে ApiError — status সহ warn, আগের ok/non-ok বিভাজন অটুট।
      await apiClient.get('/api/v1/live', { headers: { 'Cache-Control': 'no-cache' } });
      console.warn(`[Heartbeat] ✅ Live: ${url}/api/v1/live`);
    } catch (e) {
      const status = e && typeof e === 'object' && 'status' in e ? ` (HTTP ${(e as { status?: number }).status})` : '';
      console.warn(`[Heartbeat] ❌ Could not reach: ${url}/api/v1/live${status}`);
    }
  });
};
