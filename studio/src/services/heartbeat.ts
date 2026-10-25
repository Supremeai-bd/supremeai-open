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
      // বাংলা: /health প্রোব — public endpoint (auth লাগে না), তাই unauthenticated
      // ভিজিটরদের জন্যও 401 কনসোল এরর আসে না। Render free-tier cold start সামলাতে
      // health check DB/Redis-ও টাচ করে — anti-sleep উদ্দেশ্যে এটাই উপযুক্ত।
      await apiClient.get('/health', { headers: { 'Cache-Control': 'no-cache' } });
      console.warn(`[Heartbeat] ✅ Live: ${url}/health`);
    } catch (e) {
      const status = e && typeof e === 'object' && 'status' in e ? ` (HTTP ${(e as { status?: number }).status})` : '';
      console.warn(`[Heartbeat] ❌ Could not reach: ${url}/health${status}`);
    }
  });
};
