// apps/studio-client/src/utils/deviceFingerprint.ts
// বাংলা মন্তব্য: কোনো এক্সটার্নাল সার্ভিস ছাড়াই (Zero-Cost) ব্রাউজার/হার্ডওয়্যার সিগন্যাল থেকে
// একটি স্থিতিশীল SHA-256 হ্যাশ তৈরি করা হয়। একই ডিভাইস/ব্রাউজারে বারবার একই ভ্যালু আসে,
// তাই backend-এর AntiHackingContextMiddleware এটাকে IP/country-এর পাশে তৃতীয় সিগন্যাল হিসেবে ব্যবহার করতে পারে।

let cachedFingerprint: string | null = null;
let inFlight: Promise<string> | null = null;

async function computeFingerprint(): Promise<string> {
  const nav = navigator as Navigator & { deviceMemory?: number };
  const raw = [
    navigator.userAgent,
    navigator.language,
    `${screen.colorDepth}`,
    `${screen.width}x${screen.height}`,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
    `${navigator.hardwareConcurrency ?? 'na'}`,
    `${nav.deviceMemory ?? 'na'}`,
    navigator.platform ?? 'na',
  ].join('|');

  try {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
    return Array.from(new Uint8Array(buf))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');
  } catch (e) {
    console.error('🚨 [FINGERPRINT_HASH_FAILED]: Failed to compute SHA-256 device fingerprint', e);
    return 'fallback_fingerprint';
  }
}

// বাংলা মন্তব্য: বারবার হ্যাশ recompute না করে একবার করে মেমরিতে ক্যাশ রাখা হচ্ছে
export const getDeviceFingerprint = async (): Promise<string> => {
  if (cachedFingerprint) return cachedFingerprint;
  if (!inFlight) {
    inFlight = computeFingerprint()
      .then((fp) => {
        cachedFingerprint = fp;
        return fp;
      })
      .catch((err: unknown) => {
        // বাংলা মন্তব্য (#2478): ফায়ার-অ্যান্ড-ফরগেট prime পাথে unhandled rejection
        // না হয় — hash ফাংশনের বিদ্যমান fallback চুক্তিতে নামিয়ে ক্যাশ রিসেট করা হয়
        // (পরের কলে পুনরায় চেষ্টা করা যাবে)।
        console.error('🚨 [FINGERPRINT_INFLIGHT_FAILED]: device fingerprint cache failed', err);
        inFlight = null;
        return 'fallback_fingerprint';
      });
  }
  return inFlight;
};

// অ্যাপ বুটের সাথে সাথেই ব্যাকগ্রাউন্ডে প্রিলোড করার জন্য — লগইন রিকোয়েস্টে দেরি হবে না
export const primeDeviceFingerprint = (): void => {
  if (typeof window !== 'undefined') {
    void getDeviceFingerprint();
  }
};
