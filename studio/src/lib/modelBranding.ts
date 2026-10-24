// বাংলা মন্তব্য: বাহিরের AI প্রোভাইডার (GPT/Claude/Gemini) এর র বদলে SupremeAI ব্র্যান্ডেড নাম দেখানোর জন্য সেন্ট্রাল ম্যাপিং ইউটিলিটি।
// ব্যাকএন্ড `/api/config/public/branding` থেকে ফেচ করা ম্যাপ দিয়ে এই লোকাল ম্যাপ ওভাররাইড করা যায় (single source of truth)।

export interface SupremeModelInfo {
  label: string;
  family: 'core' | 'reason' | 'vision' | 'deep' | 'spark' | 'llama' | 'mistral' | 'generic';
}

const MODEL_MAP: Record<string, SupremeModelInfo> = {
  // OpenAI
  'gpt-4': { label: 'SupremeAI Core', family: 'core' },
  'gpt-4o': { label: 'SupremeAI Core', family: 'core' },
  'gpt-4o-mini': { label: 'SupremeAI Core Mini', family: 'core' },
  'gpt-4-turbo': { label: 'SupremeAI Core Turbo', family: 'core' },
  'gpt-3.5-turbo': { label: 'SupremeAI Spark', family: 'spark' },
  // Anthropic
  'claude-3.5': { label: 'SupremeAI Reason', family: 'reason' },
  'claude-3-5-sonnet': { label: 'SupremeAI Reason', family: 'reason' },
  'claude-3-5-haiku': { label: 'SupremeAI Spark', family: 'spark' },
  'claude-3-opus': { label: 'SupremeAI Reason Pro', family: 'reason' },
  'claude-3': { label: 'SupremeAI Reason', family: 'reason' },
  // Google
  'gemini-1.5-pro': { label: 'SupremeAI Vision', family: 'vision' },
  'gemini-2.0-flash': { label: 'SupremeAI Vision Flash', family: 'vision' },
  'gemini-pro': { label: 'SupremeAI Vision', family: 'vision' },
  'gemini': { label: 'SupremeAI Vision', family: 'vision' },
  // DeepSeek
  'deepseek-chat': { label: 'SupremeAI Deep', family: 'deep' },
  'deepseek-coder': { label: 'SupremeAI Deep Coder', family: 'deep' },
  // Meta / Groq
  'llama3-70b-groq': { label: 'SupremeAI Llama', family: 'llama' },
  'llama': { label: 'SupremeAI Llama', family: 'llama' },
  // Mistral
  'mistral': { label: 'SupremeAI Mistral', family: 'mistral' },
};

// বাংলা মন্তব্য: ব্যাকএন্ড থেকে ফেচ করা ওভাররাইড ম্যাপ (runtime-এ আপডেট হয়)। লোকাল MODEL_MAP এর উপরে প্রায়োরিটি পায়।
let OVERRIDE_MODELS: Record<string, string> = {};
let OVERRIDE_PROVIDERS: Record<string, string> = {};

export function setBrandingOverrides(models: Record<string, string> = {}, providers: Record<string, string> = {}): void {
  OVERRIDE_MODELS = models || {};
  OVERRIDE_PROVIDERS = providers || {};
}

const normalize = (raw: string): string =>
  raw?.trim().toLowerCase() ?? '';

export function getSupremeModelInfo(raw: string | undefined | null): SupremeModelInfo {
  if (!raw) return { label: 'SupremeAI Core', family: 'generic' };
  const key = normalize(raw);
  if (OVERRIDE_MODELS[key]) return { label: OVERRIDE_MODELS[key], family: 'generic' };
  if (MODEL_MAP[key]) return MODEL_MAP[key];

  // ফলব্যাক: আংশিক মিল (যেমন gpt-4o-2024-...) খোঁজা
  const partial = Object.keys(MODEL_MAP).find((k) => key.startsWith(k) || k.startsWith(key));
  if (partial) return MODEL_MAP[partial];

  return { label: 'SupremeAI Core', family: 'generic' };
}

// বাংলা মন্তব্য: ইউজার সিলেক্ট করতে পারে এমন মডেলের ক্যানোনিক্যাল লিস্ট (raw provider id)।
// সব জায়গায় (SettingsPage, Onboarding) এই একটি লিস্ট থেকেই নেওয়া হয় — নতুন মডেল যোগ করতে হলে শুধু এখানে যোগ করুন।
export const SUPREME_AVAILABLE_MODELS: string[] = [
  'gpt-4o',
  'gpt-4o-mini',
  'claude-3-5-sonnet',
  'gemini-1.5-pro',
  'deepseek-chat',
];

export function getSupremeModelLabel(raw: string | undefined | null): string {
  return getSupremeModelInfo(raw).label;
}

// বাংলা মন্তব্য: বাহিরের প্রোভাইডার (Google/Groq/OpenAI) নামের বদলে SupremeAI ব্র্যান্ডেড প্রোভাইডার নাম
const PROVIDER_MAP: Record<string, string> = {
  openai: 'SupremeAI Core',
  google: 'SupremeAI Vision',
  gemini: 'SupremeAI Vision',
  anthropic: 'SupremeAI Reason',
  claude: 'SupremeAI Reason',
  deepseek: 'SupremeAI Deep',
  groq: 'SupremeAI Llama',
  together: 'SupremeAI Collective',
  togetherai: 'SupremeAI Collective',
  ollama: 'SupremeAI Local',
  mistral: 'SupremeAI Mistral',
  meta: 'SupremeAI Llama',
  llama: 'SupremeAI Llama',
};

export function getSupremeProviderLabel(raw: string | undefined | null): string {
  if (!raw) return 'SupremeAI';
  const key = normalize(raw);
  if (OVERRIDE_PROVIDERS[key]) return OVERRIDE_PROVIDERS[key];
  if (PROVIDER_MAP[key]) return PROVIDER_MAP[key];
  const partial = Object.keys(PROVIDER_MAP).find((k) => key.includes(k));
  if (partial) return PROVIDER_MAP[partial];
  return 'SupremeAI';
}

// বাংলা মন্তব্য: ব্যাকএন্ড থেকে ক্যানোনিক্যাল ব্র্যান্ডিং ম্যাপ ফেচ করে লোকাল কপি ওভাররাইড করে (single source of truth)।
// নেটওয়ার্ক এরর/অফলাইন হলে লোকাল MODEL_MAP/PROVIDER_MAP-ই ফলব্যাক হিসেবে থাকে — কোনো ক্র্যাশ নেই।
export async function loadSupremeBranding(): Promise<void> {
  try {
    const { apiClient } = await import('../services/apiClient');
    const data = await apiClient.get<{ models?: Record<string, string>; providers?: Record<string, string> }>(
      '/api/config/public/branding',
    );
    setBrandingOverrides(data?.models ?? {}, data?.providers ?? {});
  } catch {
    // offline / endpoint unavailable — keep local defaults
  }
}

